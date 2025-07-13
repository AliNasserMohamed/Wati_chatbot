import os
import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions
from typing import List, Dict, Any, Optional
import uuid
from vectorstore.model_cache import model_cache
from vectorstore.cached_embedding_function import CachedSentenceTransformerEmbeddingFunction

# Create vector store directory if it doesn't exist
os.makedirs("vectorstore/data_lite", exist_ok=True)

class ChromaManagerLite:
    def __init__(self):
        # Initialize Chroma client with persistence
        self.client = chromadb.PersistentClient(
            path="vectorstore/data_lite",
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Use a lightweight English embedding model with caching that supports multiple languages
        print("🔧 Initializing lightweight embedding model with caching...")
        self.embedding_function = CachedSentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"  # Much smaller and faster model
        )
        
        # Create or get the collection
        self.collection = self.client.get_or_create_collection(
            name="abar_knowledge_base_lite",
            embedding_function=self.embedding_function,
            metadata={"description": "Lightweight knowledge base for Abar chatbot", "hnsw:space": "cosine"}
        )
    
    def add_knowledge(self, questions: List[str], answers: List[str], 
                     metadatas: Optional[List[Dict[str, Any]]] = None) -> List[str]:
        """
        Add question-answer pairs to the knowledge base
        Returns list of IDs added
        """
        # Generate IDs if not provided
        ids = [str(uuid.uuid4()) for _ in range(len(questions))]
        
        # Create default metadata if not provided
        if metadatas is None:
            metadatas = [{"source": "manual"} for _ in range(len(questions))]
        
        # Add to collection
        self.collection.add(
            documents=answers,
            metadatas=metadatas,
            ids=ids
        )
        
        # Also add the questions with references to answer IDs
        question_ids = [f"q_{id}" for id in ids]
        question_metadatas = [{"answer_id": id, "type": "question"} for id in ids]
        
        self.collection.add(
            documents=questions,
            metadatas=question_metadatas,
            ids=question_ids
        )
        
        return ids
    
    def search(self, query: str, n_results: int = 3) -> List[Dict[str, Any]]:
        """
        Search the knowledge base for similar questions/answers using cosine similarity
        Returns list of results with their similarity scores (higher is better)
        """
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
        
        print(f"🔍 ChromaDB Lite: Search completed for query: '{query[:50]}...'")
        print(f"   - Found {len(formatted_results)} results")
        for i, result in enumerate(formatted_results, 1):
            print(f"   - Result {i}: Similarity={result['similarity']:.4f}, Distance={result['distance']:.4f}")
        
        return formatted_results
    
    def populate_default_knowledge(self):
        """
        Populate the knowledge base with default question-answer pairs for Abar
        """
        questions = [
            "ما هو تطبيق ابار؟",
            "كيف يعمل تطبيق ابار؟",
            "كم عدد العلامات التجارية المتوفرة في ابار؟",
            "هل التوصيل مجاني؟",
            "كيف يمكنني متابعة طلبي؟",
            "How to order water?",
            "What is Abar app?",
            "Is delivery free?"
        ]
        
        answers = [
            "تطبيق ابار هو تطبيق لتوصيل المياه المعبأة من أكثر من 200 علامة تجارية مختلفة للمياه.",
            "تطبيق ابار يتيح لك طلب المياه من أكثر من 200 علامة تجارية، وتحديد وقت التوصيل المناسب لك، واختيار طريقة الدفع، ومتابعة المندوب على الخريطة.",
            "تطبيق ابار يوفر أكثر من 200 علامة تجارية للمياه المعبأة.",
            "نعم، التوصيل مجاني 100% في تطبيق ابار.",
            "يمكنك متابعة طلبك من خلال التواصل مع المندوب ومتابعته على الخريطة في التطبيق.",
            "You can order water through the Abar app by selecting your preferred brand and delivery time.",
            "Abar is a water delivery app with over 200 different water brands available for delivery.",
            "Yes, delivery is 100% free with the Abar app."
        ]
        
        metadatas = [
            {"source": "default", "category": "general_info", "language": "ar"},
            {"source": "default", "category": "usage", "language": "ar"},
            {"source": "default", "category": "brands", "language": "ar"},
            {"source": "default", "category": "delivery", "language": "ar"},
            {"source": "default", "category": "tracking", "language": "ar"},
            {"source": "default", "category": "ordering", "language": "en"},
            {"source": "default", "category": "general_info", "language": "en"},
            {"source": "default", "category": "delivery", "language": "en"}
        ]
        
        self.add_knowledge(questions, answers, metadatas)

# Create and export the lite instance
chroma_manager_lite = ChromaManagerLite() 