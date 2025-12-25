---
name: Quest.json 配置說明
description: 說明 quest.json 的配置格式，包含目標類型、滑動方向、ROI 參數、_EOT 結束動作等。當使用者詢問如何配置任務、新增地城目標、或設定 TARGETINFOLIST 時，應啟用此技能。
---

# Quest.json 配置說明

本技能說明 `resources/quest/quest.json` 的配置格式和所有可用選項。

## 任務結構基本格式

每個任務是一個 JSON 物件：

```json
"任務ID": {
    "_TYPE": "dungeon",
    "questName": "顯示在 GUI 的名稱",
    "_TARGETINFOLIST": [...],
    "_EOT": [...],
    "_preEOTcheck": "可選",
    "_SPELLSEQUENCE": {...}
}
```

## 目標類型 (_TARGETINFOLIST)

每個目標格式：`[目標類型, 滑動方向, ROI/座標]`

### 常用目標類型
| 類型 | 格式 | 說明 |
|------|------|------|
| `position` | `["position", "右下", [713, 1027]]` | 走到指定座標 |
| `stair_XXX` | `["stair_fortress1f", "左上", [720, 395]]` | 樓梯 |
| `minimap_stair` | `["minimap_stair", "右下", [73,1240], "DH-R5-minimap"]` | 小地圖樓梯偵測 |
| `chest` | `["chest", "左上", [[0,0,900,1600]]]` | 寶箱搜索 |
| `harken` | `["harken", "左下", null]` 或 `["harken", "方向", ROI, "樓層"]` | 哈肯傳送 |

### 滑動方向
| 值 | 說明 |
|----|------|
| `null` | 全方向搜索（6個方向）|
| `"左上"` / `"右上"` / `"左下"` / `"右下"` | 指定方向滑動 |

### ROI 參數
| 值 | 說明 |
|----|------|
| `null` | 全螢幕搜索 |
| `[x, y]` | 指定座標 |
| `[[x,y,w,h]]` | 限制搜索區域 |
| `"default"` | 預設排除區域 |

## _EOT 結束動作

格式：`["動作", "圖片名稱", "回退操作", 等待時間]`

```json
"_EOT": [
    ["press", "TradeWaterway", ["EdgeOfTown", [1,1]], 1],
    ["press", "Dist", "input swipe 650 250 650 900", 1]
]
```

## 完整範例

```json
"DH-6f": {
    "_TYPE": "dungeon",
    "questName": "*新!*[宝箱+刷怪]深雪R6",
    "_TARGETINFOLIST": [
        ["position", "左上", [35, 707]],
        ["chest", "左下", [[0,0,900,1600]]],
        ["stair_DH_R5", "右下", [73, 1240]],
        ["harken", "左上", null]
    ],
    "_EOT": [
        ["press", "DH", ["EdgeOfTown", [1,1]], 1],
        ["press", "DH-R6", "input swipe 650 250 650 900", 1]
    ]
}
```
