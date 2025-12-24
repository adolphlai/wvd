# 小地圖樓梯偵測功能說明

## 功能概述

`minimap_stair` 是一個目標類型，透過偵測**主畫面右上角小地圖**中的樓層標識來判斷是否已通過樓梯，無需打開大地圖確認樓層。

---

## 配置格式

```json
["minimap_stair", "方向", [樓梯座標], "樓層圖片名稱"]
```

| 參數 | 說明 |
|------|------|
| 第1個 | 固定 `"minimap_stair"` |
| 第2個 | 滑動方向（`"左上"`, `"右上"`, `"左下"`, `"右下"` 等） |
| 第3個 | 樓梯在大地圖上的座標 `[x, y]` |
| 第4個 | 到達後在小地圖中應出現的樓層標識圖片名稱 |

---

## 範例

```json
"_TARGETINFOLIST":[
    ["minimap_stair", "右下", [73,1240], "DH-R5-minimap"],
    ["harken", "左上", null]
]
```

---

## 處理邏輯

```
【StateSearch 函數】
│
├─ 識別 minimap_stair 類型
│
├─ 設置 runtimeContext._MINIMAP_STAIR_FLOOR_TARGET = "DH-R5-minimap"
│
├─ 設置 runtimeContext._MINIMAP_STAIR_IN_PROGRESS = True
│
├─ 點擊樓梯座標開始移動
│
└─ 調用 StateMoving_CheckFrozen() 監控移動
      │
      └─【StateMoving_CheckFrozen 函數】
            │
            ├─ 持續截圖主畫面
            │
            ├─ 在小地圖區域搜索樓層標識
            │   └─ ROI: (651,24) 到 (870,244)
            │
            ├─ 偵測到樓層標識
            │   ├─ 清除 _MINIMAP_STAIR_FLOOR_TARGET
            │   ├─ 清除 _MINIMAP_STAIR_IN_PROGRESS
            │   └─ 打開地圖繼續下一個目標
            │
            └─ 返回 StateSearch → 彈出目標
```

---

## 關鍵變數

### runtimeContext._MINIMAP_STAIR_FLOOR_TARGET

| 屬性 | 說明 |
|------|------|
| 類型 | `str` 或 `None` |
| 設置時機 | `StateSearch()` 中，移動開始前 |
| 清除時機 | `StateMoving_CheckFrozen()` 中，偵測到樓層標識後 |

### runtimeContext._MINIMAP_STAIR_IN_PROGRESS

| 屬性 | 說明 |
|------|------|
| 類型 | `bool` |
| 設置時機 | `StateSearch()` 中，移動開始前 |
| 清除時機 | `StateMoving_CheckFrozen()` 中，偵測到樓層標識後 |

---

## 小地圖 ROI

固定區域：左上角 `(651, 24)` 到 右下角 `(870, 244)`

```python
MINIMAP_ROI = [651, 24, 870, 244]  # [x1, y1, x2, y2]
```

---

## 與 stair 類型的差異

| 項目 | stair_XXX | minimap_stair |
|------|-----------|---------------|
| 偵測時機 | 點擊前（在地圖上確認） | 移動中（持續監控小地圖） |
| 偵測位置 | 地圖界面 | 主畫面右上角小地圖 |
| 用途 | 一般樓梯（地圖可見） | Resume 優化模式下的樓梯 |

---

## 圖片資源

需要在 `resources/images/` 中準備小地圖樓層標識圖片：

| 圖片名稱 | 說明 |
|----------|------|
| `DH-R5-minimap.png` | 深雪 R5 層在小地圖中的標識 |

---

## 測試功能

GUI 測試分頁中提供獨立測試功能：

1. 開啟程式 → 切換到「測試」分頁
2. 輸入樓層圖片名稱、樓梯座標、滑動方向
3. 點擊「測試完整流程」
4. 觀察日誌輸出

---

## 更新歷史

- **2024-12-24**：新增 minimap_stair 目標類型
- **2024-12-24**：整合到主流程（StateSearch + StateMoving_CheckFrozen）
- **2024-12-24**：新增 GUI 測試功能
