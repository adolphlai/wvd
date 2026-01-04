# DungeonMover 架構重構

將所有移動邏輯統一整合到 `DungeonMover` 類別內。

---

## 新架構

| 目標類型 | 移動方法 | 容錯 |
|---------|---------|------|
| chest_auto | `chest_search()` | `_fallback_gohome()` |
| position | `resume_navigation()` | `_fallback_gohome()` |
| harken | `resume_navigation()` | `_fallback_gohome()` |
| stair | `resume_navigation()` | `_fallback_gohome()` |
| minimap_stair | `resume_navigation()` | `_fallback_gohome()` |

> [!NOTE]
> `routenotfound` 和 `notresure` 是**漸變文字**，需要 **0.5 秒延遲**後才能正確偵測。

---

## chest_search

```
chest_search（開始找 = 中斷恢復，遊戲機制決定）
    │
    ├─ 1. 檢查寶箱按鈕（ROI: [710,250,180,180]）
    │   ├─ 找到 → 點擊
    │   ├─ 偵測 notresure → pop 目標（無寶箱），返回 DungeonState.Map
    │   └─ 找不到 → 打開地圖 → 再找 → 盲點座標 [459,1248]
    │
    ├─ 2. 進入 _monitor_move
    │   ├─ 狀態轉換（戰鬥/寶箱）→ return 給 StateDungeon 處理
    │   ├─ 檢測到 `visibilityistoopoor` → 點擊 Resume
    │   │   └─ 進入臨時導航監控 (Flag: waiting_for_arrival)
    │   │       ├─ 檢測到 `routenotfound` → break (視為臨時導航完成)
    │   │       └─ 繼續執行戰鬥/異常/靜止檢測
    │   │           └─ break 後回到 Step 1 (重新找寶箱/開地圖)
    │   ├─ 每 5 秒點擊寶箱按鈕 → 檢測 notresure
    │   └─ 靜止判定（連續 3 次）
    │       ├─ 在地城中 (dungflag)
    │       │   ├─ 檢測到 notresure → pop（無寶箱），返回 DungeonState.Map
    │       │   └─ 未檢測到 notresure → 不 pop，返回 DungeonState.Dungeon (交回主流程判斷)
    │       └─ 在地圖中 (mapflag) → PressReturn → pop → _fallback_gohome()（防卡死）
    │
    └─ 3. 主流程整合：戰鬥/寶箱後 StateDungeon 再次呼叫 → 回到 Step 1（開始找 = 中斷恢復）
```

---

## resume_navigation

適用目標：**position / harken / stair / minimap_stair**

### 共用流程

```
resume_navigation
    │
    ├─ 1. 啟動移動
    │   ├─ 首次進入 → 開地圖 [777,150] → 點目標座標
    │   └─ 中斷後恢復
    │       ├─ 偵測 Resume（最多 3 次）→ 點擊繼續
    │       └─ 未偵測到 → 開地圖重新點目標
    │
    ├─ 2. 進入 _monitor_move
    │   ├─ 狀態轉換（戰鬥/寶箱）→ return 給 StateDungeon 處理
    │   ├─ 檢測到 `visibilityistoopoor` → 點擊 Resume (嘗試脫困)
    │   ├─ 【依目標類型執行完成檢測】
    │   └─ 靜止判定 → _fallback_gohome()（防卡死）
    │
    └─ 3. 主流程整合：戰鬥/寶箱後 StateDungeon 再次呼叫 → 回到 Step 1
```

---

### 目標類型差異

#### position

| 項目 | 說明 |
|-----|------|
| 完成偵測 | `routenotfound` 文字 |
| Keep-Alive | 每 5 秒點擊 resume |
| 特殊處理 | 無 |

#### harken

| 項目 | 說明 |
|-----|------|
| 完成偵測 | `_HARKEN_TELEPORT_JUST_COMPLETED` flag + `dungFlag` 可見 |
| 樓層選擇 | `IdentifyState` 偵測到 `floorImage` 後點擊 |
| 傳送判定 | 點擊樓層 → 黑畫面 → `dungFlag` 再次可見 = 完成 |
| Keep-Alive | 無（傳送中不需要） |

> [!NOTE]
> **harken 傳送完成判定原理：**
> 1. 點擊樓層 → 設置 `_HARKEN_TELEPORT_JUST_COMPLETED = True`
> 2. 傳送黑畫面 → `dungFlag` 不可見 → 不觸發完成
> 3. 黑畫面結束 → `dungFlag` 可見 → 觸發完成 → pop

