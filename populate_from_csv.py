#!/usr/bin/env python3
"""
Efficient script to populate vector database from Excel with progress tracking
"""
import sys
import os
import time
from datetime import datetime

# Add the parent directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.excel_manager import csv_manager
from vectorstore.chroma_db import chroma_manager

def populate_vector_db_from_excel():
    """
    Populate vector database from Excel file with progress tracking (SYNC VERSION for speed)
    """
    print("🚀 Populating Vector Database from Excel")
    print("=" * 60)
    
    try:
        # Step 1: Read Excel data
        print("\n📖 Step 1: Reading Excel data...")
        start_time = time.time()
        
        qa_pairs = csv_manager.read_qa_pairs()
        if not qa_pairs:
            print("❌ No Q&A pairs found in Excel file")
            return False
        
        read_time = time.time() - start_time
        print(f"   ✅ Successfully read {len(qa_pairs)} Q&A pairs from Excel ({read_time:.2f}s)")

        # Step 2: Prepare data for ChromaDB
        print("\n📋 Step 2: Preparing data for ChromaDB...")
        start_time = time.time()
        
        questions = []
        answers = []
        metadatas = []
        
        for i, pair in enumerate(qa_pairs):
            question = pair.get('question', '').strip()
            answer = pair.get('answer', '').strip()
            
            if not question or not answer:
                print(f"   ⚠️  Skipping empty Q&A pair at index {i}")
                continue
            
            # Prepare metadata (same for both question and answer)
            metadata = {
                "category": pair.get('category', 'general'),
                "language": pair.get('language', 'ar'),
                "source": pair.get('source', 'excel'),
                "priority": pair.get('priority', 'normal'),
            }
            
            # Add any additional metadata
            if pair.get('metadata') and isinstance(pair['metadata'], dict):
                metadata.update(pair['metadata'])
            
            questions.append(question)
            answers.append(answer)
            metadatas.append(metadata)
        
        prep_time = time.time() - start_time
        print(f"   ✅ Prepared {len(questions)} Q&A pairs for vector database ({prep_time:.2f}s)")
        
        # Step 3: Check for existing data and clear if necessary
        print("\n🔍 Step 3: Checking existing data...")
        start_time = time.time()
        
        existing_stats = chroma_manager.get_stats()
        if existing_stats['total_documents'] > 0:
            print(f"   ⚠️  Found {existing_stats['total_documents']} existing documents")
            print("   🧹 Clearing existing data to avoid duplicates...")
            
            # Get all existing IDs and delete them
            all_data = chroma_manager.collection.get()
            if all_data and all_data.get("ids"):
                chroma_manager.collection.delete(ids=all_data["ids"])
                print(f"   ✅ Cleared {len(all_data['ids'])} existing documents")
        
        check_time = time.time() - start_time
        print(f"   ✅ Database ready for new data ({check_time:.2f}s)")
        
        # Step 4: Add to vector database using proper method
        print("\n💾 Step 4: Adding to vector database...")
        start_time = time.time()
        
        # Use the proper add_knowledge_sync method that adds both questions and answers
        result = chroma_manager.add_knowledge_sync(
            questions=questions,
            answers=answers,
            metadatas=metadatas,
            check_duplicates=True  # Enable duplicate checking for this script
        )
        
        add_time = time.time() - start_time
        print(f"   ✅ Added {result['added_count']} Q&A pairs to vector database ({add_time:.2f}s)")
        if result['skipped_count'] > 0:
            print(f"   ⚠️  Skipped {result['skipped_count']} duplicates")
        
        # Step 5: Verify the addition
        print("\n✅ Step 5: Verifying addition...")
        start_time = time.time()
        
        final_stats = chroma_manager.get_stats()
        verify_time = time.time() - start_time
        
        print(f"   📊 Final database stats:")
        print(f"      Total documents: {final_stats['total_documents']}")
        print(f"      Questions: {final_stats['questions']}")
        print(f"      Answers: {final_stats['answers']}")
        print(f"      Q&A pairs: {final_stats['qa_pairs']}")
        print(f"      Arabic documents: {final_stats['arabic_documents']}")
        print(f"   ✅ Verification completed ({verify_time:.2f}s)")
        
        # Print performance summary
        total_time = read_time + prep_time + check_time + add_time + verify_time
        print(f"\n🎉 SUCCESS! Vector database populated in {total_time:.2f}s")
        print(f"   📖 Read: {read_time:.2f}s")
        print(f"   📋 Prep: {prep_time:.2f}s")
        print(f"   🔍 Check: {check_time:.2f}s")
        print(f"   💾 Add: {add_time:.2f}s")
        print(f"   ✅ Verify: {verify_time:.2f}s")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🤖 Abar Chatbot - Vector Database Population from Excel")
    print("This version includes progress tracking and duplicate checking")
    print("=" * 60)
    
    # Show current database state
    try:
        current_stats = chroma_manager.get_stats()
        print(f"\n📊 Current database state:")
        print(f"   Total documents: {current_stats['total_documents']}")
        print(f"   Questions: {current_stats['questions']}")
        print(f"   Answers: {current_stats['answers']}")
        print(f"   Q&A pairs: {current_stats['qa_pairs']}")
        
        if current_stats['total_documents'] > 0:
            print(f"\n⚠️  Warning: This will replace {current_stats['total_documents']} existing documents")
        
    except Exception as e:
        print(f"⚠️  Could not get current stats: {str(e)}")
    
    # Run the population
    print("\n🚀 Starting population process...")
    success = populate_vector_db_from_excel()
    
    if success:
        print("\n✅ SUCCESS: Vector database has been populated with Excel data!")
        print("💡 You can now run your chatbot and it will use the Q&A pairs from Excel")
        print("🔄 To add new Q&A pairs, edit the Excel file and run this script again")
    else:
        print("\n❌ FAILED: Could not populate vector database")
        print("🔧 Check the error messages above and try again") 