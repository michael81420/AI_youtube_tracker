"""
簡單測試腳本來驗證通知重複發送的修正
"""

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from models.video import VideoMetadata
from models.channel import ChannelConfig
from storage.database import Video, get_session, DatabaseUtils
from agents.youtube_tracker import youtube_tracker_agent
from datetime import datetime

async def test_notification_duplicate_prevention():
    """測試通知重複發送的防護機制"""
    
    # 創建測試影片數據
    test_video = VideoMetadata(
        video_id="dQw4w9WgXcQ",  # 11 字元的測試 ID
        channel_id="UC1234567890123456789012",
        title="Test Video",
        description="Test description",
        published_at=datetime.utcnow(),
        thumbnail_url="https://example.com/thumb.jpg",
        duration="PT5M30S",
        view_count=1000,
        like_count=50,
        comment_count=10
    )
    
    test_channel = ChannelConfig(
        channel_id="UC1234567890123456789012",
        channel_name="Test Channel",
        telegram_chat_id="123456789",
        check_interval=3600
    )
    
    print("[TEST 1] 檢查新影片處理...")
    
    # 清理測試數據
    async for session in get_session():
        existing = await DatabaseUtils.get_video_by_id(session, test_video.video_id)
        if existing:
            await session.delete(existing)
            await session.commit()
        break
    
    # 模擬首次處理（應該會嘗試處理）
    try:
        result1 = await youtube_tracker_agent.process_video(test_video, test_channel)
        print(f"[OK] 首次處理結果: already_processed={result1.get('already_processed', False)}")
        print(f"     notification_sent={result1.get('notification_sent', False)}")
    except Exception as e:
        print(f"[WARN] 首次處理失敗（預期的，因為缺少外部服務）: {e}")
    
    print("\n[TEST 2] 手動設置已通知狀態並重新測試...")
    
    # 手動設置影片為已通知狀態
    async for session in get_session():
        video_record = await DatabaseUtils.get_video_by_id(session, test_video.video_id)
        if video_record:
            video_record.notification_sent = True
            video_record.processed_at = datetime.utcnow()
            video_record.summary = "Test summary"
            await session.commit()
            print("[OK] 已設置影片為已通知狀態")
        else:
            # 創建已通知的影片記錄
            new_video = Video(
                video_id=test_video.video_id,
                channel_id=test_channel.channel_id,
                title=test_video.title,
                description=test_video.description,
                published_at=test_video.published_at,
                thumbnail_url=test_video.thumbnail_url,
                duration=test_video.duration,
                view_count=test_video.view_count,
                like_count=test_video.like_count,
                comment_count=test_video.comment_count,
                processed_at=datetime.utcnow(),
                summary="Test summary",
                notification_sent=True
            )
            session.add(new_video)
            await session.commit()
            print("[OK] 已創建已通知的影片記錄")
        break
    
    # 再次處理同一影片（應該跳過）
    result2 = await youtube_tracker_agent.process_video(test_video, test_channel)
    print(f"[OK] 重複處理結果: already_processed={result2.get('already_processed', False)}")
    print(f"     notification_sent={result2.get('notification_sent', False)}")
    
    if result2.get('already_processed') and result2.get('notification_sent'):
        print("[SUCCESS] 通知重複發送防護機制正常工作！")
    else:
        print("[ERROR] 通知重複發送防護機制存在問題！")
    
    print("\n[TEST 3] 測試已處理但未通知的情況...")
    
    # 設置為已處理但未通知
    async for session in get_session():
        video_record = await DatabaseUtils.get_video_by_id(session, test_video.video_id)
        if video_record:
            video_record.notification_sent = False  # 設為未通知
            await session.commit()
            print("[OK] 已設置影片為已處理但未通知狀態")
        break
    
    # 再次處理（應該只發送通知）
    try:
        result3 = await youtube_tracker_agent.process_video(test_video, test_channel)
        print(f"[OK] 未通知影片處理結果: already_processed={result3.get('already_processed', False)}")
        print(f"     summary_generated={result3.get('summary_generated', False)}")
        if result3.get('already_processed') and result3.get('summary_generated'):
            print("[SUCCESS] 已處理影片的通知補發機制正常工作！")
        else:
            print("[ERROR] 已處理影片的通知補發機制存在問題！")
    except Exception as e:
        print(f"[WARN] 通知補發測試失敗（預期的，因為缺少 Telegram API）: {e}")
    
    # 清理測試數據
    async for session in get_session():
        existing = await DatabaseUtils.get_video_by_id(session, test_video.video_id)
        if existing:
            await session.delete(existing)
            await session.commit()
            print("[CLEANUP] 測試數據已清理")
        break

if __name__ == "__main__":
    asyncio.run(test_notification_duplicate_prevention())