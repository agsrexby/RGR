"""
RAG (Retrieval-Augmented Generation) Engine.
Обеспечивает контекстный поиск и генерацию на основе базы знаний.
"""

from typing import List, Dict, Optional, Any
from dataclasses import dataclass
import hashlib
import os

try:
    import chromadb
    from chromadb.config import Settings
except ImportError:
    chromadb = None

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None


@dataclass
class Document:
    """Документ для индексации."""
    content: str
    metadata: Dict[str, Any]
    doc_id: Optional[str] = None
    
    def __post_init__(self):
        if not self.doc_id:
            self.doc_id = hashlib.md5(
                self.content.encode()
            ).hexdigest()[:12]


@dataclass
class SearchResult:
    """Результат поиска."""
    document: Document
    score: float
    highlights: List[str]


class EmbeddingService:
    """Сервис для создания эмбеддингов текста."""
    
    def __init__(
        self,
        model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    ):
        if SentenceTransformer is None:
            raise ImportError(
                "Установите sentence-transformers: "
                "pip install sentence-transformers"
            )
        
        self.model = SentenceTransformer(model_name)
        self.embedding_dim = self.model.get_sentence_embedding_dimension()
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        """Создание эмбеддингов для списка текстов."""
        embeddings = self.model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()
    
    def embed_single(self, text: str) -> List[float]:
        """Создание эмбеддинга для одного текста."""
        return self.embed([text])[0]


class TextChunker:
    """Разбиение текста на чанки для индексации."""
    
    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    def chunk_text(self, text: str) -> List[str]:
        """Разбиение текста на перекрывающиеся чанки."""
        if len(text) <= self.chunk_size:
            return [text]
        
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + self.chunk_size
            
            # Ищем конец предложения для более естественного разбиения
            if end < len(text):
                # Ищем точку, вопросительный или восклицательный знак
                for punct in ['. ', '? ', '! ', '\n\n']:
                    punct_pos = text.rfind(punct, start, end)
                    if punct_pos != -1:
                        end = punct_pos + len(punct)
                        break
            
            chunks.append(text[start:end].strip())
            start = end - self.chunk_overlap
        
        return chunks
    
    def chunk_document(
        self,
        document: Document
    ) -> List[Document]:
        """Разбиение документа на чанки."""
        chunks = self.chunk_text(document.content)
        
        return [
            Document(
                content=chunk,
                metadata={
                    **document.metadata,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "parent_doc_id": document.doc_id
                },
                doc_id=f"{document.doc_id}_chunk_{i}"
            )
            for i, chunk in enumerate(chunks)
        ]


