#!/usr/bin/env python3
"""
Debug script to test cosine similarity calculation in ChromaDB
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from vectorstore.chroma_db import chroma_manager
import numpy as np

def debug_cosine_similarity():
    """Debug the cosine similarity calculation"""
    
    print("🔍 Debugging Cosine Similarity Calculation")
    print("=" * 60)
    
    # Test query
    test_query = "السلام عليكم"
    print(f"🧪 Test Query: {test_query}")
    
    try:
        # Get the current collection state
        all_data = chroma_manager.collection.get(include=["documents", "metadatas", "embeddings"])
        print(f"📊 Total documents in collection: {len(all_data['documents'])}")
        
        # Generate query embedding
        print("\n🔧 Generating query embedding...")
        query_embedding = chroma_manager._l2_normalize_embeddings([test_query])[0]
        print(f"   Query embedding shape: {len(query_embedding)}")
        print(f"   Query embedding norm: {np.linalg.norm(query_embedding):.6f}")
        
        # Perform raw ChromaDB query
        print("\n🔍 Performing ChromaDB query...")
        results = chroma_manager.collection.query(
            query_embeddings=[query_embedding],
            n_results=3,
            include=["documents", "metadatas", "distances", "embeddings"]
        )
        
        print(f"   Query returned {len(results['documents'][0]) if results['documents'] else 0} results")
        
        # Debug the results
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                print(f"\n📄 Result {i+1}:")
                print(f"   Document: {doc}")
                print(f"   Metadata: {results['metadatas'][0][i]}")
                
                # Check if distances are available
                if "distances" in results and results["distances"]:
                    distance = results["distances"][0][i]
                    print(f"   Raw distance: {distance}")
                    print(f"   Negative distance: {-distance}")
                    
                    # Calculate cosine similarity manually if embeddings are available
                    if "embeddings" in results and results["embeddings"]:
                        stored_embedding = results["embeddings"][0][i]
                        stored_embedding_norm = np.linalg.norm(stored_embedding)
                        
                        # Calculate dot product manually
                        dot_product = np.dot(query_embedding, stored_embedding)
                        print(f"   Manual dot product: {dot_product:.6f}")
                        print(f"   Stored embedding norm: {stored_embedding_norm:.6f}")
                        
                        # Since both embeddings are L2 normalized, dot product = cosine similarity
                        print(f"   Manual cosine similarity: {dot_product:.6f}")
                    
                    # Show the converted similarity
                    dot_product_score = -distance
                    cosine_similarity = max(0.0, min(1.0, dot_product_score))
                    print(f"   Converted cosine similarity: {cosine_similarity:.6f}")
                else:
                    print("   ❌ No distances in results!")
        
        # Test the formatted search method
        print(f"\n🔍 Testing formatted search method...")
        formatted_results = chroma_manager.search(test_query, n_results=3)
        
        for i, result in enumerate(formatted_results):
            print(f"\n📄 Formatted Result {i+1}:")
            print(f"   Document: {result['document']}")
            print(f"   Cosine Similarity: {result['cosine_similarity']:.6f}")
            print(f"   Metadata: {result['metadata']}")
        
    except Exception as e:
        print(f"❌ Error during debugging: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_cosine_similarity() 