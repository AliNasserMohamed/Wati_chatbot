#!/usr/bin/env python3
"""
Lightweight test script for embedding agent using smaller models
This should work without memory issues
"""

import asyncio
import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def test_lite_embedding_agent():
    """
    Test embedding agent with lightweight ChromaDB
    """
    print("🚀 Lightweight Embedding Agent Test")
    print("=" * 60)
    
    # Check OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ ERROR: OPENAI_API_KEY not found")
        print("Please add OPENAI_API_KEY=your_key to .env file")
        return
    
    print("✅ OpenAI API key found")
    
    try:
        # Import the lightweight ChromaDB manager
        from vectorstore.chroma_db_lite import chroma_manager_lite
        print("✅ Lightweight ChromaDB manager imported successfully")
        
        # Populate knowledge base
        print("\n📚 Populating knowledge base...")
        chroma_manager_lite.populate_default_knowledge()
        print("✅ Knowledge base populated!")
        
        # Test ChromaDB search directly
        print("\n🔍 Testing direct ChromaDB search...")
        test_queries = [
            "كيف أطلب المياه؟",
            "How to order water?", 
            "هل التوصيل مجاني؟",
            "What is Abar?"
        ]
        
        for query in test_queries:
            print(f"\n🔎 Searching for: '{query}'")
            results = chroma_manager_lite.search(query, n_results=2)
            
            for i, result in enumerate(results, 1):
                similarity = result.get('similarity', 0)
                doc_preview = result['document'][:60] + "..." if len(result['document']) > 60 else result['document']
                print(f"   {i}. Similarity: {similarity:.4f}")
                print(f"      Content: {doc_preview}")
        
        # Now test with a simplified embedding agent
        print(f"\n🤖 Testing simplified embedding agent flow...")
        
        # Create a simple embedding agent class for testing
        class SimpleEmbeddingAgent:
            def __init__(self):
                self.similarity_threshold = 0.20
                self.high_similarity_threshold = 0.80
                
            async def process_message(self, user_message: str, language: str = 'ar'):
                print(f"🔍 Processing: '{user_message}'")
                
                # Search in knowledge base
                search_results = chroma_manager_lite.search(user_message, n_results=3)
                
                if not search_results:
                    return {
                        'action': 'continue_to_classification',
                        'confidence': 0,
                        'response': None
                    }
                
                best_match = search_results[0]
                cosine_similarity = best_match.get('similarity', 0.0)
                
                print(f"   Best match similarity: {cosine_similarity:.4f}")
                print(f"   Best match: {best_match['document'][:50]}...")
                
                # Check threshold
                if cosine_similarity < self.similarity_threshold:
                    print(f"   → Similarity too low, continue to classification")
                    return {
                        'action': 'continue_to_classification',
                        'confidence': cosine_similarity,
                        'response': None
                    }
                
                # Get answer
                matched_document = best_match['document']
                metadata = best_match['metadata']
                
                if metadata.get('type') == 'question':
                    answer_id = metadata.get('answer_id')
                    if answer_id:
                        answer_results = chroma_manager_lite.collection.get(ids=[answer_id])
                        if answer_results and answer_results['documents']:
                            matched_answer = answer_results['documents'][0]
                        else:
                            matched_answer = matched_document
                    else:
                        matched_answer = matched_document
                else:
                    matched_answer = matched_document
                
                print(f"   Found answer: {matched_answer[:50]}...")
                
                # High similarity - direct reply
                if cosine_similarity >= self.high_similarity_threshold:
                    print(f"   → High similarity, direct reply")
                    return {
                        'action': 'reply',
                        'confidence': cosine_similarity,
                        'response': matched_answer
                    }
                else:
                    print(f"   → Moderate similarity, would normally send to LLM")
                    # For this test, just return the answer
                    return {
                        'action': 'reply',
                        'confidence': cosine_similarity,
                        'response': matched_answer
                    }
        
        # Test the simple embedding agent
        simple_agent = SimpleEmbeddingAgent()
        
        test_messages = [
            "ما هو تطبيق ابار؟",
            "How to order water?",
            "هل التوصيل مجاني؟",
            "كيف حالك؟",  # Should have low similarity
            "كيف أطلب مياه؟"
        ]
        
        print(f"\n🧪 Testing {len(test_messages)} messages:")
        print("=" * 60)
        
        for i, message in enumerate(test_messages, 1):
            print(f"\n🔬 TEST {i}: '{message}'")
            print("-" * 40)
            
            result = await simple_agent.process_message(message)
            
            print(f"📊 RESULT:")
            print(f"   Action: {result['action']}")
            print(f"   Confidence: {result['confidence']:.4f}")
            if result.get('response'):
                response_preview = result['response'][:80] + "..." if len(result['response']) > 80 else result['response']
                print(f"   Response: {response_preview}")
            else:
                print(f"   Response: None")
        
        print(f"\n🎉 Lightweight test completed successfully!")
        
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()

async def main():
    """
    Main test function
    """
    print("🌟 ABAR LITE EMBEDDING TEST")
    print("=" * 60)
    
    await test_lite_embedding_agent()
    
    print("\n✅ Test completed!")
    print("💡 If this works, you can proceed to fix the memory issue for the full Arabic model")

if __name__ == "__main__":
    print("🔧 Running lightweight test...")
    asyncio.run(main()) 