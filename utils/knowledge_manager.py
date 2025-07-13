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
            
            # Add knowledge with duplicate checking
            result = self.chroma_manager.add_knowledge([question], [answer], [metadata], check_duplicates=True)
            
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
            result = self.chroma_manager.add_knowledge(questions, answers, metadatas, check_duplicates)
            
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
            return self.chroma_manager.search(query, n_results)
        except Exception as e:
            print(f"❌ Error in search_knowledge: {str(e)}")
            return []
    
    def check_duplicate(self, question: str, similarity_threshold: float = 0.85) -> Optional[Dict[str, Any]]:
        """
        Check if a question already exists in the knowledge base
        """
        try:
            return self.chroma_manager.check_duplicate_question(question, similarity_threshold)
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
    
    async def populate_abar_knowledge(self) -> Dict[str, Any]:
        """
        Populate the knowledge base with greeting-related QA pairs from the frontend system
        """
        try:
            print("🚀 Starting Abar knowledge population...")
            
            # Greeting-related questions and responses from the frontend system
            questions = [
                # Arabic greetings
                "السلام عليكم",
                "الوووو", 
                "هلا",
                "يعطيك العافية",
                "شكراً لكم",
                "مساء الخير",
                "صباح الخير",
                "الله يوفقكم",
                "أوكي تمام",
                "تفضل",
                "مرحبا",
                # English greetings
                "Hello",
                "Hi",
                "Good morning",
                "Good evening",
                "Good afternoon",
                "Thank you",
                "Thanks",
                "Thanks a lot",
                "Much appreciated",
                "OK",
                "Alright",
                "Sure",
                "No problem"
            ]
            
            answers = [
                # Arabic responses
                "عليكم السلام ورحمة الله، تفضل طال عمرك",
                "حياك الله، تفضل استاذي",
                "حياك الله، تفضل طال عمرك",
                "الله يعافيك",
                "العفو، بالخدمة طال عمرك",
                "مساء النور، تفضل طال عمرك",
                "صباح  النور، تفضل طال عمرك",
                "وياك الله يسعدك",
                "",  # No reply needed for "أوكي تمام"
                "",  # No reply needed for "تفضل"
                "مرحبا طال عمرك",
                # English responses
                "Hello! Welcome to Abar Water Delivery. How can I help you today?",
                "Hi there! How can I assist you with your water delivery needs?",
                "Good morning! Welcome to Abar. How may I help you?",
                "Good evening! How can I help you with water delivery today?",
                "Good afternoon! Welcome to Abar Water Delivery. What can I do for you?",
                "You're welcome! Is there anything else I can help you with?",
                "You're welcome! How else can I assist you?",
                "You're very welcome! Feel free to ask if you need anything else.",
                "My pleasure! Let me know if you need any other assistance.",
                "",  # No reply needed for "OK"
                "",  # No reply needed for "Alright"  
                "",  # No reply needed for "Sure"
                ""   # No reply needed for "No problem"
            ]
            
            metadatas = [
                # Arabic metadata
                {"source": "custom", "category": "greeting", "language": "ar"},
                {"source": "custom", "category": "greeting", "language": "ar"},
                {"source": "custom", "category": "greeting", "language": "ar"},
                {"source": "custom", "category": "thanks", "language": "ar"},
                {"source": "custom", "category": "thanks", "language": "ar"},
                {"source": "custom", "category": "greeting", "language": "ar"},
                {"source": "custom", "category": "greeting", "language": "ar"},  # صباح الخير
                {"source": "custom", "category": "conversation", "language": "ar"},
                {"source": "custom", "category": "conversation", "language": "ar"},
                {"source": "custom", "category": "conversation", "language": "ar"},
                {"source": "custom", "category": "greeting", "language": "ar"},
                # English metadata
                {"source": "custom", "category": "greeting", "language": "en"},
                {"source": "custom", "category": "greeting", "language": "en"},
                {"source": "custom", "category": "greeting", "language": "en"},
                {"source": "custom", "category": "greeting", "language": "en"},
                {"source": "custom", "category": "greeting", "language": "en"},
                {"source": "custom", "category": "thanks", "language": "en"},
                {"source": "custom", "category": "thanks", "language": "en"},
                {"source": "custom", "category": "thanks", "language": "en"},
                {"source": "custom", "category": "thanks", "language": "en"},
                {"source": "custom", "category": "conversation", "language": "en"},
                {"source": "custom", "category": "conversation", "language": "en"},
                {"source": "custom", "category": "conversation", "language": "en"},
                {"source": "custom", "category": "conversation", "language": "en"}
            ]
            
            # Use the ChromaManager's populate_default_knowledge and this method together
            result1 = await self.chroma_manager.populate_default_knowledge()
            result2 = await self.chroma_manager.add_knowledge(questions, answers, metadatas, check_duplicates=True)
            
            # Combine results
            total_added = result1["added_count"] + result2["added_count"]
            total_skipped = result1["skipped_count"] + result2["skipped_count"]
            all_ids = result1["added_ids"] + result2["added_ids"]
            all_skipped = result1["skipped_duplicates"] + result2["skipped_duplicates"]
            
            return {
                "success": True,
                "added_ids": all_ids,
                "added_count": total_added,
                "skipped_duplicates": all_skipped,
                "skipped_count": total_skipped,
                "message": f"Successfully populated knowledge base. Added {total_added} Q&A pairs, skipped {total_skipped} duplicates."
            }
            
        except Exception as e:
            print(f"❌ Error in populate_abar_knowledge: {str(e)}")
            return {"success": False, "error": str(e)}

# Create an instance
knowledge_manager = KnowledgeManager() 