# Harken 樓層選擇邏輯說明

## 執行前提

> **harken 是地城目標之一，用於觸發哈肯傳送**

---

## 修改位置

| 功能 | 檔案 | 函數 |
|------|------|------|
| TargetInfo 類定義 | `src/script.py` | `class TargetInfo` |
| 多模板匹配 | `src/script.py` | `get_multi_templates()`, `CheckIf()` |
| 地圖搜索 | `src/script.py` | `StateMap_FindSwipeClick()` |
| 設置樓層 flag | `src/script.py` | `StateSearch()` |
| 樓層選擇處理 | `src/script.py` | `IdentifyState()` |

---

## 配置格式

### 基本格式（返回城鎮）

```json
["harken", "方向", null]
```

### 完整格式（樓層選擇）

```json
["harken", "方向", ROI, "樓層圖片名稱"]
```

| 參數位置 | 名稱 | 類型 | 說明 |
|---------|------|------|------|
| 第1個 | target | string | 固定 `"harken"` |
| 第2個 | swipeDir | string/null | 滑動方向：`"左上"`, `"右上"`, `"左下"`, `"右下"`, `null` |
| 第3個 | roi | array/null | 搜索區域限制：`null` 全螢幕，`[[x,y,w,h]]` 限制區域 |
| 第4個 | floorImage | string/null | 樓層圖片名稱（可選），如 `"DH-R5"` |

---

## 處理邏輯

### 階段 1：地圖搜索 (StateMap_FindSwipeClick)

```
【DungeonState.Map 狀態】
│
├─ 1. 多模板匹配
│     │
│     ├─ 掃描 resources/images/ 中符合 harken\d* 的圖片
│     │   （harken.png, harken2.png, harken3.png...）
│     │
│     ├─ 依序嘗試每個模板進行匹配
│     │
│     └─ 選擇匹配度最高的結果
│           │
│           ├─ 匹配度 >= 80% → 返回座標
│           │
│           └─ 匹配度 < 80% → 滑動地圖繼續搜索
│
└─ 2. 返回 harken 座標給 StateSearch
```

### 階段 2：設置樓層 flag 並開始移動 (StateSearch)

```
【StateSearch 函數】
│
├─ 接收到 harken 座標
│
├─ 檢查 targetInfo.floorImage 是否設置
│     │
│     ├─ 已設置 (如 "DH-R5")
│     │     │
│     │     └─ 設置 runtimeContext._HARKEN_FLOOR_TARGET = "DH-R5"
│     │        └─ 日誌: "哈肯樓層選擇: 設置目標樓層 DH-R5"
│     │
│     └─ 未設置 → 跳過此步驟
│
├─ 點擊 harken 座標
│
├─ 點擊 automove 按鈕 [280, 1433]
│
└─ 調用 StateMoving_CheckFrozen() 監控移動
```

### 階段 3：傳送後狀態檢測 (IdentifyState)

```
【IdentifyState 函數】
│
├─ 0. 檢查停止信號
│     └─ 設置了 _FORCESTOPING → 返回 Quit 狀態
│
├─ 1. 優先檢查 harken 樓層選擇 (如果 _HARKEN_FLOOR_TARGET != None)
│     │
│     ├─ 搜索樓層圖片 (如 DH-R5.png)
│     │     │
│     │     ├─ 找到樓層按鈕
│     │     │     │
│     │     │     ├─ 點擊樓層按鈕
│     │     │     ├─ 清除 _HARKEN_FLOOR_TARGET = None
│     │     │     ├─ 日誌: "哈肯樓層選擇: 點擊樓層 DH-R5"
│     │     │     └─ 遞歸調用 IdentifyState()
│     │     │
│     │     └─ 未找到樓層按鈕
│     │           │
│     │           └─ 檢查 returnText
│     │                 │
│     │                 ├─ 找到 returnText → 點擊並等待
│     │                 │     └─ 日誌: "哈肯樓層選擇: 等待樓層 DH-R5 出現..."
│     │                 │     └─ 遞歸調用 IdentifyState()
│     │                 │
│     │                 └─ 未找到 → 繼續狀態檢測
│     │
│     └─ (如果 _HARKEN_FLOOR_TARGET = None，跳過此步驟)
│
├─ 2. 標準狀態檢測 (identifyConfig)
│     │
│     ├─ combatActive → 進入戰鬥
│     ├─ dungFlag → 進入地城狀態
│     ├─ chestFlag → 進入寶箱狀態
│     └─ mapFlag → 進入地圖狀態
│
└─ 3. 正常返回處理 (只有當 _HARKEN_FLOOR_TARGET = None 時)
      │
      ├─ returnText → 點擊返回
      │
      └─ returntoTown → 回城完成
```

