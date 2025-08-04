"""
Test to verify that the Telegram notification fix is working properly.
This test ensures notifications are sent successfully for new videos.
"""

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from unittest.mock import AsyncMock, patch
from models.video import VideoMetadata
from tools.telegram_tools import send_video_notification


async def test_notification_fix():
    """Test that the notification fix handles long summaries correctly."""
    print("="*70)
    print("Testing Notification Fix")
    print("="*70)
    
    try:
        # Create a test video with potential problematic title
        test_video = VideoMetadata(
            video_id="NOTIFTEST12",  # 11 characters
            channel_id="UCerJk0-d22M7MFy8opOuyjA",
            title="[ 阿伟科普 ] 混合律師和其他工程師方法 Polymerization",  # Contains special chars
            description="Test video for notification fix verification",
            published_at=datetime.utcnow(),
            thumbnail_url="https://i.ytimg.com/vi/qVhLXKLFQVQ/hqdefault.jpg",
            duration="PT6M49S",
            view_count=94896,
            like_count=3051,
            comment_count=430,
            url="https://www.youtube.com/watch?v=NOTIFTEST12"
        )
        
        # Create a long summary (over 1000 characters)
        long_summary = """
這是一個非常長的摘要，用來測試 Telegram 通知系統是否能正確處理長文本。
這個摘要包含了許多詳細的資訊，包括影片的主要內容、重點摘要、以及其他相關資訊。
在這個測試中，我們要確保系統能夠正確處理超過 1024 字元限制的情況。
Telegram 的照片說明有字元限制，所以我們需要確保系統能夠分割訊息。
這個測試驗證了我們的修復是否正確工作，能夠處理各種邊緣情況。
包括特殊字元、長文本、以及各種 Markdown 格式。
系統應該能夠自動檢測訊息長度並採取適當的處理方式。
如果訊息太長，應該分成多個部分發送。
如果照片發送失敗，應該回退到純文字訊息。
這些都是我們在修復中實現的功能。
""" * 5  # Make it really long
        
        test_chat_id = "6121833171"
        
        print("Testing video: Special Characters Title")
        print(f"Summary length: {len(long_summary)} characters")
        print(f"Chat ID: {test_chat_id}")
        
        # Test 1: Long summary (should split into photo + text)
        print("\n1. Testing long summary handling...")
        try:
            result = await send_video_notification.ainvoke({
                "video": test_video,
                "summary": long_summary,
                "chat_id": test_chat_id,
                "include_thumbnail": True
            })
            
            if result.success:
                print("   [OK] Long summary notification sent successfully!")
                print(f"   Message ID: {result.message_id}")
            else:
                print(f"   [ERROR] Long summary notification failed: {result.error_message}")
                return False
                
        except Exception as e:
            print(f"   [ERROR] Exception during long summary test: {e}")
            return False
        
        # Test 2: Short summary (should send as single photo with caption)
        print("\n2. Testing short summary handling...")
        short_summary = "這是一個簡短的摘要，用來測試正常的通知功能。"
        
        try:
            result = await send_video_notification.ainvoke({
                "video": test_video,
                "summary": short_summary,
                "chat_id": test_chat_id,
                "include_thumbnail": True
            })
            
            if result.success:
                print("   [OK] Short summary notification sent successfully!")
                print(f"   Message ID: {result.message_id}")
            else:
                print(f"   [ERROR] Short summary notification failed: {result.error_message}")
                return False
                
        except Exception as e:
            print(f"   [ERROR] Exception during short summary test: {e}")
            return False
        
        # Test 3: No summary (should send basic notification)
        print("\n3. Testing no summary handling...")
        try:
            result = await send_video_notification.ainvoke({
                "video": test_video,
                "summary": None,
                "chat_id": test_chat_id,
                "include_thumbnail": True
            })
            
            if result.success:
                print("   [OK] No summary notification sent successfully!")
                print(f"   Message ID: {result.message_id}")
            else:
                print(f"   [ERROR] No summary notification failed: {result.error_message}")
                return False
                
        except Exception as e:
            print(f"   [ERROR] Exception during no summary test: {e}")
            return False
        
        # Test 4: Text-only (no thumbnail)
        print("\n4. Testing text-only notification...")
        try:
            result = await send_video_notification.ainvoke({
                "video": test_video,
                "summary": "測試純文字通知功能",
                "chat_id": test_chat_id,
                "include_thumbnail": False
            })
            
            if result.success:
                print("   [OK] Text-only notification sent successfully!")
                print(f"   Message ID: {result.message_id}")
            else:
                print(f"   [ERROR] Text-only notification failed: {result.error_message}")
                return False
                
        except Exception as e:
            print(f"   [ERROR] Exception during text-only test: {e}")
            return False
        
        print("\n" + "="*70)
        print("[SUCCESS] All notification tests passed!")
        print("[OK] Long summary handling works correctly")
        print("[OK] Short summary handling works correctly") 
        print("[OK] No summary handling works correctly")
        print("[OK] Text-only notifications work correctly")
        print("[OK] Notification fix is fully functional")
        print("="*70)
        
        return True
        
    except Exception as e:
        print(f"\n[ERROR] Notification fix test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_test():
    """Run the notification fix verification test."""
    print("Running Notification Fix Verification Test...")
    
    try:
        success = await test_notification_fix()
        
        if success:
            print("\n[SUCCESS] Notification fix verification completed successfully!")
            return True
        else:
            print("\n[ERROR] Notification fix verification failed!")
            return False
            
    except Exception as e:
        print(f"\n[ERROR] Test execution failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(run_test())
    if success:
        exit(0)
    else:
        exit(1)