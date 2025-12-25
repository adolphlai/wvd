---
name: 寶箱搜尋優化
description: "⚠️ 未完成功能：模組已開發但未整合到主程式。說明基於歷史記錄的寶箱搜尋優化機制。當使用者詢問寶箱搜尋效率或方向跳過邏輯時，應告知此功能尚未啟用。"
---

# 寶箱搜尋優化功能

> ⚠️ **注意：此功能尚未完成整合**
>
> - 模組位置：`src/chest_search_optimizer.py`
> - 狀態：**已開發，但未整合到主程式 `script.py`**
> - 目前寶箱搜尋使用原始邏輯，不會自動跳過方向

---

## 設計目標（待實現）

基於歷史記錄的智能方向跳過系統，自動學習哪些方向沒有寶箱。

## 模組現況

### 檔案位置
`src/chest_search_optimizer.py` - `ChestSearchOptimizer` 類

### 實際實現的功能
- 基於**當前會話**的區域標記（不是跨會話的歷史記錄）
- 每次進入地城 `reset()` 重置
- 記錄滑動偏移判斷當前區域
- 同一會話內已搜索區域會被跳過

### 數據文件
`chest_search_history.json`（不是 `chest_direction_history.json`）

```json
{
  "地城名稱": {
    "區域": {
      "found_count": 0,
      "search_count": 0,
      "last_search": "2025-..."
    }
  }
}
```

## 原始設計（未實現）

以下是原始設計的跳過邏輯，目前**尚未實現**：

### 預計存儲結構
```json
{
  "地城名稱": {
    "chest": {
      "左上": {"attempts": 5, "found": 2},
      "右上": {"attempts": 3, "found": 0}
    }
  }
}
```

### 預計跳過邏輯
```python
if attempts >= 3 and found == 0:
    return False  # 跳過該方向
```

### 配置A vs 配置B（設計概念）

| 特性 | 配置A | 配置B |
|------|-------|-------|
| 目標項數量 | 1個 `["chest"]` | 多個 `["chest", "左上", null]` |
| 每個目標方向數 | 5個 | 1個 |
| 找到就停止 | ✅ | ❌ |

## 待辦事項

1. 將 `ChestSearchOptimizer` 整合到 `script.py`
2. 在 `StateSearch` 中調用優化器
3. 實現跨會話的方向跳過邏輯
4. 測試歷史記錄功能
