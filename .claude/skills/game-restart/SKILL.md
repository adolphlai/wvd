---
name: 遊戲重啟機制
description: 說明遊戲崩潰和卡死時的重啟邏輯，包含 restartGame、RestartableSequenceExecution、異常恢復。當使用者詢問遊戲卡住、重啟、或異常恢復問題時，應啟用此技能。
---

# 遊戲重啟機制 (Game Restart & Recovery System)

## 檔案位置
`src/script.py`

## 核心函數

### restartGame() - 重啟遊戲
- **位置**: line 1137
- **功能**: 強制停止並重啟遊戲應用

```python
def restartGame():
    # 1. 保存崩潰前截圖
    save_crash_screenshot()

    # 2. 強制停止應用
    DeviceShell('am force-stop com.game.app')

    # 3. 等待
    Sleep(3)

    # 4. 重啟應用
    DeviceShell('am start -n com.game.app/.MainActivity')

    # 5. 設置重啟標誌
    runtimeContext._RESTART_OPEN_MAP_PENDING = True
    runtimeContext._FIRST_COMBAT_AFTER_RESTART = 2
```

### RestartableSequenceExecution() - 可重啟序列執行
- **位置**: line 1172
- **功能**: 包裝操作序列，異常時自動重啟並重試

```python
def RestartableSequenceExecution(sequence_func):
    try:
        sequence_func()
    except RestartException:
        restartGame()
        # 重新執行序列
        sequence_func()
```

## 重啟觸發條件

在 IdentifyState() 中：

| 條件 | 觸發 |
|------|------|
| `counter >= 25` | 狀態識別失敗超過 25 次 |
| `counter > 15` | 黑屏檢測 |
| 網路錯誤 | 連接斷開 |

## 重啟後處理

### _RESTART_OPEN_MAP_PENDING
- 重啟後跳過 Resume 優化
- 直接嘗試打開地圖

### _FIRST_COMBAT_AFTER_RESTART
- 重啟後前 N 次戰鬥使用強力技能
- 避免因狀態不明導致戰鬥失敗

### _STEPAFTERRESTART
- 重啟後左右平移
- 重新定位角色位置

## 重啟流程圖

```
異常檢測
    │
    ▼
┌─────────────────┐
│ counter >= 25?  │
└────────┬────────┘
         │ Yes
         ▼
    保存截圖
         │
         ▼
    強制停止遊戲
         │
         ▼
    等待 3 秒
         │
         ▼
    重啟遊戲
         │
         ▼
    設置恢復標誌
         │
         ▼
    等待遊戲載入
         │
         ▼
    繼續正常流程
```

## 異常類型

### RestartException
- 用於觸發重啟的自定義異常
- 被 RestartableSequenceExecution 捕獲

## 日誌記錄

重啟時會記錄：
- 崩潰前截圖（保存到 log 目錄）
- 重啟原因
- 重啟時間

## RuntimeContext 相關變數

| 變數 | 說明 |
|------|------|
| `_RESTART_OPEN_MAP_PENDING` | 重啟後待打開地圖 |
| `_FIRST_COMBAT_AFTER_RESTART` | 重啟後戰鬥計數器 |
| `_STEPAFTERRESTART` | 重啟後平移標誌 |
