# Resume 優化失效問題 - 調試指南

## 問題描述

在寶箱/戰鬥結束後，腳本沒有使用 Resume 按鈕恢復移動，而是重新打開地圖並點擊目標。

## 已添加的調試 LOG

### 1. **寶箱恢復處** (Line 4880)
```
[DEBUG] 設置 _MEET_CHEST_OR_COMBAT = True (寶箱後)
```
**目的**: 確認寶箱後確實設置了 `_MEET_CHEST_OR_COMBAT` flag

### 2. **戰鬥恢復處** (Line 4890)
```
[DEBUG] 設置 _MEET_CHEST_OR_COMBAT = True (戰鬥後)
```
**目的**: 確認戰鬥後確實設置了 `_MEET_CHEST_OR_COMBAT` flag

### 3. **DungeonState.Dungeon 轉態前** (Line 4982-4985)
```
[DungeonState.Dungeon-DEBUG] 準備轉交 Map 狀態，當前變數:
  ├─ _STEPAFTERRESTART = True/False
  ├─ _RESTART_OPEN_MAP_PENDING = True/False
  └─ _MEET_CHEST_OR_COMBAT = True/False
```
**目的**: 檢查在轉交給 Map 狀態前，三個條件變數的值是否正確

### 4. **resume_navigation 函數開頭** (Line 3873-3878)
```
[DungeonMover-DEBUG] Resume 條件檢查:
  ├─ _STEPAFTERRESTART = True/False
  ├─ _RESTART_OPEN_MAP_PENDING = True/False
  ├─ _MEET_CHEST_OR_COMBAT = True/False
  └─ 條件結果 = True/False (需為 True 才執行 Resume 優化)
```
**目的**: 精確顯示 Resume 優化條件的每個變數值和最終判斷結果

## 如何使用這些 LOG

### 步驟 1: 執行腳本並觸發戰鬥/寶箱
正常執行你的地城刷本腳本，等待進入戰鬥或寶箱。

### 步驟 2: 尋找關鍵 LOG 序列
在戰鬥/寶箱結束後，你應該會看到以下 LOG 序列：

```
[時間] INFO: 進行開啓寶箱後的恢復.
[時間] INFO: [DEBUG] 設置 _MEET_CHEST_OR_COMBAT = True (寶箱後)  ← 確認設置
[時間] INFO: 由於面板配置, 跳過了開啓寶箱後恢復.
[時間] INFO: ----------------------
[時間] INFO: 當前狀態(地下城): DungeonState.Dungeon
[時間] INFO: [DungeonState.Dungeon-DEBUG] 準備轉交 Map 狀態，當前變數:  ← 檢查值
[時間] INFO:   ├─ _STEPAFTERRESTART = ?
[時間] INFO:   ├─ _RESTART_OPEN_MAP_PENDING = ?
[時間] INFO:   └─ _MEET_CHEST_OR_COMBAT = ?  ← 這裡應該是 True
[時間] INFO: ----------------------
[時間] INFO: 當前狀態(地下城): DungeonState.Map
[時間] INFO: [StateDungeon] 使用 DungeonMover 處理移動
[時間] INFO: [DungeonMover] 啟動移動: 目標=position
[時間] INFO: [DungeonMover-DEBUG] Resume 條件檢查:  ← 最終判斷
[時間] INFO:   ├─ _STEPAFTERRESTART = ?
[時間] INFO:   ├─ _RESTART_OPEN_MAP_PENDING = ?
[時間] INFO:   ├─ _MEET_CHEST_OR_COMBAT = ?  ← 這裡也應該是 True
[時間] INFO:   └─ 條件結果 = ?  ← 這裡應該是 True
```

### 步驟 3: 分析結果

#### **情況 A: `_MEET_CHEST_OR_COMBAT` 在某處變成 False**
如果看到：
- Line 4880: `設置 _MEET_CHEST_OR_COMBAT = True` ✅
- Line 4985: `_MEET_CHEST_OR_COMBAT = False` ❌
- 或 Line 3875: `_MEET_CHEST_OR_COMBAT = False` ❌

**原因**: 某處的代碼在設置後又將其重置為 False（可能是遺漏的 `restartGame()` 呼叫或其他重置邏輯）

#### **情況 B: 其他條件失敗**
如果看到：
- Line 3874: `_STEPAFTERRESTART = False` ❌
- 或 Line 3875: `_RESTART_OPEN_MAP_PENDING = True` ❌

**原因**: 其他條件變數的邏輯有問題

#### **情況 C: 所有條件都是 True 但仍然沒有執行 Resume**
如果看到：
- Line 3878: `條件結果 = True` ✅
- 但下一行是: `[DungeonMover] Resume 優化結束或不適用，執行標準導航流程` ❌

**原因**: Resume 按鈕在畫面上不存在，或者點擊後無效（可能是時機問題）

## 預期的正確輸出

如果一切正常，你應該看到：

```
[時間] INFO: [DEBUG] 設置 _MEET_CHEST_OR_COMBAT = True (寶箱後)
[時間] INFO: [DungeonState.Dungeon-DEBUG] 準備轉交 Map 狀態，當前變數:
[時間] INFO:   ├─ _STEPAFTERRESTART = True
[時間] INFO:   ├─ _RESTART_OPEN_MAP_PENDING = False
[時間] INFO:   └─ _MEET_CHEST_OR_COMBAT = True
[時間] INFO: [DungeonMover-DEBUG] Resume 條件檢查:
[時間] INFO:   ├─ _STEPAFTERRESTART = True
[時間] INFO:   ├─ _RESTART_OPEN_MAP_PENDING = False
[時間] INFO:   ├─ _MEET_CHEST_OR_COMBAT = True
[時間] INFO:   └─ 條件結果 = True (需為 True 才執行 Resume 優化)
[時間] INFO: [DungeonMover] 嘗試 Resume 優化...  ← 進入 Resume 流程
[時間] INFO: [DungeonMover] 發現 Resume 按鈕 [x, y]，點擊恢復移動
```

## 下一步

執行腳本後，將包含以上 DEBUG 訊息的 LOG 片段提供給我，我就能準確診斷問題所在。
