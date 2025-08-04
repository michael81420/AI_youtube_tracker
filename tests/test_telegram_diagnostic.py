"""
Diagnostic test for Telegram API issues.
This test helps identify why Telegram notifications are failing.
"""

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import get_settings
from tools.telegram_tools import telegram_client


async def test_telegram_connection():
    """Test basic Telegram bot connection."""
    print("="*70)
    print("TELEGRAM API DIAGNOSTIC TEST")
    print("="*70)
    
    try:
        settings = get_settings()
        print(f"Bot token configured: {'Yes' if settings.telegram_bot_token else 'No'}")
        
        if not settings.telegram_bot_token:
            print("[ERROR] No Telegram bot token configured!")
            return False
        
        # Test bot connection
        print("\n1. Testing bot connection...")
        try:
            bot_info = await telegram_client.get_me()
            print(f"   [OK] Bot connected: @{bot_info.get('username', 'Unknown')}")
            print(f"   Bot ID: {bot_info.get('id')}")
            print(f"   Bot name: {bot_info.get('first_name')}")
        except Exception as e:
            print(f"   [ERROR] Bot connection failed: {e}")
            return False
        
        # Test chat validation
        print("\n2. Testing chat validation...")
        test_chat_id = "6121833171"  # From the logs
        
        try:
            chat_info = await telegram_client.get_chat(test_chat_id)
            print(f"   [OK] Chat found: {chat_info.get('type')}")
            if 'title' in chat_info:
                print(f"   Chat title: {chat_info['title']}")
            if 'username' in chat_info:
                print(f"   Chat username: @{chat_info['username']}")
        except Exception as e:
            print(f"   [ERROR] Chat validation failed: {e}")
            print(f"   This suggests the bot cannot access chat {test_chat_id}")
            return False
        
        # Test simple message sending
        print("\n3. Testing simple message sending...")
        try:
            result = await telegram_client.send_message(
                chat_id=test_chat_id,
                text="🤖 Diagnostic test message from YouTube tracker"
            )
            print(f"   [OK] Message sent successfully!")
            print(f"   Message ID: {result.get('message_id')}")
        except Exception as e:
            print(f"   [ERROR] Message sending failed: {e}")
            return False
        
        # Test photo sending (this is what's failing)
        print("\n4. Testing photo sending...")
        try:
            test_photo_url = "https://i.ytimg.com/vi/qVhLXKLFQVQ/hqdefault.jpg"
            result = await telegram_client.send_photo(
                chat_id=test_chat_id,
                photo_url=test_photo_url,
                caption="📹 Test photo from YouTube tracker"
            )
            print(f"   [OK] Photo sent successfully!")
            print(f"   Message ID: {result.get('message_id')}")
        except Exception as e:
            print(f"   [ERROR] Photo sending failed: {e}")
            print(f"   This is the exact error causing notification failures!")
            print(f"   Error details: {str(e)}")
            
            # Try sending without photo
            print("\n5. Testing notification without photo...")
            try:
                result = await telegram_client.send_message(
                    chat_id=test_chat_id,
                    text="📹 **New Video Alert** (without photo)\n\n**Title:** Test Video\n**Link:** https://youtube.com/watch?v=test"
                )
                print(f"   [OK] Text-only notification works!")
                print(f"   Message ID: {result.get('message_id')}")
                print(f"   [SOLUTION] Consider sending text-only notifications when photo fails")
            except Exception as e2:
                print(f"   [ERROR] Even text-only notification failed: {e2}")
            
            return False
        
        print("\n" + "="*70)
        print("[SUCCESS] All Telegram API tests passed!")
        print("Notifications should work correctly.")
        print("="*70)
        return True
        
    except Exception as e:
        print(f"\n[ERROR] Diagnostic test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_diagnostic():
    """Run the Telegram diagnostic test."""
    print("Running Telegram API Diagnostic Test...")
    
    try:
        success = await test_telegram_connection()
        
        if success:
            print("\n[SUCCESS] Telegram API is working correctly!")
            return True
        else:
            print("\n[ERROR] Telegram API has issues that need to be resolved!")
            return False
            
    except Exception as e:
        print(f"\n[ERROR] Diagnostic execution failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(run_diagnostic())
    if success:
        exit(0)
    else:
        exit(1)