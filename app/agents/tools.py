from langchain.tools import Tool
from langchain_experimental.utilities import PythonREPL
from app.database.clickhouse import clickhouse_client
from app.utils.logging import logger
from langchain_community.vectorstores import FAISS
from langchain_huggingface.embeddings import HuggingFaceEmbeddings
from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain_core.documents import Document

def setup_rag_tool():
    """Инициализация RAG для схемы БД"""
    try:
        # Ваша существующая логика RAG
        file_md = open('db_schema_docs.md', encoding='utf-8').read()
        text_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[("#", "Header 1"), ("##", "Header 2")],
            strip_headers=False
        )
        
        chunks = []
        for chunk in text_splitter.split_text(file_md):
            if hasattr(chunk, 'page_content'):
                chunks.append(Document(
                    page_content=chunk.page_content,
                    metadata=getattr(chunk, 'metadata', {}).copy()
                ))
            else:
                chunks.append(Document(page_content=chunk, metadata={}))
                
        embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}
        )
        
        return FAISS.from_documents(chunks, embeddings)
    except Exception as e:
        logger.error(f"RAG setup error: {str(e)}")
        # Fallback
        return FAISS.from_texts(
            ["Ошибка загрузки схемы БД"], 
            HuggingFaceEmbeddings(model_name="cointegrated/rubert-tiny2")
        )

def schema_retriever(query: str) -> str:
    """Поиск информации о структуре БД"""
    try:
        vector_db = setup_rag_tool()
        docs = vector_db.similarity_search(query, k=4)
        return "\n\n".join([d.page_content for d in docs])
    except Exception as e:
        logger.error(f"Schema retrieval error: {str(e)}")
        return "Ошибка при поиске в схеме БД"

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
