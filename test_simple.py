#!/usr/bin/env python3
"""
Simple test script for embedding agent with lightweight model
"""

import asyncio
import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Simple test without heavy models
async def test_simple():
    """
    Simple test without loading heavy embedding models
    """
    print("🚀 Simple Embedding Agent Test")
    print("=" * 50)
    
    # Check environment
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ ERROR: OPENAI_API_KEY not found")
        print("Please add OPENAI_API_KEY=your_key to .env file")
        return
    
    print("✅ OpenAI API key found")
    
    # Test basic imports first
    try:
        print("\n🔍 Testing imports...")
        
        # Test basic imports
        import chromadb
        print("✅ chromadb imported successfully")
        
        import openai
        print("✅ openai imported successfully")
        
        from sentence_transformers import SentenceTransformer
        print("✅ sentence_transformers imported successfully")
        
        print("\n🧪 Testing lightweight embedding model...")
        
        # Use a much smaller, lightweight model
        model = SentenceTransformer('all-MiniLM-L6-v2')  # Much smaller model
        print("✅ Lightweight embedding model loaded successfully")
        
        # Test basic embedding
        test_text = "Hello world"
        embedding = model.encode([test_text])
        print(f"✅ Generated embedding with shape: {embedding.shape}")
        
        # Test ChromaDB with lightweight model
        print("\n📊 Testing ChromaDB with lightweight model...")
        
        from chromadb.utils import embedding_functions
        
        # Create lightweight embedding function
        lightweight_ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        
        # Test basic ChromaDB functionality
        client = chromadb.EphemeralClient()  # Use in-memory client for testing
        collection = client.create_collection(
            name="test_collection",
            embedding_function=lightweight_ef
        )
        
        # Add test documents
        test_docs = [
            "How to order water?",
            "كيف أطلب المياه؟",
            "When will my order arrive?"
        ]
        
        collection.add(
            documents=test_docs,
            ids=["doc1", "doc2", "doc3"]
        )
        
        print("✅ Documents added to ChromaDB")
        
        # Test search
        results = collection.query(
            query_texts=["order water"],
            n_results=2
        )
        
        print(f"✅ Search completed - found {len(results['documents'][0])} results")
        for i, doc in enumerate(results['documents'][0]):
            distance = results['distances'][0][i]
            similarity = 1.0 - distance
            print(f"   {i+1}. Document: {doc}")
            print(f"       Distance: {distance:.4f}, Similarity: {similarity:.4f}")
        
        print("\n🎉 Basic functionality test PASSED!")
        
    except Exception as e:
        print(f"❌ ERROR during testing: {str(e)}")
        print(f"Error type: {type(e).__name__}")
        return False
    
    return True

async def test_openai_connection():
    """
    Test OpenAI API connection
    """
    print("\n🤖 Testing OpenAI API connection...")
    
    try:
        client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Say 'OpenAI connection test successful'"}],
            max_tokens=20
        )
        
        result = response.choices[0].message.content
        print(f"✅ OpenAI API response: {result}")
        
    except Exception as e:
        print(f"❌ OpenAI API error: {str(e)}")
        return False
    
    return True

async def main():
    """
    Main test function
    """
    print("🌟 SIMPLE ABAR EMBEDDING TEST")
    print("=" * 50)
    
    # Run basic tests
    basic_success = await test_simple()
    openai_success = await test_openai_connection()
    
    if basic_success and openai_success:
        print("\n✅ ALL TESTS PASSED!")
        print("🎯 Your system is ready for the full embedding agent")
        print("\n💡 To fix the memory issue with the Arabic model:")
        print("   1. Increase virtual memory (paging file)")
        print("   2. Or use a smaller Arabic model")
        print("   3. Or run on a machine with more RAM")
    else:
        print("\n❌ SOME TESTS FAILED")
        print("Please fix the issues above before running the full test")

if __name__ == "__main__":
    print("🔧 Running simplified test...")
    asyncio.run(main()) 