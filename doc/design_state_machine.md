# 地城流程設計文件（狀態機與移動監控重構）

版本: 0.1
日期: 2025-12-30
作者: Codex

## 1. 背景與問題
目前流程中，狀態識別 (IdentifyState) 只在移動監控內執行，當流程卡在「開地圖失敗」等啟動階段時，監控與狀態識別不會進入，導致無窮循環與超時邏輯失效。此問題在 log 中表現為反覆 Resume 優化与開圖失敗。

## 2. 目標
- 統一狀態識別入口，使任何流程節點都能可靠取得「權威狀態」。
- 移動流程只負責執行與監控，不做策略決策。
- 由單一狀態機接收事件並決策下一步，避免模組互相跳轉造成死循環。
- 支援分階段重構，不要求一次性推翻現有架構。

## 3. 非目標
- 不更換影像辨識邏輯或模板資產。
- 不重寫戰鬥/寶箱流程細節。
- 不引入外部依賴或改變現有平台 (ADB/pyscrcpy)。

## 4. 現況痛點摘要
- 開圖失敗直接 return，導致 IdentifyState 與 timeout 邏輯不執行。
- 模組各自做狀態判斷，容易互相矛盾。
- timeout 僅在移動監控內生效，流程未進入監控時即失效。

## 5. 設計概念
核心概念為「事件驅動狀態機」：
- StateDetector: 狀態識別唯一權威來源。
- MoveController: 只做「移動行為 + 監控」，輸出事件。
- DungeonStateMachine: 接收事件並決策下一步。

### 5.1 模組責任邊界
- StateDetector
  - Input: screen
  - Output: DungeonState (Combat/Chest/Map/Dungeon/Quit/Unknown)
  - 特性: 可被任何流程節點呼叫

- MoveController
  - Input: target, context
  - Output: MoveEvent (Arrived/EnterCombat/EnterChest/FailedOpenMap/TimeoutSoft/TimeoutHard)
  - 特性: 不決策下一步，只回事件

- DungeonStateMachine
  - Input: current state + event
  - Output: next state + action
  - 特性: 統一決策與重試策略

## 6. 狀態與事件定義

### 6.1 DungeonState
- Combat
- Chest
- Map
- Dungeon
- Quit
- Unknown

### 6.2 MoveEvent
- Arrived
- EnterCombat
- EnterChest
- FailedOpenMap
- TimeoutSoft
- TimeoutHard
- Cancelled

## 7. 核心流程（概念）

1) 主迴圈每輪先截圖，呼叫 StateDetector
2) 根據狀態交由對應 StateHandler
3) Dungeon 狀態若需要移動，交由 MoveController
4) MoveController 產生 MoveEvent，回交 StateMachine
5) StateMachine 決定 Retry/GoHome/Restart 或轉狀態

## 8. 介面草案

### 8.1 StateDetector
- detect(screen) -> (DungeonState, meta)

### 8.2 MoveController
- start(target, context) -> None
- tick() -> MoveEvent
- reset() -> None

### 8.3 DungeonStateMachine
- step(state, event, context) -> (next_state, action)

## 9. 分階段遷移計畫

### Phase 1: 最小可行調整
- IdentifyState 抽成 StateDetector (不改邏輯，只改呼叫入口)
- MoveController 在「開圖失敗」時也回傳事件
- StateDungeon 仍可維持原樣，但在關鍵節點改為讀取事件

### Phase 2: 事件驅動化
- 把 DungeonMover 的 return 改為 MoveEvent
- 將策略 (retry/gohome/restart) 移至 DungeonStateMachine

### Phase 3: 模組化完成
- StateDungeon/StateChest/StateCombat 僅保留行為
- 事件流成為唯一流程控制管道

## 10. 風險與緩解
- 風險: 狀態判斷仍依賴模板品質
  - 緩解: 保留原模板組合，多加一層 Unknown 狀態處理
- 風險: 事件傳遞增加複雜度
  - 緩解: 僅引入最小事件集，避免事件爆炸

## 11. 日誌與可觀測性
- 每次 detect/事件回傳都打 log (狀態、分數、耗時)
- MoveEvent 發生時記錄前後狀態與目标
- timeout 決策由 StateMachine 統一 log

## 12. 測試建議
- 以錄製的截圖集做 StateDetector 回歸測試
- 模擬 MoveEvent 流程測試狀態機決策
- 對 timeout 与 FailedOpenMap 設置獨立測試案例

## 13. 成果定義
- 不再出現「開圖失敗 -> Resume -> 再開圖失敗」的無窮循環
- IdentifyState 不再只在移動監控內才被呼叫
- timeout 能在啟動階段與監控階段都生效
