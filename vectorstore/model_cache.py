import os
import logging
from sentence_transformers import SentenceTransformer
from typing import Optional

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ModelCache:
    """
    Manages caching of embedding models to avoid repeated downloads
    """
    
    def __init__(self, cache_dir: str = "models/cache"):
        """
        Initialize model cache
        
        Args:
            cache_dir: Directory to store cached models
        """
        self.cache_dir = os.path.abspath(cache_dir)
        self.ensure_cache_dir()
    
    def ensure_cache_dir(self):
        """Create cache directory if it doesn't exist"""
        os.makedirs(self.cache_dir, exist_ok=True)
        logger.info(f"📁 Model cache directory: {self.cache_dir}")
    
    def get_model_path(self, model_name: str) -> str:
        """
        Get the local path for a model
        
        Args:
            model_name: Name of the model (e.g., 'mohamed2811/Muffakir_Embedding_V2')
            
        Returns:
            Local path where model should be stored
        """
        # Replace slashes with underscores for safe file names
        safe_name = model_name.replace("/", "_").replace("\\", "_")
        return os.path.join(self.cache_dir, safe_name)
    
    def is_model_cached(self, model_name: str) -> bool:
        """
        Check if model is already cached locally
        
        Args:
            model_name: Name of the model
            
        Returns:
            True if model exists locally, False otherwise
        """
        model_path = self.get_model_path(model_name)
        
        # Check if model directory exists and has required files
        if os.path.exists(model_path):
            # Check for essential model files
            required_files = ['config.json', 'pytorch_model.bin']
            has_required = any(
                os.path.exists(os.path.join(model_path, f)) 
                for f in required_files
            )
            if has_required:
                logger.info(f"✅ Model {model_name} found in cache: {model_path}")
                return True
        
        logger.info(f"❌ Model {model_name} not found in cache")
        return False
    
    def download_and_cache_model(self, model_name: str) -> str:
        """
        Download model and cache it locally
        
        Args:
            model_name: Name of the model to download
            
        Returns:
            Local path of the cached model
        """
        model_path = self.get_model_path(model_name)
        
        try:
            logger.info(f"🔄 Downloading model {model_name}...")
            logger.info(f"📥 Saving to: {model_path}")
            
            # Download and save model
            model = SentenceTransformer(model_name, cache_folder=self.cache_dir)
            
            # Save to specific path
            model.save(model_path)
            
            logger.info(f"✅ Model {model_name} downloaded and cached successfully")
            return model_path
            
        except Exception as e:
            logger.error(f"❌ Error downloading model {model_name}: {str(e)}")
            raise
    
    def load_model(self, model_name: str) -> SentenceTransformer:
        """
        Load model from cache or download if not cached
        
        Args:
            model_name: Name of the model to load
            
        Returns:
            Loaded SentenceTransformer model
        """
        # Check if model is cached
        if self.is_model_cached(model_name):
            model_path = self.get_model_path(model_name)
            logger.info(f"📂 Loading cached model from: {model_path}")
            return SentenceTransformer(model_path)
        else:
            # Download and cache model
            logger.info(f"🔄 Model not cached, downloading: {model_name}")
            model_path = self.download_and_cache_model(model_name)
            return SentenceTransformer(model_path)
    
    def get_cache_info(self) -> dict:
        """
        Get information about cached models
        
        Returns:
            Dictionary with cache information
        """
        if not os.path.exists(self.cache_dir):
            return {"cache_dir": self.cache_dir, "models": [], "total_size": 0}
        
        models = []
        total_size = 0
        
        for item in os.listdir(self.cache_dir):
            item_path = os.path.join(self.cache_dir, item)
            if os.path.isdir(item_path):
                # Calculate directory size
                size = sum(
                    os.path.getsize(os.path.join(dirpath, filename))
                    for dirpath, dirnames, filenames in os.walk(item_path)
                    for filename in filenames
                )
                
                models.append({
                    "name": item.replace("_", "/"),  # Convert back to original name
                    "path": item_path,
                    "size_mb": round(size / (1024 * 1024), 2)
                })
                total_size += size
        
        return {
            "cache_dir": self.cache_dir,
            "models": models,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "model_count": len(models)
        }
    
    def clear_cache(self, model_name: Optional[str] = None):
        """
        Clear model cache
        
        Args:
            model_name: Specific model to clear, or None to clear all
        """
        if model_name:
            model_path = self.get_model_path(model_name)
            if os.path.exists(model_path):
                import shutil
                shutil.rmtree(model_path)
                logger.info(f"🗑️ Cleared cache for model: {model_name}")
            else:
                logger.info(f"ℹ️ Model {model_name} not found in cache")
        else:
            if os.path.exists(self.cache_dir):
                import shutil
                shutil.rmtree(self.cache_dir)
                self.ensure_cache_dir()
                logger.info(f"🗑️ Cleared all model cache")

# Create global model cache instance
model_cache = ModelCache() 