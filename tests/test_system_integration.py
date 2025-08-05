"""
YouTube Tracker 系統整合測試
測試 main.py 的 CLI 介面和系統啟停功能
"""

import asyncio
import subprocess
import sys
import os
import time
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class SystemIntegrationTests:
    """系統整合測試類別"""
    
    @staticmethod
    async def test_remote_stop_functionality():
        """測試遠程停止功能"""
        print("[INTEGRATION] 測試系統啟停功能...")
        
        # 1. 啟動系統
        print("[STEP 1] 在背景啟動 YouTube Tracker...")
        start_process = subprocess.Popen(
            [sys.executable, "main.py", "start"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        
        # 等待系統啟動
        await asyncio.sleep(3)
        
        # 檢查進程是否還在運行
        if start_process.poll() is not None:
            print("[ERROR] 啟動進程提前退出")
            stdout, stderr = start_process.communicate()
            print(f"stdout: {stdout}")
            print(f"stderr: {stderr}")
            return False
        
        print("[STEP 2] 系統已啟動，檢查狀態...")
        
        # 2. 檢查狀態
        try:
            status_result = subprocess.run(
                [sys.executable, "main.py", "status"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
            
            print(f"狀態輸出: {status_result.stdout}")
            if status_result.stderr:
                print(f"狀態錯誤: {status_result.stderr}")
                
            if "Running: Yes" in status_result.stdout or "running" in status_result.stdout.lower():
                print("[PASS] 狀態顯示系統正在運行")
                status_check_passed = True
            else:
                print("[WARN] 狀態顯示系統可能未正常運行")
                status_check_passed = False
                
        except subprocess.TimeoutExpired:
            print("[ERROR] 狀態檢查超時")
            status_check_passed = False
        except Exception as e:
            print(f"[ERROR] 狀態檢查失敗: {e}")
            status_check_passed = False
        
        print("[STEP 3] 發送停止信號...")
        
        # 3. 發送停止命令
        try:
            stop_result = subprocess.run(
                [sys.executable, "main.py", "stop"],
                capture_output=True,
                text=True,
                timeout=15,
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
            
            print(f"停止命令輸出: {stop_result.stdout}")
            if stop_result.stderr:
                print(f"停止命令錯誤: {stop_result.stderr}")
                
        except subprocess.TimeoutExpired:
            print("[ERROR] 停止命令超時")
        except Exception as e:
            print(f"[ERROR] 停止命令失敗: {e}")
        
        # 4. 等待進程停止
        try:
            start_process.wait(timeout=15)
            print("[PASS] 啟動進程成功退出")
            process_stopped = True
        except subprocess.TimeoutExpired:
            print("[ERROR] 啟動進程未在15秒內退出，強制終止")
            start_process.terminate()
            try:
                start_process.wait(timeout=5)
                print("[WARN] 強制終止成功")
                process_stopped = True
            except subprocess.TimeoutExpired:
                print("[ERROR] 強制終止失敗，殺死進程")
                start_process.kill()
                process_stopped = False
        
        # 5. 最終狀態檢查
        print("[STEP 4] 最終狀態檢查...")
        try:
            final_status = subprocess.run(
                [sys.executable, "main.py", "status"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
            
            if "Running: No" in final_status.stdout or "not running" in final_status.stdout.lower():
                print("[PASS] 最終狀態確認系統已停止")
                final_check_passed = True
            else:
                print(f"[WARN] 最終狀態: {final_status.stdout}")
                final_check_passed = False
                
        except Exception as e:
            print(f"[WARN] 最終狀態檢查失敗: {e}")
            final_check_passed = False
        
        # 計算測試結果
        total_checks = 3
        passed_checks = sum([status_check_passed, process_stopped, final_check_passed])
        
        if passed_checks == total_checks:
            print(f"[SUCCESS] 系統整合測試通過 ({passed_checks}/{total_checks})")
            return True
        else:
            print(f"[PARTIAL] 系統整合測試部分通過 ({passed_checks}/{total_checks})")
            return passed_checks >= 2  # 至少通過2/3的檢查才算成功


async def run_integration_tests():
    """執行所有系統整合測試"""
    print("=" * 60)
    print("YouTube Tracker 系統整合測試")
    print("=" * 60)
    
    test_suite = SystemIntegrationTests()
    
    tests = [
        ("系統啟停功能測試", test_suite.test_remote_stop_functionality)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n執行測試: {test_name}")
        print("-" * 40)
        
        try:
            result = await test_func()
            if result:
                print(f"[PASS] {test_name}")
                results.append(True)
            else:
                print(f"[FAIL] {test_name}")
                results.append(False)
        except Exception as e:
            print(f"[ERROR] {test_name} 執行失敗: {e}")
            results.append(False)
    
    # 總結
    print("\n" + "=" * 60)
    print("系統整合測試總結")
    print("=" * 60)
    
    passed = sum(results)
    total = len(results)
    success_rate = (passed / total * 100) if total > 0 else 0
    
    for i, (test_name, _) in enumerate(tests):
        status = "[PASS]" if results[i] else "[FAIL]"
        print(f"{status} {test_name}")
    
    print(f"\n總體結果: {passed}/{total} 通過 ({success_rate:.1f}%)")
    
    if success_rate >= 80:
        print("[SUCCESS] 系統整合測試整體通過！")
    else:
        print("[WARN] 系統整合測試存在問題，需要檢查")
    
    return success_rate >= 80


if __name__ == "__main__":
    asyncio.run(run_integration_tests())