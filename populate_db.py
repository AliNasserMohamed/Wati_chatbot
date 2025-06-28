#!/usr/bin/env python3
"""
Script to populate the ChromaDB database with default knowledge
"""

import sys
sys.path.append('.')

from vectorstore.chroma_db import chroma_manager

def populate_database():
    """Populate the database with default knowledge"""
    print("🚀 Starting database population...")
    
    # Check current state
    print("\n📊 Checking current database state...")
    questions = chroma_manager.list_questions()
    
    if len(questions) > 0:
        print(f"✅ Database already has {len(questions)} questions.")
        print("Current questions:")
        for i, q in enumerate(questions, 1):
            print(f"  {i}. {q}")
        
        user_input = input("\n❓ Do you want to add more default knowledge? (y/n): ").lower()
        if user_input != 'y':
            print("✋ Skipping population.")
            return
    
    # Populate with default knowledge
    print("\n📝 Adding default knowledge to database...")
    chroma_manager.populate_default_knowledge()
    
    # Check final state
    print("\n✅ Population completed! Checking final state...")
    final_questions = chroma_manager.list_questions()
    print(f"📄 Database now contains {len(final_questions)} questions:")
    for i, q in enumerate(final_questions, 1):
        print(f"  {i}. {q}")

def test_search():
    """Test the search functionality"""
    print("\n\n🧪 Testing search functionality...")
    
    test_queries = [
        "ما هو ابار؟",
        "التوصيل مجاني؟",
        "كم علامة تجارية؟"
    ]
    
    for query in test_queries:
        print(f"\n🔍 Query: '{query}'")
        results = chroma_manager.search(query, n_results=2)
        
        if results:
            for i, result in enumerate(results, 1):
                print(f"  📄 Result {i}: (Similarity: {result['similarity']:.4f})")
                print(f"     Document: {result['document'][:100]}...")
                print(f"     Metadata: {result['metadata']}")
        else:
            print("  ❌ No results found")
        print("-" * 60)

if __name__ == "__main__":
    try:
        populate_database()
        test_search()
        print("\n🎉 Database setup and testing completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc() 