---
description: 整理背包自動放入倉庫功能
---

# 整理背包功能

## 功能概述

返回城鎮後自動將指定物品放入倉庫。

## 配置變數

```python
["organize_backpack_enabled_var", tk.BooleanVar, "_ORGANIZE_BACKPACK_ENABLED", False],
["organize_backpack_count_var",   tk.IntVar,     "_ORGANIZE_BACKPACK_COUNT",   0],
```

## 執行流程

1. 點選角色座標 → Sleep(5)
2. 點選 inventory → Sleep(5)
3. 遍歷物品：點擊 → Sleep(5) → 點 putinstorage → Sleep(5)
4. 關閉 inventory → Sleep(5)
5. 返回角色選擇 → Sleep(5)

## 角色座標

| 角色 | X | Y |
|------|-----|------|
| 0 | 162 | 1333 |
| 1 | 465 | 1333 |
| 2 | 750 | 1333 |
| 3 | 162 | 1515 |
| 4 | 465 | 1515 |
| 5 | 750 | 1515 |

## 使用方法

### 正式使用
1. 將物品圖片放入 `resources/images/Organize/`
2. 在「進階設定」啟用整理背包
3. 設定角色數量

### 獨立測試
1. 確保遊戲在 Inn 角色選擇畫面
2. 切換到「測試」分頁
3. 點擊「測試整理背包」

## 需要的圖片

| 圖片 | 路徑 |
|------|------|
| inventory.png | resources/images/ |
| putinstorage.png | resources/images/ |
| closeInventory.png | resources/images/ |
| *.png | resources/images/Organize/ |
