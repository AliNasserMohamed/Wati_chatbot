#!/usr/bin/env python3
"""
Performance test for the full chroma_db.py with lightweight embedding model
"""
import sys
import os
import asyncio
import time

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.csv_manager import csv_manager

async def test_full_version_performance():
    """
    Test the performance of the full chroma_db.py with lightweight model
    """
    print("🚀 Testing Full ChromaDB Performance with Lightweight Model")
    print("=" * 70)
    
    try:
        # Import the full version (now with lightweight model)
        from vectorstore.chroma_db import chroma_manager
        
        # Step 1: Initialization time
        print("\n⏱️  Step 1: Measuring initialization time...")
        init_start = time.time()
        
        # The import already initializes it, so we just measure access time
        collection = chroma_manager.get_collection_safe()
        
        init_time = time.time() - init_start
        print(f"   ✅ Initialization: {init_time:.3f} seconds")
        
        # Step 2: Read CSV data
        print("\n📖 Step 2: Reading CSV data...")
        csv_start = time.time()
        
        qa_pairs = csv_manager.read_qa_pairs()
        if not qa_pairs:
            print("❌ No Q&A pairs found in CSV file")
            return False
            
        csv_time = time.time() - csv_start
        print(f"   ✅ Read {len(qa_pairs)} Q&A pairs: {csv_time:.3f} seconds")
        
        # Step 3: Clear existing data
        print("\n🗑️  Step 3: Clearing existing data...")
        clear_start = time.time()
        
        try:
            # Clear the collection
            collection.delete()
            print("   ✅ Cleared existing data")
        except Exception as e:
            print(f"   ⚠️  Could not clear: {str(e)}")
        
        clear_time = time.time() - clear_start
        print(f"   ⏱️  Clear time: {clear_time:.3f} seconds")
        
        # Step 4: Prepare data
        print("\n📋 Step 4: Preparing data...")
        prep_start = time.time()
        
        questions = []
        answers = []
        metadatas = []
        
        for pair in qa_pairs:
            questions.append(pair['question'])
            answers.append(pair['answer'])
            
            metadata = {
                "source": pair.get('source', 'csv'),
                "category": pair.get('category', 'general'),
                "language": pair.get('language', 'ar'),
                "priority": pair.get('priority', 'normal')
            }
            
            if pair.get('metadata'):
                metadata.update(pair['metadata'])
            
            metadatas.append(metadata)
        
        prep_time = time.time() - prep_start
        print(f"   ✅ Prepared {len(questions)} Q&A pairs: {prep_time:.3f} seconds")
        
        # Step 5: Add data to vector database (the main test)
        print("\n🔄 Step 5: Adding data to vector database...")
        add_start = time.time()
        
        # Use the full version's add_knowledge method with all features
        result = await chroma_manager.add_knowledge(
            questions, 
            answers, 
            metadatas, 
            check_duplicates=True  # Test with duplicate checking
        )
        
        add_time = time.time() - add_start
        print(f"   ✅ Added to vector database: {add_time:.3f} seconds")
        print(f"      📊 Added: {result['added_count']} Q&A pairs")
        print(f"      📊 Skipped: {result['skipped_count']} duplicates")
        
        # Step 6: Test search performance
        print("\n🔍 Step 6: Testing search performance...")
        
        test_queries = [
            "السلام عليكم",
            "مرحبا", 
            "Hello",
            "ما هو تطبيق ابار؟",
            "هل التوصيل مجاني؟"
        ]
        
        total_search_time = 0
        
        for i, query in enumerate(test_queries, 1):
            search_start = time.time()
            
            search_results = await chroma_manager.search(query, n_results=2)
            
            search_time = time.time() - search_start
            total_search_time += search_time
            
            print(f"   {i}. Query '{query}': {search_time:.3f}s - Found {len(search_results)} results")
        
        avg_search_time = total_search_time / len(test_queries)
        print(f"   📊 Average search time: {avg_search_time:.3f} seconds")
        
        # Step 7: Test duplicate checking performance
        print("\n🔍 Step 7: Testing duplicate checking...")
        dup_start = time.time()
        
        duplicate_check = await chroma_manager.check_duplicate_question("مرحبا", 0.85)
        
        dup_time = time.time() - dup_start
        print(f"   ✅ Duplicate check: {dup_time:.3f} seconds")
        
        if duplicate_check:
            print(f"      Found duplicate with similarity: {duplicate_check.get('similarity', 'N/A')}")
        else:
            print("      No duplicates found")
        
        # Step 8: Get stats
        print("\n📊 Step 8: Getting database stats...")
        stats_start = time.time()
        
        stats = chroma_manager.get_stats()
        
        stats_time = time.time() - stats_start
        print(f"   ✅ Stats retrieved: {stats_time:.3f} seconds")
        print(f"      Total documents: {stats['total_documents']}")
        print(f"      Q&A pairs: {stats['qa_pairs']}")
        
        # Summary
        total_time = time.time() - init_start
        print(f"\n🎉 Performance Test Complete!")
        print("=" * 70)
        print(f"📊 PERFORMANCE SUMMARY:")
        print(f"   🔧 Initialization:        {init_time:.3f}s")
        print(f"   📖 CSV Reading:          {csv_time:.3f}s") 
        print(f"   📋 Data Preparation:     {prep_time:.3f}s")
        print(f"   🔄 Vector DB Population: {add_time:.3f}s")
        print(f"   🔍 Average Search:       {avg_search_time:.3f}s")
        print(f"   🔍 Duplicate Check:      {dup_time:.3f}s")
        print(f"   📊 Stats Retrieval:      {stats_time:.3f}s")
        print(f"   ⏱️  TOTAL TIME:          {total_time:.3f}s")
        print("=" * 70)
        
        # Performance rating
        if add_time < 10:
            print("🟢 EXCELLENT: Very fast performance!")
        elif add_time < 30:
            print("🟡 GOOD: Acceptable performance")
        elif add_time < 60:
            print("🟠 MODERATE: Could be improved")
        else:
            print("🔴 SLOW: Consider optimization")
        
        return True
        
    except Exception as e:
        print(f"❌ Critical error during test: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🤖 Abar Chatbot - Full ChromaDB Performance Test")
    print("Testing the full-featured ChromaDB with lightweight embedding model")
    print("This will measure initialization, population, and search performance...")
    print()
    
    try:
        success = asyncio.run(test_full_version_performance())
        
        if success:
            print("\n✅ Performance test completed successfully!")
            print("💡 The full ChromaDB with lightweight model is ready for production!")
        else:
            print("\n❌ Performance test failed!")
            
    except KeyboardInterrupt:
        print("\n❌ Test cancelled by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {str(e)}") 