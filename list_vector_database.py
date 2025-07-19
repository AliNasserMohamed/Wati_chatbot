#!/usr/bin/env python3
"""
Script to list all questions and answers in the vector database
"""
import os
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from vectorstore.chroma_db import chroma_manager

def list_all_qa_pairs():
    """List all question-answer pairs from the vector database"""
    
    print("🔍 Listing all Q&A pairs from vector database...")
    print("=" * 80)
    
    try:
        # Get all data from the collection
        collection = chroma_manager.get_collection_safe()
        all_data = collection.get(include=["documents", "metadatas"])
        
        if not all_data or not all_data.get("documents"):
            print("❌ No data found in vector database")
            return
        
        questions_count = 0
        qa_pairs = []
        
        # Process all documents
        for i, document in enumerate(all_data["documents"]):
            metadata = all_data["metadatas"][i]
            doc_id = all_data["ids"][i]
            
            # Only process questions (not answers)
            if metadata.get("type") == "question":
                questions_count += 1
                
                # Get the answer from metadata
                answer = metadata.get("answer_text", "")
                category = metadata.get("category", "general")
                language = metadata.get("language", "ar")
                source = metadata.get("source", "unknown")
                
                qa_pairs.append({
                    "id": doc_id,
                    "question": document,
                    "answer": answer,
                    "category": category,
                    "language": language,
                    "source": source,
                    "metadata": metadata
                })
        
        # Sort by category for better organization
        qa_pairs.sort(key=lambda x: (x["category"], x["question"]))
        
        print(f"📊 Found {questions_count} question-answer pairs")
        print("=" * 80)
        
        current_category = None
        
        # Display all Q&A pairs
        for i, pair in enumerate(qa_pairs, 1):
            # Print category header if changed
            if pair["category"] != current_category:
                current_category = pair["category"]
                print(f"\n📁 CATEGORY: {current_category.upper()}")
                print("-" * 40)
            
            print(f"\n{i}. ID: {pair['id']}")
            print(f"   QUESTION ({pair['language']}): {pair['question']}")
            
            if pair['answer']:
                print(f"   ANSWER: {pair['answer']}")
            else:
                print(f"   ANSWER: [NO ANSWER PROVIDED]")
            
            print(f"   SOURCE: {pair['source']}")
            
            # Show additional metadata if available
            extra_meta = {k: v for k, v in pair['metadata'].items() 
                         if k not in ['type', 'answer_text', 'category', 'language', 'source']}
            if extra_meta:
                print(f"   METADATA: {extra_meta}")
            
            print()
        
        # Summary statistics
        print("=" * 80)
        print("📈 SUMMARY:")
        
        # Count by category
        category_counts = {}
        language_counts = {}
        source_counts = {}
        empty_answers = 0
        
        for pair in qa_pairs:
            category_counts[pair["category"]] = category_counts.get(pair["category"], 0) + 1
            language_counts[pair["language"]] = language_counts.get(pair["language"], 0) + 1
            source_counts[pair["source"]] = source_counts.get(pair["source"], 0) + 1
            
            if not pair["answer"]:
                empty_answers += 1
        
        print(f"   Total Q&A pairs: {len(qa_pairs)}")
        print(f"   Questions without answers: {empty_answers}")
        print(f"   Categories: {dict(category_counts)}")
        print(f"   Languages: {dict(language_counts)}")
        print(f"   Sources: {dict(source_counts)}")
        
    except Exception as e:
        print(f"❌ Error listing Q&A pairs: {str(e)}")
        import traceback
        traceback.print_exc()

def search_specific_question(query: str):
    """Search for a specific question in the database"""
    print(f"\n🔍 Searching for: '{query}'")
    print("-" * 50)
    
    try:
        results = chroma_manager.search_sync(query, n_results=5)
        
        if not results:
            print("❌ No results found")
            return
        
        for i, result in enumerate(results, 1):
            metadata = result["metadata"]
            similarity = result["similarity"]
            
            print(f"\n{i}. SIMILARITY: {similarity:.4f}")
            print(f"   QUESTION: {result['document']}")
            
            answer = metadata.get("answer_text", "")
            if answer:
                print(f"   ANSWER: {answer}")
            else:
                print(f"   ANSWER: [NO ANSWER PROVIDED]")
            
            print(f"   CATEGORY: {metadata.get('category', 'general')}")
            print(f"   ID: {result['id']}")
    
    except Exception as e:
        print(f"❌ Error searching: {str(e)}")

def main():
    """Main function"""
    if len(sys.argv) > 1:
        # Search mode
        query = " ".join(sys.argv[1:])
        search_specific_question(query)
    else:
        # List all mode
        list_all_qa_pairs()

if __name__ == "__main__":
    main() 