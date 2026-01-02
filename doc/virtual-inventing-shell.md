# 即時監控面板設計方案

## 用戶需求
1. 目前程序正在運行怎樣的邏輯
2. 如果卡住，卡在哪裡
3. 目前這個狀態持續多久
4. 其他可以增加即時狀況判斷的資訊

## 監控面板內容設計

### 更新頻率：每 1 秒

---

### 區塊 1：當前狀態 (核心資訊)

| 欄位 | 資料來源 | 範例顯示 |
|------|----------|----------|
| 主狀態 | `state` (State 枚舉) | `Inn` / `Dungeon` / `EoT` |
| 地城狀態 | `DungeonState` | `Map` / `Combat` / `Chest` / `Dungeon` |
| 當前目標 | `dungeon_mover.current_target` | `chest_auto` / `position` / `harken` / `gohome` |
| 目標詳情 | `targetInfoList[0]` | `position: 3F_EntranceToKronos` |

---

### 區塊 2：時間追蹤

| 欄位 | 計算方式 | 範例顯示 |
|------|----------|----------|
| 狀態持續 | `time.time() - move_start_time` | `12.3 秒` |
| 軟超時進度 | `elapsed / SOFT_TIMEOUT * 100%` | `[████████░░] 80% (24/30s)` |
| 硬超時進度 | `elapsed / HARD_TIMEOUT * 100%` | `[████░░░░░░] 40% (24/60s)` |

---

### 區塊 3：卡死偵測指標

| 欄位 | 資料來源 | 範例顯示 |
|------|----------|----------|
| 畫面靜止 | `still_count / STILL_REQUIRED` | `3/10 (30%)` |
| Resume 重試 | `resume_consecutive_count` | `2/5 次` |
| GoHome 模式 | `is_gohome_mode` | `否` / `是 (撤離中)` |
| 轉向解卡 | `turn_attempt_count` | `0/3 次` |

---

### 區塊 4：戰鬥資訊 (僅戰鬥狀態顯示)

| 欄位 | 資料來源 | 範例顯示 |
|------|----------|----------|
| 當前第幾戰 | `_COMBAT_BATTLE_COUNT` | `第 2 戰` |
| 行動計數 | `_COMBAT_ACTION_COUNT` | `3 次行動` |
| AOE 觸發 | `_AOE_TRIGGERED_THIS_DUNGEON` | `已觸發` / `未觸發` |

---

### 區塊 5：統計資訊 (累計)

| 欄位 | 資料來源 | 範例顯示 |
|------|----------|----------|
| 地城完成 | `_COUNTERDUNG` | `5 次` |
| 戰鬥完成 | `_COUNTERCOMBAT` | `23 次` |
| 寶箱開啟 | `_COUNTERCHEST` | `12 個` |
| **死亡次數** | `_COUNTERDEATH` (新增) | `2 次` |
| **善惡調整** | `setting._KARMAADJUST` | `-3` / `+2` |
| 總運行時間 | `_TOTALTIME` | `1234.5 秒` |
| 效率 | `_TOTALTIME / _COUNTERCHEST` | `102.9 秒/箱` |

---

### 區塊 6：異常警告 (紅色高亮)

| 條件 | 顯示內容 |
|------|----------|
| `is_gohome_mode == True` | `⚠️ 軟超時觸發，正在撤離` |
| `resume_consecutive_count >= 3` | `⚠️ Resume 多次失敗` |
| `still_count >= 8` | `⚠️ 畫面長時間靜止` |
| `elapsed > SOFT_TIMEOUT` | `⚠️ 移動超時` |
| `_COUNTERADBRETRY > 0` | `⚠️ ADB 重連 {n} 次` |
| `_CRASHCOUNTER > 3` | `🔴 連續崩潰 {n} 次` |

---

## 實作方式

### 新增共享狀態類別
在 `script.py` 中新增 `MonitorState` 類別，集中管理所有監控數據：

```python
class MonitorState:
    # 當前狀態
    current_state: str = ""           # Inn/Dungeon/EoT
    current_dungeon_state: str = ""   # Map/Combat/Chest/Dungeon
    current_target: str = ""          # chest_auto/position/harken/gohome
    target_detail: str = ""           # 目標詳情

    # 時間追蹤
    state_start_time: float = 0       # 狀態開始時間
    soft_timeout_progress: float = 0  # 0-100%
    hard_timeout_progress: float = 0  # 0-100%

    # 卡死偵測
    still_count: int = 0
    still_max: int = 10
    resume_count: int = 0
    resume_max: int = 5
    is_gohome_mode: bool = False
    turn_attempt_count: int = 0

    # 戰鬥資訊
    battle_count: int = 0
    action_count: int = 0
    aoe_triggered: bool = False

    # 統計
    dungeon_count: int = 0
    combat_count: int = 0
    chest_count: int = 0
    death_count: int = 0              # 死亡次數 (新增)
    karma_adjust: str = ""            # 善惡調整剩餘次數 (如 "-3" / "+2")
    total_time: float = 0

    # 警告
    warnings: list = []
```

### GUI 端讀取
GUI 每 1 秒讀取 `MonitorState` 並更新顯示。

---

## 修改檔案清單

| 檔案 | 修改內容 |
|------|----------|
| `src/script.py` | 新增 `MonitorState` 類別，在關鍵位置更新狀態 |
| `src/gui.py` | 新增監控面板 UI，定時讀取並顯示 |

---

## 狀態更新位置 (script.py)

1. **DungeonFarm 主循環** - 更新 `current_state`
2. **StateDungeon** - 更新 `current_dungeon_state`
3. **DungeonMover.initiate_move()** - 更新 `current_target`, `state_start_time`
4. **DungeonMover._monitor_move()** - 更新超時進度、靜止計數
5. **StateCombat** - 更新戰鬥資訊
6. **各計數器位置** - 更新統計資訊
7. **RiseAgainReset()** - 更新 `death_count` (新增 `_COUNTERDEATH` 計數器)
8. **IdentifyState 善惡調整處** - 更新 `karma_adjust` (讀取 `setting._KARMAADJUST`)
