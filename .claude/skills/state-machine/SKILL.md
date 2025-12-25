---
name: 狀態機核心
description: 說明遊戲狀態識別和主要流程控制，包含 State/DungeonState 枚舉、IdentifyState、DungeonFarm、QuestFarm 等核心函數。當使用者詢問狀態流轉、主循環邏輯、或整體架構時，應啟用此技能。
---

# 狀態機核心 (State Machine System)

## 檔案位置
`src/script.py`

## 狀態枚舉

### State（主狀態）
```python
class State(Enum):
    Inn = 1      # 旅店
    Dungeon = 2  # 地下城
    EoT = 3      # 邊緣之城（傳送）
    Quit = 4     # 結束
```

### DungeonState（地下城子狀態）
```python
class DungeonState(Enum):
    Dungeon = 1  # 地下城內（非地圖）
    Map = 2      # 地圖打開
    Chest = 3    # 寶箱
    Combat = 4   # 戰鬥
    Quit = 5     # 結束
```

## 核心函數

### IdentifyState() - 狀態識別
- **位置**: line 1454
- **功能**: 識別當前遊戲畫面對應的狀態
- **返回**: `State` 枚舉值
- **邏輯**:
  1. 檢測各種狀態標識圖片
  2. 異常處理（counter >= 4 時觸發恢復邏輯）
  3. 黑屏檢測和遊戲重啟

### DungeonFarm() - 地下城農場主循環
- **位置**: line 2869
- **功能**: 地下城內的主要循環邏輯
- **流程**:
  ```
  while dungState != DungeonState.Quit:
      if dungState == DungeonState.Dungeon:
          StateDungeon()
      elif dungState == DungeonState.Map:
          StateMap_FindSwipeClick()
      elif dungState == DungeonState.Chest:
          StateChest()
      elif dungState == DungeonState.Combat:
          StateCombat()
  ```

### QuestFarm() - 特殊任務循環
- **位置**: line 2935
- **功能**: 執行特殊任務（7000G、Fordraig 等）
- **支援任務**:
  - `turn_to_7000G` - 7000G 任務
  - `fordraig` - Fordraig 任務
  - `organize` - 背包整理

### Farm() - 總入口
- **位置**: line 3696
- **功能**: 整個農場流程的入口函數
- **流程**:
  ```
  while state != State.Quit:
      if state == State.Inn:
          StateInn()
      elif state == State.EoT:
          StateEoT()
      elif state == State.Dungeon:
          DungeonFarm() 或 QuestFarm()
  ```

## 狀態流轉圖

```
┌─────────────────────────────────────────────────────────┐
│                        Farm()                            │
│  ┌──────┐    ┌──────┐    ┌────────────────────────────┐ │
│  │ Inn  │───▶│ EoT  │───▶│        Dungeon             │ │
│  └──────┘    └──────┘    │  ┌─────────┐  ┌─────────┐  │ │
│      ▲                   │  │ Dungeon │◀▶│   Map   │  │ │
│      │                   │  └────┬────┘  └─────────┘  │ │
│      │                   │       │                     │ │
│      │                   │  ┌────▼────┐  ┌─────────┐  │ │
│      │                   │  │  Chest  │  │ Combat  │  │ │
│      │                   │  └─────────┘  └─────────┘  │ │
│      │                   └────────────────────────────┘ │
│      │                              │                    │
│      └──────────────────────────────┘                    │
│                    (gohome/結束)                          │
└─────────────────────────────────────────────────────────┘
```

## RuntimeContext 重要變數

| 變數 | 說明 |
|------|------|
| `_FIRST_DUNGEON_ENTRY` | 第一次進入地城 |
| `_GOHOME_IN_PROGRESS` | 正在回城 |
| `_RESTART_OPEN_MAP_PENDING` | 重啟後待打開地圖 |
| `_SUICIDE` | 自殺模式（強制死亡） |
