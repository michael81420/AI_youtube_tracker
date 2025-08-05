"""
Telegram 通知系統測試
測試各種通知場景和錯誤處理
"""

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from models.video import VideoMetadata
from tools.telegram_tools import send_video_notification


class TelegramNotificationTests:
    """Telegram 通知測試類別"""
    
    @staticmethod
    def create_test_video(video_id: str = "TELETEST123", title: str = "Telegram Test Video") -> VideoMetadata:
        """創建測試影片"""
        return VideoMetadata(
            video_id=video_id,
            channel_id="UCerJk0-d22M7MFy8opOuyjA",
            title=title,
            description="Test video for Telegram notification testing",
            published_at=datetime.utcnow(),
            thumbnail_url="https://i.ytimg.com/vi/test/hqdefault.jpg",
            duration="PT3M45S",
            view_count=1500,
            like_count=75,
            comment_count=20,
            url=f"https://www.youtube.com/watch?v={video_id}"
        )
    
    async def test_short_summary_notification(self):
        """測試短摘要通知"""
        print("=" * 60)
        print("測試: 短摘要通知")
        print("=" * 60)
        
        test_video = self.create_test_video("SHORTSUM123", "Short Summary Test")
        short_summary = "這是一個簡短的測試摘要，用來驗證正常的通知功能。"
        test_chat_id = "6121833171"
        
        try:
            result = await send_video_notification.ainvoke({
                "video": test_video,
                "summary": short_summary,
                "chat_id": test_chat_id,
                "include_thumbnail": True
            })
            
            print(f"短摘要通知 - 成功: {result.success}")
            print(f"短摘要通知 - 訊息ID: {result.message_id}")
            print(f"短摘要通知 - 錯誤: {result.error_message}")
            
            assert result.success, f"短摘要通知應該成功: {result.error_message}"
            assert result.message_id is not None, "應該有訊息ID"
            
            print("[OK] 短摘要通知成功")
            return True
            
        except Exception as e:
            print(f"[ERROR] 短摘要通知測試失敗: {e}")
            return False
    
    async def test_long_summary_notification(self):
        """測試長摘要通知（會分割成多個訊息）"""
        print("\n" + "=" * 60)
        print("測試: 長摘要通知")
        print("=" * 60)
        
        test_video = self.create_test_video("LONGSUM1234", "Long Summary Test")
        
        # 創建超過1000字符的長摘要
        long_summary = """
這是一個非常詳細的影片摘要，用來測試系統處理長文本的能力。
這個摘要包含了大量的資訊，包括影片的主要內容、關鍵觀點、討論要點等等。
當摘要文本超過Telegram的字符限制時，系統應該能夠智能地處理這種情況。
系統會首先發送縮圖和簡短標題，然後再發送完整的摘要文本。
這樣可以確保用戶能夠收到完整的資訊，同時避免Telegram API的限制。
這種處理方式既保證了用戶體驗，又確保了系統的穩定性。
影片內容涵蓋了多個技術主題，包括軟體開發、系統架構、資料庫設計等。
講者詳細解釋了各種概念和實作方法，提供了豐富的實例和案例研究。
觀眾可以從中學習到實用的技能和知識，應用到自己的工作和專案中。
這是教育性內容，對於專業發展具有很高的價值。
        """ * 3  # 重複3次使其變得很長
        
        test_chat_id = "6121833171"
        
        try:
            result = await send_video_notification.ainvoke({
                "video": test_video,
                "summary": long_summary,
                "chat_id": test_chat_id,
                "include_thumbnail": True
            })
            
            print(f"長摘要通知 - 成功: {result.success}")
            print(f"長摘要通知 - 訊息ID: {result.message_id}")
            print(f"長摘要長度: {len(long_summary)} 字符")
            
            assert result.success, f"長摘要通知應該成功: {result.error_message}"
            
            print("[OK] 長摘要通知成功（系統自動分割處理）")
            return True
            
        except Exception as e:
            print(f"[ERROR] 長摘要通知測試失敗: {e}")
            return False
    
    async def test_no_summary_notification(self):
        """測試無摘要通知"""
        print("\n" + "=" * 60)
        print("測試: 無摘要通知")
        print("=" * 60)
        
        test_video = self.create_test_video("NOSUM123456", "No Summary Test")
        test_chat_id = "6121833171"
        
        try:
            result = await send_video_notification.ainvoke({
                "video": test_video,
                "summary": None,
                "chat_id": test_chat_id,
                "include_thumbnail": True
            })
            
            print(f"無摘要通知 - 成功: {result.success}")
            print(f"無摘要通知 - 訊息ID: {result.message_id}")
            
            assert result.success, f"無摘要通知應該成功: {result.error_message}"
            
            print("[OK] 無摘要通知成功")
            return True
            
        except Exception as e:
            print(f"[ERROR] 無摘要通知測試失敗: {e}")
            return False
    
    async def test_text_only_notification(self):
        """測試純文字通知（無縮圖）"""
        print("\n" + "=" * 60)
        print("測試: 純文字通知")
        print("=" * 60)
        
        test_video = self.create_test_video("TEXTONLY123", "Text Only Test")
        test_summary = "這是純文字通知測試，不包含縮圖。"
        test_chat_id = "6121833171"
        
        try:
            result = await send_video_notification.ainvoke({
                "video": test_video,
                "summary": test_summary,
                "chat_id": test_chat_id,
                "include_thumbnail": False
            })
            
            print(f"純文字通知 - 成功: {result.success}")
            print(f"純文字通知 - 訊息ID: {result.message_id}")
            
            assert result.success, f"純文字通知應該成功: {result.error_message}"
            
            print("[OK] 純文字通知成功")
            return True
            
        except Exception as e:
            print(f"[ERROR] 純文字通知測試失敗: {e}")
            return False
    
    async def test_special_characters_handling(self):
        """測試特殊字符處理"""
        print("\n" + "=" * 60)
        print("測試: 特殊字符處理")
        print("=" * 60)
        
        # 包含特殊Markdown字符的標題
        special_title = "[ 測試 ] *重要* _內容_ `代碼` \\反斜線\\ **粗體**"
        test_video = self.create_test_video("SPECIAL1234", special_title)
        test_summary = "這個摘要包含特殊字符: *星號* _下劃線_ `反引號` [方括號] {大括號}"
        test_chat_id = "6121833171"
        
        try:
            result = await send_video_notification.ainvoke({
                "video": test_video,
                "summary": test_summary,
                "chat_id": test_chat_id,
                "include_thumbnail": True
            })
            
            print(f"特殊字符通知 - 成功: {result.success}")
            print(f"特殊字符通知 - 訊息ID: {result.message_id}")
            
            assert result.success, f"特殊字符通知應該成功: {result.error_message}"
            
            print("[OK] 特殊字符處理成功")
            return True
            
        except Exception as e:
            print(f"[ERROR] 特殊字符處理測試失敗: {e}")
            return False


