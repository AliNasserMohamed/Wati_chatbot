import os
import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions
from typing import List, Dict, Any, Optional
import uuid
import numpy as np
import asyncio
import threading
from contextlib import asynccontextmanager
from vectorstore.model_cache import model_cache
from vectorstore.cached_embedding_function import CachedSentenceTransformerEmbeddingFunction

# Create vector store directory if it doesn't exist
os.makedirs("vectorstore/data", exist_ok=True)

class ChromaManager:
    def __init__(self):
        # Initialize Chroma client with persistence
        self.client = chromadb.PersistentClient(
            path="vectorstore/data",
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Use Arabic-specific embedding model with caching for better Arabic language support
        print("🔧 Initializing Arabic embedding model with caching...")
        self.embedding_function = CachedSentenceTransformerEmbeddingFunction(
            model_name="mohamed2811/Muffakir_Embedding_V2"
        )
        
        # Create or get the collection with inner product space for dot product similarity
        self.collection = self.client.get_or_create_collection(
            name="abar_knowledge_base",
            embedding_function=self.embedding_function,
            metadata={"description": "Knowledge base for Abar chatbot with Arabic embeddings","hnsw:space": "ip"}
        )
        
        # Add thread-safe locking for concurrent access
        self._lock = asyncio.Lock()
        self._thread_lock = threading.Lock()
    
    @asynccontextmanager
    async def _async_lock(self):
        """Async context manager for thread-safe operations"""
        async with self._lock:
            yield
    
    def _sync_lock(self):
        """Synchronous context manager for thread-safe operations"""
        return self._thread_lock
    
    def _l2_normalize_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings and apply L2 normalization
        """
        # Get embeddings from the cached embedding function
        embeddings = self.embedding_function(texts)
        
        # Convert to numpy array and apply L2 normalization
        embeddings_array = np.array(embeddings)
        norms = np.linalg.norm(embeddings_array, axis=1, keepdims=True)
        # Avoid division by zero
        norms = np.where(norms == 0, 1, norms)
        normalized_embeddings = embeddings_array / norms
        
        return normalized_embeddings.tolist()
    
    async def check_duplicate_question(self, question: str, similarity_threshold: float = 0.85) -> Optional[Dict[str, Any]]:
        """
        Check if a question already exists in the knowledge base
        Returns the existing question data if found, None otherwise
        """
        async with self._async_lock():
            try:
                # Search for similar questions
                results = await self.search(question, n_results=5)
                
                for result in results:
                    # Check if this is a question (not an answer)
                    if result.get("metadata", {}).get("type") == "question":
                        # Check similarity threshold
                        similarity = result.get("cosine_similarity", 0)
                        if similarity >= similarity_threshold:
                            print(f"🔍 Found duplicate question with similarity {similarity:.3f}")
                            print(f"   Existing: {result['document']}")
                            print(f"   New: {question}")
                            return result
                
                # Also check for exact text matches
                all_data = self.collection.get(include=["documents", "metadatas"])
                if all_data and all_data.get("documents"):
                    for i, doc in enumerate(all_data["documents"]):
                        metadata = all_data["metadatas"][i]
                        if metadata.get("type") == "question":
                            # Check for exact match (case-insensitive)
                            if doc.strip().lower() == question.strip().lower():
                                print(f"🔍 Found exact duplicate question")
                                return {
                                    "document": doc,
                                    "metadata": metadata,
                                    "id": f"exact_match_{i}",  # Generate a temporary ID
                                    "cosine_similarity": 1.0
                                }
                
                return None
                
            except Exception as e:
                print(f"❌ Error checking for duplicates: {str(e)}")
                return None
    
    async def add_knowledge(self, questions: List[str], answers: List[str], 
                     metadatas: Optional[List[Dict[str, Any]]] = None, 
                     check_duplicates: bool = True) -> Dict[str, Any]:
        """
        Add question-answer pairs to the knowledge base with L2 normalized embeddings
        Returns dict with added IDs and any skipped duplicates
        """
        if len(questions) != len(answers):
            raise ValueError("Questions and answers lists must have the same length")
        
        # Create default metadata if not provided
        if metadatas is None:
            metadatas = [{"source": "manual"} for _ in range(len(questions))]
        
        added_ids = []
        skipped_duplicates = []
        
        for i, (question, answer) in enumerate(zip(questions, answers)):
            question = question.strip()
            answer = answer.strip()
            
            if not question or not answer:
                print(f"⚠️ Skipping empty question or answer at index {i}")
                continue
            
            # Check for duplicates if enabled
            if check_duplicates:
                duplicate = await self.check_duplicate_question(question)
                if duplicate:
                    skipped_duplicates.append({
                        "question": question,
                        "existing_question": duplicate["document"],
                        "similarity": duplicate.get("cosine_similarity", 0)
                    })
                    print(f"⏭️ Skipping duplicate question: {question[:50]}...")
                    continue
            
            # Generate unique ID
            qa_id = str(uuid.uuid4())
            
            # Get metadata for this pair
            metadata = metadatas[i] if i < len(metadatas) else {"source": "manual"}
            
            try:
                # Generate L2 normalized embeddings for answer
                answer_embeddings = self._l2_normalize_embeddings([answer])
                
                # Add answer to collection
                self.collection.add(
                    documents=[answer],
                    embeddings=answer_embeddings,
                    metadatas=[metadata],
                    ids=[qa_id]
                )
                
                # Generate L2 normalized embeddings for question
                question_embeddings = self._l2_normalize_embeddings([question])
                
                # Add question with reference to answer ID
                question_id = f"q_{qa_id}"
                question_metadata = {"answer_id": qa_id, "type": "question", **metadata}
                
                self.collection.add(
                    documents=[question],
                    embeddings=question_embeddings,
                    metadatas=[question_metadata],
                    ids=[question_id]
                )
                
                added_ids.append(qa_id)
                print(f"✅ Added Q&A pair: {question[:50]}...")
                
            except Exception as e:
                print(f"❌ Error adding Q&A pair {i}: {str(e)}")
                continue
        
        result = {
            "added_ids": added_ids,
            "added_count": len(added_ids),
            "skipped_duplicates": skipped_duplicates,
            "skipped_count": len(skipped_duplicates)
        }
        
        print(f"📊 Add knowledge summary: {len(added_ids)} added, {len(skipped_duplicates)} skipped")
        return result
    
    async def search(self, query: str, n_results: int = 3) -> List[Dict[str, Any]]:
        """
        Search the knowledge base using L2 normalized embeddings and dot product similarity
        Returns list of results with their metadata and cosine similarity scores
        """
        async with self._async_lock():
            try:
                # Generate L2 normalized embedding for the query
                query_embedding = self._l2_normalize_embeddings([query])[0]
                
                # Query using the normalized embedding
                results = self.collection.query(
                    query_embeddings=[query_embedding],
                    n_results=n_results
                )
                
                formatted_results = []
                if results and results["documents"]:
                    for i, doc in enumerate(results["documents"][0]):
                        # With L2 normalized vectors and inner product space, 
                        # the distance represents (1 - cosine_similarity)
                        # So cosine_similarity = 1 - distance
                        if "distances" in results and results["distances"] and len(results["distances"][0]) > i:
                            distance = results["distances"][0][i]
                            # For inner product space with normalized vectors: cosine_similarity = 1 - distance
                            cosine_similarity = 1.0 - distance
                            # Clamp to [0, 1] range to handle any numerical precision issues
                            cosine_similarity = max(0.0, min(1.0, cosine_similarity))
                        else:
                            cosine_similarity = 0.0
                        
                        formatted_results.append({
                            "document": doc,
                            "metadata": results["metadatas"][0][i],
                            "id": results["ids"][0][i],
                            "cosine_similarity": cosine_similarity
                        })
                
                return formatted_results
                
            except Exception as e:
                print(f"❌ Error searching: {str(e)}")
                return []
    
    async def populate_default_knowledge(self) -> Dict[str, Any]:
        """
        Populate the knowledge base with default question-answer pairs for Abar
        """
        print("🚀 Starting to populate default knowledge...")
        
        questions = [
            "ما هو تطبيق ابار؟",
        ]
        
        answers = [
            "تطبيق ابار هو تطبيق لتوصيل المياه المعبأة من أكثر من 200 علامة تجارية مختلفة للمياه.",
        ]
        
        metadatas = [
            {"source": "default", "category": "general_info"},
        ]
        
        # Add knowledge with duplicate checking enabled
        result = await self.add_knowledge(questions, answers, metadatas, check_duplicates=True)
        
        print(f"✅ Default knowledge population completed!")
        print(f"   Added: {result['added_count']} new Q&A pairs")
        print(f"   Skipped: {result['skipped_count']} duplicates")
        
        return result

    def list_questions(self) -> List[str]:
        """
        List all question documents from the collection.
        """
        with self._sync_lock():
            try:
                all_data = self.collection.get(include=["documents", "metadatas"])
                
                questions = []
                for doc, meta in zip(all_data["documents"], all_data["metadatas"]):
                    if meta.get("type") == "question":
                        questions.append(doc)
                
                print(f"📄 Found {len(questions)} questions in the knowledge base.")
                return questions
                
            except Exception as e:
                print(f"❌ Error listing questions: {str(e)}")
                return []
    
    def get_stats(self) -> Dict[str, int]:
        """
        Get statistics about the knowledge base
        """
        with self._sync_lock():
            try:
                all_data = self.collection.get(include=["metadatas"])
                
                questions_count = 0
                answers_count = 0
                
                for meta in all_data["metadatas"]:
                    if meta.get("type") == "question":
                        questions_count += 1
                    else:
                        answers_count += 1
                
                return {
                    "total_documents": len(all_data["metadatas"]),
                    "questions": questions_count,
                    "answers": answers_count,
                    "qa_pairs": answers_count  # Each answer represents one Q&A pair
                }
                
            except Exception as e:
                print(f"❌ Error getting stats: {str(e)}")
                return {"total_documents": 0, "questions": 0, "answers": 0, "qa_pairs": 0}
    
    def get_collection_safe(self):
        """Get collection with thread safety for direct operations"""
        with self._sync_lock():
            return self.collection


# Create and export the instance
chroma_manager = ChromaManager()

# Uncomment the lines below if you want to run tests manually

# def run_tests():
#     """Run manual tests for ChromaDB functionality"""
#     questions = chroma_manager.list_questions()
#     for i, q in enumerate(questions, 1):
#         print(f"{i}. {q}")
#     
#     # Test input queries
#     test_queries = [
#         "السسلام عليكم",
#         "السلام عليكم", 
#         "مرحبا",
#         "هلا هلا"
#     ]
#     
#     # Run test queries
#     print("🔍 Running test queries...\n")
#     for query in test_queries:
#         print(f"🧪 Query: {query}")
#         results = chroma_manager.search(query, n_results=1)
#         
#         if results:
#             top_result = results[0]
#             print(f"✅ Top Match: {top_result['document']}")
#             print(f"🔗 Similarity: {top_result['similarity']:.4f}")
#             print(f"🗂️ Metadata: {top_result['metadata']}")
#         else:
#             print("❌ No result found.")
#         
#         print("-" * 50)

# To run tests manually, uncomment and call: run_tests()