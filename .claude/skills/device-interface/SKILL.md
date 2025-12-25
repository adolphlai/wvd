---
name: 設備通信層
description: 說明 ADB 設備通信和截圖機制，包含 pyscrcpy 串流優先、ADB 降級、設備重連邏輯。當使用者詢問截圖速度、ADB 連接、或設備通信問題時，應啟用此技能。
---

# 設備通信層 (Device Interface Layer)

## 檔案位置
`src/script.py`

## 截圖機制

### ScreenShot() - 主截圖函數
- **位置**: line 670
- **優先順序**:
  1. pyscrcpy 串流（~1ms）
  2. ADB 截圖（~150-570ms）

```python
def ScreenShot():
    # 1. 嘗試 pyscrcpy 串流
    if scrcpy_manager and scrcpy_manager.is_running():
        frame = scrcpy_manager.get_latest_frame()
        if frame is not None:
            return frame  # ~1ms

    # 2. 降級到 ADB
    return _ScreenShot_ADB()  # ~150-570ms
```

### _ScreenShot_ADB() - ADB 截圖
- **位置**: line 724
- **方法**: `adb exec-out screencap -p`
- **速度**: 約 150-570ms

### ScrcpyStreamManager 類
- **位置**: line 26
- **功能**: 管理 pyscrcpy 視頻串流
- **方法**:
  - `start()`: 啟動串流
  - `stop()`: 停止串流
  - `get_latest_frame()`: 獲取最新幀
  - `is_running()`: 檢查串流狀態

## 設備通信

### DeviceShell() - ADB Shell 執行
- **位置**: line 611
- **功能**: 執行 ADB shell 命令
- **重試機制**: 失敗時自動重試

### ResetADBDevice() - 設備重連
- **位置**: line 598
- **功能**: 重新連接 ADB 設備
- **觸發時機**: 連接斷開或命令超時

## 輸入操作

### Press() - 點擊
```python
Press([x, y])  # 點擊座標
```

### Swipe() - 滑動
```python
Swipe([x1, y1, x2, y2], duration=300)
```

### PressReturn() - 返回鍵
```python
PressReturn()  # 發送 KEYCODE_BACK
```

## 串流重連機制

```
截圖請求
    │
    ▼
┌─────────────────┐
│ pyscrcpy 可用？ │
└────────┬────────┘
         │
    ┌────┴────┐
    │ Yes     │ No
    ▼         ▼
  使用串流   ┌─────────────────┐
  (~1ms)    │ ADB 截圖        │
            │ (~150-570ms)    │
            └─────────────────┘
```

## 配置項

| 設定 | 說明 |
|------|------|
| `setting._ADBDEVICE` | ADB 設備地址 |
| `setting._ENABLEPYSCRCPY` | 啟用 pyscrcpy 串流 |

## 日誌

截圖模式會記錄在日誌中：
- `[截圖] 使用 pyscrcpy 串流`
- `[截圖] 使用 ADB 截圖`
