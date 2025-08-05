# YouTube Tracker 測試套件

## 📋 測試架構

整理後的測試架構更加清晰和高效：

```
tests/
├── __init__.py
├── README.md                               # 此文檔
├── run_all_tests.py                        # 測試執行工具
├── test_youtube_tracker_comprehensive.py   # 核心功能測試
├── test_telegram_notifications.py          # 通知系統測試
└── test_system_integration.py              # 系統整合測試
```

## 🎯 測試覆蓋範圍

### 核心功能測試 (`test_youtube_tracker_comprehensive.py`)
- ✅ **重複通知防護機制** - 確保同一影片不會重複發送通知
- ✅ **無新影片時的行為** - 驗證無新影片時系統的正確處理
- ✅ **非活躍頻道處理** - 確認非活躍頻道被正確跳過
- ✅ **無摘要時的通知發送** - 驗證摘要生成失敗時仍能發送通知
- ✅ **頻道狀態更新** - 確認 `last_check` 和 `last_video_id` 正確更新

### 通知系統測試 (`test_telegram_notifications.py`)
- ✅ **短摘要通知** - 測試正常長度摘要的通知發送
- ✅ **長摘要通知（自動分割）** - 測試超長摘要的智能分割處理
- ✅ **無摘要通知** - 測試無摘要情況下的通知發送
- ✅ **純文字通知** - 測試不含縮圖的純文字通知
- ⚠️ **特殊字符處理** - 測試特殊Markdown字符的處理（已知問題）

### 系統整合測試 (`test_system_integration.py`)
- ✅ **CLI 介面測試** - 測試 main.py 的命令行介面
- ✅ **系統啟停功能** - 測試 start/stop/status 命令
- ✅ **進程管理** - 測試後台進程的啟動和停止

## 🚀 執行方式

### 執行所有測試
```bash
python tests/run_all_tests.py
```

### 執行特定測試套件
```bash
# 核心功能測試
python tests/test_youtube_tracker_comprehensive.py

# 通知系統測試  
python tests/test_telegram_notifications.py

# 系統整合測試
python tests/test_system_integration.py
```

### 工具命令
```bash
# 顯示測試結構
python tests/run_all_tests.py --structure

# 清理舊的重複測試文件（已完成）
python tests/run_all_tests.py --cleanup
```

## 📊 測試結果摘要

### 最近測試結果
- **通知系統測試**: 4/5 通過 (80% 成功率)
  - ✅ 短摘要通知
  - ✅ 長摘要通知
  - ✅ 無摘要通知  
  - ✅ 純文字通知
  - ❌ 特殊字符處理 (已知Markdown格式問題)

## 🔧 測試改進

### 已完成的改進
1. **整合重複測試** - 將12個重複的測試文件整合為3個專門測試文件
2. **統一測試架構** - 採用統一的測試類別和方法結構
3. **修復編碼問題** - 解決Windows中文環境下的Unicode顯示問題
4. **完善錯誤處理** - 添加完整的異常處理和清理機制
5. **提升測試覆蓋** - 涵蓋所有核心功能、通知系統和系統整合
6. **清理根目錄** - 移除根目錄下的重複測試文件，統一放在 tests/ 目錄

### 已知問題
1. **特殊字符Markdown格式** - 複雜特殊字符的Markdown轉義仍需改進
2. **Telegram API限制** - 某些測試可能因API限制而偶爾失敗
3. **Windows編碼** - 部分Unicode字符在Windows控制台中顯示異常

## 🛠️ 維護指南

### 添加新測試
1. 根據功能類型選擇合適的測試文件
2. 使用現有的測試類別和輔助方法
3. 確保包含適當的清理機制
4. 添加到對應的測試套件中

### 測試數據管理
- 測試使用臨時數據，執行後自動清理
- 測試頻道ID: `UC1234567890123456789012`
- 測試影片ID格式: `TESTXXXXXX` (11字符)
- 測試聊天ID: `6121833171`

### 執行環境
- 需要有效的Telegram Bot Token
- 需要YouTube API配置
- 建議在開發環境中執行，避免影響生產數據

## 📈 未來改進計劃

1. **添加性能測試** - 測試大量頻道和影片的處理性能
2. **集成CI/CD** - 自動化測試執行和報告生成
3. **Mock改進** - 減少對外部API的依賴
4. **覆蓋率報告** - 生成詳細的測試覆蓋率報告
5. **壓力測試** - 測試系統在高負載下的穩定性