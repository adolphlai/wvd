---
name: 小地圖樓梯偵測
description: 說明 minimap_stair 目標類型，透過偵測主畫面右上角小地圖中的樓層標識判斷換樓。當使用者詢問小地圖偵測、minimap_stair 配置、或 Resume 優化模式下的樓梯偵測時，應啟用此技能。
---

# 小地圖樓梯偵測功能

## 功能概述

`minimap_stair` 透過偵測**主畫面右上角小地圖**中的樓層標識來判斷是否已通過樓梯。

## 配置格式

```json
["minimap_stair", "方向", [樓梯座標], "樓層圖片名稱"]
```

| 參數 | 說明 |
|------|------|
| 第1個 | 固定 `"minimap_stair"` |
| 第2個 | 滑動方向 |
| 第3個 | 樓梯在大地圖上的座標 `[x, y]` |
| 第4個 | 小地圖中的樓層標識圖片名稱 |

## 範例

```json
"_TARGETINFOLIST":[
    ["minimap_stair", "右下", [73,1240], "DH-R5-minimap"],
    ["harken", "左上", null]
]
```

## 處理邏輯

1. 設置 `_MINIMAP_STAIR_FLOOR_TARGET` 和 `_MINIMAP_STAIR_IN_PROGRESS`
2. 點擊樓梯座標開始移動
3. 持續監控小地圖區域 `(651,24)` 到 `(870,244)`
4. 偵測到樓層標識 → 清除標記 → 打開地圖繼續

## 與 stair 類型的差異

| 項目 | stair_XXX | minimap_stair |
|------|-----------|---------------|
| 偵測時機 | 點擊前（地圖確認） | 移動中（持續監控） |
| 偵測位置 | 地圖界面 | 主畫面小地圖 |
| 用途 | 一般樓梯 | Resume 優化模式 |

## 圖片資源

需要 `resources/images/DH-R5-minimap.png` 等小地圖標識圖片。
