# chest 類型整合完成報告

## 修改完成

已成功將 `chest` 目標類型整合到 DungeonMover 架構中。

## 修改內容

### 1. `initiate_move` 函數 (L3745-3755)

**位置**：`src/script.py:3745-3755`

新增 `chest` 類型的路由分支：

```python
elif self.current_target == 'chest':
    return self.chest_navigation(targetInfoList, ctx)
```

這個分支位於 `chest_auto` 之後、`gohome` 之前。

---

### 2. `chest_navigation` 函數 (L3820-3867)

**位置**：`src/script.py:3820-3867`

新增獨立的 `chest_navigation` 函數，處理流程：

1. **檢查戰鬥/寶箱狀態**（避免在錯誤狀態下開地圖）
2. **確保地圖開啟**
   - 如果地圖未開啟，嘗試打開
   - 連續 3 次失敗觸發 GoHome
3. **使用 `StateMap_FindSwipeClick` 搜索寶箱**
   - 找到：點擊 + automove → 進入 `_monitor_move`
   - 找不到：pop 目標，返回 Map 狀態

**完成檢測**：使用 `routenotfound`（與 position 相同）

---

## 設計特點

✅ **完全不修改 `resume_navigation`**  
✅ **使用獨立函數，邏輯清晰**  
✅ **複用現有的 `StateMap_FindSwipeClick` 和 `_monitor_move`**  
✅ **支援連續開地圖失敗保護機制**  
✅ **代碼編譯通過，無語法錯誤**

---

## 使用方式

在 `quest.json` 中定義 chest 類型目標：

```python
TargetInfo('chest', swipeDir, roi)
```

**參數說明：**
- `'chest'`：目標類型
- `swipeDir`：地圖滑動方向（列表格式）
- `roi`：搜尋區域（ROI）

**範例**（參考 v1.9.20）：
```python
TargetInfo('chest', ['撌虫?'], [[0,0,900,1600],[640,0,260,1600],[506,0,200,700]])
```

---

## 驗證步驟

### 手動測試

1. **測試 chest 類型**
   - 在 `quest.json` 中設定一個使用 `chest` 類型的地城
   - 運行腳本，觀察日誌：
     - `[DungeonMover] chest: 打開地圖`
     - `[DungeonMover] chest: 找到寶箱位置 [x, y]`
   - 預期：找到寶箱時移動，找不到時 pop

2. **測試 position/harken 仍正常**
   - 運行原本正常的地城（如 Deep Sleep City）
   - 確認 position/harken 類型仍能正確執行
   - 預期：行為與修改前完全一致

---

## 與原版 chest 的差異

| 項目 | v1.9.20 chest | 現行 chest |
|------|---------------|-----------|
| 搜尋方式 | 直接調用 `StateMap_FindSwipeClick` | ✅ 相同 |
| 開地圖處理 | 由 `StateSearch` 處理 | ✅ 整合到 `chest_navigation` |
| 找不到處理 | 直接 pop | ✅ 相同 |
| 完成檢測 | `StateMoving_CheckFrozen` | ✅ `_monitor_move` (功能相同) |
| 超時保護 | 無 | ✅ 新增（連續失敗 → GoHome） |

---

## 後續建議

1. **實際測試**：找一個包含 chest 目標的地城進行測試
2. **日誌監控**：觀察 `[DungeonMover] chest:` 開頭的日誌
3. **回退計劃**：如有問題，可以直接切回 master 分支

---

## Git 分支

- 分支名稱：`chestcombine`
- 修改文件：`src/script.py`
- 修改行數：約 +52 行
