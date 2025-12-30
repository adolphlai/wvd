# WVD 重構總體方案（以目前程式碼為準）

版本: 0.3
日期: 2025-12-30
作者: Codex

## 1. 範圍
本文件完全以目前 `src/script.py` 為準，涵蓋主要功能模塊：
- 移動 + Resume
- 寶箱（StateChest）
- 戰鬥（StateCombat）
- 狀態機（StateDungeon / IdentifyState / DungeonFarm）
- 回村補給（StateInn）
- 大地圖移動（StateEoT / TeleportFromCityToWorldLocation）

## 2. 目前程式碼地圖（事實基準）
核心函式 / 類別（皆在 `src/script.py`）：
- `IdentifyState()`（狀態識別）
- `DungeonMover`（新移動控制器）
- `StateMoving_CheckFrozen()`（舊移動監控）
- `StateSearch()`（地圖搜尋 + 舊移動）
- `StateDungeon()`（主狀態流程 + Resume 優化）
- `StateChest()`（寶箱流程）
- `StateCombat()`（戰鬥流程）
- `StateInn()`（住宿 / 補給 / 整理背包）
- `StateEoT()`（邊境 / 進地城流程）
- `TeleportFromCityToWorldLocation()`（大地圖移動）

入口流程：
- `DungeonFarm()` 驅動 `State`（Inn / EoT / Dungeon）切換。

## 3. 現行流程（高層）
### 3.1 主迴圈（DungeonFarm）
- `state` 依序流轉：`None -> Inn -> EoT -> Dungeon`。
- 進入 `State.Dungeon` 後，呼叫 `StateDungeon(targetInfoList, initial_dungState)`。

### 3.2 狀態識別（IdentifyState）
行為摘要：
- 每輪截圖後依序比對模板。
- 特殊處理：
  - 黑屏判定（早期戰鬥 AOE 斷自動）。
  - 哈肯樓層選擇（`_HARKEN_FLOOR_TARGET` + `returnText`）。
  - 處理 `returnText` / `returntoTown` / `openworldmap` / `RoyalCityLuknalia` / `fortressworldmap` / `Inn`。
- 回傳 `(State, DungeonState, screen)`。

### 3.3 移動 + Resume（兩條管線並存）
目前有兩條移動管線：

A) 新管線（DungeonMover）
- `StateDungeon` 在 `DungeonState.Map` 時呼叫 `dungeon_mover.initiate_move()`。
- `DungeonMover` 內含：
  - `_start_chest_auto` / `_start_gohome` / `_start_normal_move`
  - `_monitor_move`（soft/hard timeout、IdentifyState、Resume、解卡）

B) 舊管線（StateMoving_CheckFrozen）
- 仍被以下流程使用：
  - `StateSearch()`
  - `StateDungeon` 的 Resume 優化
  - 小地圖樓梯（minimap_stair）監控

這造成移動規則不一致、參數分裂、行為重複。

### 3.4 Resume 優化（StateDungeon）
位置：`DungeonState.Dungeon` 分支內。
行為摘要：
- 檢查 mapFlag / chest / combat。
- 多次偵測 Resume 按鈕並重試。
- 處理 `routenotfound`。
- `visibliityistoopoor` 觸發緊急 gohome。
- Resume 點擊後呼叫 `StateMoving_CheckFrozen()`。

### 3.5 寶箱流程（StateChest）
行為摘要：
- Loop 流程，包含：
  - 異常檢查（abnormal_states）
  - 戰鬥 / 死亡檢查
  - dungFlag 連續確認
  - whowillopenit / chestOpening / chestFlag 分支
  - 默認 spam click（快進 / retry / 連點）

### 3.6 戰鬥流程（StateCombat）
行為摘要：
- 處理自動 / 手動切換。
- 技能選擇與強制技能（AOE / 單體）。
- 使用 AE caster sequence（依設定）。
- 透過 runtimeContext 記錄戰鬥計數。

### 3.7 回村補給（StateInn）
行為摘要：
- 住宿（Economy / Royal Suite）
- 補給（Auto Refill，選用）
- 整理背包（選用）

### 3.8 大地圖移動（StateEoT / TeleportFromCityToWorldLocation）
行為摘要：
- `StateEoT` 依 `quest._EOT` 執行進圖流程。
- `TeleportFromCityToWorldLocation`：
  - 確保 worldmapflag 出現
  - 處理縮放
  - 滑動並點擊目標

## 4. 目前主要痛點（依程式碼觀察）
1) 移動管線雙軌（DungeonMover / StateMoving_CheckFrozen）導致規則分裂。
2) 開圖失敗等「移動啟動階段」不一定進入 IdentifyState。
3) Resume / gohome / restart 分散在多處，策略不一致。
4) 參數不一致（still 次數、timeout、Resume 次數）。
5) 大地圖 / 地城共享狀態旗標，但流程隔離不足。

## 5. 重構目標架構（與目前用語對齊）
### 5.1 模塊角色
- 狀態識別模塊（IdentifyState 抽離）：唯一狀態來源。
- 移動控制模塊（統一 DungeonMover + StateMoving_CheckFrozen）。
- 地城狀態機（統一 StateDungeon 的決策邏輯）。
- 行為模塊（StateChest / StateCombat / StateInn / WorldMap）。

### 5.2 事件概念（保留現有用語）
MoveEvent：
 - Arrived（到達 / RouteNotFound）
 - EnterCombat（進戰鬥）
 - EnterChest（進寶箱）
 - FailedOpenMap（無法打開地圖）
 - TimeoutSoft / TimeoutHard

StateEvent：
 - DetectedDungeon / DetectedMap / DetectedCombat / DetectedChest / DetectedQuit

## 6. 重構路線（以目前代碼為準）
### Phase 1：參數統一
將以下參數對齊，避免行為不一致：
- still 判斷次數與門檻（DungeonMover / StateMoving_CheckFrozen / StateDungeon）
- Resume 重試次數
- soft/hard timeout

### Phase 2：狀態識別抽離
- 保留 IdentifyState 邏輯，抽出為獨立入口。
- 其他模塊只呼叫狀態識別，不自行散落判斷。

### Phase 3：移動流程統一
- 將 StateMoving_CheckFrozen 的核心邏輯合併到 DungeonMover。
- 讓 StateSearch / Resume 僅走單一路徑。
- 逐步淘汰 StateMoving_CheckFrozen。

### Phase 4：StateDungeon 決策集中
- StateDungeon 不直接分支到各種流程，改為事件驅動決策。
- 明確區分「行為」與「決策」。

### Phase 5：大地圖 / 回村模塊化
- StateEoT 與 TeleportFromCityToWorldLocation 拆成 WorldMap 模塊。
- StateInn 完整獨立，避免與地城狀態旗標交錯。

## 7. 驗收標準
- 不再出現「開圖失敗 -> Resume -> 再開圖失敗」無窮循環。
- 移動只剩單一管線。
- Resume 行為一致，參數統一。
- IdentifyState 在所有移動階段可被呼叫。
- 回村補給與大地圖流程從地城邏輯隔離。

## 8. 待確認問題
- Resume 參數要以哪組為「最終標準」？（仍需你確認）
- gohome 是否保留作為主要 fallback？
- 是否有特殊地城仍需舊流程（StateMoving_CheckFrozen）保留？
