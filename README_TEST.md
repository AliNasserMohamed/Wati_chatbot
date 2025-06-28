# 🧪 Abar Embedding Agent Test Suite

This test suite validates the embedding agent functionality with vector similarity search using ChromaDB and cosine similarity.

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Set Up Environment Variables
Create a `.env` file in the project root:
```bash
OPENAI_API_KEY=your_openai_api_key_here
```

### 3. Run the Tests
```bash
# Option 1: Direct test
python test_embedding_agent.py

# Option 2: Using the runner script
python run_test.py
```

## 📋 What the Test Does

### 🔍 **ChromaDB Direct Search Test**
- Tests vector similarity search directly
- Shows similarity scores and distances
- Tests with Arabic and English queries

### 🤖 **Embedding Agent Flow Test**
Tests the complete flow:
```
📱 Message → 🔍 ChromaDB Search → 🎯 Similarity Check → 🤖 LLM Validation → 📤 Response
```

### 📊 **Test Cases**
1. **High Similarity Test**: `"كيف يمكنني طلب المياه من ابار؟"`
   - Expected: Direct reply (skip LLM validation)
   
2. **Moderate Similarity Test**: `"اريد اطلب ماء"`
   - Expected: LLM evaluation required
   
3. **Low Similarity Test**: `"كيف حالك اليوم؟"`
   - Expected: Continue to classification
   
4. **Delivery Time Query**: `"متى سيصل طلبي؟"`
   - Expected: Match delivery information
   
5. **English Test**: `"How can I order water?"`
   - Expected: Cross-language similarity test
   
6. **Greeting Test**: `"السلام عليكم"`
   - Expected: Skip or continue to classification

## 📈 Expected Output

The test will show:
- ✅ **Detailed similarity scores** for each query
- 📊 **ChromaDB search results** with cosine similarity
- 🔍 **Complete decision flow** with explanations
- 📝 **LLM evaluation process** when needed
- 📋 **Test summary** with action counts

## 🎯 Key Features Tested

### Vector Similarity Search
- ✅ Cosine similarity calculation (0-1 scale)
- ✅ Distance to similarity conversion
- ✅ Proper sorting by similarity score

### Smart Thresholds
- ✅ `similarity_threshold = 0.20` (minimum to consider)
- ✅ `high_similarity_threshold = 0.80` (skip LLM validation)

### LLM Integration
- ✅ ChatGPT evaluation for moderate similarity
- ✅ Context-aware responses
- ✅ Multi-language support

## 🔧 Troubleshooting

### Common Issues

1. **ImportError**: Make sure all dependencies are installed
   ```bash
   pip install -r requirements.txt
   ```

2. **OpenAI API Error**: Check your API key in `.env` file

3. **ChromaDB Error**: Delete `vectorstore/data` folder and restart

4. **Encoding Issues**: Ensure your terminal supports UTF-8 for Arabic text

## 📊 Sample Output

```
🔍 ChromaDB: Search completed for query: 'كيف يمكنني طلب المياه من ابار...'
   - Found 3 results
   - Result 1: Similarity=0.8500, Distance=0.1500
   - Result 2: Similarity=0.7200, Distance=0.2800

🎯 EmbeddingAgent: Best match selected (sorted by ChromaDB):
   - Cosine Similarity: 0.8500
   - Flow: Message → ChromaDB → High Similarity → DIRECT REPLY (Skip LLM)

📊 RESULT:
   - Action: reply
   - Confidence: 0.8500
   - Response: يمكنك طلب المياه من خلال تطبيق ابار...
```

## 🎉 Success Criteria

The test is successful if:
- ✅ All imports work correctly
- ✅ ChromaDB search returns similarity scores
- ✅ High similarity queries get direct replies
- ✅ Low similarity queries continue to classification
- ✅ LLM evaluation works for moderate similarity
- ✅ Arabic text is displayed correctly

---

**Happy Testing! 🚀** 