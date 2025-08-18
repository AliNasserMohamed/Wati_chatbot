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
import re
import unicodedata

# Create vector store directory if it doesn't exist
os.makedirs("vectorstore/data", exist_ok=True)

class ArabicTextProcessor:
    """Helper class for Arabic text preprocessing"""
    
    @staticmethod
    def normalize_arabic_text(text: str) -> str:
        """
        Normalize Arabic text for better embedding
        """
        if not text:
            return ""
        
        # Ensure UTF-8 encoding
        if isinstance(text, bytes):
            text = text.decode('utf-8')
        
        # Remove diacritics (تشكيل)
        text = re.sub(r'[\u064B-\u065F\u0670\u06D6-\u06ED]', '', text)
        
        # Normalize Arabic characters
        text = text.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا')
        text = text.replace('ة', 'ه')
        text = text.replace('ى', 'ي')
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Normalize Unicode
        text = unicodedata.normalize('NFKC', text)
        
        return text
    
    @staticmethod
    def is_arabic_text(text: str) -> bool:
        """Check if text contains Arabic characters"""
        arabic_pattern = re.compile(r'[\u0600-\u06FF]')
        return bool(arabic_pattern.search(text))

class ChromaManager:
    def __init__(self):
        # Initialize Chroma client with persistence
        self.client = chromadb.PersistentClient(
            path="vectorstore/data",
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Use better Arabic-capable embedding model
        print("🔧 Initializing Arabic-capable embedding model...")
        try:
            # Try to use a better model for Arabic
            from sentence_transformers import SentenceTransformer
            
            # This model is specifically good for Arabic
            model_name = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
            # Alternative: "CAMeL-Lab/bert-base-arabic-camelbert-mix"
            
            print(f"🌐 Loading model: {model_name}")
            self.embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=model_name
            )
            
        except ImportError:
            print("⚠️  sentence-transformers not available, using default model")
            # Fallback to default
            self.embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="paraphrase-multilingual-MiniLM-L12-v2"
            )
        
        # Initialize text processor
        self.text_processor = ArabicTextProcessor()
        
        # Create or get the collection with cosine similarity space
        self.collection = self.client.get_or_create_collection(
            name="abar_knowledge_base",
            embedding_function=self.embedding_function,
            metadata={"description": "Arabic knowledge base for Abar chatbot", "hnsw:space": "cosine"}
        )
        
        # Add thread-safe locking for concurrent access
        self._lock = asyncio.Lock()
        self._thread_lock = threading.Lock()
    
    def _preprocess_text(self, text: str) -> str:
        """
        Preprocess text before embedding
        """
        # Normalize Arabic text
        processed_text = self.text_processor.normalize_arabic_text(text)
        
        # Log preprocessing for debugging
        if text != processed_text:
            print(f"📝 Text preprocessed:")
            print(f"   Original: {text[:50]}...")
            print(f"   Processed: {processed_text[:50]}...")
        
        return processed_text
    
    def _preprocess_texts(self, texts: List[str]) -> List[str]:
        """
        Preprocess multiple texts
        """
        return [self._preprocess_text(text) for text in texts]
    
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
        # Preprocess texts before embedding
        processed_texts = self._preprocess_texts(texts)
        
        # Get embeddings from the embedding function
        embeddings = self.embedding_function(processed_texts)
        
        # Convert to numpy array and apply L2 normalization
        embeddings_array = np.array(embeddings)
        norms = np.linalg.norm(embeddings_array, axis=1, keepdims=True)
        # Avoid division by zero
        norms = np.where(norms == 0, 1, norms)
        normalized_embeddings = embeddings_array / norms
        
        return normalized_embeddings.tolist()
    
    def check_duplicate_question_sync(self, question: str, similarity_threshold: float = 0.85) -> Optional[Dict[str, Any]]:
        """
        Synchronous version: Check if a question already exists in the knowledge base
        """
        with self._sync_lock():
            try:
                # Preprocess the question
                processed_question = self._preprocess_text(question)
                
                # Search for similar questions
                results = self.search_sync(processed_question, n_results=5)
                
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
                
                # Also check for exact text matches (with normalization)
                all_data = self.collection.get(include=["documents", "metadatas"])
                if all_data and all_data.get("documents"):
                    for i, doc in enumerate(all_data["documents"]):
                        metadata = all_data["metadatas"][i]
                        if metadata.get("type") == "question":
                            # Check for exact match (normalized)
                            normalized_existing = self._preprocess_text(doc)
                            if normalized_existing == processed_question:
                                print(f"🔍 Found exact duplicate question (normalized)")
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
                answer = answer.strip() if answer else ""  # Allow empty answers
                
                # Only skip if question is empty
                if not question:
                    print(f"⚠️ Skipping empty question at index {i}")
                    continue
                
                # Allow questions without answers
                if not answer:
                    print(f"ℹ️ Adding question without answer at index {i}: {question[:50]}...")
                    # Add has_answer flag to metadata
                    metadata = metadatas[i] if i < len(metadatas) else {"source": "manual"}
                    metadata["has_answer"] = False
                    metadatas[i] = metadata
                
                # Debug: Print Arabic text detection
                if self.text_processor.is_arabic_text(question):
                    print(f"🔤 Arabic text detected in question: {question[:30]}...")
                if self.text_processor.is_arabic_text(answer):
                    print(f"🔤 Arabic text detected in answer: {answer[:30]}...")
                
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
                
                # Add language detection to metadata
                if self.text_processor.is_arabic_text(question):
                    metadata["detected_language"] = "arabic"
                
                try:
                    # Preprocess texts before adding
                    processed_answer = self._preprocess_text(answer)
                    processed_question = self._preprocess_text(question)
                    
                    # COMMENTED OUT: Do not embed answers - only embed questions
                    # Prepare answer metadata - force type="answer" based on column
                    # answer_metadata = {**metadata, "type": "answer"}
                    
                    # Add answer to collection - COMMENTED OUT
                    # self.collection.add(
                    #     documents=[processed_answer],
                    #     metadatas=[answer_metadata],
                    #     ids=[qa_id]
                    # )
                    
                    # Add question with reference to answer ID - force type="question" based on column
                    question_id = f"q_{qa_id}"
                    question_metadata = {"answer_id": qa_id, "type": "question", "answer_text": answer, **metadata}
                    
                    self.collection.add(
                        documents=[processed_question],
                        metadatas=[question_metadata],
                        ids=[question_id]
                    )
                    
                    added_ids.append(qa_id)
                    print(f"✅ Added Arabic Q&A pair: {question[:50]}...")
                    
                except Exception as e:
                    print(f"❌ Error adding Q&A pair {i}: {str(e)}")
                    # Print more details for debugging
                    print(f"   Question: {question}")
                    print(f"   Answer: {answer}")
                    continue
            
            # Return detailed results if duplicate checking was enabled
            if check_duplicates:
                result = {
                    "added_ids": added_ids,
                    "added_count": len(added_ids),
                    "skipped_duplicates": skipped_duplicates,
                    "skipped_count": len(skipped_duplicates)
                }
                print(f"📊 Arabic knowledge summary: {len(added_ids)} added, {len(skipped_duplicates)} skipped")
                return result
            else:
                return added_ids
    
    def search_sync(self, query: str, n_results: int = 3) -> List[Dict[str, Any]]:
        """
        Synchronous version: Search the knowledge base using cosine similarity
        """
        with self._sync_lock():
            try:
                # Preprocess query
                processed_query = self._preprocess_text(query)
                
                # Debug: Show query preprocessing
                if query != processed_query:
                    print(f"🔍 Query preprocessed:")
                    print(f"   Original: {query}")
                    print(f"   Processed: {processed_query}")
                
                results = self.collection.query(
                    query_texts=[processed_query],
                    n_results=n_results
                )
                
                formatted_results = []
                if results and results["documents"]:
                    for i, doc in enumerate(results["documents"][0]):
                        # Skip if document is None or empty
                        if not doc:
                            continue
                            
                        # Convert distance to similarity for cosine distance
                        distance = results["distances"][0][i] if "distances" in results else 1.0
                        similarity = 1.0 - distance
                        
                        # Get metadata safely - handle None values
                        metadata = results["metadatas"][0][i] if i < len(results["metadatas"][0]) else {}
                        if metadata is None:
                            metadata = {}
                        
                        # Get ID safely
                        doc_id = results["ids"][0][i] if i < len(results["ids"][0]) else f"doc_{i}"
                        
                        formatted_results.append({
                            "document": doc,
                            "metadata": metadata,
                            "id": doc_id,
                            "distance": distance,
                            "similarity": similarity
                        })
                
                # Sort by similarity (highest first)
                formatted_results.sort(key=lambda x: x["similarity"], reverse=True)
                
                print(f"🔍 ChromaDB Search: '{query[:50]}...'")
                print(f"   Found {len(formatted_results)} results")
                for i, result in enumerate(formatted_results, 1):
                    # Safely get metadata with null checking
                    metadata = result.get("metadata", {})
                    if metadata is None:
                        metadata = {}
                    doc_type = metadata.get("type", "answer")
                    print(f"   Result {i}: [{doc_type.upper()}] Similarity={result['similarity']:.4f}")
                
                return formatted_results
                
            except Exception as e:
                print(f"❌ Error searching text: {str(e)}")
                return []
    
    async def search(self, query: str, n_results: int = 3) -> List[Dict[str, Any]]:
        """
        Async wrapper for search_sync method
        """
        # Run the synchronous search in a thread pool to avoid blocking
        import asyncio
        import concurrent.futures
        
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as executor:
            result = await loop.run_in_executor(
                executor, 
                self.search_sync, 
                query, 
                n_results
            )
        return result
    
    # ... [Include other methods with similar Arabic text preprocessing] ...
    
    def get_stats(self) -> Dict[str, int]:
        """Get statistics about the knowledge base (optimized for speed)"""
        with self._sync_lock():
            try:
                # Use count() method if available, otherwise fall back to get()
                try:
                    # First try to get just the count efficiently
                    total_count = self.collection.count()
                    
                    # If we have a reasonable number of documents, get detailed stats
                    if total_count < 1000:  # Only get detailed stats for smaller collections
                        all_data = self.collection.get(include=["metadatas"])
                        
                        questions_count = 0
                        answers_count = 0
                        arabic_count = 0
                        categories = {}
                        
                        for meta in all_data["metadatas"]:
                            if meta.get("type") == "question":
                                questions_count += 1
                                # Count answers by checking if answer_text exists in metadata
                                if meta.get("answer_text") and meta.get("answer_text").strip():
                                    answers_count += 1
                            # Note: We no longer embed answers separately, only questions
                            
                            if meta.get("detected_language") == "arabic":
                                arabic_count += 1
                                
                            # Count categories
                            category = meta.get("category", "general")
                            categories[category] = categories.get(category, 0) + 1
                        
                        return {
                            "total_documents": total_count,
                            "questions": questions_count,
                            "answers": answers_count,
                            "qa_pairs": answers_count,
                            "arabic_documents": arabic_count,
                            "categories": categories
                        }
                    else:
                        # For large collections, just return basic stats
                        return {
                            "total_documents": total_count,
                            "questions": "N/A (large collection)",
                            "answers": "N/A (large collection)",
                            "qa_pairs": "N/A (large collection)",
                            "arabic_documents": "N/A (large collection)",
                            "categories": {}
                        }
                except Exception as e:
                    print(f"❌ Error getting collection count: {str(e)}")
                    return {
                        "total_documents": 0,
                        "questions": 0,
                        "answers": 0,
                        "qa_pairs": 0,
                        "arabic_documents": 0,
                        "categories": {}
                    }
            except Exception as e:
                print(f"❌ Error getting knowledge base stats: {str(e)}")
                return {
                    "total_documents": 0,
                    "questions": 0,
                    "answers": 0,
                    "qa_pairs": 0,
                    "arabic_documents": 0,
                    "categories": {}
                }
    
    def get_collection_safe(self):
        """Get collection with thread safety for direct operations"""
        with self._sync_lock():
            return self.collection

    def test_arabic_embedding(self, test_text: str = "مرحبا كيف حالك") -> bool:
        """
        Test if Arabic text can be embedded successfully
        """
        try:
            print(f"🧪 Testing Arabic embedding with: '{test_text}'")
            
            # Test preprocessing
            processed = self._preprocess_text(test_text)
            print(f"   Preprocessed: '{processed}'")
            
            # Test embedding generation
            embeddings = self._l2_normalize_embeddings([processed])
            print(f"   Embedding shape: {np.array(embeddings).shape}")
            print(f"   Embedding norm: {np.linalg.norm(embeddings[0]):.4f}")
            
            # Test adding to collection
            test_id = "test_arabic_" + str(uuid.uuid4())
            self.collection.add(
                documents=[processed],
                metadatas=[{"source": "test", "language": "arabic"}],
                ids=[test_id]
            )
            
            # Test search
            results = self.search_sync(test_text, n_results=1)
            
            # Cleanup
            self.collection.delete(ids=[test_id])
            
            print(f"✅ Arabic embedding test passed!")
            return True
            
        except Exception as e:
            print(f"❌ Arabic embedding test failed: {str(e)}")
            return False

    def delete_question_by_text(self, question_text: str) -> bool:
        """
        Delete a question from the vector database by matching the question text
        
        Args:
            question_text: The question text to find and delete
            
        Returns:
            bool: True if deleted successfully, False otherwise
        """
        with self._sync_lock():
            try:
                # Get all documents from the collection
                all_data = self.collection.get(include=["documents", "metadatas"])
                
                if not all_data or not all_data.get("documents"):
                    return False
                
                # Process the question text the same way as during embedding
                processed_question_text = self._preprocess_text(question_text)
                
                # Search for the matching question
                found_id = None
                for i, doc in enumerate(all_data["documents"]):
                    processed_doc = self._preprocess_text(doc)
                    metadata = all_data["metadatas"][i]
                    
                    # Check if this is a question and matches our text
                    if (metadata.get("type") == "question" and 
                        processed_doc == processed_question_text):
                        found_id = all_data["ids"][i]
                        break
                
                if found_id:
                    # Delete the question
                    self.collection.delete(ids=[found_id])
                    return True
                else:
                    return False
                    
            except Exception as e:
                print(f"❌ Error deleting question from vector database: {str(e)}")
                return False

    def populate_default_knowledge_sync(self) -> Dict[str, Any]:
        """
        Populate the knowledge base with Q&A pairs from Excel file
        """
        try:
            print("🚀 ChromaManager: Reading data from Excel file...")
            
            # Import Excel manager
            from utils.excel_manager import csv_manager
            
            # Read Q&A pairs from Excel
            qa_pairs = csv_manager.read_qa_pairs()
            if not qa_pairs:
                return {
                    "success": False,
                    "error": "No Q&A pairs found in Excel file",
                    "added_ids": [],
                    "added_count": 0,
                    "skipped_duplicates": [],
                    "skipped_count": 0
                }
            
            # Prepare data for ChromaDB
            questions = []
            answers = []
            metadatas = []
            
            for pair in qa_pairs:
                question = pair.get('question', '').strip()
                answer = pair.get('answer', '').strip()
                
                # Only skip if question is empty
                if not question:
                    continue
                
                # Allow empty answers
                if not answer:
                    answer = ""
                
                # Prepare metadata
                metadata = {
                    "category": pair.get('category', 'general'),
                    "language": pair.get('language', 'ar'),
                    "source": pair.get('source', 'excel'),
                    "priority": pair.get('priority', 'normal'),
                }
                
                # Add any additional metadata
                if pair.get('metadata') and isinstance(pair['metadata'], dict):
                    metadata.update(pair['metadata'])
                
                questions.append(question)
                answers.append(answer)
                metadatas.append(metadata)
            
            # Use the add_knowledge_sync method
            result = self.add_knowledge_sync(
                questions=questions,
                answers=answers,
                metadatas=metadatas,
                check_duplicates=True
            )
            
            return result
            
        except Exception as e:
            print(f"❌ Error populating from Excel: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "added_ids": [],
                "added_count": 0,
                "skipped_duplicates": [],
                "skipped_count": 0
            }

# Create and export the instance
chroma_manager = ChromaManager()

# Test Arabic functionality on initialization
print("🧪 Testing Arabic text processing...")
chroma_manager.test_arabic_embedding()

# For backward compatibility
chroma_manager_lite = chroma_manager