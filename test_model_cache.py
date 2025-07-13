#!/usr/bin/env python3
"""
Test script to demonstrate model caching functionality
"""
import sys
import os
import time

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vectorstore.model_cache import model_cache
from vectorstore.cached_embedding_function import CachedSentenceTransformerEmbeddingFunction

def test_model_caching():
    """Test the model caching functionality"""
    print("🧪 Testing Model Caching Functionality")
    print("=" * 60)
    
    # Test model name
    model_name = "all-MiniLM-L6-v2"  # Using lightweight model for testing
    
    print(f"📊 Initial cache info:")
    initial_info = model_cache.get_cache_info()
    print(f"   Models cached: {initial_info['model_count']}")
    print(f"   Total size: {initial_info['total_size_mb']:.2f} MB")
    print()
    
    # Test 1: First load (should download)
    print(f"🔄 Test 1: First load of {model_name}")
    start_time = time.time()
    
    embedding_func = CachedSentenceTransformerEmbeddingFunction(model_name)
    test_texts = ["Hello world", "السلام عليكم", "مرحبا"]
    embeddings1 = embedding_func(test_texts)
    
    first_load_time = time.time() - start_time
    print(f"✅ First load completed in {first_load_time:.2f} seconds")
    print(f"   Generated {len(embeddings1)} embeddings of size {len(embeddings1[0])}")
    print()
    
    # Test 2: Second load (should use cache)
    print(f"🔄 Test 2: Second load of {model_name} (should be faster)")
    start_time = time.time()
    
    embedding_func2 = CachedSentenceTransformerEmbeddingFunction(model_name)
    embeddings2 = embedding_func2(test_texts)
    
    second_load_time = time.time() - start_time
    print(f"✅ Second load completed in {second_load_time:.2f} seconds")
    print(f"   Generated {len(embeddings2)} embeddings of size {len(embeddings2[0])}")
    print()
    
    # Compare performance
    speedup = first_load_time / second_load_time if second_load_time > 0 else "N/A"
    print(f"⚡ Performance comparison:")
    print(f"   First load:  {first_load_time:.2f} seconds")
    print(f"   Second load: {second_load_time:.2f} seconds")
    print(f"   Speedup:     {speedup:.2f}x faster" if isinstance(speedup, float) else f"   Speedup:     {speedup}")
    print()
    
    # Test 3: Verify embeddings are identical
    print(f"🔍 Test 3: Verifying embedding consistency")
    import numpy as np
    
    embeddings1_array = np.array(embeddings1)
    embeddings2_array = np.array(embeddings2)
    
    if np.allclose(embeddings1_array, embeddings2_array):
        print("✅ Embeddings are identical - caching is working correctly!")
    else:
        print("❌ Embeddings differ - there may be an issue with caching")
    print()
    
    # Final cache info
    print(f"📊 Final cache info:")
    final_info = model_cache.get_cache_info()
    print(f"   Models cached: {final_info['model_count']}")
    print(f"   Total size: {final_info['total_size_mb']:.2f} MB")
    
    if final_info['models']:
        print("   Cached models:")
        for model in final_info['models']:
            print(f"     - {model['name']}: {model['size_mb']:.2f} MB")
    print()
    
    print("🎉 Model caching test completed!")

def test_with_chroma_manager():
    """Test caching with ChromaManager"""
    print("\n🔧 Testing with ChromaManager")
    print("=" * 40)
    
    try:
        from vectorstore.chroma_db_lite import ChromaManagerLite
        
        print("🔄 Initializing ChromaManagerLite (should use cached model)...")
        start_time = time.time()
        
        chroma_lite = ChromaManagerLite()
        
        init_time = time.time() - start_time
        print(f"✅ ChromaManagerLite initialized in {init_time:.2f} seconds")
        
        # Test search functionality
        print("🔍 Testing search functionality...")
        test_query = "Hello world"
        
        # Add some test data first
        test_questions = ["Hello", "Hi there", "Good morning"]
        test_answers = ["Hello! How can I help?", "Hi! What do you need?", "Good morning! How are you?"]
        
        chroma_lite.add_knowledge(test_questions, test_answers)
        
        # Perform search
        results = chroma_lite.search(test_query, n_results=2)
        print(f"✅ Search returned {len(results)} results")
        
        for i, result in enumerate(results, 1):
            print(f"   {i}. {result['document'][:50]}... (similarity: {result['similarity']:.3f})")
        
    except Exception as e:
        print(f"❌ Error testing with ChromaManager: {str(e)}")

if __name__ == "__main__":
    test_model_caching()
    test_with_chroma_manager() 