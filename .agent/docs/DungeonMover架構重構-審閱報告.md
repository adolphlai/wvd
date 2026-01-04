# DungeonMover 架構重構 - 審閱報告

## 分支狀態
- **分支**: `refactor/dungeon-mover-v2`
- **修改統計**: 刪除 338 行，新增 98 行

## 重構目標（來自 `.agent/docs/DungeonMover架構重構.md`）

將所有移動邏輯統一整合到 `DungeonMover` 類別內。

## 已完成的修改

### 1. 函數重命名 ✅
| 原名 | 新名 |
|------|------|
| `_start_chest_auto` | `chest_search` |
| `_start_normal_move` | `resume_navigation` |
| `_start_gohome` | `_fallback_gohome` |

### 2. Resume 邏輯遷移 ✅
- 原本在 `StateDungeon` L4523-4710 的 Resume 優化邏輯
- 現已整合到 `resume_navigation` 開頭（最多重試 3 次）

### 3. 新增輔助函數 ✅
- `_check_combat_or_chest(screen)`: 抽取戰鬥/寶箱快速檢測

### 4. StateDungeon 簡化 ✅
- 刪除約 287 行 Resume/地圖相關邏輯
- 只負責環境初始化和狀態轉換
- 統一轉交 `DungeonState.Map` → `DungeonMover`

## 已確認的設計決策

| 問題 | 處理方式 |
|------|----------|
| minimap_stair 恢復邏輯 | 移到 `_monitor_move` 主循環，每 0.5 秒持續檢查 |
| Resume 失敗計數器 | 新增 `consecutive_map_open_failures`，3 次失敗重啟 |
| stair 換樓判定 | 用地圖驗證（`StateMap_FindSwipeClick` 搜尋失敗）取代直接假設 |
| Panic Mode | 由 `_fallback_gohome` + `_monitor_move` 替代（非阻塞、明確退出條件） |
| 返回 `DungeonState.Dungeon` | 故意設計，讓 `IdentifyState` 精確識別（降低耦合） |

## 下一步

重構已完成，可以進行測試驗證：
1. **chest_auto**：正常移動、靜止 pop、被中斷後恢復
2. **position/harken/stair/minimap_stair**：首次開地圖、有 Resume 繼續、無 Resume 重新開地圖、被中斷後恢復
3. **gohome**：觸發條件、持續執行、離開地城

## 關鍵文件
- `src/script.py`: DungeonMover 類別（L3457-3914）、StateDungeon（L4425-4475）
