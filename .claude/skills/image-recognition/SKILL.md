---
name: 圖像識別引擎
description: 說明基於 OpenCV 模板匹配的圖像識別系統，包含 CheckIf 系列函數、ROI 裁剪、多模板匹配。當使用者詢問圖片識別、模板匹配、或 CheckIf 相關問題時，應啟用此技能。
---

# 圖像識別引擎 (Template Matching System)

## 檔案位置
`src/script.py`

## 核心函數

### CheckIf() - 主要識別函數
- **位置**: line 842
- **參數**:
  - `screen`: 截圖（numpy array）
  - `name`: 模板名稱（不含 .png）
  - `thres`: 匹配閾值（預設 0.9）
  - `rect`: ROI 區域 `[x1, y1, x2, y2]`
  - `returnPos`: 是否返回座標
  - `returnVal`: 是否返回匹配值
  - `returnSize`: 是否返回模板尺寸

- **多模板支援**:
  ```python
  # 自動嘗試 harken.png, harken2.png, harken3.png...
  CheckIf(screen, 'harken')
  ```

- **返回值**:
  - 預設: `True/False`
  - `returnPos=True`: `(x, y)` 或 `None`
  - `returnVal=True`: `float` 匹配度

### CheckIf_MultiRect() - 多區域檢測
- **位置**: line 893
- **功能**: 在多個 ROI 區域中檢測模板
- **用途**: 同時檢測多個可能位置

### CheckIf_FocusCursor() - 焦點遊標檢測
- **位置**: line 916
- **功能**: 檢測選單遊標位置
- **用途**: 確認當前選中的選項

### CheckIf_ReachPosition() - 到達位置檢測
- **位置**: line 946
- **功能**: 檢測是否到達目標位置
- **用途**: 判斷移動是否完成

### CheckIf_throughStair() - 樓梯通過檢測
- **位置**: line 963
- **功能**: 檢測是否通過樓梯
- **用途**: 換樓判定

### CheckIf_minimapFloor() - 小地圖樓層檢測
- **位置**: line 997
- **功能**: 在小地圖上檢測樓層標識
- **用途**: minimap_stair 功能

### CheckIf_fastForwardOff() - 快進關閉檢測
- **位置**: line 1036
- **功能**: 檢測快進是否關閉
- **用途**: 確保戰鬥加速開啟

## 模板圖片位置
`src/res/` 目錄下的 `.png` 文件

## 常用模板

| 模板名稱 | 用途 |
|----------|------|
| `mapFlag` | 地圖打開狀態 |
| `resume` | Resume 按鈕 |
| `routenotfound` | 路徑無效 |
| `chestFlag` | 寶箱標識 |
| `combatActive` | 戰鬥中 |
| `harken` | Harken 標識 |
| `gohome` | 回家按鈕 |

## ROI 區域定義

常用 ROI 定義在 `setting` 物件中：
```python
setting._MAPRECT     # 地圖區域
setting._COMBATRECT  # 戰鬥區域
setting._CHESTRECT   # 寶箱區域
```

## 匹配閾值建議

| 場景 | 閾值 |
|------|------|
| 精確匹配（按鈕） | 0.9 |
| 一般匹配 | 0.85 |
| 模糊匹配（變化大） | 0.75 |
