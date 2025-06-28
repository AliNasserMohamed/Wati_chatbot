#!/usr/bin/env python3
"""
Simple test script for embedding agent with specific questions
Tests cosine similarity and retrieves results from database
"""

import asyncio
import os
from dotenv import load_dotenv
from agents.embedding_agent import embedding_agent
from vectorstore.chroma_db import chroma_manager
from database.db_utils import DatabaseManager, SessionLocal

# Load environment variables
load_dotenv()

async def test_specific_questions():
    """
    Test specific questions and print results from database
    """
    
    print("🚀 Simple Embedding Agent Test")
    print("=" * 50)
    
    # First, populate the knowledge base with test data
    print("\n📚 Populating knowledge base...")
    chroma_manager.populate_default_knowledge()
    
    # Add greeting questions for testing
    greeting_questions = [
        "السلام عليكم ورحمة الله وبركاته",
        "مرحبا بك",
        "أهلا وسهلا"
    ]
    
    greeting_answers = [
        "وعليكم السلام ورحمة الله وبركاته، أهلاً وسهلاً! كيف يمكنني مساعدتك اليوم؟",
        "أهلاً وسهلاً بك! كيف يمكنني مساعدتك؟",
        "مرحباً بك! يسعدني خدمتك، كيف يمكنني مساعدتك؟"
    ]
    
    greeting_metadata = [
        {"source": "test", "category": "greeting"},
        {"source": "test", "category": "greeting"},
        {"source": "test", "category": "greeting"}
    ]
    
    chroma_manager.add_knowledge(greeting_questions, greeting_answers, greeting_metadata)
    print("✅ Knowledge base populated!")
    
    # Test questions
    test_queries = [
        "السسلام عليكم",  # Main test case with typo
        "السلام عليكم",   # Correct spelling
        "مرحبا",
        "كيف أطلب المياه؟",
        "ما هو تطبيق ابار؟"
    ]
    
    # Create test user for database storage
    with SessionLocal() as db:
        test_user = DatabaseManager.create_user(db, "simple_test_user", "Simple Test User")
        test_user_id = test_user.id
    
    print(f"\n🧪 Testing {len(test_queries)} questions...")
    print("=" * 50)
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n🔬 TEST {i}: '{query}'")
        print("-" * 40)
        
        try:
            # Create a test message in database
            with SessionLocal() as db:
                test_message = DatabaseManager.create_message(db, test_user_id, query)
                test_message_id = test_message.id
            
            # Test the embedding agent
            result = await embedding_agent.process_message(
                user_message=query,
                conversation_history=[],
                user_language='ar',
                user_id=test_user_id,
                user_message_id=test_message_id
            )
            
            print(f"📊 RESULT:")
            print(f"   - Action: {result['action']}")
            print(f"   - Cosine Similarity: {result.get('confidence', 0):.4f}")
            
            if result.get('response'):
                print(f"   - Response: {result['response']}")
            
            if result.get('matched_question'):
                print(f"   - Matched Question: {result['matched_question']}")
            
        except Exception as e:
            print(f"❌ ERROR: {str(e)}")
        
        print("=" * 40)
    
    # Print database results
    print(f"\n💾 DATABASE RESULTS:")
    print("=" * 50)
    
    with SessionLocal() as db:
        # Get embedding Q&A statistics
        qa_stats = DatabaseManager.get_embedding_qa_stats(db, test_user_id)
        print(f"Total Q&A Records: {qa_stats['total_records']}")
        
        if qa_stats['total_records'] > 0:
            print(f"Average Cosine Similarity: {qa_stats['avg_similarity']:.4f}")
            print(f"Min Similarity: {qa_stats['min_similarity']:.4f}")
            print(f"Max Similarity: {qa_stats['max_similarity']:.4f}")
            print(f"LLM Evaluations: {qa_stats['llm_evaluations']}")
        
        # Get detailed Q&A history
        qa_history = DatabaseManager.get_embedding_qa_history(db, test_user_id, 10)
        
        print(f"\n📋 DETAILED Q&A HISTORY:")
        print("-" * 50)
        
        for i, qa in enumerate(qa_history, 1):
            print(f"{i}. Question: '{qa.question}'")
            print(f"   Cosine Similarity: {qa.cosine_similarity:.4f}")
            print(f"   LLM Evaluation: {qa.llm_evaluation}")
            print(f"   Matched Question: '{qa.matched_question or 'None'}'")
            print(f"   Answer: '{qa.answer or 'None'}'")
            print(f"   Created: {qa.created_at}")
            print()

def main():
    """Main function"""
    try:
        asyncio.run(test_specific_questions())
    except KeyboardInterrupt:
        print("\n⚠️ Test interrupted by user")
    except Exception as e:
        print(f"\n💥 Test failed: {str(e)}")

if __name__ == "__main__":
    main() 