#!/usr/bin/env python3
"""
Test script for the new CSV-based knowledge management system
"""
import sys
import os
import asyncio

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.csv_manager import csv_manager
from utils.knowledge_manager import knowledge_manager
from vectorstore.chroma_db import chroma_manager

async def test_csv_system():
    """
    Test the CSV-based knowledge management system
    """
    print("🧪 Testing CSV-based Knowledge Management System")
    print("=" * 60)
    
    # Test 1: Read Q&A pairs from CSV
    print("\n1. Testing CSV reading...")
    qa_pairs = csv_manager.read_qa_pairs()
    print(f"   ✅ Successfully read {len(qa_pairs)} Q&A pairs from CSV")
    
    # Show first few pairs
    if qa_pairs:
        print("   📋 First few Q&A pairs:")
        for i, pair in enumerate(qa_pairs[:3]):
            print(f"      {i+1}. Q: {pair['question'][:50]}...")
            print(f"         A: {pair['answer'][:50]}...")
            print(f"         Category: {pair['category']}, Language: {pair['language']}")
    
    # Test 2: Get CSV statistics
    print("\n2. Testing CSV statistics...")
    stats = csv_manager.get_stats()
    print(f"   ✅ CSV Statistics:")
    print(f"      Total pairs: {stats['total']}")
    print(f"      Categories: {stats['categories']}")
    print(f"      Languages: {stats['languages']}")
    print(f"      Sources: {stats['sources']}")
    
    # Test 3: Test adding a new Q&A pair
    print("\n3. Testing adding new Q&A pair...")
    test_question = "هل يمكنني إلغاء الطلب؟"
    test_answer = "نعم، يمكنك إلغاء الطلب قبل وصول المندوب بـ 10 دقائق."
    
    add_success = csv_manager.add_qa_pair(
        question=test_question,
        answer=test_answer,
        category="support",
        language="ar",
        source="test",
        priority="normal",
        metadata={"test": True}
    )
    
    if add_success:
        print("   ✅ Successfully added test Q&A pair to CSV")
        
        # Verify it was added
        updated_pairs = csv_manager.read_qa_pairs()
        print(f"   ✅ CSV now contains {len(updated_pairs)} Q&A pairs")
        
        # Find the added pair
        added_pair = None
        for pair in updated_pairs:
            if pair['question'] == test_question:
                added_pair = pair
                break
        
        if added_pair:
            print(f"   ✅ Found added pair: {added_pair['question']}")
            print(f"      Answer: {added_pair['answer']}")
            print(f"      Metadata: {added_pair['metadata']}")
    else:
        print("   ❌ Failed to add test Q&A pair")
    
    # Test 4: Test populating vector database from CSV
    print("\n4. Testing vector database population from CSV...")
    try:
        result = await knowledge_manager.populate_abar_knowledge()
        if result["success"]:
            print(f"   ✅ Successfully populated vector database from CSV")
            print(f"      Added: {result['added_count']} Q&A pairs")
            print(f"      Skipped: {result['skipped_count']} duplicates")
        else:
            print(f"   ❌ Failed to populate vector database: {result['error']}")
    except Exception as e:
        print(f"   ❌ Error populating vector database: {str(e)}")
    
    # Test 5: Test searching in vector database
    print("\n5. Testing vector database search...")
    try:
        search_results = await chroma_manager.search("مرحبا", n_results=3)
        print(f"   ✅ Search returned {len(search_results)} results")
        
        if search_results:
            print("   📋 Search results:")
            for i, result in enumerate(search_results[:2]):
                print(f"      {i+1}. Document: {result['document'][:50]}...")
                print(f"         Similarity: {result.get('cosine_similarity', 'N/A')}")
                print(f"         Metadata: {result.get('metadata', {})}")
    except Exception as e:
        print(f"   ❌ Search error: {str(e)}")
    
    # Test 6: Test CSV search functionality
    print("\n6. Testing CSV search functionality...")
    search_results = csv_manager.search_qa_pairs("مرحبا")
    print(f"   ✅ CSV search returned {len(search_results)} results")
    
    if search_results:
        print("   📋 CSV search results:")
        for i, result in enumerate(search_results[:2]):
            print(f"      {i+1}. Q: {result['question']}")
            print(f"         A: {result['answer']}")
            print(f"         Category: {result['category']}")
    
    # Test 7: Test backup functionality
    print("\n7. Testing CSV backup functionality...")
    backup_path = csv_manager.backup_csv("test_backup")
    if backup_path:
        print(f"   ✅ Created backup at: {backup_path}")
        
        # Clean up backup
        try:
            os.remove(backup_path)
            print("   ✅ Cleaned up test backup")
        except:
            print("   ⚠️  Could not clean up backup file")
    else:
        print("   ❌ Failed to create backup")
    
    print("\n🎉 CSV System Test Complete!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_csv_system()) 