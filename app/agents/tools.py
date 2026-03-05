from langchain_classic.tools import Tool
from langchain_experimental.utilities import PythonREPL
from app.database.clickhouse import clickhouse_client
from app.database.postgres import postgres_client, _is_pg_configured as is_pg_configured
from app.utils.logging import logger
from app.utils.metrics import track_query_performance
from langchain_community.vectorstores import FAISS
from langchain_huggingface.embeddings import HuggingFaceEmbeddings
from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain_core.documents import Document
from config.settings import settings
from functools import lru_cache
from hashlib import md5
import os
import re

def _schema_files():
    """Пары (путь к файлу схемы, название БД). PostgreSQL добавляется только если настроен."""
    files = [(settings.DB_SCHEMA_PATH, "ClickHouse")]
    if is_pg_configured():
        files.append((settings.DB_SCHEMA_PATH_PG, "PostgreSQL"))
    return files

# Паттерн строки-колонки: "- **column_name**: ..." (начало списка колонок)
_COLUMN_LINE_RE = re.compile(r"^-\s+\*\*[a-zA-Z0-9_]+\*\*:\s*")


def _split_table_content(content: str):
    """
    Разделяет блок таблицы на смысловую часть (для эмбеддинга) и полный текст.
    Смысловая часть: название, синонимы, использование, описание (до первого списка колонок).
    """
    lines = content.splitlines()
    semantic_lines = []
    for line in lines:
        if _COLUMN_LINE_RE.match(line.strip()):
            break
        semantic_lines.append(line)
    semantic = "\n".join(semantic_lines).rstrip()
    return semantic if semantic else content


def _chunks_from_schema_file(file_path: str, database: str):
    """Загружает файл схемы и возвращает список Document.
    В page_content — только смысловая часть (для эмбеддинга): база, название, синонимы, использование, описание.
    В metadata["full_content"] — полное описание таблицы (для контекста LLM): + колонки + индексы.
    """
    text_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[("#", "Header 1"), ("##", "Header 2")],
        strip_headers=False,
    )
    try:
        with open(file_path, encoding="utf-8") as f:
            file_md = f.read()
    except Exception as e:
        logger.warning(f"RAG: Could not load schema {file_path}: {e}")
        return []
    docs = []
    for chunk in text_splitter.split_text(file_md):
        content = chunk.page_content if hasattr(chunk, "page_content") else str(chunk)
        table_match = re.search(r"# Таблица:\s*(\w+)", content)
        table_name = table_match.group(1) if table_match else "unknown"
        semantic_part = _split_table_content(content)
        db_prefix = f"**База данных:** {database}\n\n"
        # Для эмбеддинга — только смысловая часть (без колонок и индексов)
        page_content = db_prefix + semantic_part
        # Для контекста LLM — полное описание таблицы
        full_content = db_prefix + content
        meta = {
            **getattr(chunk, "metadata", {}).copy(),
            "table_name": table_name,
            "database": database,
            "source": "db_schema",
            "full_content": full_content,
        }
        docs.append(Document(page_content=page_content, metadata=meta))
    return docs


def _chunks_from_data_catalog(file_path: str):
    """Загружает дата-каталог (темы: клиенты, заказы, маркетинг, лояльность и т.д.).
    Один чанк = одна тема с таблицей таблиц. Используется для тематического поиска по RAG.
    """
    text_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[("#", "Header 1")],
        strip_headers=False,
    )
    try:
        with open(file_path, encoding="utf-8") as f:
            file_md = f.read()
    except Exception as e:
        logger.warning(f"RAG: Could not load data catalog {file_path}: {e}")
        return []
    docs = []
    for chunk in text_splitter.split_text(file_md):
        content = chunk.page_content if hasattr(chunk, "page_content") else str(chunk)
        if "ДАТА-КАТАЛОГ:" not in content:
            continue
        theme_match = re.search(r"#\s*ДАТА-КАТАЛОГ:\s*(.+)", content)
        theme = theme_match.group(1).strip() if theme_match else "unknown"
        meta = {
            **getattr(chunk, "metadata", {}).copy(),
            "source": "data_catalog",
            "theme": theme,
        }
        docs.append(Document(page_content=content, metadata=meta))
    return docs


def _build_embeddings(cache_dir: str):
    """Создаёт экземпляр эмбеддингов (FRIDA)."""
    return HuggingFaceEmbeddings(
        model_name="ai-forever/FRIDA",
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
        cache_folder=cache_dir,
    )


