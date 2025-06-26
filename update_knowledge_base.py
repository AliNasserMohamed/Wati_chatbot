#!/usr/bin/env python3
"""
Script to update the knowledge base with new Arabic Q&A pairs
This will clear the existing database and add the new questions and answers
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from vectorstore.chroma_db import chroma_manager
from utils.knowledge_manager import knowledge_manager

def clear_knowledge_base():
    """Clear all existing data from the knowledge base"""
    try:
        # Get all existing IDs
        results = chroma_manager.collection.get()
        if results and results.get("ids"):
            all_ids = results["ids"]
            print(f"🗑️ Deleting {len(all_ids)} existing entries from knowledge base...")
            
            # Delete all existing data
            chroma_manager.collection.delete(ids=all_ids)
            print("✅ Successfully cleared existing knowledge base")
        else:
            print("📭 Knowledge base is already empty")
    except Exception as e:
        print(f"❌ Error clearing knowledge base: {str(e)}")
        raise

def add_new_qa_pairs():
    """Add the new Arabic Q&A pairs to the knowledge base"""
    
    # New Q&A pairs from the user's table
    questions = [
        "السلام عليكم",
        "الوووو", 
        "هلا",
        "يعطيك العافية",
        "شكراً لكم",
        "مساء الخير",
        "الله يوفقكم",
        "أوكي تمام",
        "تفضل",
        "مابينسمح مافيه العياره"
    ]
    
    answers = [
        "عليكم السلام ورحمة الله، تفضل طال عمرك",
        "حياك الله، تفضل استاذي",
        "حياك الله، تفضل طال عمرك",
        "الله يعافيك",
        "العفو، بالخدمة طال عمرك",
        "مساء النور، تفضل طال عمرك",
        "وياك الله يسعدك",
        "",  # No reply needed for "أوكي تمام"
        "",  # No reply needed for "تفضل"
        " مافهمت العباره"
    ]
    
    # Metadata for each Q&A pair
    metadatas = [
        {"source": "custom", "category": "greeting", "language": "ar"},
        {"source": "custom", "category": "greeting", "language": "ar"},
        {"source": "custom", "category": "greeting", "language": "ar"},
        {"source": "custom", "category": "thanks", "language": "ar"},
        {"source": "custom", "category": "thanks", "language": "ar"},
        {"source": "custom", "category": "greeting", "language": "ar"},
        {"source": "custom", "category": "conversation", "language": "ar"},
        {"source": "custom", "category": "conversation", "language": "ar"},
        {"source": "custom", "category": "conversation", "language": "ar"},
        {"source": "custom", "category": "conversation", "language": "ar"}
    ]
    
    try:
        print(f"📝 Adding {len(questions)} new Q&A pairs to knowledge base...")
        
        # Add the new Q&A pairs using the knowledge manager
        ids = knowledge_manager.add_multiple_qa_pairs(questions, answers, metadatas)
        
        print(f"✅ Successfully added {len(ids)} Q&A pairs with IDs: {ids[:3]}..." if len(ids) > 3 else f"✅ Successfully added Q&A pairs with IDs: {ids}")
        
        return ids
        
    except Exception as e:
        print(f"❌ Error adding new Q&A pairs: {str(e)}")
        raise

def verify_knowledge_base():
    """Verify that the new data was added correctly"""
    try:
        print("🔍 Verifying knowledge base...")
        
        # Get all items from the database
        results = chroma_manager.collection.get()
        
        if results and results.get("documents"):
            total_items = len(results["documents"])
            print(f"📊 Total items in knowledge base: {total_items}")
            
            # Show a few examples
            print("📋 Sample entries:")
            for i, doc in enumerate(results["documents"][:3]):
                metadata = results["metadatas"][i] if results.get("metadatas") else {}
                print(f"   {i+1}. Document: {doc[:50]}...")
                print(f"      Metadata: {metadata}")
                
        else:
            print("⚠️ No documents found in knowledge base")
            
    except Exception as e:
        print(f"❌ Error verifying knowledge base: {str(e)}")

def main():
    """Main function to update the knowledge base"""
    print("🚀 Starting knowledge base update...")
    print("=" * 50)
    
    try:
        # Step 1: Clear existing data
        clear_knowledge_base()
        print()
        
        # Step 2: Add new Q&A pairs
        add_new_qa_pairs()
        print()
        
        # Step 3: Verify the update
        verify_knowledge_base()
        print()
        
        print("🎉 Knowledge base update completed successfully!")
        print("✨ The vector database now contains your custom Arabic Q&A pairs")
        print("🔧 Using embedding model: mohamed2811/Muffakir_Embedding_V2")
        
    except Exception as e:
        print(f"💥 Knowledge base update failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 