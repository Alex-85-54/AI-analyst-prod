from langchain.tools import Tool
from langchain_experimental.utilities import PythonREPL
from app.database.clickhouse import clickhouse_client
from app.utils.logging import logger
from app.utils.metrics import track_query_performance
from langchain_community.vectorstores import FAISS
from langchain_huggingface.embeddings import HuggingFaceEmbeddings
from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain_core.documents import Document
from config.settings import settings
from functools import lru_cache
from hashlib import md5
import re

def setup_rag_tool() -> FAISS:
    """Инициализация RAG для схемы БД (выполняется 1 раз при старте процесса)
    
    Улучшения Фазы 1:
    - Использует модель ai-forever/FRIDA для лучшего понимания русского языка
    - Добавляет метаданные таблиц к каждому чанку для улучшения поиска
    """
    try:
        logger.info(f"RAG: Loading schema from {settings.DB_SCHEMA_PATH}...")
        file_md = open(settings.DB_SCHEMA_PATH, encoding='utf-8').read()
        
        text_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[("#", "Header 1"), ("##", "Header 2")],
            strip_headers=False
        )
        
        chunks = []
        for chunk in text_splitter.split_text(file_md):
            # Извлекаем название таблицы из заголовка
            table_name = None
            content = chunk.page_content if hasattr(chunk, 'page_content') else str(chunk)
            
            # Ищем паттерн "# Таблица: table_name"
            table_match = re.search(r'# Таблица:\s*(\w+)', content)
            if table_match:
                table_name = table_match.group(1)
                logger.debug(f"RAG: Found table name: {table_name}")
            
            # Создаем документ с метаданными
            if hasattr(chunk, 'page_content'):
                chunks.append(Document(
                    page_content=chunk.page_content,
                    metadata={
                        **getattr(chunk, 'metadata', {}).copy(),
                        'table_name': table_name or 'unknown',
                        'source': 'db_schema'
                    }
                ))
            else:
                chunks.append(Document(
                    page_content=str(chunk),
                    metadata={
                        'table_name': table_name or 'unknown',
                        'source': 'db_schema'
                    }
                ))
        
        logger.info(f"RAG: Creating embeddings with FRIDA model for {len(chunks)} chunks...")
        embeddings = HuggingFaceEmbeddings(
            model_name="ai-forever/FRIDA",  # Замена на FRIDA для лучшего понимания русского языка
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}
        )
        
        logger.info("RAG: Building FAISS index...")
        vector_db = FAISS.from_documents(chunks, embeddings)
        logger.info("RAG: FAISS index created successfully")
        return vector_db
    except Exception as e:
        logger.error(f"RAG setup error: {str(e)}")
        # Fallback на более простую модель
        logger.warning("RAG: Falling back to cointegrated/rubert-tiny2")
        return FAISS.from_texts(
            ["Ошибка загрузки схемы БД"], 
            HuggingFaceEmbeddings(model_name="cointegrated/rubert-tiny2")
        )

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
        
        # Логируем найденные таблицы для отладки
        found_tables = [doc.metadata.get('table_name', 'unknown') for doc in docs if doc.metadata.get('table_name') != 'unknown']
        if found_tables:
            logger.debug(f"RAG: Found tables for query '{query[:50]}...': {', '.join(set(found_tables))}")
        
        return "\n\n".join([d.page_content for d in docs])
    except Exception as e:
        logger.error(f"Schema retrieval error: {str(e)}")
        # Fallback на простой поиск при ошибке MMR
        try:
            logger.warning("RAG: Falling back to simple similarity_search")
            docs = vector_db.similarity_search(query, k=6)
            return "\n\n".join([d.page_content for d in docs])
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
    
    return [
        Tool(
            name="ClickHouse_Query",
            func=clickhouse_client.execute_safe_query,
            description=(
                "EXECUTING SQL QUERIES TO A DATABASE. USE THIS TOOL TO GET DATA FROM THE DATABASE. "
                "Input: SQL query. Output: the result is in the form of a table. "
                "EXAMPLE: SELECT * FROM rees46.order_items WHERE shop_id = 123"
            )
        ),
        Tool(
            name="Database_Schema",
            func=schema_retriever,
            description=(
                "SEARCH FOR INFORMATION ABOUT THE DATABASE STRUCTURE. "
                "Use it to specify the names of tables and columns before executing the query. "
                "Entry: natural language in Russian."
            )
        ),
        Tool(
            name="Python_REPL",
            func=python_repl.run,
            description=(
                "Executing Python code for complex calculations." 
                "Use it only when it is impossible to solve through SQL. "
                "Input: valid Python code."
            )
        )
    ]

__all__ = ['get_tools', 'schema_retriever']
