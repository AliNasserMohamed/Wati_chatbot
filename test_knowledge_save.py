import sys
import os
import traceback

# Add the current directory to the path so we can import modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("🧪 Testing Knowledge Base Save Functionality")
print("=" * 60)

# Test 1: Check if Excel manager works
print("\n1. Testing Excel Manager...")
try:
    from utils.excel_manager import csv_manager
    print("✅ Excel manager imported successfully")
    
    # Test reading existing data
    existing_data = csv_manager.read_qa_pairs()
    print(f"📚 Found {len(existing_data)} existing Q&A pairs")
    
    # Test adding a new Q&A pair
    test_question = "ما هي خدمات شركة آبار؟"
    test_answer = "شركة آبار تقدم خدمات توصيل المياه المعبأة في السعودية"
    
    print(f"\n📝 Testing adding Q&A pair:")
    print(f"   Question: {test_question}")
    print(f"   Answer: {test_answer}")
    
    success = csv_manager.add_qa_pair(
        question=test_question,
        answer=test_answer,
        category="general",
        language="ar",
        source="test",
        priority="normal"
    )
    
    if success:
        print("✅ Successfully added Q&A pair to Excel")
        
        # Read again to verify
        new_data = csv_manager.read_qa_pairs()
        print(f"📚 Now have {len(new_data)} Q&A pairs")
        
        # Find our test question
        found = False
        for pair in new_data:
            if pair['question'] == test_question:
                print(f"✅ Found test question in Excel: {pair['question']}")
                found = True
                break
        
        if not found:
            print("❌ Test question not found in Excel after adding")
    else:
        print("❌ Failed to add Q&A pair to Excel")
        
except Exception as e:
    print(f"❌ Error testing Excel manager: {str(e)}")
    traceback.print_exc()

# Test 2: Check if Knowledge Manager works  
print("\n2. Testing Knowledge Manager...")
try:
    from utils.knowledge_manager import knowledge_manager
    print("✅ Knowledge manager imported successfully")
    
    # Get current stats
    stats_result = knowledge_manager.get_knowledge_stats()
    print(f"📊 Current knowledge base stats: {stats_result}")
    
    # Test adding the same Q&A pair to vector database
    test_question = "ما هي خدمات شركة آبار للاختبار؟"
    test_answer = "شركة آبار تقدم خدمات توصيل المياه المعبأة في السعودية - اختبار"
    
    print(f"\n📝 Testing adding Q&A pair to vector database:")
    print(f"   Question: {test_question}")
    print(f"   Answer: {test_answer}")
    
    result = knowledge_manager.add_qa_pair(
        question=test_question,
        answer=test_answer,
        metadata={"source": "test", "category": "general", "language": "ar"}
    )
    
    print(f"📊 Add result: {result}")
    
    if result["success"]:
        print("✅ Successfully added Q&A pair to vector database")
        
        # Test searching for it
        search_results = knowledge_manager.search_knowledge(test_question, n_results=1)
        print(f"🔍 Search results: {len(search_results)} found")
        
        if search_results:
            print(f"   Found: {search_results[0]['document'][:50]}...")
    else:
        print(f"❌ Failed to add Q&A pair to vector database: {result['error']}")
        
except Exception as e:
    print(f"❌ Error testing knowledge manager: {str(e)}")
    traceback.print_exc()

# Test 3: Check ChromaDB directly
print("\n3. Testing ChromaDB directly...")
try:
    from vectorstore.chroma_db import chroma_manager
    print("✅ ChromaDB manager imported successfully")
    
    # Test Arabic embedding
    print("🧪 Testing Arabic text processing...")
    test_result = chroma_manager.test_arabic_embedding("مرحبا كيف حالك؟")
    print(f"🧪 Arabic embedding test result: {test_result}")
    
    # Get stats
    stats = chroma_manager.get_stats()
    print(f"📊 ChromaDB stats: {stats}")
    
except Exception as e:
    print(f"❌ Error testing ChromaDB: {str(e)}")
    traceback.print_exc()

# Test 4: Check dependencies
print("\n4. Checking Dependencies...")
try:
    import pandas as pd
    print("✅ pandas imported successfully")
    
    import chromadb
    print("✅ chromadb imported successfully")
    
    import sentence_transformers
    print("✅ sentence_transformers imported successfully")
    
    print("✅ All dependencies are available")
    
except Exception as e:
    print(f"❌ Error with dependencies: {str(e)}")
    traceback.print_exc()

print("\n" + "=" * 60)
print("🏁 Test completed!") 