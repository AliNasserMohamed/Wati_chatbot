#!/usr/bin/env python3
"""
Test script to verify the embedding agent fix for None handling
"""
import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agents.embedding_agent import embedding_agent

async def test_embedding_agent():
    """Test the embedding agent with the problematic input"""
    
    test_message = "السلام عليكم"
    
    print(f"🧪 Testing embedding agent with message: '{test_message}'")
    print("=" * 60)
    
    try:
        result = await embedding_agent.process_message(
            user_message=test_message,
            conversation_history=[],
            user_language='ar',
            journey_id="test_journey_123"
        )
        
        print(f"\n✅ Test completed successfully!")
        print(f"Result: {result}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Main test function"""
    print("🔧 Testing Embedding Agent Fix")
    print("=" * 40)
    
    success = await test_embedding_agent()
    
    if success:
        print(f"\n🎉 All tests passed! The fix is working correctly.")
    else:
        print(f"\n❌ Tests failed. Please check the error messages above.")
    
    return success

if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print(f"\n🛑 Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        sys.exit(1)
