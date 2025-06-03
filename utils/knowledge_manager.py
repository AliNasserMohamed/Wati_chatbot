from vectorstore.chroma_db import chroma_manager
from typing import List, Dict, Any, Optional

class KnowledgeManager:
    def __init__(self):
        self.chroma_manager = chroma_manager
    
    def add_qa_pair(self, question: str, answer: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Add a single question-answer pair to the knowledge base
        Returns the ID of the added pair
        """
        if metadata is None:
            metadata = {"source": "manual"}
            
        ids = self.chroma_manager.add_knowledge([question], [answer], [metadata])
        return ids[0] if ids else None
    
    def add_multiple_qa_pairs(self, questions: List[str], answers: List[str], 
                             metadatas: Optional[List[Dict[str, Any]]] = None) -> List[str]:
        """
        Add multiple question-answer pairs to the knowledge base
        Returns the list of added IDs
        """
        return self.chroma_manager.add_knowledge(questions, answers, metadatas)
    
    def search_knowledge(self, query: str, n_results: int = 3) -> List[Dict[str, Any]]:
        """
        Search the knowledge base for similar questions/answers
        """
        return self.chroma_manager.search(query, n_results)
    
    def populate_abar_knowledge(self):
        """
        Populate the knowledge base with Abar-specific QA pairs
        """
        questions = [
            "ما هو تطبيق ابار؟",
            "كيف يمكنني طلب المياه؟",
            "هل يوجد حد أدنى للطلب؟",
            "ماهي طرق الدفع المتاحة؟",
            "متى يتم توصيل الطلبات؟",
            "كم تكلفة التوصيل؟",
            "هل يمكنني إلغاء طلبي؟",
            "كيف أتواصل مع خدمة العملاء؟"
        ]
        
        answers = [
            "ابار هو تطبيق يوفر لك توصيل المياه المعبأة من أكثر من 200 علامة تجارية مختلفة.",
            "يمكنك طلب المياه عن طريق تحميل تطبيق ابار، واختيار المنتجات اللي تبيها، وتحديد وقت التوصيل المناسب لك.",
            "ما فيه حد أدنى للطلب في تطبيق ابار، تقدر تطلب اللي تحتاجه بدون قيود.",
            "نقبل الدفع الإلكتروني (مدى، فيزا، ماستركارد) أو الدفع عند الاستلام.",
            "نوصل الطلبات حسب الوقت اللي تختاره أنت، وتقدر تتبع المندوب على الخريطة.",
            "التوصيل مجاني 100% على كل الطلبات.",
            "أيوه، تقدر تلغي طلبك قبل بدء التجهيز عبر التطبيق أو بالتواصل مع خدمة العملاء.",
            "تقدر تتواصل مع خدمة العملاء عبر الرقم الموجود في التطبيق أو من خلال الواتساب أو الايميل support@abar.app"
        ]
        
        metadatas = [
            {"source": "abar", "category": "general_info"},
            {"source": "abar", "category": "ordering"},
            {"source": "abar", "category": "ordering"},
            {"source": "abar", "category": "payment"},
            {"source": "abar", "category": "delivery"},
            {"source": "abar", "category": "delivery"},
            {"source": "abar", "category": "cancellation"},
            {"source": "abar", "category": "support"}
        ]
        
        return self.chroma_manager.add_knowledge(questions, answers, metadatas)

# Create an instance
knowledge_manager = KnowledgeManager() 