---
description: Harken 樓層選擇與多模板匹配邏輯
---

# Harken 樓層選擇邏輯

## 配置格式

### 基本格式（返回城鎮）
```json
["harken", "方向", null]
```

### 完整格式（樓層選擇）
```json
["harken", "方向", ROI, "樓層圖片名稱"]
```

| 參數 | 說明 |
|------|------|
| target | 固定 `"harken"` |
| swipeDir | `"左上"`, `"右上"`, `"左下"`, `"右下"`, `null` |
| roi | `null` 全螢幕，`[[x,y,w,h]]` 限制區域 |
| floorImage | 樓層圖片名稱（如 `"DH-R5"`）|

## 處理邏輯

1. **地圖搜索**: 多模板匹配 `harken*.png`
2. **設置樓層 flag**: `_HARKEN_FLOOR_TARGET = "DH-R5"`
3. **傳送後檢測**: `IdentifyState()` 點擊樓層按鈕
4. **傳送完成**: `_HARKEN_TELEPORT_JUST_COMPLETED = True`

## 多模板匹配

自動嘗試 `harken.png`, `harken2.png`, `harken3.png`...，選擇匹配度最高的。

## 配置範例

```json
// 返回城鎮
["harken", "左下", null]

// 跳轉樓層
["harken", "右上", [[769,874,131,68]], "DH-R5-harken"]

// 多個 harken（先跳樓層，再返回城鎮）
"_TARGETINFOLIST":[
    ["harken", "右上", [[769,874,131,68]], "DH-R5-harken"],
    ["harken", "左上", null]
]
```

## 依賴圖片

- `harken.png`, `harken2.png` - 地圖上的 harken 圖標
- `DH-R5.png` 等 - 樓層選擇按鈕
- `returnText.png` - "返回" 文字