async def run_notification_tests():
    """執行所有通知測試"""
    print("開始執行 Telegram 通知系統測試...")
    print("=" * 80)
    
    test_suite = TelegramNotificationTests()
    
    tests = [
        ("短摘要通知", test_suite.test_short_summary_notification),
        ("長摘要通知", test_suite.test_long_summary_notification),
        ("無摘要通知", test_suite.test_no_summary_notification),
        ("純文字通知", test_suite.test_text_only_notification),
        ("特殊字符處理", test_suite.test_special_characters_handling)
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            print(f"\n執行測試: {test_name}")
            result = await test_func()
            if result:
                passed += 1
                print(f"[PASS] {test_name} - 通過")
            else:
                failed += 1
                print(f"[FAIL] {test_name} - 失敗")
        except Exception as e:
            failed += 1
            print(f"[ERROR] {test_name} - 異常: {e}")
    
    print("\n" + "=" * 80)
    print("通知測試總結:")
    print(f"通過: {passed}")
    print(f"失敗: {failed}")
    print(f"總計: {passed + failed}")
    
    if failed == 0:
        print("\n[SUCCESS] 所有通知測試通過！")
        return True
    else:
        print(f"\n[WARNING] {failed} 個通知測試失敗")
        return False


if __name__ == "__main__":
    success = asyncio.run(run_notification_tests())
    exit(0 if success else 1)