def _load_all_chunks():
    """Загружает все чанки из файлов схем и дата-каталога. Возвращает (all_chunks, cache_dir)."""
    all_chunks = []
    for file_path, database in _schema_files():
        logger.info(f"RAG: Loading schema from {file_path} (database={database})...")
        chunks = _chunks_from_schema_file(file_path, database)
        all_chunks.extend(chunks)
        logger.info(f"RAG: Loaded {len(chunks)} chunks for {database}")
    catalog_path = getattr(settings, "DATA_CATALOG_PATH", "app/agents/data_catalog.md")
    try:
        catalog_chunks = _chunks_from_data_catalog(catalog_path)
        all_chunks.extend(catalog_chunks)
        logger.info(f"RAG: Loaded {len(catalog_chunks)} chunks from data catalog")
    except Exception as e:
        logger.warning(f"RAG: Skipping data catalog: {e}")
    if not all_chunks:
        raise ValueError("No schema chunks loaded from any file")
    cache_dir = getattr(settings, "HF_CACHE_DIR", "cache/huggingface")
    os.makedirs(cache_dir, exist_ok=True)
    return all_chunks, cache_dir


def setup_rag_tool() -> FAISS:
    """Инициализация RAG для схем БД ClickHouse и PostgreSQL (одна векторная база).
    - dev: загружает FAISS с хоста (FAISS_INDEX_PATH), если нет — строит и сохраняет.
    - prod: каждый раз пересоздаёт FAISS из схемы, не сохраняет на диск.
    """
    global rag_embedding_model
    mode = (getattr(settings, "MODE", "prod") or "prod").strip().lower()
    cache_dir = getattr(settings, "HF_CACHE_DIR", "cache/huggingface")
    os.makedirs(cache_dir, exist_ok=True)
    logger.info(f"RAG: mode={mode}")

    try:
        embeddings = _build_embeddings(cache_dir)
        rag_embedding_model = "ai-forever/FRIDA"

        if mode == "dev":
            index_path = (getattr(settings, "FAISS_INDEX_PATH", "cache/faiss_index") or "cache/faiss_index").strip()
            index_file = os.path.join(index_path, "index.faiss")
            if os.path.isfile(index_file):
                try:
                    logger.info(f"RAG: Loading FAISS index from {index_path}...")
                    vector_db = FAISS.load_local(index_path, embeddings, allow_dangerous_deserialization=True)
                    logger.info("RAG: FAISS index loaded from disk")
                    return vector_db
                except Exception as e:
                    logger.warning(f"RAG: Failed to load FAISS from {index_path}: {e}, rebuilding...")

            all_chunks, _ = _load_all_chunks()
            logger.info(f"RAG: Creating embeddings for {len(all_chunks)} chunks...")
            logger.info("RAG: Building FAISS index...")
            vector_db = FAISS.from_documents(all_chunks, embeddings)
            os.makedirs(index_path, exist_ok=True)
            vector_db.save_local(index_path)
            logger.info(f"RAG: FAISS index built and saved to {index_path}")
            return vector_db

        # prod: всегда пересоздаём, не сохраняем
        all_chunks, _ = _load_all_chunks()
        logger.info(f"RAG: Using model cache dir: {os.path.abspath(cache_dir)}")
        logger.info(f"RAG: Creating embeddings for {len(all_chunks)} chunks...")
        logger.info("RAG: Building FAISS index...")
        vector_db = FAISS.from_documents(all_chunks, embeddings)
        logger.info("RAG: FAISS index created successfully")
        return vector_db
    except Exception as e:
        logger.error(f"RAG setup error: {str(e)}")
        logger.warning("RAG: Falling back to cointegrated/rubert-tiny2")
        cache_dir = getattr(settings, "HF_CACHE_DIR", "cache/huggingface")
        os.makedirs(cache_dir, exist_ok=True)
        rag_embedding_model = "cointegrated/rubert-tiny2"
        return FAISS.from_texts(
            ["Ошибка загрузки схемы БД"],
            HuggingFaceEmbeddings(
                model_name=rag_embedding_model,
                cache_folder=cache_dir,
            ),
        )


# Модель, использованная при построении индекса (для health check)
rag_embedding_model: str = "unknown"