class RAGEngine:
    """
    Движок RAG для контекстного поиска и генерации.
    """
    
    def __init__(
        self,
        collection_name: str = "sdlc_documents",
        persist_directory: str = "./data/chromadb",
        embedding_model: Optional[str] = None
    ):
        if chromadb is None:
            raise ImportError(
                "Установите chromadb: pip install chromadb"
            )
        
        self.collection_name = collection_name
        self.persist_directory = persist_directory
        
        # Инициализация ChromaDB
        os.makedirs(persist_directory, exist_ok=True)
        
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Инициализация эмбеддинг-сервиса
        self.embedding_service = EmbeddingService(
            model_name=embedding_model or 
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        )
        
        # Получение или создание коллекции
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        
        self.chunker = TextChunker()
    
    def add_document(
        self,
        document: Document,
        chunk: bool = True
    ) -> List[str]:
        """
        Добавление документа в базу знаний.
        
        Args:
            document: Документ для добавления
            chunk: Разбивать ли на чанки
            
        Returns:
            Список ID добавленных документов/чанков
        """
        if chunk:
            docs = self.chunker.chunk_document(document)
        else:
            docs = [document]
        
        ids = [doc.doc_id for doc in docs]
        contents = [doc.content for doc in docs]
        metadatas = [doc.metadata for doc in docs]
        
        # Создаём эмбеддинги
        embeddings = self.embedding_service.embed(contents)
        
        # Добавляем в коллекцию
        self.collection.add(
            ids=ids,
            documents=contents,
            embeddings=embeddings,
            metadatas=metadatas
        )
        
        return ids
    
    def add_documents(
        self,
        documents: List[Document],
        chunk: bool = True
    ) -> List[str]:
        """Пакетное добавление документов."""
        all_ids = []
        for doc in documents:
            ids = self.add_document(doc, chunk)
            all_ids.extend(ids)
        return all_ids
    
    def search(
        self,
        query: str,
        n_results: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[SearchResult]:
        """
        Семантический поиск по базе знаний.
        
        Args:
            query: Поисковый запрос
            n_results: Количество результатов
            filter_metadata: Фильтр по метаданным
            
        Returns:
            Список результатов поиска
        """
        query_embedding = self.embedding_service.embed_single(query)
        
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=filter_metadata
        )
        
        search_results = []
        
        for i in range(len(results['ids'][0])):
            doc = Document(
                content=results['documents'][0][i],
                metadata=results['metadatas'][0][i] if results['metadatas'] else {},
                doc_id=results['ids'][0][i]
            )
            
            score = 1 - results['distances'][0][i] if results['distances'] else 0
            
            search_results.append(SearchResult(
                document=doc,
                score=score,
                highlights=[]  # Можно добавить подсветку
            ))
        
        return search_results
    
    def get_context_for_query(
        self,
        query: str,
        n_results: int = 3,
        min_score: float = 0.5
    ) -> List[Dict[str, str]]:
        """
        Получение контекста для RAG-запроса.
        
        Возвращает список документов в формате,
        подходящем для LLM.
        """
        results = self.search(query, n_results)
        
        context = []
        for result in results:
            if result.score >= min_score:
                context.append({
                    "content": result.document.content,
                    "metadata": result.document.metadata,
                    "score": result.score
                })
        
        return context
    
    def delete_document(self, doc_id: str) -> bool:
        """Удаление документа по ID."""
        try:
            self.collection.delete(ids=[doc_id])
            return True
        except Exception:
            return False
    
    def clear_collection(self):
        """Очистка всей коллекции."""
        self.client.delete_collection(self.collection_name)
        self.collection = self.client.create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Статистика по коллекции."""
        return {
            "collection_name": self.collection_name,
            "document_count": self.collection.count(),
            "embedding_dim": self.embedding_service.embedding_dim
        }


class RAGPipeline:
    """
    Полный пайплайн RAG: поиск + генерация.
    """
    
    def __init__(
        self,
        rag_engine: RAGEngine,
        llm_service: Any  # LLMService из llm_service.py
    ):
        self.rag_engine = rag_engine
        self.llm_service = llm_service
    
    def query(
        self,
        question: str,
        system_prompt: Optional[str] = None,
        n_context_docs: int = 3
    ) -> Dict[str, Any]:
        """
        Выполнение RAG-запроса.
        
        Args:
            question: Вопрос пользователя
            system_prompt: Системный промпт для LLM
            n_context_docs: Количество документов контекста
            
        Returns:
            Словарь с ответом и метаданными
        """
        # Получаем релевантный контекст
        context = self.rag_engine.get_context_for_query(
            question,
            n_results=n_context_docs
        )
        
        if not context:
            return {
                "answer": "Не найдено релевантных документов в базе знаний.",
                "context_used": [],
                "sources": []
            }
        
        # Генерируем ответ с контекстом
        response = self.llm_service.provider.generate_with_context(
            prompt=question,
            context=context,
            system_prompt=system_prompt
        )
        
        return {
            "answer": response.content,
            "context_used": context,
            "sources": [
                c.get("metadata", {}).get("source", "unknown")
                for c in context
            ],
            "tokens_used": response.tokens_used
        }