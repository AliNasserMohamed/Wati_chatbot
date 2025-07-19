#!/usr/bin/env python3
"""
Debug script to find specific answers and problematic responses in the vector database
"""
import os
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from vectorstore.chroma_db import chroma_manager

def find_answer_containing(search_text: str):
    """Find all Q&A pairs where the answer contains specific text"""
    
    print(f"🔍 Searching for answers containing: '{search_text}'")
    print("=" * 60)
    
    try:
        # Get all data from the collection
        collection = chroma_manager.get_collection_safe()
        all_data = collection.get(include=["documents", "metadatas"])
        
        if not all_data or not all_data.get("documents"):
            print("❌ No data found in vector database")
            return
        
        found_pairs = []
        
        # Process all documents
        for i, document in enumerate(all_data["documents"]):
            metadata = all_data["metadatas"][i]
            doc_id = all_data["ids"][i]
            
            # Only process questions
            if metadata.get("type") == "question":
                answer = metadata.get("answer_text", "")
                
                # Check if answer contains the search text
                if search_text.lower() in answer.lower():
                    found_pairs.append({
                        "id": doc_id,
                        "question": document,
                        "answer": answer,
                        "category": metadata.get("category", "general"),
                        "source": metadata.get("source", "unknown")
                    })
        
        if found_pairs:
            print(f"✅ Found {len(found_pairs)} Q&A pairs with answers containing '{search_text}':")
            print()
            
            for i, pair in enumerate(found_pairs, 1):
                print(f"{i}. ID: {pair['id']}")
                print(f"   QUESTION: {pair['question']}")
                print(f"   ANSWER: {pair['answer']}")
                print(f"   CATEGORY: {pair['category']}")
                print(f"   SOURCE: {pair['source']}")
                print("-" * 40)
        else:
            print(f"❌ No answers found containing '{search_text}'")
    
    except Exception as e:
        print(f"❌ Error searching answers: {str(e)}")
        import traceback
        traceback.print_exc()

def find_question_containing(search_text: str):
    """Find all questions containing specific text"""
    
    print(f"🔍 Searching for questions containing: '{search_text}'")
    print("=" * 60)
    
    try:
        # Get all data from the collection
        collection = chroma_manager.get_collection_safe()
        all_data = collection.get(include=["documents", "metadatas"])
        
        if not all_data or not all_data.get("documents"):
            print("❌ No data found in vector database")
            return
        
        found_pairs = []
        
        # Process all documents
        for i, document in enumerate(all_data["documents"]):
            metadata = all_data["metadatas"][i]
            doc_id = all_data["ids"][i]
            
            # Only process questions
            if metadata.get("type") == "question":
                # Check if question contains the search text
                if search_text.lower() in document.lower():
                    answer = metadata.get("answer_text", "")
                    found_pairs.append({
                        "id": doc_id,
                        "question": document,
                        "answer": answer,
                        "category": metadata.get("category", "general"),
                        "source": metadata.get("source", "unknown")
                    })
        
        if found_pairs:
            print(f"✅ Found {len(found_pairs)} Q&A pairs with questions containing '{search_text}':")
            print()
            
            for i, pair in enumerate(found_pairs, 1):
                print(f"{i}. ID: {pair['id']}")
                print(f"   QUESTION: {pair['question']}")
                print(f"   ANSWER: {pair['answer']}")
                print(f"   CATEGORY: {pair['category']}")
                print(f"   SOURCE: {pair['source']}")
                print("-" * 40)
        else:
            print(f"❌ No questions found containing '{search_text}'")
    
    except Exception as e:
        print(f"❌ Error searching questions: {str(e)}")
        import traceback
        traceback.print_exc()

