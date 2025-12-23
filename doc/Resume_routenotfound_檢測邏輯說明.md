# Resume + routenotfound 檢測邏輯說明

## 執行前提

> **所有邏輯都在 `DungeonState.Dungeon` 狀態下執行**

---

## 修改位置

**檔案**: `src/script.py`  
**函數**: `StateDungeon()`  
**分支**: `case DungeonState.Dungeon:`  

---

## 處理邏輯

```
【DungeonState.Dungeon 狀態】
│
├─ 0. 正在回城中 (_GOHOME_IN_PROGRESS = True)
│     → 繼續執行 gohome（之前被戰鬥/寶箱打斷）
│
├─ 1. 第一次進入地城 (_FIRST_DUNGEON_ENTRY = True)
│     → 無條件打開地圖
│
├─ 2. 剛重啟過遊戲 (_STEPAFTERRESTART = False)
│     → 跳過 Resume 優化，直接打開地圖（之前的路徑可能已失效）
│
└─ 3. 非第一次進入且非重啟後 (Resume 優化啟用時)
      │
      ├─ 3.0 檢測 Resume 按鈕（最多重試 3 次）
      │       │
      │       ├─ 檢測到 Resume → 進入 3.1
      │       │
      │       └─ 3 次都沒檢測到 → 打開地圖 → 進入 3.3
      │
      ├─ 3.1 點擊 Resume 按鈕（最多 5 次）
      │       │
      │       ├─ 出現 routenotfound → 已到目的地（進入 3.2）
      │       │
      │       ├─ 沒出現 routenotfound，畫面有變化 → 還在路上
      │       │     → 呼叫 StateMoving_CheckFrozen() 監控移動
      │       │         （若移動中檢測到 routenotfound → 直接打開地圖）
      │       │
      │       └─ 點了 5 次 Resume，畫面沒變化 或 沒出現 routenotfound
      │             │
      │             ├─ 當前目標是樓梯 (stair_XXX) → 判定為換樓成功（進入 3.4）
      │             │
      │             └─ 當前目標非樓梯 → 執行 gohome
      │
      ├─ 3.2 出現 routenotfound
      │       → 打開地圖
      │
      ├─ 3.3 打開地圖後
      │       ├─ 顯示 visibliityistoopoor → 執行 gohome
      │       └─ 正常 → 繼續搜尋目標
      │
      └─ 3.4 樓梯換樓成功判定
              → 彈出當前樓梯目標
              → 打開地圖
              → 繼續下一個目標
```

---

## Gohome 狀態追蹤

當執行 gohome 時，會設置 `runtimeContext._GOHOME_IN_PROGRESS = True`。

### 處理流程

```
開始 gohome
  ↓
_GOHOME_IN_PROGRESS = True
  ↓
持續點擊 gohome 按鈕
  │
  ├─ 遇到戰鬥 → 處理戰鬥 → 返回 DungeonState.Dungeon
  │                        → 檢測到 _GOHOME_IN_PROGRESS = True
  │                        → 繼續 gohome（不進入 Resume 優化）
  │
  ├─ 遇到寶箱 → 處理寶箱 → 返回 DungeonState.Dungeon
  │                        → 檢測到 _GOHOME_IN_PROGRESS = True
  │                        → 繼續 gohome（不進入 Resume 優化）
  │
  └─ 成功回城 (DungeonState.Quit)
       → _GOHOME_IN_PROGRESS = False
```

---

## 關鍵參數

| 參數 | 值 | 說明 |
|------|-----|------|
| `MAX_RESUME_DETECT_RETRIES` | 3 | Resume 按鈕檢測最大重試次數 |
| `MAX_RESUME_RETRIES` | 5 | Resume 按鈕點擊最大次數 |
| 靜止判定閾值 | 0.02 | 畫面差異 < 0.02 視為靜止 |

---

## 關鍵說明

| 項目 | 說明 |
|------|------|
| **回城中斷恢復** | 戰鬥/寶箱結束後檢查 `_GOHOME_IN_PROGRESS`，為 True 則繼續回城 |
| **Resume 按鈕檢測** | 最多重試 3 次（每次間隔 1 秒），等待畫面過渡 |
| **Resume 點擊失敗（5次）** | 畫面沒變化 或 沒出現 routenotfound → 檢查目標類型 |
| **樓梯目標 Resume 失敗** | 判定為換樓成功 → 彈出目標 → 打開地圖繼續 |
| **非樓梯目標 Resume 失敗** | 執行 gohome 回城 |
| **出現 routenotfound** | 已到達目的地 → 打開地圖 |
| **打開地圖後 visibliityistoopoor** | 執行 gohome |

