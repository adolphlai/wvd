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
      │             → 執行 gohome
      │
      ├─ 3.2 出現 routenotfound
      │       → 打開地圖
      │
      └─ 3.3 打開地圖後
              ├─ 顯示 visibliityistoopoor → 執行 gohome
              └─ 正常 → 繼續搜尋目標
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
| **Resume 點擊失敗（5次）** | 畫面沒變化 或 沒出現 routenotfound → 執行 gohome |
| **出現 routenotfound** | 已到達目的地 → 打開地圖 |
| **打開地圖後 visibliityistoopoor** | 執行 gohome |

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

當遊戲重啟後（`_FIRST_COMBAT_AFTER_RESTART > 0`）：

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
