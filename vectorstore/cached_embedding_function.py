import numpy as np
from typing import Union, List
from chromadb import EmbeddingFunction, Embeddings
from vectorstore.model_cache import model_cache

class CachedSentenceTransformerEmbeddingFunction(EmbeddingFunction):
    """
    Custom embedding function that uses cached SentenceTransformer models
    """
    
    def __init__(self, model_name: str):
        """
        Initialize with model name
        
        Args:
            model_name: Name of the SentenceTransformer model to use
        """
        self.model_name = model_name
        self._model = None
        
    def _ensure_model_loaded(self):
        """Ensure the model is loaded (lazy loading)"""
        if self._model is None:
            print(f"🔄 Loading embedding model: {self.model_name}")
            self._model = model_cache.load_model(self.model_name)
            print(f"✅ Model loaded successfully: {self.model_name}")
    
    def __call__(self, input: Union[str, List[str]]) -> Embeddings:
        """
        Generate embeddings for input text(s)
        
        Args:
            input: Single string or list of strings to embed
            
        Returns:
            List of embeddings (list of lists of floats)
        """
        self._ensure_model_loaded()
        
        # Ensure input is a list
        if isinstance(input, str):
            texts = [input]
        else:
            texts = input
        
        # Generate embeddings
        embeddings = self._model.encode(texts, convert_to_numpy=True)
        
        # Convert to list of lists (ChromaDB requirement)
        if len(embeddings.shape) == 1:
            # Single embedding
            return [embeddings.tolist()]
        else:
            # Multiple embeddings
            return embeddings.tolist()
    
    def get_model_info(self) -> dict:
        """Get information about the current model"""
        return {
            "model_name": self.model_name,
            "is_loaded": self._model is not None,
            "cache_info": model_cache.get_cache_info()
        } 