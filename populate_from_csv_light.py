#!/usr/bin/env python3
"""
SUPER FAST script to populate vector database from Excel using lightweight embeddings
"""
import sys
import os
import time
from typing import List, Dict, Any

# Add the parent directory to the Python path  
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.excel_manager import csv_manager

def populate_vector_db_from_excel_light():
    """
    FAST populate vector database from Excel using lightweight embeddings
    """
    print("🚀 FAST Populating Vector Database from Excel (Lightweight Mode)")
    print("=" * 70)
    
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
            
            # Skip only if question is empty (questions without answers should be embedded)
            if not question:
                print(f"   ⚠️  Skipping empty question at index {i}")
                continue
            
            # Allow questions without answers - embed them with empty answer
            if not answer:
                print(f"   ℹ️  Question without answer at index {i}: '{question[:50]}...' - will embed with empty answer")
                answer = ""  # Explicitly set to empty string for embedding
            
            # Prepare metadata (same for both question and answer)
            metadata = {
                "category": pair.get('category', 'general'),
                "language": pair.get('language', 'ar'),
                "source": pair.get('source', 'excel'),
                "priority": pair.get('priority', 'normal'),
                "has_answer": bool(answer),  # Track if the original had an answer
            }
            
            # Add any additional metadata
            if pair.get('metadata') and isinstance(pair['metadata'], dict):
                metadata.update(pair['metadata'])
            
            questions.append(question)
            answers.append(answer)
            metadatas.append(metadata)
        
        prep_time = time.time() - start_time
        print(f"   ✅ Prepared {len(questions)} Q&A pairs for ChromaDB ({prep_time:.2f}s)")
        
        # Step 3: Clear existing data
        print("\n🧹 Step 3: Clearing existing data...")
        start_time = time.time()
        
        from vectorstore.chroma_db import chroma_manager
        
        # Get existing stats
        existing_stats = chroma_manager.get_stats()
        if existing_stats['total_documents'] > 0:
            print(f"   ⚠️  Found {existing_stats['total_documents']} existing documents")
            
            # Clear existing data
            collection = chroma_manager.collection
            all_data = collection.get()
            if all_data and all_data.get("ids"):
                collection.delete(ids=all_data["ids"])
                print(f"   ✅ Cleared {len(all_data['ids'])} existing documents")
        
        clear_time = time.time() - start_time
        print(f"   ✅ Database cleared ({clear_time:.2f}s)")
        
        # Step 4: Add to ChromaDB using proper method (adds both questions and answers)
        print("\n💾 Step 4: Adding to ChromaDB (FAST mode)...")
        start_time = time.time()
        
        # Use the proper add_knowledge_sync method that adds both questions and answers
        result = chroma_manager.add_knowledge_sync(
            questions=questions,
            answers=answers,
            metadatas=metadatas,
            check_duplicates=False  # Skip duplicate checking for speed
        )
        
        add_time = time.time() - start_time
        print(f"   ✅ Added {len(questions)} Q&A pairs to ChromaDB ({add_time:.2f}s)")
        
        # Step 5: Verify the addition
        print("\n✅ Step 5: Verifying results...")
        start_time = time.time()
        
        final_stats = chroma_manager.get_stats()
        verify_time = time.time() - start_time
        
        print(f"   📊 Final database stats:")
        print(f"      Total documents: {final_stats['total_documents']}")
        print(f"      Questions: {final_stats['questions']}")
        print(f"      Answers: {final_stats['answers']}")
        print(f"      Q&A pairs: {final_stats['qa_pairs']}")
        print(f"   ✅ Verification completed ({verify_time:.2f}s)")
        
        # Print performance summary
        total_time = read_time + prep_time + clear_time + add_time + verify_time
        print(f"\n🎉 SUCCESS! Vector database populated in {total_time:.2f}s")
        print(f"   📖 Read: {read_time:.2f}s")
        print(f"   📋 Prep: {prep_time:.2f}s")
        print(f"   🧹 Clear: {clear_time:.2f}s")
        print(f"   💾 Add: {add_time:.2f}s")
        print(f"   ✅ Verify: {verify_time:.2f}s")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🤖 Abar Chatbot - FAST Vector Database Population from Excel")
    print("This is the LIGHTWEIGHT version for super fast population")
    print("=" * 70)
    
    # Show current database state
    try:
        from vectorstore.chroma_db import chroma_manager
        current_stats = chroma_manager.get_stats()
        print(f"\n📊 Current database state:")
        print(f"   Total documents: {current_stats['total_documents']}")
        print(f"\n🚀 Starting FAST population process...")
        
        success = populate_vector_db_from_excel_light()
        
        if success:
            print(f"\n✅ SUCCESS: Vector database has been populated with Excel data!")
            print(f"💡 You can now run your chatbot and it will use the Q&A pairs from Excel")
            print(f"🔄 To add new Q&A pairs, edit the Excel file and run this script again")
        else:
            print(f"\n❌ FAILED: Could not populate vector database")
            
    except Exception as e:
        print(f"❌ Script error: {str(e)}")
        import traceback
        traceback.print_exc() 