#!/usr/bin/env python3
"""
Test script to verify vector database improvements
Tests duplicate checking, population, and Q&A addition functionality
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from vectorstore.chroma_db import chroma_manager
from utils.knowledge_manager import knowledge_manager

def test_duplicate_checking():
    """Test the duplicate checking functionality"""
    print("🧪 Testing duplicate checking functionality...")
    
    # Test question
    test_question = "ما هو تطبيق ابار؟"
    
    # First, populate some default knowledge
    print("\n📚 Populating default knowledge...")
    result = chroma_manager.populate_default_knowledge()
    print(f"   Added: {result['added_count']}, Skipped: {result['skipped_count']}")
    
    # Test duplicate detection
    print(f"\n🔍 Checking for duplicate: '{test_question}'")
    duplicate = chroma_manager.check_duplicate_question(test_question)
    
    if duplicate:
        print(f"✅ Duplicate detection working! Found:")
        print(f"   Similarity: {duplicate.get('cosine_similarity', 0):.3f}")
        print(f"   Existing: {duplicate['document'][:80]}...")
    else:
        print("❌ No duplicate found (unexpected)")
    
    # Test with a new question
    new_question = "هل يمكنني طلب المياه في منتصف الليل؟"
    print(f"\n🔍 Checking new question: '{new_question}'")
    duplicate = chroma_manager.check_duplicate_question(new_question)
    
    if duplicate:
        print(f"⚠️ Unexpected duplicate found for new question")
    else:
        print("✅ No duplicate found for new question (expected)")

def test_knowledge_manager():
    """Test the improved knowledge manager"""
    print("\n🧪 Testing KnowledgeManager functionality...")
    
    # Test adding a new Q&A pair
    test_question = "كيف يمكنني الغاء اشتراكي؟"
    test_answer = "يمكنك إلغاء اشتراكك من خلال التطبيق أو التواصل مع خدمة العملاء."
    
    print(f"\n➕ Adding new Q&A: '{test_question[:50]}...'")
    result = knowledge_manager.add_qa_pair(test_question, test_answer)
    
    if result["success"]:
        print(f"✅ Q&A added successfully! ID: {result['id']}")
    else:
        print(f"❌ Failed to add Q&A: {result['error']}")
    
    # Test adding a duplicate
    print(f"\n➕ Attempting to add duplicate...")
    duplicate_result = knowledge_manager.add_qa_pair(test_question, test_answer)
    
    if not duplicate_result["success"] and "duplicate" in duplicate_result.get("error", "").lower():
        print("✅ Duplicate detection working in KnowledgeManager!")
    else:
        print("❌ Duplicate detection not working properly")

def test_population():
    """Test the population functionality"""
    print("\n🧪 Testing population functionality...")
    
    # Get initial stats
    initial_stats = chroma_manager.get_stats()
    print(f"Initial stats: {initial_stats}")
    
    # Test Abar knowledge population
    print("\n📚 Testing Abar knowledge population...")
    result = knowledge_manager.populate_abar_knowledge()
    
    if result["success"]:
        print(f"✅ Population successful!")
        print(f"   Added: {result['added_count']} Q&A pairs")
        print(f"   Skipped: {result['skipped_count']} duplicates")
    else:
        print(f"❌ Population failed: {result['error']}")
    
    # Get final stats
    final_stats = chroma_manager.get_stats()
    print(f"Final stats: {final_stats}")

def test_search():
    """Test search functionality"""
    print("\n🧪 Testing search functionality...")
    
    test_queries = [
        "ما هو ابار",
        "التوصيل مجاني",
        "كيف اطلب المياه",
        "خدمة العملاء"
    ]
    
    for query in test_queries:
        print(f"\n🔍 Searching: '{query}'")
        results = chroma_manager.search(query, n_results=2)
        
        if results:
            for i, result in enumerate(results, 1):
                similarity = result.get('cosine_similarity', 0)
                doc_preview = result['document'][:60] + "..." if len(result['document']) > 60 else result['document']
                print(f"   {i}. Similarity: {similarity:.3f} - {doc_preview}")
        else:
            print("   No results found")

def main():
    """Run all tests"""
    print("🚀 Vector Database Improvements Test Suite")
    print("=" * 60)
    
    try:
        test_duplicate_checking()
        test_knowledge_manager()
        test_population()
        test_search()
        
        print("\n" + "=" * 60)
        print("✅ All tests completed!")
        
        # Final summary
        stats = chroma_manager.get_stats()
        print(f"\n📊 Final Knowledge Base Stats:")
        print(f"   Total documents: {stats['total_documents']}")
        print(f"   Questions: {stats['questions']}")
        print(f"   Answers: {stats['answers']}")
        print(f"   Q&A pairs: {stats['qa_pairs']}")
        
    except Exception as e:
        print(f"❌ Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 