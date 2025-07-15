import os
import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions
from typing import List, Dict, Any, Optional, Union
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
        
        # Use lightweight multilingual embedding model with caching for faster performance
        print("🔧 Initializing lightweight multilingual embedding model with caching...")
        self.embedding_function = CachedSentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        
        # Create or get the collection with cosine similarity space (merged from lite version)
        self.collection = self.client.get_or_create_collection(
            name="abar_knowledge_base",
            embedding_function=self.embedding_function,
            metadata={"description": "Knowledge base for Abar chatbot with lightweight embeddings", "hnsw:space": "cosine"}
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
    
    # SYNCHRONOUS METHODS (merged from lite version)
    def check_duplicate_question_sync(self, question: str, similarity_threshold: float = 0.85) -> Optional[Dict[str, Any]]:
        """
        Synchronous version: Check if a question already exists in the knowledge base
        Returns the existing question data if found, None otherwise
        """
        with self._sync_lock():
            try:
                # Search for similar questions
                results = self.search_sync(question, n_results=5)
                
                for result in results:
                    # Check if this is a question (not an answer)
                    if result.get("metadata", {}).get("type") == "question":
                        # Check similarity threshold
                        similarity = result.get("similarity", 0)
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
                                    "id": f"exact_match_{i}",
                                    "similarity": 1.0
                                }
                
                return None
                
            except Exception as e:
                print(f"❌ Error checking for duplicates: {str(e)}")
                return None
    
    def add_knowledge_sync(self, questions: List[str], answers: List[str], 
                          metadatas: Optional[List[Dict[str, Any]]] = None, 
                          check_duplicates: bool = True) -> Union[List[str], Dict[str, Any]]:
        """
        Synchronous version: Add question-answer pairs to the knowledge base
        Returns list of IDs (simple mode) or dict with detailed results (with duplicate checking)
        """
        with self._sync_lock():
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
                    duplicate = self.check_duplicate_question_sync(question)
                    if duplicate:
                        skipped_duplicates.append({
                            "question": question,
                            "existing_question": duplicate["document"],
                            "similarity": duplicate.get("similarity", 0)
                        })
                        print(f"⏭️ Skipping duplicate question: {question[:50]}...")
                        continue
                
                # Generate unique ID
                qa_id = str(uuid.uuid4())
                
                # Get metadata for this pair
                metadata = metadatas[i] if i < len(metadatas) else {"source": "manual"}
                
                try:
                    # Add answer to collection
                    self.collection.add(
                        documents=[answer],
                        metadatas=[metadata],
                        ids=[qa_id]
                    )
                    
                    # Add question with reference to answer ID
                    question_id = f"q_{qa_id}"
                    question_metadata = {"answer_id": qa_id, "type": "question", **metadata}
                    
                    self.collection.add(
                        documents=[question],
                        metadatas=[question_metadata],
                        ids=[question_id]
                    )
                    
                    added_ids.append(qa_id)
                    print(f"✅ Added Q&A pair: {question[:50]}...")
                    
                except Exception as e:
                    print(f"❌ Error adding Q&A pair {i}: {str(e)}")
                    continue
            
            # Return detailed results if duplicate checking was enabled
            if check_duplicates:
                result = {
                    "added_ids": added_ids,
                    "added_count": len(added_ids),
                    "skipped_duplicates": skipped_duplicates,
                    "skipped_count": len(skipped_duplicates)
                }
                print(f"📊 Add knowledge summary: {len(added_ids)} added, {len(skipped_duplicates)} skipped")
                return result
            else:
                # Return simple list of IDs (lite version compatibility)
                return added_ids
    
    def search_sync(self, query: str, n_results: int = 3) -> List[Dict[str, Any]]:
        """
        Synchronous version: Search the knowledge base using cosine similarity
        Returns list of results with their similarity scores (higher is better)
        """
        with self._sync_lock():
            try:
                results = self.collection.query(
                    query_texts=[query],
                    n_results=n_results
                )
                
                formatted_results = []
                if results and results["documents"]:
                    for i, doc in enumerate(results["documents"][0]):
                        # Convert distance to similarity for cosine distance
                        # For cosine distance: similarity = 1 - distance
                        distance = results["distances"][0][i] if "distances" in results else 1.0
                        similarity = 1.0 - distance  # Convert distance to similarity
                        
                        formatted_results.append({
                            "document": doc,
                            "metadata": results["metadatas"][0][i],
                            "id": results["ids"][0][i],
                            "distance": distance,  # Keep distance for backward compatibility
                            "similarity": similarity  # Add similarity score (higher is better)
                        })
                
                # Sort by similarity (highest first)
                formatted_results.sort(key=lambda x: x["similarity"], reverse=True)
                
                print(f"🔍 ChromaDB: Search completed for query: '{query[:50]}...'")
                print(f"   - Found {len(formatted_results)} results")
                for i, result in enumerate(formatted_results, 1):
                    print(f"   - Result {i}: Similarity={result['similarity']:.4f}, Distance={result['distance']:.4f}")
                
                return formatted_results
                
            except Exception as e:
                print(f"❌ Error searching: {str(e)}")
                return []
    
    def populate_default_knowledge_sync(self) -> Union[List[str], Dict[str, Any]]:
        """
        Synchronous version: Populate the knowledge base with Q&A pairs from CSV file
        """
        print("🚀 Starting to populate knowledge from CSV file...")
        
        try:
            # Import CSV manager
            from utils.csv_manager import csv_manager
            
            # Read Q&A pairs from CSV
            qa_pairs = csv_manager.read_qa_pairs()
            
            if not qa_pairs:
                print("❌ No Q&A pairs found in CSV file")
                return {
                    "added_ids": [],
                    "added_count": 0,
                    "skipped_duplicates": [],
                    "skipped_count": 0
                }
            
            # Separate questions, answers, and metadatas
            questions = []
            answers = []
            metadatas = []
            
            for pair in qa_pairs:
                questions.append(pair['question'])
                answers.append(pair['answer'])
                
                # Build metadata
                metadata = {
                    "source": pair.get('source', 'csv'),
                    "category": pair.get('category', 'general'),
                    "language": pair.get('language', 'ar'),
                    "priority": pair.get('priority', 'normal')
                }
                
                # Add additional metadata if present
                if pair.get('metadata'):
                    metadata.update(pair['metadata'])
                
                metadatas.append(metadata)
            
            print(f"📊 Found {len(questions)} Q&A pairs in CSV file")
            
            # Add knowledge with duplicate checking enabled
            result = self.add_knowledge_sync(questions, answers, metadatas, check_duplicates=True)
            
            if isinstance(result, dict):
                print(f"✅ CSV knowledge population completed!")
                print(f"   Added: {result['added_count']} new Q&A pairs")
                print(f"   Skipped: {result['skipped_count']} duplicates")
            else:
                print(f"✅ CSV knowledge population completed!")
                print(f"   Added: {len(result)} Q&A pairs")
            
            return result
            
        except Exception as e:
            print(f"❌ Error populating knowledge from CSV: {str(e)}")
            return {
                "added_ids": [],
                "added_count": 0,
                "skipped_duplicates": [],
                "skipped_count": 0
            }
    
    # ASYNC METHODS (existing advanced functionality)
    async def check_duplicate_question(self, question: str, similarity_threshold: float = 0.85) -> Optional[Dict[str, Any]]:
        """
        Async version: Check if a question already exists in the knowledge base
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
                        similarity = result.get("similarity", result.get("cosine_similarity", 0))
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
                                    "id": f"exact_match_{i}",
                                    "similarity": 1.0,
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
        Async version: Add question-answer pairs to the knowledge base with L2 normalized embeddings
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
                        "similarity": duplicate.get("similarity", duplicate.get("cosine_similarity", 0))
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
        Async version: Search the knowledge base using L2 normalized embeddings and cosine similarity
        Returns list of results with their metadata and similarity scores
        """
        async with self._async_lock():
            try:
                # Use the sync version for now since chromadb doesn't support async queries
                return self.search_sync(query, n_results)
                
            except Exception as e:
                print(f"❌ Error searching: {str(e)}")
                return []
    
    async def populate_default_knowledge(self) -> Dict[str, Any]:
        """
        Async version: Populate the knowledge base with Q&A pairs from CSV file
        """
        print("🚀 Starting to populate knowledge from CSV file...")
        
        try:
            # Import CSV manager
            from utils.csv_manager import csv_manager
            
            # Read Q&A pairs from CSV
            qa_pairs = csv_manager.read_qa_pairs()
            
            if not qa_pairs:
                print("❌ No Q&A pairs found in CSV file")
                return {
                    "added_ids": [],
                    "added_count": 0,
                    "skipped_duplicates": [],
                    "skipped_count": 0
                }
            
            # Separate questions, answers, and metadatas
            questions = []
            answers = []
            metadatas = []
            
            for pair in qa_pairs:
                questions.append(pair['question'])
                answers.append(pair['answer'])
                
                # Build metadata
                metadata = {
                    "source": pair.get('source', 'csv'),
                    "category": pair.get('category', 'general'),
                    "language": pair.get('language', 'ar'),
                    "priority": pair.get('priority', 'normal')
                }
                
                # Add additional metadata if present
                if pair.get('metadata'):
                    metadata.update(pair['metadata'])
                
                metadatas.append(metadata)
            
            print(f"📊 Found {len(questions)} Q&A pairs in CSV file")
            
            # Add knowledge with duplicate checking enabled
            result = await self.add_knowledge(questions, answers, metadatas, check_duplicates=True)
            
            print(f"✅ CSV knowledge population completed!")
            print(f"   Added: {result['added_count']} new Q&A pairs")
            print(f"   Skipped: {result['skipped_count']} duplicates")
            
            return result
            
        except Exception as e:
            print(f"❌ Error populating knowledge from CSV: {str(e)}")
            return {
                "added_ids": [],
                "added_count": 0,
                "skipped_duplicates": [],
                "skipped_count": 0
            }

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

# For backward compatibility, create a lite manager alias
chroma_manager_lite = chroma_manager

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
#         results = chroma_manager.search_sync(query, n_results=1)
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