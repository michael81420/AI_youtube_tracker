"""
檢查最近處理的影片總結內容
"""

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from storage.database import get_session, DatabaseUtils


async def check_recent_summaries():
    """檢查最近的影片總結"""
    print("=" * 70)
    print("檢查最近處理的影片總結")
    print("=" * 70)
    
    try:
        async for session in get_session():
            # 獲取最近的影片記錄
            from sqlalchemy import select, desc
            from storage.database import Video
            
            result = await session.execute(
                select(Video).order_by(desc(Video.processed_at)).limit(3)
            )
            
            videos = result.scalars().all()
            
            if not videos:
                print("沒有找到任何影片記錄")
                break
            
            print(f"找到 {len(videos)} 個最近的影片記錄:\n")
            
            for i, video in enumerate(videos, 1):
                print(f"{i}. 影片ID: {video.video_id}")
                print(f"   標題: {video.title}")
                print(f"   處理時間: {video.processed_at}")
                print(f"   通知已發送: {video.notification_sent}")
                print(f"   總結長度: {len(video.summary) if video.summary else 0} 字元")
                
                if video.summary:
                    print(f"   總結內容:")
                    # 只顯示前300字元避免太長
                    summary_preview = video.summary[:300]
                    if len(video.summary) > 300:
                        summary_preview += "..."
                    print(f"   {summary_preview}")
                else:
                    print("   [ERROR] 沒有總結內容!")
                
                print("-" * 50)
            
            break
            
    except Exception as e:
        print(f"[ERROR] 檢查總結時發生錯誤: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(check_recent_summaries())