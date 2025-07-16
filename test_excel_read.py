#!/usr/bin/env python3
"""
Test script to verify Excel reading functionality
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.excel_manager import csv_manager

def test_excel_read():
    """Test reading Excel file"""
    print("🧪 Testing Excel file reading...")
    
    try:
        qa_pairs = csv_manager.read_qa_pairs()
        
        if qa_pairs:
            print(f"✅ Successfully read {len(qa_pairs)} Q&A pairs from Excel file!")
            print(f"📊 First question: {qa_pairs[0]['question'][:50]}...")
            print(f"📊 First answer: {qa_pairs[0]['answer'][:50]}...")
            print(f"📊 Language: {qa_pairs[0]['language']}")
            print(f"📊 Category: {qa_pairs[0]['category']}")
            
            # Test stats
            stats = csv_manager.get_stats()
            print(f"\n📈 Stats:")
            print(f"   Total: {stats['total']}")
            print(f"   Languages: {stats['languages']}")
            print(f"   Categories: {stats['categories']}")
            
            return True
        else:
            print("❌ No Q&A pairs found in Excel file")
            return False
            
    except Exception as e:
        print(f"❌ Error reading Excel file: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_excel_read()
    if success:
        print("\n🎉 Excel functionality is working correctly!")
    else:
        print("\n❌ Excel functionality has issues") 