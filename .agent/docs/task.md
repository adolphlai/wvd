# DungeonMover 架構重構

## 目標
統一地城移動邏輯，將分散在 `StateDungeon` 和 `DungeonMover` 的 Resume 邏輯整合到 `DungeonMover` 類別內。

## 任務列表

- [x] **DungeonMover 函數重命名與整理**
    - [x] Rename `_start_chest_auto` -> `chest_search`
    - [x] Rename `_start_normal_move` -> `resume_navigation`
    - [x] Rename `_start_gohome` -> `_fallback_gohome`
    - [x] 確保所有內部調用都更新為新名稱

- [x] **實作 `chest_search`**
    - [x] 確保包含 failed-safe 邏輯（如找不到圖片時的盲點）
    - [x] 確保正確的狀態返回（找到->OpenMap or Move, 沒找到->Map to next target）

- [x] **實作 `resume_navigation`** (核心重構)
    - [x] **遷移 StateDungeon Resume 邏輯**：將 StateDungeon 中的 Resume 判斷邏輯搬移至此。
    - [x] 實作順序：
        1.  **Resume Check**: 嘗試點擊 Resume 按鈕（如果非首次進入）。
        2.  **Resume Success**: 進入 `_monitor_move`。
        3.  **Resume Failed/Needed**: 打開地圖 (`StateMap_FindSwipeClick` + `Press`) -> 進入 `_monitor_move`。
        4.  **Fallback Protection**: 連續 3 次開地圖失敗觸發重啟。

- [x] **實作 `_fallback_gohome`**
    - [x] 作為 `resume_navigation` 軟超時後的 fallback。
    - [x] Panic Mode 整合。

- [x] **簡化 `StateDungeon`**
    - [x] 移除原本冗長的 Resume 判斷邏輯。
    - [x] `case DungeonState.Map` 直接調用 `dungeon_mover.initiate_move()`。
    - [x] `case DungeonState.Resume` (如果有) 應被整合進 Map 或移除。
    
- [x] **用戶反饋修正**
    - [x] 修正 minimap_stair 的即時偵測 (移出靜止檢查)。
    - [x] 加回 3 次失敗重啟保護。
    - [x] 確認 Stair Resume 失敗後的 Fallback 機制 (Open Map Verify)。
    - [x] 確認 Panic Mode 機制。
