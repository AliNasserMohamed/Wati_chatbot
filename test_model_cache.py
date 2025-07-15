#!/usr/bin/env python3
"""
Test Model Cache Functionality
Tests the model caching system and vector database integration
"""

import os
import sys
import time
from typing import Dict, Any

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_model_cache():
    """Test the model caching system"""
    print("🔧 Testing Model Cache System")
    print("=" * 50)
    
    try:
        from vectorstore.model_cache import model_cache
        
        # Test cache info
        print("📊 Cache Information:")
        cache_info = model_cache.get_cache_info()
        print(f"   Cache directory: {cache_info['cache_dir']}")
        print(f"   Cached models: {cache_info['model_count']}")
        print(f"   Total size: {cache_info['total_size_mb']:.2f} MB")
        
        if cache_info['models']:
            print("   Models in cache:")
            for model in cache_info['models']:
                print(f"      - {model['name']}: {model['size_mb']:.2f} MB")
        
        # Test model loading
        print("\n🔄 Testing Model Loading...")
        model_name = "all-MiniLM-L6-v2"
        
        start_time = time.time()
        model = model_cache.load_model(model_name)
        load_time = time.time() - start_time
        
        print(f"   ✅ Model loaded in {load_time:.2f} seconds")
        print(f"   📏 Model type: {type(model)}")
        
        # Test encoding
        print("\n🧪 Testing Encoding...")
        test_texts = ["Hello world", "مرحبا بكم", "Welcome to Abar"]
        
        start_time = time.time()
        embeddings = model.encode(test_texts)
        encoding_time = time.time() - start_time
        
        print(f"   ✅ Encoded {len(test_texts)} texts in {encoding_time:.4f} seconds")
        print(f"   📊 Embedding shape: {embeddings.shape}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing model cache: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_chroma_manager():
    """Test the ChromaManager functionality"""
    print("\n🗄️ Testing ChromaManager")
    print("=" * 50)
    
    try:
        from vectorstore.chroma_db import chroma_manager
        
        # Test database stats
        print("📊 Database Statistics:")
        stats = chroma_manager.get_stats()
        print(f"   Total documents: {stats['total_documents']}")
        print(f"   Questions: {stats['questions']}")
        print(f"   Answers: {stats['answers']}")
        print(f"   Q&A pairs: {stats['qa_pairs']}")
        
        # Test search functionality
        print("\n🔍 Testing Search Functionality...")
        test_queries = ["مرحبا", "السلام عليكم", "شكرا"]
        
        for query in test_queries:
            print(f"\n   🧪 Query: {query}")
            start_time = time.time()
            results = chroma_manager.search_sync(query, n_results=2)
            search_time = time.time() - start_time
            
            print(f"      ⏱️  Search time: {search_time:.4f} seconds")
            print(f"      📊 Results found: {len(results)}")
            
            for i, result in enumerate(results[:2]):
                print(f"         {i+1}. Document: {result['document'][:50]}...")
                print(f"            Similarity: {result.get('similarity', 'N/A'):.4f}")
                print(f"            Distance: {result.get('distance', 'N/A'):.4f}")
        
        # Test duplicate checking
        print("\n🔍 Testing Duplicate Checking...")
        test_question = "مرحبا"
        duplicate = chroma_manager.check_duplicate_question_sync(test_question)
        
        if duplicate:
            print(f"   ✅ Duplicate found for '{test_question}'")
            print(f"      Existing: {duplicate['document'][:50]}...")
            print(f"      Similarity: {duplicate.get('similarity', 'N/A'):.4f}")
        else:
            print(f"   ❌ No duplicate found for '{test_question}'")
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing ChromaManager: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_csv_integration():
    """Test CSV integration"""
    print("\n📄 Testing CSV Integration")
    print("=" * 50)
    
    try:
        from utils.csv_manager import csv_manager
        
        # Test CSV reading
        print("📖 Testing CSV Reading...")
        qa_pairs = csv_manager.read_qa_pairs()
        
        if qa_pairs:
            print(f"   ✅ Read {len(qa_pairs)} Q&A pairs from CSV")
            print(f"   📊 Sample pair:")
            sample = qa_pairs[0]
            print(f"      Question: {sample['question'][:50]}...")
            print(f"      Answer: {sample['answer'][:50]}...")
            print(f"      Category: {sample.get('category', 'N/A')}")
            print(f"      Language: {sample.get('language', 'N/A')}")
        else:
            print("   ❌ No Q&A pairs found in CSV")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing CSV integration: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main test function"""
    print("🧪 ABAR CHATBOT - MODEL CACHE & CHROMA TESTING")
    print("=" * 60)
    print()
    
    results = []
    
    # Test model cache
    results.append(test_model_cache())
    
    # Test ChromaManager
    results.append(test_chroma_manager())
    
    # Test CSV integration
    results.append(test_csv_integration())
    
    # Summary
    print("\n🎯 TEST SUMMARY")
    print("=" * 60)
    
    tests = ["Model Cache", "ChromaManager", "CSV Integration"]
    
    for i, (test_name, result) in enumerate(zip(tests, results)):
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {i+1}. {test_name}: {status}")
    
    passed = sum(results)
    total = len(results)
    
    print(f"\n📊 Overall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! System is working correctly.")
    else:
        print("⚠️  Some tests failed. Please check the errors above.")

if __name__ == "__main__":
    main() 