#!/usr/bin/env python3
"""
Script to clean/clear the vector database completely
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from vectorstore.chroma_db import chroma_manager

def clean_database():
    """Clean the entire vector database"""
    print("🧹 Cleaning Vector Database...")
    print("=" * 50)
    
    try:
        # Get current stats before cleaning
        print("📊 Current database state:")
        stats = chroma_manager.get_stats()
        print(f"   Total documents: {stats['total_documents']}")
        print(f"   Questions: {stats['questions']}")
        print(f"   Answers: {stats['answers']}")
        print(f"   Q&A pairs: {stats['qa_pairs']}")
        
        if stats['total_documents'] == 0:
            print("✅ Database is already empty!")
            return
        
        # Confirm deletion
        print(f"\n⚠️  This will delete ALL {stats['total_documents']} documents from the vector database!")
        confirm = input("Are you sure you want to continue? (yes/y/no): ").lower().strip()
        
        if confirm not in ['yes', 'y']:
            print("❌ Operation cancelled.")
            return
        
        # Get all document IDs
        print("\n🗑️  Deleting all documents...")
        all_data = chroma_manager.collection.get()
        
        if all_data and all_data.get("ids"):
            all_ids = all_data["ids"]
            print(f"   Found {len(all_ids)} documents to delete...")
            
            # Delete all documents
            chroma_manager.collection.delete(ids=all_ids)
            print(f"   Deleted {len(all_ids)} documents")
        
        # Verify deletion
        print("\n✅ Verifying database is clean...")
        final_stats = chroma_manager.get_stats()
        print(f"   Total documents: {final_stats['total_documents']}")
        print(f"   Questions: {final_stats['questions']}")
        print(f"   Answers: {final_stats['answers']}")
        print(f"   Q&A pairs: {final_stats['qa_pairs']}")
        
        if final_stats['total_documents'] == 0:
            print("\n🎉 Vector database cleaned successfully!")
        else:
            print(f"\n⚠️  Warning: {final_stats['total_documents']} documents still remain")
            
    except Exception as e:
        print(f"❌ Error cleaning database: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    clean_database() 