---

## 多模板匹配邏輯

### 匹配流程

```
搜索 "harken"
    │
    ▼
調用 get_multi_templates("harken")
    │
    ├─ 掃描 resources/images/harken*.png
    │
    ├─ 過濾：只保留符合 harken\d* 模式的檔案
    │   ✓ harken.png
    │   ✓ harken2.png
    │   ✓ harken3.png
    │   ✗ harken_floor.png
    │   ✗ harken_special.png
    │
    └─ 返回模板列表: ['harken', 'harken2', ...]
    │
    ▼
CheckIf() 函數
    │
    ├─ 對每個模板進行 cv2.matchTemplate()
    │
    ├─ 記錄最佳匹配（匹配度最高的模板）
    │
    ├─ 日誌輸出:
    │   "搜索到疑似harken, 匹配程度:79.05%"
    │   "搜索到疑似harken2, 匹配程度:84.32%"
    │   "多模板匹配: 選擇 harken2 (匹配度 84.32%)"
    │
    └─ 返回最佳匹配的座標
```

### 支持的檔案命名

| 檔案名 | 正則匹配 | 是否使用 |
|--------|----------|----------|
| `harken.png` | `^harken\d*$` | ✓ |
| `harken2.png` | `^harken\d*$` | ✓ |
| `harken3.png` | `^harken\d*$` | ✓ |
| `harken10.png` | `^harken\d*$` | ✓ |
| `harken_floor.png` | 不匹配 | ✗ |
| `harken_special.png` | 不匹配 | ✗ |

---

## 關鍵變數

### runtimeContext._HARKEN_FLOOR_TARGET

| 屬性 | 說明 |
|------|------|
| 類型 | `str` 或 `None` |
| 預設值 | `None` |
| 設置時機 | `StateSearch()` 中，移動開始前 |
| 清除時機 | `IdentifyState()` 中，點擊樓層按鈕後 |
| 作用 | 告訴 IdentifyState 傳送後應該點擊哪個樓層按鈕 |

### runtimeContext._HARKEN_TELEPORT_JUST_COMPLETED

| 屬性 | 說明 |
|------|------|
| 類型 | `bool` |
| 預設值 | `False` |
| 設置時機 | `IdentifyState()` 中，點擊樓層按鈕後 |
| 清除時機 | `StateMoving_CheckFrozen()` 中，檢測到傳送完成後 |
| 作用 | 通知 StateMoving_CheckFrozen 傳送已完成，應立即退出移動監控 |

### targetInfo.floorImage

| 屬性 | 說明 |
|------|------|
| 類型 | `str` 或 `None` |
| 來源 | quest.json 中 harken 目標的第4個參數 |
| 傳遞路徑 | quest.json → TargetInfo → runtimeContext._HARKEN_FLOOR_TARGET |

---

## 階段 4：傳送完成檢測 (StateMoving_CheckFrozen)

```
【StateMoving_CheckFrozen 函數】
│
├─ 監控移動狀態
│
├─ 調用 IdentifyState() 獲取當前狀態
│     │
│     └─ IdentifyState 內部:
│           ├─ 點擊樓層按鈕
│           ├─ 設置 _HARKEN_TELEPORT_JUST_COMPLETED = True
│           └─ 返回 dungFlag (DungeonState.Dungeon)
│
├─ 檢測傳送完成條件:
│     │
│     ├─ _HARKEN_FLOOR_TARGET == None (樓層按鈕已點擊)
│     │
│     └─ _HARKEN_TELEPORT_JUST_COMPLETED == True
│           │
│           └─ 符合條件:
│                 ├─ 日誌: "哈肯樓層傳送完成，退出移動監控"
│                 ├─ 清除 _HARKEN_TELEPORT_JUST_COMPLETED = False
│                 └─ 立即退出移動監控循環
│
└─ (如果未設置傳送完成標記，繼續正常的 Resume 按鈕檢測)
```

