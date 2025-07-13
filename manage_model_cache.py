#!/usr/bin/env python3
"""
Utility script to manage embedding model cache
"""
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vectorstore.model_cache import model_cache

def show_cache_info():
    """Display information about cached models"""
    info = model_cache.get_cache_info()
    
    print("📊 Model Cache Information")
    print("=" * 50)
    print(f"Cache Directory: {info['cache_dir']}")
    print(f"Total Models: {info['model_count']}")
    print(f"Total Size: {info['total_size_mb']:.2f} MB")
    print()
    
    if info['models']:
        print("Cached Models:")
        print("-" * 30)
        for model in info['models']:
            print(f"  📦 {model['name']}")
            print(f"     Size: {model['size_mb']:.2f} MB")
            print(f"     Path: {model['path']}")
            print()
    else:
        print("No models cached yet.")

def preload_models():
    """Pre-download and cache the models used by the application"""
    models_to_cache = [
        "mohamed2811/Muffakir_Embedding_V2",  # Arabic model used in main ChromaDB
        "all-MiniLM-L6-v2"  # Lightweight model used in ChromaDB Lite
    ]
    
    print("🚀 Pre-loading embedding models...")
    print("=" * 50)
    
    for model_name in models_to_cache:
        try:
            print(f"\n📥 Loading model: {model_name}")
            model = model_cache.load_model(model_name)
            print(f"✅ Successfully loaded: {model_name}")
        except Exception as e:
            print(f"❌ Error loading {model_name}: {str(e)}")
    
    print("\n🎉 Model pre-loading completed!")
    show_cache_info()

def clear_cache(model_name=None):
    """Clear model cache"""
    if model_name:
        print(f"🗑️ Clearing cache for model: {model_name}")
        model_cache.clear_cache(model_name)
    else:
        print("🗑️ Clearing all model cache...")
        model_cache.clear_cache()
    
    print("✅ Cache cleared successfully!")

def test_models():
    """Test loading and using cached models"""
    print("🧪 Testing cached models...")
    print("=" * 50)
    
    test_texts = [
        "السلام عليكم",
        "Hello world",
        "مرحبا"
    ]
    
    models_to_test = [
        "mohamed2811/Muffakir_Embedding_V2",
        "all-MiniLM-L6-v2"
    ]
    
    for model_name in models_to_test:
        try:
            print(f"\n🔄 Testing model: {model_name}")
            model = model_cache.load_model(model_name)
            
            # Test encoding
            embeddings = model.encode(test_texts)
            print(f"✅ Generated embeddings: {len(embeddings)} x {len(embeddings[0])}")
            
        except Exception as e:
            print(f"❌ Error testing {model_name}: {str(e)}")

def main():
    """Main function with command line interface"""
    if len(sys.argv) < 2:
        print("📋 Model Cache Manager")
        print("=" * 30)
        print("Usage:")
        print("  python manage_model_cache.py <command>")
        print()
        print("Commands:")
        print("  info      - Show cache information")
        print("  preload   - Pre-download all models")
        print("  clear     - Clear all cached models")
        print("  clear <model> - Clear specific model")
        print("  test      - Test cached models")
        return
    
    command = sys.argv[1].lower()
    
    if command == "info":
        show_cache_info()
    
    elif command == "preload":
        preload_models()
    
    elif command == "clear":
        if len(sys.argv) > 2:
            model_name = sys.argv[2]
            clear_cache(model_name)
        else:
            clear_cache()
    
    elif command == "test":
        test_models()
    
    else:
        print(f"❌ Unknown command: {command}")
        print("Use 'python manage_model_cache.py' to see available commands")

if __name__ == "__main__":
    main() 