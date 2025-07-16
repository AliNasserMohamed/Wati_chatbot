from vectorstore.chroma_db import chroma_manager
from typing import List, Dict, Any, Optional

class KnowledgeManager:
    def __init__(self):
        self.chroma_manager = chroma_manager
    
    def add_qa_pair(self, question: str, answer: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Add a single question-answer pair to the knowledge base
        Returns result dict with operation details
        """
        if metadata is None:
            metadata = {"source": "manual"}
        
        try:
            # Check if question and answer are valid
            if not question or not question.strip():
                return {"success": False, "error": "Question cannot be empty"}
            
            if not answer or not answer.strip():
                return {"success": False, "error": "Answer cannot be empty"}
            
            # Add knowledge with duplicate checking using synchronous method
            result = self.chroma_manager.add_knowledge_sync([question], [answer], [metadata], check_duplicates=True)
            
            if result["added_count"] > 0:
                return {
                    "success": True,
                    "id": result["added_ids"][0],
                    "message": "Q&A pair added successfully",
                    "added_count": result["added_count"],
                    "skipped_count": result["skipped_count"]
                }
            else:
                # Check if it was skipped due to duplicate
                if result["skipped_count"] > 0:
                    duplicate_info = result["skipped_duplicates"][0]
                    return {
                        "success": False,
                        "error": "Duplicate question found",
                        "duplicate_info": duplicate_info,
                        "skipped_count": result["skipped_count"]
                    }
                else:
                    return {"success": False, "error": "Failed to add Q&A pair"}
                    
        except Exception as e:
            print(f"❌ Error in add_qa_pair: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def add_multiple_qa_pairs(self, questions: List[str], answers: List[str], 
                             metadatas: Optional[List[Dict[str, Any]]] = None,
                             check_duplicates: bool = True) -> Dict[str, Any]:
        """
        Add multiple question-answer pairs to the knowledge base
        Returns result dict with operation details
        """
        try:
            result = self.chroma_manager.add_knowledge_sync(questions, answers, metadatas, check_duplicates)
            
            return {
                "success": True,
                "added_ids": result["added_ids"],
                "added_count": result["added_count"],
                "skipped_duplicates": result["skipped_duplicates"],
                "skipped_count": result["skipped_count"],
                "message": f"Added {result['added_count']} Q&A pairs, skipped {result['skipped_count']} duplicates"
            }
            
        except Exception as e:
            print(f"❌ Error in add_multiple_qa_pairs: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def search_knowledge(self, query: str, n_results: int = 3) -> List[Dict[str, Any]]:
        """
        Search the knowledge base for similar questions/answers
        """
        try:
            return self.chroma_manager.search_sync(query, n_results)
        except Exception as e:
            print(f"❌ Error in search_knowledge: {str(e)}")
            return []
    
    def check_duplicate(self, question: str, similarity_threshold: float = 0.85) -> Optional[Dict[str, Any]]:
        """
        Check if a question already exists in the knowledge base
        """
        try:
            return self.chroma_manager.check_duplicate_question_sync(question, similarity_threshold)
        except Exception as e:
            print(f"❌ Error in check_duplicate: {str(e)}")
            return None
    
    def get_knowledge_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the knowledge base
        """
        try:
            stats = self.chroma_manager.get_stats()
            return {"success": True, "stats": stats}
        except Exception as e:
            print(f"❌ Error getting knowledge stats: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def populate_abar_knowledge(self) -> Dict[str, Any]:
        """
        Populate the knowledge base with Q&A pairs from Excel file
        """
        try:
            print("🚀 Starting Abar knowledge population from Excel...")
            
            # Use the ChromaManager's populate_default_knowledge_sync which now reads from Excel
            result = self.chroma_manager.populate_default_knowledge_sync()
            
            return {
                "success": True,
                "added_ids": result["added_ids"],
                "added_count": result["added_count"],
                "skipped_duplicates": result["skipped_duplicates"],
                "skipped_count": result["skipped_count"],
                "message": f"Successfully populated knowledge base from Excel. Added {result['added_count']} Q&A pairs, skipped {result['skipped_count']} duplicates."
            }
            
        except Exception as e:
            print(f"❌ Error in populate_abar_knowledge: {str(e)}")
            return {"success": False, "error": str(e)}

# Create an instance
knowledge_manager = KnowledgeManager() 