# ВАЖНО: создаём векторную базу один раз при импорте модуля (при старте приложения)
vector_db = setup_rag_tool()

@lru_cache(maxsize=100)
def schema_retriever_cached(query_hash: str, query: str) -> str:
    """Кэшированный поиск в схеме БД с MMR для разнообразия результатов
    
    Улучшения Фазы 1:
    - Использует MMR (Maximum Marginal Relevance) вместо простого similarity_search
    - Увеличено k с 4 до 6 для лучшего покрытия таблиц
    - MMR обеспечивает баланс между релевантностью и разнообразием результатов
    """
    try:
        # MMR: баланс между релевантностью и разнообразием
        # fetch_k=12: сначала выбираем 12 наиболее релевантных
        # k=6: затем фильтруем до 6 с учетом разнообразия
        # lambda_mult=0.5: баланс (0 = только разнообразие, 1 = только релевантность)
        docs = vector_db.max_marginal_relevance_search(
            query,
            k=6,  # Увеличено с 4 до 6
            fetch_k=12,  # Сначала выбираем 12, потом фильтруем до 6
            lambda_mult=0.5  # Баланс релевантности и разнообразия
        )
        
        # Логируем найденные таблицы и БД для отладки
        found = [
            f"{doc.metadata.get('table_name', '?')}({doc.metadata.get('database', '?')})"
            for doc in docs if doc.metadata.get("table_name") != "unknown"
        ]
        if found:
            logger.debug(f"RAG: Found for query '{query[:50]}...': {', '.join(set(found))}")
        
        # В контекст LLM отдаём полное описание (с колонками и индексами) для написания SQL
        return "\n\n".join([d.metadata.get("full_content", d.page_content) for d in docs])
    except Exception as e:
        logger.error(f"Schema retrieval error: {str(e)}")
        # Fallback на простой поиск при ошибке MMR
        try:
            logger.warning("RAG: Falling back to simple similarity_search")
            docs = vector_db.similarity_search(query, k=6)
            return "\n\n".join([d.metadata.get("full_content", d.page_content) for d in docs])
        except Exception as fallback_error:
            logger.error(f"Schema retrieval fallback error: {str(fallback_error)}")
            return "Ошибка при поиске в схеме БД"

@track_query_performance(query_type="schema_search")
def schema_retriever(query: str) -> str:
    """Поиск информации о структуре БД (используем уже загруженную базу и кэш)"""
    query_hash = md5(query.encode('utf-8')).hexdigest()
    return schema_retriever_cached(query_hash, query)

def get_tools():
    """Инициализация инструментов LangChain"""
    python_repl = PythonREPL()
    tools_list = [
        Tool(
            name="ClickHouse_Query",
            func=clickhouse_client.execute_safe_query,
            description=(
                "EXECUTE SQL QUERIES AGAINST CLICKHOUSE. Use this tool when the schema search (Database_Schema) "
                "returned tables with 'База данных: ClickHouse'. Input: SQL query (e.g. SELECT ... FROM rees46.table_name WHERE ...). "
                "Output: table result."
            ),
        ),
    ]
    if is_pg_configured():
        tools_list.append(
            Tool(
                name="PostgreSQL_Query",
                func=postgres_client.execute_safe_query,
                description=(
                    "EXECUTE SQL QUERIES AGAINST POSTGRESQL. Use this tool when the schema search (Database_Schema) "
                    "returned tables with 'База данных: PostgreSQL'. Input: SQL query (e.g. SELECT ... FROM table_name WHERE ...). "
                    "Output: table result."
                ),
            ),
        )
    tools_list.extend([
        Tool(
            name="Database_Schema",
            func=schema_retriever,
            description=(
                "SEARCH FOR DATABASE STRUCTURE (TABLES AND COLUMNS). Returns descriptions of tables from BOTH ClickHouse and PostgreSQL. "
                "Each table description includes 'База данных: ClickHouse' or 'База данных: PostgreSQL' — use that to choose "
                "ClickHouse_Query vs PostgreSQL_Query. Input: natural language in Russian."
            ),
        ),
        Tool(
            name="Python_REPL",
            func=python_repl.run,
            description=(
                "Executing Python code for complex calculations. "
                "Use it only when it is impossible to solve through SQL. Input: valid Python code."
            ),
        ),
    ])
    return tools_list

__all__ = ['get_tools', 'schema_retriever']
