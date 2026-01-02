# chest_auto 機制文檔

## 概述

`chest_auto` 是一種自動尋找寶箱的目標類型，透過圖像識別尋找畫面中的寶箱按鈕並自動點擊移動。

---

## 配置方式

```json
// quest.json
"_TARGETINFOLIST":[
    ["chest_auto"],               // 第一優先
    ["position","右上",[771,921]] // 備選
]
```

**特點**：
- `chest_auto` 是單元素陣列 `["chest_auto"]`，沒有其他參數
- 通常作為目標列表的第一個元素
- 後續搭配 `position` 目標作為備選方案

---

## 處理流程

### _start_chest_auto (script.py:3273)

```
_start_chest_auto
    │
    ├─ 在主畫面找按鈕 (ROI: [710,250,180,180])
    │   ├─ 找到 → 點擊
    │   ├─ 偵測到 notresure → pop 目標，返回 Map
    │   └─ 找不到 → 打開地圖 → 再找一次
    │       ├─ 找到 → 點擊（嘗試一次）
    │       └─ 都找不到 → 點擊盲點座標 [459, 1248]（嘗試一次）
    │
    └─ 進入 _monitor_move
```

### _monitor_move (chest_auto 專用邏輯)

```
_monitor_move (is_chest_auto = True)
    │
    ├─ 每次循環檢查
    │   ├─ 偵測 notresure → pop 目標，返回 Map
    │   ├─ 狀態轉換（戰鬥、寶箱等）→ 正常處理
    │   └─ chest_resume: 每 5 秒點擊一次寶箱按鈕
    │
    └─ 靜止判定（連續 2 次 diff < 0.1）
        │
        ├─ 檢測 mapFlag（已在地圖狀態）
        │   └─ PressReturn 離開地圖，pop 目標，返回 Map
        │
        └─ 無 mapFlag（主畫面狀態）
            └─ 直接 pop 目標，返回 Map
```

---

## 與其他目標的差異

| 項目 | chest_auto | position/harken |
|------|-----------|-----------------|
| Resume 檢查 | 不使用 | 3秒間隔 |
| 更新間隔 | 5 秒 | 3 秒 |
| 搜索區域 | 固定 `[710,250,180,180]` | 依配置 |
| 首次進入地城 | 跳過自動打開地圖 | 正常打開 |
| 靜止判定 | 2 次 → pop 目標 | 10 次 → 判定到達 |

---

## 關鍵座標

| 用途 | 座標 |
|------|------|
| 搜索區域 (ROI) | `[710, 250, 180, 180]` |
| 地圖按鈕 | `[777, 150]` |
| 盲點座標 | `[459, 1248]` |

---

## 超時機制

| 超時類型 | 時間 | 觸發動作 |
|---------|------|---------|
| 軟超時 | 60s | 切換 GoHome 模式 |
| 硬超時 | 90s | 重啟遊戲 |

---

## 失敗處理

| 情況 | 處理方式 |
|------|---------|
| 按鈕找不到 | 點擊盲點座標 `[459, 1248]` |
| 主畫面持續靜止 2 次 | 直接 pop 目標，返回 Map |
| MAP 狀態持續靜止 2 次 | PressReturn 離開，pop 目標 |
| 偵測到 `notresure` | 直接 pop 目標，返回 Map |

---

## 常數設定

```python
POLL_INTERVAL = 0.5                    # 輪詢間隔
CHEST_AUTO_STILL_THRESHOLD = 2         # chest_auto 靜止判定次數
CHEST_AUTO_CLICK_INTERVAL = 5          # chest_auto 檢查間隔
```

---

## 關鍵程式碼位置

| 項目 | 檔案路徑 | 行號 |
|------|---------|------|
| 配置定義 | `resources/quest/quest.json` | 5-7, 20-22 等 |
| TargetInfo 類 | `src/script.py` | 462-496 |
| DungeonMover 類 | `src/script.py` | 3150-3637 |
| _start_chest_auto | `src/script.py` | 3273-3307 |
| _monitor_move | `src/script.py` | 3381-3636 |
| chest_auto 靜止處理 | `src/script.py` | 3549-3564 |
