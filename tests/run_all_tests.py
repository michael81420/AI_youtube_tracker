"""
測試執行工具
執行所有整理後的測試並生成報告
"""

import asyncio
import sys
import os
import time
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from test_youtube_tracker_comprehensive import run_comprehensive_tests
from test_telegram_notifications import run_notification_tests
from test_system_integration import run_integration_tests


async def run_all_tests():
    """執行所有測試套件"""
    print("[TESTS] YouTube Tracker 完整測試套件")
    print("=" * 100)
    print(f"開始時間: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 100)
    
    test_suites = [
        ("YouTube Tracker 核心功能測試", run_comprehensive_tests),
        ("Telegram 通知系統測試", run_notification_tests),
        ("系統整合測試", run_integration_tests)
    ]
    
    total_passed = 0
    total_failed = 0
    suite_results = []
    
    for suite_name, suite_func in test_suites:
        print(f"\n[RUNNING] 執行測試套件: {suite_name}")
        print("-" * 80)
        
        try:
            start_time = time.time()
            result = await suite_func()
            end_time = time.time()
            
            execution_time = end_time - start_time
            
            if result:
                suite_results.append((suite_name, "[PASS] 通過", execution_time))
                total_passed += 1
                print(f"[PASS] {suite_name} - 全部通過 (耗時: {execution_time:.2f}秒)")
            else:
                suite_results.append((suite_name, "[FAIL] 失敗", execution_time))
                total_failed += 1
                print(f"[FAIL] {suite_name} - 部分或全部失敗 (耗時: {execution_time:.2f}秒)")
                
        except Exception as e:
            suite_results.append((suite_name, f"[ERROR] 異常: {e}", 0))
            total_failed += 1
            print(f"[ERROR] {suite_name} - 執行異常: {e}")
    
    # 生成最終報告
    print("\n" + "=" * 100)
    print("[SUMMARY] 測試執行總結")
    print("=" * 100)
    
    for suite_name, status, exec_time in suite_results:
        if exec_time > 0:
            print(f"{status:20} | {suite_name:40} | {exec_time:8.2f}秒")
        else:
            print(f"{status:20} | {suite_name:40} | {'N/A':>8}")
    
    print("-" * 100)
    print(f"總計測試套件: {len(test_suites)}")
    print(f"通過套件: {total_passed}")
    print(f"失敗套件: {total_failed}")
    
    if total_failed == 0:
        print("\n[SUCCESS] 所有測試套件全部通過！系統功能正常運作！")
        return True
    else:
        print(f"\n[WARNING] 有 {total_failed} 個測試套件失敗，需要檢查相關功能")
        return False


async def cleanup_old_tests():
    """清理舊的重複測試文件"""
    print("\n[CLEANUP] 清理舊的重複測試文件...")
    
    # 需要刪除的重複測試文件
    files_to_remove = [
        "test_duplicate_notifications.py",
        "test_notification_fix.py", 
        "test_simple_notification_fix.py",
        "test_code_fix_verification.py",
        "test_no_new_videos_behavior.py",
        "test_channel_state_update.py",
        "test_telegram_diagnostic.py",
        "test_notification_fix_verification.py",
        "test_check_summary.py"
    ]
    
    tests_dir = os.path.dirname(__file__)
    removed_count = 0
    
    for filename in files_to_remove:
        file_path = os.path.join(tests_dir, filename)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"  [OK] 已刪除: {filename}")
                removed_count += 1
            except Exception as e:
                print(f"  [ERROR] 刪除失敗 {filename}: {e}")
        else:
            print(f"  - 不存在: {filename}")
    
    print(f"\n清理完成，共刪除 {removed_count} 個重複文件")
    
    # 顯示保留的測試文件
    remaining_files = [
        "test_youtube_tracker_comprehensive.py",
        "test_telegram_notifications.py", 
        "run_all_tests.py",
        "__init__.py"
    ]
    
    print("\n[FILES] 保留的測試文件:")
    for filename in remaining_files:
        file_path = os.path.join(tests_dir, filename)
        if os.path.exists(file_path):
            print(f"  [OK] {filename}")
        else:
            print(f"  [MISSING] {filename} (不存在)")


def show_test_structure():
    """顯示新的測試結構"""
    print("\n[TEST STRUCTURE] 新的測試結構:")
    print("=" * 60)
    print("tests/")
    print("├── __init__.py")
    print("├── run_all_tests.py           # 測試執行工具")
    print("├── test_youtube_tracker_comprehensive.py  # 核心功能測試")
    print("├── test_telegram_notifications.py         # 通知系統測試")
    print("└── test_system_integration.py              # 系統整合測試")
    print("")
    print("[COVERAGE] 測試覆蓋範圍:")
    print("  • 重複通知防護機制")
    print("  • 無新影片時的行為")  
    print("  • 非活躍頻道處理")
    print("  • 無摘要時的通知發送")
    print("  • 頻道狀態更新")
    print("  • 短摘要通知")
    print("  • 長摘要通知（自動分割）")
    print("  • 純文字通知")
    print("  • 特殊字符處理")
    print("  • CLI 介面測試")
    print("  • 系統啟停功能")
    print("")
    print("[USAGE] 執行方式:")
    print('  python tests/run_all_tests.py           # 執行所有測試')
    print('  python tests/test_youtube_tracker_comprehensive.py  # 核心功能測試')
    print('  python tests/test_telegram_notifications.py         # 通知測試') 
    print('  python tests/test_system_integration.py             # 系統整合測試')


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="YouTube Tracker 測試工具")
    parser.add_argument("--cleanup", action="store_true", help="清理重複的舊測試文件")
    parser.add_argument("--structure", action="store_true", help="顯示測試結構")
    
    args = parser.parse_args()
    
    if args.cleanup:
        asyncio.run(cleanup_old_tests())
    elif args.structure:
        show_test_structure()
    else:
        # 執行所有測試
        success = asyncio.run(run_all_tests())
        exit(0 if success else 1)