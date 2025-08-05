"""
YouTube Tracker 綜合測試套件
整合所有核心功能的測試，避免重複
"""

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from models.video import VideoMetadata
from models.channel import ChannelConfig
from storage.database import Video, Channel, get_session, DatabaseUtils


class YouTubeTrackerTests:
    """YouTube Tracker 綜合測試類別"""
    
    @staticmethod
    def create_test_video(video_id: str = "TESTYTB1234", title: str = "Test Video") -> VideoMetadata:
        """創建測試影片數據"""
        return VideoMetadata(
            video_id=video_id,
            channel_id="UC1234567890123456789012",
            title=title,
            description="Test video for comprehensive testing",
            published_at=datetime.utcnow(),
            thumbnail_url="https://i.ytimg.com/vi/test/hqdefault.jpg",
            duration="PT5M30S",
            view_count=1000,
            like_count=50,
            comment_count=10,
            url=f"https://www.youtube.com/watch?v={video_id}"
        )
    
    @staticmethod
    def create_test_channel(channel_id: str = "UC1234567890123456789012", is_active: bool = True) -> ChannelConfig:
        """創建測試頻道配置"""
        return ChannelConfig(
            channel_id=channel_id,
            channel_name="Test Channel",
            telegram_chat_id="123456789",
            check_interval=3600,
            is_active=is_active,
            last_check=datetime.utcnow() - timedelta(hours=2)
        )
    
    @staticmethod
    async def cleanup_test_data(identifier: str):
        """清理測試數據"""
        async for session in get_session():
            try:
                # 清理影片記錄
                if len(identifier) == 11 or identifier.startswith("TEST"):
                    video_record = await DatabaseUtils.get_video_by_id(session, identifier)
                    if video_record:
                        await session.delete(video_record)
                        await session.commit()
                
                # 清理頻道記錄
                if identifier.startswith("UC"):
                    channel_record = await DatabaseUtils.get_channel_by_id(session, identifier)
                    if channel_record:
                        await session.delete(channel_record)
                        await session.commit()
                    
                    # 清理該頻道的所有影片
                    from sqlalchemy import select
                    videos_to_delete = await session.execute(
                        select(Video).where(Video.channel_id == identifier)
                    )
                    for video in videos_to_delete.scalars():
                        await session.delete(video)
                    await session.commit()
                    
            except Exception:
                pass
            break
    
    async def test_duplicate_notification_prevention(self):
        """測試重複通知防護機制"""
        print("=" * 60)
        print("測試: 重複通知防護機制")
        print("=" * 60)
        
        test_video = self.create_test_video("DUPTEST1234", "Duplicate Test Video")
        test_channel = self.create_test_channel()
        
        # 清理舊數據
        await self.cleanup_test_data("DUPTEST1234")
        await self.cleanup_test_data("UC1234567890123456789012")
        
        try:
            # Mock API 調用
            with patch('tools.youtube_tools.get_channel_videos') as mock_get_videos:
                mock_get_videos.ainvoke = AsyncMock(return_value=[test_video])
                
                with patch('agents.telegram_agent.notify_new_video') as mock_notify:
                    mock_notify.ainvoke = AsyncMock()
                    mock_notify.ainvoke.return_value = AsyncMock()
                    mock_notify.ainvoke.return_value.success = True
                    
                    # 第一次處理 - 應該發送通知
                    from chains.tracking_chain import TrackingChain
                    tracking_chain = TrackingChain()
                    
                    result1 = await tracking_chain.execute_tracking_workflow(
                        channel_config=test_channel,
                        force_check=True
                    )
                    
                    print(f"第一次檢查 - 成功: {result1['success']}")
                    print(f"第一次檢查 - 處理影片數: {result1['videos_processed']}")
                    print(f"第一次檢查 - 發送通知數: {result1['notifications_sent']}")
                    
                    # 驗證第一次發送了通知
                    assert result1["success"], "第一次檢查應該成功"
                    assert result1["videos_processed"] == 1, "應該處理1個影片"
                    assert result1["notifications_sent"] == 1, "應該發送1個通知"
                    assert mock_notify.ainvoke.call_count == 1, "應該調用通知API一次"
                    
                    # 第二次處理 - 不應該重複發送通知
                    result2 = await tracking_chain.execute_tracking_workflow(
                        channel_config=test_channel,
                        force_check=True
                    )
                    
                    print(f"第二次檢查 - 成功: {result2['success']}")
                    print(f"第二次檢查 - 處理影片數: {result2['videos_processed']}")
                    print(f"第二次檢查 - 發送通知數: {result2['notifications_sent']}")
                    
                    # 驗證第二次沒有重複發送
                    assert result2["success"], "第二次檢查應該成功"
                    assert result2["videos_processed"] == 0, "不應該重複處理已處理的影片"
                    assert result2["notifications_sent"] == 0, "不應該發送重複通知"
                    assert mock_notify.ainvoke.call_count == 1, "通知API調用次數不應該增加"
                    
                    print("[OK] 重複通知防護機制正常工作")
                    return True
                    
        except Exception as e:
            print(f"[ERROR] 重複通知防護測試失敗: {e}")
            return False
        finally:
            await self.cleanup_test_data("DUPTEST1234")
            await self.cleanup_test_data("UC1234567890123456789012")
    
    async def test_no_new_videos_behavior(self):
        """測試無新影片時的行為"""
        print("\n" + "=" * 60)
        print("測試: 無新影片時的行為")
        print("=" * 60)
        
        test_channel = self.create_test_channel()
        
        try:
            # Mock 返回空影片列表
            with patch('tools.youtube_tools.get_channel_videos') as mock_get_videos:
                mock_get_videos.ainvoke = AsyncMock(return_value=[])
                
                with patch('agents.telegram_agent.notify_new_video') as mock_notify:
                    mock_notify.ainvoke = AsyncMock()
                    
                    from chains.tracking_chain import TrackingChain
                    tracking_chain = TrackingChain()
                    
                    result = await tracking_chain.execute_tracking_workflow(
                        channel_config=test_channel,
                        force_check=True
                    )
                    
                    print(f"無新影片檢查 - 成功: {result['success']}")
                    print(f"無新影片檢查 - 處理影片數: {result['videos_processed']}")
                    print(f"無新影片檢查 - 發送通知數: {result['notifications_sent']}")
                    print(f"無新影片檢查 - 無新影片標記: {result.get('no_new_videos', False)}")
                    
                    # 驗證行為
                    assert result["success"], "無新影片檢查應該成功"
                    assert result["videos_processed"] == 0, "不應該處理任何影片"
                    assert result["notifications_sent"] == 0, "不應該發送任何通知"
                    assert result.get("no_new_videos", False), "應該標記為無新影片"
                    assert mock_get_videos.ainvoke.call_count == 1, "應該調用YouTube API一次"
                    assert mock_notify.ainvoke.call_count == 0, "不應該調用通知API"
                    
                    print("[OK] 無新影片行為正常")
                    return True
                    
        except Exception as e:
            print(f"[ERROR] 無新影片行為測試失敗: {e}")
            return False
    
    async def test_inactive_channel_handling(self):
        """測試非活躍頻道處理"""
        print("\n" + "=" * 60)
        print("測試: 非活躍頻道處理")
        print("=" * 60)
        
        # 創建非活躍頻道
        inactive_channel = self.create_test_channel(is_active=False)
        
        # 清理並創建頻道記錄
        await self.cleanup_test_data("UC1234567890123456789012")
        
        async for session in get_session():
            channel_record = Channel(
                channel_id=inactive_channel.channel_id,
                channel_name=inactive_channel.channel_name,
                check_interval=inactive_channel.check_interval,
                telegram_chat_id=inactive_channel.telegram_chat_id,
                is_active=False,  # 設置為非活躍
                last_check=None,
                last_video_id=None
            )
            session.add(channel_record)
            await session.commit()
            break
        
        try:
            # Mock API 調用
            with patch('tools.youtube_tools.get_channel_videos') as mock_get_videos:
                mock_get_videos.ainvoke = AsyncMock(return_value=[])
                
                # 測試排程執行會跳過非活躍頻道
                from schedulers.channel_scheduler import execute_scheduled_tracking
                
                await execute_scheduled_tracking(inactive_channel.channel_id)
                
                # 驗證API沒有被調用
                assert mock_get_videos.ainvoke.call_count == 0, "非活躍頻道不應該調用YouTube API"
                
                print("[OK] 非活躍頻道正確被跳過")
                return True
                
        except Exception as e:
            print(f"[ERROR] 非活躍頻道測試失敗: {e}")
            return False
        finally:
            await self.cleanup_test_data("UC1234567890123456789012")
    
    async def test_notification_sent_without_summary(self):
        """測試無摘要時仍發送通知"""
        print("\n" + "=" * 60)
        print("測試: 無摘要時仍發送通知")
        print("=" * 60)
        
        test_video = self.create_test_video("NOSUMTEST12", "No Summary Test")
        test_channel = self.create_test_channel()
        
        await self.cleanup_test_data("NOSUMTEST12")
        await self.cleanup_test_data("UC1234567890123456789012")
        
        try:
            # Mock 摘要生成失敗
            with patch('agents.summarizer_agent.summarize_video_content') as mock_summarize:
                mock_summarize.ainvoke = AsyncMock()
                mock_summarize.ainvoke.side_effect = Exception("摘要API配額不足")
                
                # Mock 通知發送
                with patch('agents.telegram_agent.notify_new_video') as mock_notify:
                    mock_notify.ainvoke = AsyncMock()
                    mock_notify.ainvoke.return_value = AsyncMock()
                    mock_notify.ainvoke.return_value.success = True
                    
                    # 處理影片
                    from agents.youtube_tracker import youtube_tracker_agent
                    result = await youtube_tracker_agent._process_video(test_video, test_channel)
                    
                    print(f"處理結果 - 摘要生成: {result.get('summary_generated', False)}")
                    print(f"處理結果 - 通知發送: {result.get('notification_sent', False)}")
                    print(f"處理結果 - 錯誤: {result.get('error')}")
                    
                    # 驗證摘要失敗但通知仍然發送
                    assert result.get("summary_generated", False) == False, "摘要生成應該失敗"
                    assert result.get("notification_sent", False) == True, "通知應該仍然發送"
                    assert result.get("error") is not None, "應該記錄摘要錯誤"
                    assert mock_notify.ainvoke.call_count == 1, "應該調用通知API一次"
                    
                    # 檢查通知調用時摘要參數為None
                    call_args = mock_notify.ainvoke.call_args[0][0]
                    assert call_args["summary"] is None, "摘要參數應該為None"
                    
                    print("[OK] 無摘要時通知仍然正常發送")
                    return True
                    
        except Exception as e:
            print(f"[ERROR] 無摘要通知測試失敗: {e}")
            return False
        finally:
            await self.cleanup_test_data("NOSUMTEST12")
            await self.cleanup_test_data("UC1234567890123456789012")
    
    async def test_channel_state_update(self):
        """測試頻道狀態更新"""
        print("\n" + "=" * 60)  
        print("測試: 頻道狀態更新")
        print("=" * 60)
        
        test_video = self.create_test_video("STATETEST12", "State Update Test")
        test_channel = self.create_test_channel()
        
        await self.cleanup_test_data("STATETEST12")
        await self.cleanup_test_data("UC1234567890123456789012")
        
        # 創建頻道記錄
        initial_time = datetime.utcnow() - timedelta(hours=1)
        async for session in get_session():
            channel_record = Channel(
                channel_id=test_channel.channel_id,
                channel_name=test_channel.channel_name,
                check_interval=test_channel.check_interval,
                telegram_chat_id=test_channel.telegram_chat_id,
                is_active=True,
                last_check=initial_time,
                last_video_id=None
            )
            session.add(channel_record)
            await session.commit()
            break
        
        try:
            with patch('tools.youtube_tools.get_channel_videos') as mock_get_videos:
                mock_get_videos.ainvoke = AsyncMock(return_value=[test_video])
                
                with patch('agents.telegram_agent.notify_new_video') as mock_notify:
                    mock_notify.ainvoke = AsyncMock()
                    mock_notify.ainvoke.return_value = AsyncMock()
                    mock_notify.ainvoke.return_value.success = True
                    
                    from chains.tracking_chain import TrackingChain
                    tracking_chain = TrackingChain()
                    
                    result = await tracking_chain.execute_tracking_workflow(
                        channel_config=test_channel,
                        force_check=True
                    )
                    
                    print(f"狀態更新 - 成功: {result['success']}")
                    
                    # 檢查資料庫中的頻道狀態
                    async for session in get_session():
                        updated_channel = await DatabaseUtils.get_channel_by_id(session, test_channel.channel_id)
                        if updated_channel:
                            print(f"更新後的 last_check: {updated_channel.last_check}")
                            print(f"更新後的 last_video_id: {updated_channel.last_video_id}")
                            
                            # 驗證狀態已更新
                            assert updated_channel.last_check > initial_time, "last_check 應該被更新"
                            assert updated_channel.last_video_id == test_video.video_id, "last_video_id 應該被設置"
                            
                            print("[OK] 頻道狀態正確更新")
                            return True
                        else:
                            print("[ERROR] 找不到頻道記錄")
                            return False
                        break
                        
        except Exception as e:
            print(f"[ERROR] 頻道狀態更新測試失敗: {e}")
            return False
        finally:
            await self.cleanup_test_data("STATETEST12")
            await self.cleanup_test_data("UC1234567890123456789012")


async def run_comprehensive_tests():
    """執行所有綜合測試"""
    print("開始執行 YouTube Tracker 綜合測試...")
    print("=" * 80)
    
    test_suite = YouTubeTrackerTests()
    
    tests = [
        ("重複通知防護", test_suite.test_duplicate_notification_prevention),
        ("無新影片行為", test_suite.test_no_new_videos_behavior),
        ("非活躍頻道處理", test_suite.test_inactive_channel_handling),
        ("無摘要通知", test_suite.test_notification_sent_without_summary),
        ("頻道狀態更新", test_suite.test_channel_state_update)
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
    print("測試總結:")
    print(f"通過: {passed}")
    print(f"失敗: {failed}")
    print(f"總計: {passed + failed}")
    
    if failed == 0:
        print("\n[SUCCESS] 所有測試通過！")
        return True
    else:
        print(f"\n[WARNING] {failed} 個測試失敗")
        return False


if __name__ == "__main__":
    success = asyncio.run(run_comprehensive_tests())
    exit(0 if success else 1)