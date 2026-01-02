# Resume 機制文檔

## 概述

`resume` 是繼續移動的按鈕，當角色移動過程中被中斷（如戰鬥結束、開箱完成）後出現，點擊可繼續前往目的地。

---

## 處理流程

### _monitor_move (非 chest_auto 時)

```
_monitor_move (is_chest_auto = False)
    │
    ├─ 定期檢查 (每 3 秒)
    │   ├─ 檢測 resume 按鈕
    │   │   └─ 找到 → 點擊 → 檢查 routenotfound
    │   │       ├─ 有 routenotfound → 到達目的地，pop 目標
    │   │       └─ 無 → 繼續監控
    │   └─ 更新 last_resume_click_time
    │
    └─ 靜止判定 (連續 10 次 diff < 0.1)
        │
        ├─ 檢測 mapFlag（已在地圖狀態）
        │   └─ PressReturn 退出地圖，返回 Map
        │
        ├─ Resume 連續點擊（最多 5 次）
        │   ├─ 點擊 resume
        │   ├─ 等待 1 秒
        │   ├─ 檢查 routenotfound
        │   │   ├─ 有 → 到達目的地，pop 目標
        │   │   └─ 無 → 重置靜止計數，繼續監控
        │   └─ 超過 5 次無效 → 等待軟超時
        │
        ├─ 轉向解卡（最多 3 次）
        │   └─ Swipe 轉向，重置靜止計數
        │
        └─ 判定停止（無 resume 且靜止）
            └─ pop 目標，返回 Map
```

---

## 與 chest_auto 的差異

| 項目 | resume (position/harken) | chest_auto |
|------|-------------------------|------------|
| Resume 檢查 | 每 3 秒定期檢查 | 不使用 |
| 靜止閾值 | 10 次 (~5秒) | 2 次 (~1秒) |
| routenotfound 檢測 | 有 | 無 |
| 轉向解卡 | 有 (最多 3 次) | 無 |
| 連續點擊限制 | 5 次 | 無 |

---

## RouteNotFound 關係

`routenotfound` 表示角色已到達目的地附近但無法繼續前進。

```
Resume 點擊
    ↓
等待 1 秒
    ↓
檢查 routenotfound
    ├─ 是 → 到達目的地，pop 目標，返回 Map
    └─ 否 → 繼續監控
```

**檢測位置**：
- 定期檢查後：點擊 resume 後立即檢查 3 次
- 靜止判定後：點擊 resume 後檢查 1 次

---

## 常數設定

```python
POLL_INTERVAL = 0.5              # 輪詢間隔
STILL_REQUIRED = 10              # 靜止判定次數 (~5秒)
RESUME_CLICK_INTERVAL = 3        # 定期檢查間隔
MAX_RESUME_RETRIES = 5           # 連續點擊上限
MAX_TURN_ATTEMPTS = 3            # 轉向解卡上限
```

---

## 超時機制

| 超時類型 | 時間 | 觸發動作 |
|---------|------|---------|
| 軟超時 | 30s | 切換 GoHome 模式 |
| 硬超時 | 60s | 重啟遊戲 |

---

## 失敗處理

| 情況 | 處理方式 |
|------|---------|
| Resume 連續點擊 5 次無效 | 等待軟超時 |
| 轉向解卡 3 次無效 | 繼續等待 |
| 靜止且無 resume | 判定到達，pop 目標 |
| 偵測到 routenotfound | 到達目的地，pop 目標 |
| 偵測到 mapFlag | PressReturn 退出地圖 |

---

## 關鍵程式碼位置

| 項目 | 檔案路徑 | 行號 |
|------|---------|------|
| 常數定義 | `src/script.py` | 3163-3173 |
| 定期 Resume 檢查 | `src/script.py` | 3518-3539 |
| 靜止後 Resume 點擊 | `src/script.py` | 3576-3600 |
| mapFlag 檢測 | `src/script.py` | 3569-3574 |
| 轉向解卡 | `src/script.py` | 3602-3612 |
| 判定停止 | `src/script.py` | 3622-3628 |