---

## 樓梯換樓判定邏輯

### 問題背景

在暴風雪地形（如深雪 R5/R6）中，換樓後可能無法打開地圖，導致無法通過傳統方式（檢測樓層標識圖片）判斷是否換樓成功。

### 解決方案

**利用 Resume 失效來判斷換樓成功**：

1. Resume 是用來繼續之前的移動路徑
2. 換樓後，之前的路徑失效（目標在上一樓）
3. 因此 **Resume 失效 = 換樓成功**

### 處理流程

```
目標：去樓梯 stair_XXX
     ↓
移動中，Resume 失效（點擊 5 次無反應）
     ↓
檢查當前目標類型
     ↓
目標是 stair_XXX → 判定換樓成功 → 彈出目標 → 繼續下一個目標
目標不是樓梯   → 執行 gohome 回城
```

### 適用的目標類型

所有以 `stair` 開頭的目標都會觸發此邏輯：
- `stair_up`, `stair_down`, `stair_teleport`（內建樓梯）
- `stair_DH_R5`, `stair_fortress1f` 等（自定義樓梯）

---

## 依賴的圖片資源

- `resume.png` - Resume 按鈕圖片（位於 `resources/images/`）
- `routenotfound.png` - 路徑無效提示圖片（位於 `resources/images/`）
- `visibliityistoopoor.png` - 能見度差提示圖片（位於 `resources/images/`）
- `gohome.png` - 回家按鈕圖片（位於 `resources/images/`）

---

## RuntimeContext 新增變數

| 變數 | 類型 | 預設值 | 說明 |
|------|------|--------|------|
| `_FIRST_DUNGEON_ENTRY` | bool | True | 第一次進入地城標誌 |
| `_GOHOME_IN_PROGRESS` | bool | False | 正在回城標誌 |

---

## 設定開關

此功能受 `setting._ENABLE_RESUME_OPTIMIZATION` 控制。

### GUI 控制

**位置**: GUI 面板中的複選框  
**文字**: "啟用Resume按鈕優化(減少地圖操作)"  
**預設值**: 啟用（勾選）

| 設定 | 效果 |
|------|------|
| ✅ 啟用 | 使用 Resume + routenotfound 檢測邏輯 |
| ❌ 停用 | 直接打開地圖（原始邏輯） |

---

## 重啟後 / 返回後行為

### 重啟後（控制項：「重啟後首戰使用強力技能」）

**觸發條件**：
- 遊戲重啟（`restartGame()` 被調用，通常是因為閃退/卡死）
- **注意**：正常啟動腳本不會觸發（初始值 = 0）

當 `_FIRST_COMBAT_AFTER_RESTART > 0` 時：

1. **跳過 Resume 優化**：直接打開地圖（因為之前的路徑可能已失效）
2. **前兩次戰鬥**：強制使用強力單體技能（`PHYSICAL_SKILLS`），讓遊戲記住技能選擇

### 返回後（控制項：「返回後首戰使用強力技能」）

當從村庄返回地城後（`_FIRST_COMBAT_AFTER_INN = True`）：

1. **第一次戰鬥**：強制使用強力單體技能

### 相關變數

| 變數 | 類型 | 預設值 | 說明 |
|------|------|--------|------|
| `_FORCE_PHYSICAL_FIRST_COMBAT` | bool | True | 重啟後首戰使用強力技能 |
| `_FORCE_PHYSICAL_AFTER_INN` | bool | True | 返回後首戰使用強力技能 |
| `_FIRST_COMBAT_AFTER_RESTART` | int | 2 | 重啟後戰鬥計數器（倒數） |
| `_FIRST_COMBAT_AFTER_INN` | bool | False | 返回後第一次戰鬥標誌 |

### 強力單體技能列表

定義於 `script.py` 的 `PHYSICAL_SKILLS`：

```python
PHYSICAL_SKILLS = ["unendingdeaths","全力一击","tzalik","居合","精密攻击","锁腹刺","破甲","星光裂","迟钝连携击","强袭","重装一击","眩晕打击","幻影狩猎"]
```

如需新增技能，直接編輯此列表，並確保對應的圖片存在於 `resources/images/spellskill/` 資料夾。
