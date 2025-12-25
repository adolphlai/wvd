---
name: 詛咒之輪時間跳躍
description: 說明詛咒之輪時間跳躍機制，包含 CursedWheelTimeLeap、因果調整（CSC）。當使用者詢問時間跳躍、7000G 任務、因果調整問題時，應啟用此技能。
---

# 詛咒之輪時間跳躍 (Cursed Wheel Time Leap System)

## 檔案位置
`src/script.py`

## 核心函數

### CursedWheelTimeLeap() - 時間跳躍執行
- **位置**: line 1378
- **功能**: 執行詛咒之輪的時間跳躍操作

## 時間跳躍流程

```
觸發時間跳躍
    │
    ▼
┌─────────────────┐
│ 打開詛咒之輪    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 應用因果調整    │
│ (CSC 配置)      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 確認時間跳躍    │
└────────┬────────┘
         │
         ▼
    跳躍完成
```

## 因果調整 (Curse Special Config - CSC)

### 配置格式
```python
quest._CSC = {
    "curse_name": True,   # 開啟該因果
    "curse_name2": False  # 關閉該因果
}
```

### 支援的因果
- 各種詛咒開關
- 特殊任務需求的因果組合

## 特殊任務

### turn_to_7000G
- 觸發條件：收到 `turn_to_7000G` 消息
- 流程：執行時間跳躍 → 7000G 任務

### fordraig
- Fordraig 相關任務
- 需要特定因果配置

## 消息機制

```python
# 發送時間跳躍消息
send_message('turn_to_7000G')

# QuestFarm 中接收並處理
if message == 'turn_to_7000G':
    CursedWheelTimeLeap()
```

## 相關圖片資源

- `cursedWheel.png` - 詛咒之輪入口
- `cursedWheel_timeLeap.png` - 時間跳躍選項
- `curseToggle.png` - 因果開關

## 配置項

| 設定 | 說明 |
|------|------|
| `quest._CSC` | 因果特殊配置 |
| `quest._TIMELEAPTARGET` | 時間跳躍目標 |