---

## 目標切換

harken 目標完成後會自動彈出 (pop)，切換到下一個目標：

```
【StateSearch 函數】
│
├─ harken 移動完成
│
├─ 彈出當前目標: targetInfoList.pop(0)
│     └─ 日誌: "哈肯目標完成，切換到下一個目標"
│
└─ 返回狀態讓下一個目標繼續執行
```

---

## 配置範例

```json
// 1. 返回城鎮，全螢幕搜索
["harken"]

// 2. 返回城鎮，指定方向
["harken", "左下", null]

// 3. 返回城鎮，限制搜索區域（ROI 必須是二維陣列）
["harken", "右上", [[750, 850, 150, 150]]]

// 4. 跳轉樓層，不限制搜索區域
["harken", "左上", null, "DH-R6"]

// 5. 跳轉樓層，限制搜索區域
["harken", "右下", [[700, 800, 200, 200]], "DH-R5"]

// 6. 多個 harken 目標（先跳樓層，再返回城鎮）
"_TARGETINFOLIST":[
    ["harken", "右上", [[769,874,131,68]], "DH-R5-harken"],
    ["harken", "左上", null]  // 3個參數 = 返回城鎮
]
```

---

## 依賴的圖片資源

| 圖片 | 路徑 | 用途 |
|------|------|------|
| harken 模板 | `resources/images/harken.png` | 地圖上的 harken 圖標 |
| harken 變體 | `resources/images/harken2.png` | 地圖上的 harken 圖標變體 |
| 樓層按鈕 | `resources/images/DH-R5.png` 等 | 傳送後的樓層選擇按鈕 |
| returnText | `resources/images/returnText.png` | "返回" 文字圖片 |
| returntoTown | `resources/images/returntoTown.png` | 返回城鎮確認 |

---

## 常見問題

### Q: 為什麼 harken 找不到正確位置？

**可能原因**：
1. 只有 `harken.png` 匹配度不夠高
2. harken 圖標與模板不匹配

**解決方案**：
1. 新增 `harken2.png` 等變體模板
2. 或設置 ROI 限制搜索區域

### Q: 樓層選擇不生效，仍然返回城鎮？

**可能原因**：
1. `floorImage` 參數值錯誤（圖片不存在）
2. 第3個參數 ROI 格式不正確

**解決方案**：
1. 確認 `resources/images/` 中有對應的樓層圖片
2. 確認 ROI 格式為二維陣列 `[[x,y,w,h]]`
3. 如不需要 ROI，明確設置為 `null`

### Q: 第二個 harken 使用了錯誤的方向？

**可能原因**：harken 完成後目標沒有正確彈出

**解決方案**：已修復。現在 harken 完成後會自動彈出目標：
```
日誌: "哈肯目標完成，切換到下一個目標"
```

### Q: 如何知道 harken 找到哪個位置？

查看日誌中的訊息：

```
搜索harken...
搜索到疑似harken, 匹配程度:79.05%
搜索到疑似harken2, 匹配程度:84.32%
多模板匹配: 選擇 harken2 (匹配度 84.32%)
找到了 harken! [822, 918]
哈肯樓層選擇: 設置目標樓層 DH-R5
面具男, 移动.
哈肯樓層選擇: 點擊樓層 DH-R5
哈肯樓層傳送完成，退出移動監控
哈肯目標完成，切換到下一個目標
```

---

## 更新歷史

- **2024-12-24**：新增樓層選擇功能（第4個參數 floorImage）
- **2024-12-24**：新增多模板匹配功能（自動嘗試 harken, harken2...）
- **2024-12-24**：將樓層選擇檢測移到 IdentifyState 優先處理
- **2024-12-24**：新增傳送完成檢測（_HARKEN_TELEPORT_JUST_COMPLETED）
- **2024-12-24**：修復 harken 目標完成後未彈出的問題