def find_short_answers():
    """Find all short answers that might be problematic"""
    
    print("🔍 Finding potentially problematic short answers...")
    print("=" * 60)
    
    try:
        # Get all data from the collection
        collection = chroma_manager.get_collection_safe()
        all_data = collection.get(include=["documents", "metadatas"])
        
        if not all_data or not all_data.get("documents"):
            print("❌ No data found in vector database")
            return
        
        short_answers = []
        greeting_answers = []
        
        # Process all documents
        for i, document in enumerate(all_data["documents"]):
            metadata = all_data["metadatas"][i]
            doc_id = all_data["ids"][i]
            
            # Only process questions
            if metadata.get("type") == "question":
                answer = metadata.get("answer_text", "").strip()
                
                if answer:
                    # Check for short answers (less than 20 characters)
                    if len(answer) < 20:
                        short_answers.append({
                            "id": doc_id,
                            "question": document,
                            "answer": answer,
                            "length": len(answer)
                        })
                    
                    # Check for greeting-like answers
                    greeting_keywords = ["حياك", "أهلا", "مرحبا", "السلام", "صباح", "مساء"]
                    if any(keyword in answer for keyword in greeting_keywords):
                        greeting_answers.append({
                            "id": doc_id,
                            "question": document,
                            "answer": answer
                        })
        
        print("📊 SHORT ANSWERS (< 20 characters):")
        print("-" * 30)
        for answer in sorted(short_answers, key=lambda x: x['length']):
            print(f"   Length {answer['length']}: '{answer['answer']}' -> Question: '{answer['question'][:50]}...'")
        
        print(f"\n📊 GREETING-LIKE ANSWERS:")
        print("-" * 30)
        for answer in greeting_answers:
            print(f"   '{answer['answer']}' -> Question: '{answer['question'][:50]}...'")
    
    except Exception as e:
        print(f"❌ Error finding short answers: {str(e)}")
        import traceback
        traceback.print_exc()

def test_specific_question(question: str):
    """Test how a specific question would be matched in the vector database"""
    
    print(f"🧪 Testing question: '{question}'")
    print("=" * 60)
    
    try:
        # Search for similar questions
        results = chroma_manager.search_sync(question, n_results=3)
        
        if not results:
            print("❌ No similar questions found")
            return
        
        print("Top 3 similar questions:")
        print()
        
        for i, result in enumerate(results, 1):
            metadata = result["metadata"]
            similarity = result["similarity"]
            answer = metadata.get("answer_text", "")
            
            print(f"{i}. SIMILARITY: {similarity:.4f}")
            print(f"   MATCHED QUESTION: {result['document']}")
            print(f"   STORED ANSWER: {answer}")
            print(f"   WOULD BE USED: {'✅ YES' if similarity > 0.7 else '❌ NO'}")
            print("-" * 40)
    
    except Exception as e:
        print(f"❌ Error testing question: {str(e)}")
        import traceback
        traceback.print_exc()

def main():
    """Main function"""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python debug_vector_answers.py answer <text>    - Find answers containing text")
        print("  python debug_vector_answers.py question <text>  - Find questions containing text") 
        print("  python debug_vector_answers.py short           - Find short/problematic answers")
        print("  python debug_vector_answers.py test <question> - Test how a question would match")
        print()
        print("Examples:")
        print("  python debug_vector_answers.py answer 'حياك الله'")
        print("  python debug_vector_answers.py question 'الحجم الصغير'")
        print("  python debug_vector_answers.py short")
        print("  python debug_vector_answers.py test 'فيه الحجم الصغير؟'")
        return
    
    command = sys.argv[1].lower()
    
    if command == "answer" and len(sys.argv) > 2:
        search_text = " ".join(sys.argv[2:])
        find_answer_containing(search_text)
    elif command == "question" and len(sys.argv) > 2:
        search_text = " ".join(sys.argv[2:])
        find_question_containing(search_text)
    elif command == "short":
        find_short_answers()
    elif command == "test" and len(sys.argv) > 2:
        question = " ".join(sys.argv[2:])
        test_specific_question(question)
    else:
        print("❌ Invalid command or missing parameters")
        main()

if __name__ == "__main__":
    main() 