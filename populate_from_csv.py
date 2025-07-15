#!/usr/bin/env python3
"""
Efficient script to populate vector database from CSV with progress tracking
"""
import sys
import os
import time
from typing import List, Dict, Any

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.csv_manager import csv_manager
from vectorstore.chroma_db import chroma_manager

def populate_vector_db_from_csv():
    """
    Populate vector database from CSV file with progress tracking (SYNC VERSION for speed)
    """
    print("🚀 Populating Vector Database from CSV")
    print("=" * 60)
    
    try:
        # Step 1: Read CSV data
        print("\n📖 Step 1: Reading CSV data...")
        start_time = time.time()
        
        qa_pairs = csv_manager.read_qa_pairs()
        if not qa_pairs:
            print("❌ No Q&A pairs found in CSV file")
            return False
            
        read_time = time.time() - start_time
        print(f"   ✅ Successfully read {len(qa_pairs)} Q&A pairs from CSV ({read_time:.2f}s)")
        
        # Step 2: Prepare data for vector database
        print("\n📋 Step 2: Preparing data for vector database...")
        start_time = time.time()
        
        questions = []
        answers = []
        metadatas = []
        
        for i, pair in enumerate(qa_pairs):
            questions.append(pair['question'])
            answers.append(pair['answer'])
            
            # Build metadata
            metadata = {
                "source": pair.get('source', 'csv'),
                "category": pair.get('category', 'general'),
                "language": pair.get('language', 'ar'),
                "priority": pair.get('priority', 'normal')
            }
            
            # Add additional metadata if present
            if pair.get('metadata'):
                metadata.update(pair['metadata'])
            
            metadatas.append(metadata)
            
            # Show progress for large datasets
            if (i + 1) % 10 == 0:
                print(f"   📝 Processed {i + 1}/{len(qa_pairs)} pairs...")
        
        prep_time = time.time() - start_time
        print(f"   ✅ Prepared {len(questions)} Q&A pairs for embedding ({prep_time:.2f}s)")
        
        # Step 3: Clear existing vector database (optional)
        print("\n🗑️  Step 3: Clearing existing vector database...")
        try:
            # Get collection and delete if exists
            collection = chroma_manager.get_collection_safe()
            if collection:
                collection.delete()
                print("   ✅ Cleared existing vector database")
        except Exception as e:
            print(f"   ⚠️  Could not clear existing database: {str(e)}")
        
        # Step 4: Add data to vector database with progress tracking (FAST SYNC VERSION)
        print("\n🔄 Step 4: Adding data to vector database...")
        start_time = time.time()
        
        # Use larger batches for better performance
        batch_size = 20  # Process 20 Q&A pairs at a time for speed
        total_added = 0
        total_skipped = 0
        
        for i in range(0, len(questions), batch_size):
            batch_end = min(i + batch_size, len(questions))
            batch_questions = questions[i:batch_end]
            batch_answers = answers[i:batch_end]
            batch_metadatas = metadatas[i:batch_end]
            
            try:
                print(f"   🔄 Processing batch {i//batch_size + 1}/{(len(questions) + batch_size - 1)//batch_size} ({i+1}-{batch_end}/{len(questions)})...")
                
                # Add batch to vector database using FAST SYNC method
                result = chroma_manager.add_knowledge_sync(
                    batch_questions, 
                    batch_answers, 
                    batch_metadatas, 
                    check_duplicates=True
                )
                
                if isinstance(result, dict):
                    total_added += result["added_count"]
                    total_skipped += result["skipped_count"]
                    print(f"      ✅ Batch complete: {result['added_count']} added, {result['skipped_count']} skipped")
                else:
                    # Simple list of IDs returned
                    batch_added = len(result)
                    total_added += batch_added
                    print(f"      ✅ Batch complete: {batch_added} added")
                
            except Exception as e:
                print(f"      ❌ Batch failed: {str(e)}")
                continue
        
        embedding_time = time.time() - start_time
        print(f"\n   ✅ Vector database population completed ({embedding_time:.2f}s)")
        print(f"      📊 Total added: {total_added}")
        print(f"      📊 Total skipped: {total_skipped}")
        
        # Step 5: Verify the population
        print("\n🔍 Step 5: Verifying population...")
        try:
            stats = chroma_manager.get_stats()
            print(f"   ✅ Vector database stats:")
            print(f"      Total documents: {stats['total_documents']}")
            print(f"      Questions: {stats['questions']}")
            print(f"      Answers: {stats['answers']}")
            print(f"      Q&A pairs: {stats['qa_pairs']}")
        except Exception as e:
            print(f"   ❌ Could not get stats: {str(e)}")
        
        # Step 6: Test search functionality
        print("\n🔍 Step 6: Testing search functionality...")
        try:
            test_query = "مرحبا"
            search_results = chroma_manager.search_sync(test_query, n_results=2)
            
            if search_results:
                print(f"   ✅ Search test successful - found {len(search_results)} results for '{test_query}'")
                for i, result in enumerate(search_results[:2]):
                    similarity = result.get('similarity', 0)
                    print(f"      {i+1}. Document: {result['document'][:50]}...")
                    print(f"         Similarity: {similarity:.4f}")
            else:
                print(f"   ⚠️  Search test returned no results")
        except Exception as e:
            print(f"   ❌ Search test failed: {str(e)}")
        
        print("\n🎉 Vector Database Population Complete!")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"❌ Critical error during population: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main function"""
    print("🤖 Abar Chatbot - Vector Database Population from CSV")
    print("This script will populate the vector database with Q&A pairs from CSV file")
    print("The process may take a few minutes depending on the amount of data...")
    print()
    
    # Ask for confirmation
    try:
        response = input("Do you want to proceed? (y/n): ")
        if response.lower() not in ['y', 'yes']:
            print("❌ Operation cancelled by user")
            return
    except KeyboardInterrupt:
        print("\n❌ Operation cancelled by user")
        return
    
    success = populate_vector_db_from_csv()
    
    if success:
        print("\n✅ SUCCESS: Vector database has been populated with CSV data!")
        print("💡 You can now run your chatbot and it will use the Q&A pairs from CSV")
        print("🔄 To add new Q&A pairs, edit the CSV file and run this script again")
    else:
        print("\n❌ FAILED: Vector database population failed")
        print("🔧 Please check the error messages above and try again")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n❌ Operation cancelled by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc() 