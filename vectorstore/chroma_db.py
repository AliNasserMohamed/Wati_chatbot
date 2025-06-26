import os
import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions
from typing import List, Dict, Any, Optional
import uuid

# Create vector store directory if it doesn't exist
os.makedirs("vectorstore/data", exist_ok=True)

class ChromaManager:
    def __init__(self):
        # Initialize Chroma client with persistence
        self.client = chromadb.PersistentClient(
            path="vectorstore/data",
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Use Arabic-specific embedding model for better Arabic language support
        self.embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="mohamed2811/Muffakir_Embedding_V2"
        )
        
        # Create or get the collection
        self.collection = self.client.get_or_create_collection(
            name="abar_knowledge_base",
            embedding_function=self.embedding_function,
            metadata={"description": "Knowledge base for Abar chatbot with Arabic embeddings"}
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
        Search the knowledge base for similar questions/answers
        Returns list of results with their metadata
        """
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results
        )
        
        formatted_results = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                formatted_results.append({
                    "document": doc,
                    "metadata": results["metadatas"][0][i],
                    "id": results["ids"][0][i],
                    "distance": results["distances"][0][i] if "distances" in results else None
                })
        
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
            "كيف يمكنني متابعة طلبي؟"
        ]
        
        answers = [
            "تطبيق ابار هو تطبيق لتوصيل المياه المعبأة من أكثر من 200 علامة تجارية مختلفة للمياه.",
            "تطبيق ابار يتيح لك طلب المياه من أكثر من 200 علامة تجارية، وتحديد وقت التوصيل المناسب لك، واختيار طريقة الدفع، ومتابعة المندوب على الخريطة.",
            "تطبيق ابار يوفر أكثر من 200 علامة تجارية للمياه المعبأة.",
            "نعم، التوصيل مجاني 100% في تطبيق ابار.",
            "يمكنك متابعة طلبك من خلال التواصل مع المندوب ومتابعته على الخريطة في التطبيق."
        ]
        
        metadatas = [
            {"source": "default", "category": "general_info"},
            {"source": "default", "category": "usage"},
            {"source": "default", "category": "brands"},
            {"source": "default", "category": "delivery"},
            {"source": "default", "category": "tracking"}
        ]
        
        self.add_knowledge(questions, answers, metadatas)

# Create and export the instance
chroma_manager = ChromaManager() 