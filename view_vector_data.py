#!/usr/bin/env python3
"""
Script to view all data stored in the ChromaDB vector database
"""
import sys
import os

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from vectorstore.chroma_db import chroma_manager
    
    print("🗄️  ABAR KNOWLEDGE BASE - VECTOR DATABASE CONTENT")
    print("=" * 60)
    
    # Get all data from the collection (IDs are included by default)
    all_data = chroma_manager.collection.get()
    print(all_data,len(all_data))
    
    if not all_data or not all_data.get("documents"):
        print("❌ No data found in the vector database")
        sys.exit(1)
    
    print(f"📊 Total documents: {len(all_data['documents'])}")
    print()
    
    # Separate questions and answers
    questions = []
    answers = []
    
    for i, (doc, metadata, doc_id) in enumerate(zip(all_data["documents"], all_data["metadatas"], all_data["ids"])):
        if metadata.get("type") == "question":
            questions.append({
                "id": doc_id,
                "content": doc,
                "metadata": metadata,
                "answer_id": metadata.get("answer_id")
            })
        else:
            answers.append({
                "id": doc_id,
                "content": doc,
                "metadata": metadata
            })
    
    print(f"❓ Questions: {len(questions)}")
    print(f"💬 Answers: {len(answers)}")
    print()
    
    # Display Q&A pairs
    print("🔍 QUESTION & ANSWER PAIRS:")
    print("-" * 60)
    
    qa_pairs = []
    for question in questions:
        answer_id = question["answer_id"]
        # Find corresponding answer
        answer = next((a for a in answers if a["id"] == answer_id), None)
        if answer:
            qa_pairs.append({
                "question": question["content"],
                "answer": answer["content"],
                "category": answer["metadata"].get("category", "N/A"),
                "source": answer["metadata"].get("source", "N/A")
            })
    
    # Sort by category for better organization
    qa_pairs.sort(key=lambda x: x["category"])
    
    for i, pair in enumerate(qa_pairs, 1):
        print(f"\n{i}. 📋 Category: {pair['category']} | Source: {pair['source']}")
        print(f"   ❓ Q: {pair['question']}")
        print(f"   💡 A: {pair['answer']}")
    
    print("\n" + "=" * 60)
    print("✅ Database content displayed successfully!")
    
    # Test search functionality
    print("\n🔍 TESTING SEARCH FUNCTIONALITY:")
    print("-" * 40)
    
    test_queries = [
        "السسلام عليكم",
        "السلام عليكم", 
        "مرحبا",
        "هلا هلا",
        "السلام عليكم ورحمة الله وبركاته"
    ]
    
    for query in test_queries:
        print(f"\n🔍 Search: '{query}'")
        results = chroma_manager.search(query, n_results=2)
        
        if results:
            for j, result in enumerate(results, 1):
                similarity = result.get('cosine_similarity', 0)
                print(f"   {j}. 📄 {result['document'][:80]}...")
                print(f"      🎯 Cosine Similarity: {similarity:.3f}")
        else:
            print("   ❌ No results found")

except Exception as e:
    print(f"❌ Error: {str(e)}")
    import traceback
    traceback.print_exc() 