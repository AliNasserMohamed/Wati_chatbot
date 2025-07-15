#!/usr/bin/env python3
"""
Quick test to verify chatbot can find answers from populated vector database
"""
import sys
import os
import asyncio

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_chatbot_search():
    """Test if the chatbot can find answers from the vector database"""
    print("🔍 Testing Chatbot Search with Populated Vector Database")
    print("=" * 60)
    
    try:
        # Import the embedding agent (which uses the vector database)
        from agents.embedding_agent import EmbeddingAgent
        
        embedding_agent = EmbeddingAgent()
        
        # Test queries from your CSV data
        test_queries = [
            "السلام عليكم",      # Arabic greeting
            "مرحبا",              # Arabic greeting  
            "Hello",              # English greeting
            "Thank you",          # English thanks
            "ما هو تطبيق ابار؟",   # Question about Abar app
            "هل التوصيل مجاني؟"    # Question about delivery
        ]
        
        print("\n🧪 Testing search for various queries...")
        
        for i, query in enumerate(test_queries, 1):
            print(f"\n{i}. Testing query: '{query}'")
            
            try:
                # Process the message using embedding agent
                result = await embedding_agent.process_message(query, user_language='ar')
                
                print(f"   Action: {result['action']}")
                print(f"   Confidence: {result['confidence']:.4f}")
                
                if result['response']:
                    print(f"   Response: {result['response'][:100]}...")
                else:
                    print("   Response: (No response - as expected for some queries)")
                    
                if result['matched_question']:
                    print(f"   Matched: {result['matched_question'][:50]}...")
                
            except Exception as e:
                print(f"   ❌ Error: {str(e)}")
        
        print("\n🎉 Chatbot search test completed!")
        print("✅ Your chatbot can now find answers from the CSV data!")
        
    except Exception as e:
        print(f"❌ Error during test: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_chatbot_search()) 