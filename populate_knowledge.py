#!/usr/bin/env python3
"""
Script to populate the knowledge base with updated questions and answers
"""
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.knowledge_manager import knowledge_manager

def populate_knowledge_base():
    """
    Populate the knowledge base with the updated questions and answers
    """
    print("🚀 Starting knowledge base population...")
    print("=" * 60)
    
    try:
        # Get current stats before population
        stats_before = knowledge_manager.get_knowledge_stats()
        if stats_before["success"]:
            print(f"📊 Current knowledge base stats:")
            print(f"   - Total documents: {stats_before['stats']['total_documents']}")
            print(f"   - Questions: {stats_before['stats']['questions']}")
            print(f"   - Answers: {stats_before['stats']['answers']}")
            print(f"   - Q&A pairs: {stats_before['stats']['qa_pairs']}")
        
        print("\n🔄 Populating knowledge base with updated Q&A pairs...")
        
        # Populate the knowledge base (now synchronous)
        result = knowledge_manager.populate_abar_knowledge()
        
        if result["success"]:
            print(f"✅ Knowledge base population completed successfully!")
            print(f"   - Added: {result['added_count']} new Q&A pairs")
            print(f"   - Skipped: {result['skipped_count']} duplicates")
            print(f"   - Message: {result['message']}")
            
            # Show sample of added IDs
            if result['added_ids']:
                print(f"   - Sample added IDs: {result['added_ids'][:3]}...")
        else:
            print(f"❌ Error: {result['error']}")
            return False
        
        # Get stats after population
        stats_after = knowledge_manager.get_knowledge_stats()
        if stats_after["success"]:
            print(f"\n📊 Updated knowledge base stats:")
            print(f"   - Total documents: {stats_after['stats']['total_documents']}")
            print(f"   - Questions: {stats_after['stats']['questions']}")
            print(f"   - Answers: {stats_after['stats']['answers']}")
            print(f"   - Q&A pairs: {stats_after['stats']['qa_pairs']}")
        
        print("\n🎉 Knowledge base is now updated with your latest questions and answers!")
        print("💡 The vector database now includes all Q&A pairs from CSV:")
        print("   - Arabic greetings (including صباح الخير)")
        print("   - English greetings")
        print("   - Thank you messages in both languages")
        print("   - Default Abar app information")
        print("   - All other Q&A pairs from the CSV file")
        
        return True
        
    except Exception as e:
        print(f"❌ Error populating knowledge base: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = populate_knowledge_base()
    if success:
        print("\n✅ Script completed successfully!")
    else:
        print("\n❌ Script failed!")
        sys.exit(1) 