#### stair

| 項目 | 說明 |
|-----|------|
| 完成偵測 | `routenotfound` 文字（與 position 相同）|
| Keep-Alive | 每 5 秒點擊 resume |
| 開地圖檢查 | `CheckIf_throughStair()` - 判斷是否需要點擊 |

> [!NOTE]
> **stair 類型：**
> - `stair_up/down/teleport` - 檢測樓梯圖片**消失** = 已通過
> - `stair_XXX`（如 `stair_fortress1f`）- 檢測樓層圖片**出現** = 已到達

#### minimap_stair

| 項目 | 說明 |
|-----|------|
| 完成偵測 | 小地圖 ROI `[651,24,870,244]` 內樓層圖片出現 |
| Flag | `_MINIMAP_STAIR_IN_PROGRESS`, `_MINIMAP_STAIR_FLOOR_TARGET` |
| 開地圖 | ❌ 不需要（適用打不開地圖的地形）|

> [!NOTE]
> **minimap_stair vs stair：**
> - **stair** - 需開地圖檢查，區分 up/down/teleport，舊 quest.json 用
> - **minimap_stair** - 不需開地圖，只檢測新樓層圖片，新地形用

---

## _fallback_gohome

**觸發條件：**
- chest_search/resume_navigation 靜止時檢測到 mapFlag（防卡死）
- 軟超時 (60s)

```
_fallback_gohome
    │
    ├─ 1. 找 gohome 按鈕
    │   ├─ 主畫面找到 → 點擊
    │   └─ 找不到 → 打開地圖 → 再找 → 盲點座標 [252,1433]
    │
    ├─ 2. 進入 _monitor_move (is_gohome_mode=True)
    │   ├─ 每 3 秒持續點擊 gohome (Keep-Alive)
    │   └─ 偵測離開地城：worldmapflag 或 Inn
    │
    └─ 3. 離開地城
        └─ return DungeonState.Quit
```

**超時保護：** 硬超時 (90s) → 觸發 restartGame()

> [!NOTE]
> **地城離開的兩種情況：**
> - **世界地圖地城**：gohome 後進入世界地圖 → `IdentifyState` 處理城池點擊（Deepsnow/RoyalCityLuknalia/fortressworldmap）
> - **城內地城**：gohome 後進入城內地圖 → EOT 序列處理 `returntotown` 返回村內

---

## targetInfoList 為空時的行為

當所有目標都 pop 完後（`targetInfoList == []`）：
- 呼叫 `_fallback_gohome` 確保角色離開地城
- `_fallback_gohome` 偵測到 `worldmapflag` 或 `Inn` → 離開地城循環

---

## ⚠️ 架構變更記錄

### `DungeonMover` vs `IdentifyState` 的權威性
- **問題**：原設計依賴 `IdentifyState` 進行所有狀態判定。但在地城中，`DungeonMover` 的戰鬥偵測（基於特定 UI 模板）比 `IdentifyState` 更靈敏。這導致 `DungeonMover` 看到戰鬥 -> 交給 `IdentifyState` -> `IdentifyState` 沒看到 -> 跳回移動邏輯 -> 無限循環。
- **修正**：賦予 `DungeonMover` 在地城環境下的**狀態Override權限**。當 `_check_combat_or_chest` 偵測到戰鬥或寶箱時，**直接返回** `DungeonState.Combat` 或 `DungeonState.Chest`，不再經過 `IdentifyState` 確認。這是為了避免多重權威衝突導致的死循環。

---

## Proposed Changes

### [MODIFY] [script.py](file:///d:/Project/wvd/src/script.py)

**1. 重新命名函數**

| 現有 | 新 |
|-----|---|
| `_start_chest_auto` | `chest_search` |
| `_start_normal_move` | `resume_navigation` |
| `_start_gohome` | `_fallback_gohome` |

**2. 遷移 StateDungeon Resume 邏輯 (L4523-4710) 到 resume_navigation**

**3. 簡化 StateDungeon**：只負責狀態分發

---

## Verification Plan

1. **chest_auto**：正常移動、靜止 pop、被中斷後恢復
2. **position/harken/stair/minimap_stair**：首次開地圖、有 Resume 繼續、無 Resume 重新開地圖、被中斷後恢復
3. **gohome**：觸發條件、持續執行、離開地城
