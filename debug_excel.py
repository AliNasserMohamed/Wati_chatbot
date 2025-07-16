#!/usr/bin/env python3
"""
Debug script to understand Excel file structure
"""
import pandas as pd
import json

def debug_excel():
    """Debug Excel file structure"""
    print("🔍 Debugging Excel file structure...")
    
    try:
        df = pd.read_excel('knowledge_base/chatbot_qa_pairs.xlsx', engine='openpyxl')
        
        print(f"📊 Shape: {df.shape}")
        print(f"📊 Columns: {df.columns.tolist()}")
        print(f"📊 Column types: {df.dtypes}")
        
        # Check for missing values
        print(f"\n🔍 Missing values:")
        print(df.isnull().sum())
        
        # Show first few rows
        print(f"\n📝 First 3 rows:")
        for i in range(min(3, len(df))):
            row = df.iloc[i]
            print(f"Row {i}:")
            for col in df.columns:
                value = row[col]
                print(f"  {col}: '{value}' (type: {type(value)})")
            print()
        
        # Test reading specific columns
        print(f"🧪 Testing column access...")
        if 'question' in df.columns:
            print(f"   ✅ 'question' column found")
            print(f"   First question: '{df['question'].iloc[0]}'")
        else:
            print(f"   ❌ 'question' column NOT found")
            
        if 'answer' in df.columns:
            print(f"   ✅ 'answer' column found")
            print(f"   First answer: '{df['answer'].iloc[0]}'")
        else:
            print(f"   ❌ 'answer' column NOT found")
            
        return True
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    debug_excel() 