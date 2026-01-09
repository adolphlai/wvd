# GUI 即時監控 Flag 分析報告

> 分析日期: 2026-01-06

## 概述

本文檔分析 GUI 即時監控面板中各 Flag 的更新機制，以及目前存在的問題。

---

## 1. 架構說明

### 1.1 監控面板位置
- **GUI 定義**: `gui.py` 行 388-500 (`_create_general_tab` 方法)
- **更新邏輯**: `gui.py` 行 1489-1702 (`_update_monitor` 方法)
- **更新頻率**: 每秒執行一次 (`self.after(1000, self._update_monitor)`)

### 1.2 過期檢測機制
```python
def get_display_value(val, threshold_val, flag_name):
    # 檢查數據是否過期 (超過 2 秒未更新視為過期)
    last_update = MonitorState.flag_updates.get(flag_name, 0)
    if current_time - last_update > 2.0:
        return "--", "black"
    return f"{val}%", "red" if val >= threshold_val else "black"
```

**設計意圖**: 只有在 flag 被主動更新時才顯示數值，超過 2 秒未更新則顯示 `--`。

---

## 2. Flag 更新位置總覽

| Flag 變數 | 更新位置 (行號) | 更新函數/場景 | 使用方式 | `flag_updates` 時間戳更新? |
|-----------|----------------|---------------|----------|---------------------------|
| `flag_dungFlag` | 4183 | DungeonMover 移動監控 | `GetMatchValue` | ❌ 無 |
| `flag_mapFlag` | 4184 | DungeonMover 移動監控 | `GetMatchValue` | ❌ 無 |
| `flag_chestFlag` | 4185 | DungeonMover 移動監控 | `GetMatchValue` | ❌ 無 |
| `flag_worldMap` | 4186 | DungeonMover 移動監控 | `GetMatchValue` | ❌ 無 |
| `flag_chest_auto` | 4187 | DungeonMover 移動監控 | `GetMatchValue` | ❌ 無 |
| `flag_auto_text` | 2170, 2197, 4188 | IdentifyState / DungeonMover | `GetMatchValue` | ❌ 無 |
| `flag_combatActive` | 2154, 3406 | IdentifyState / StateCombat | 直接計算賦值 | ❌ 無 |
| `flag_low_hp` | 4190 | DungeonMover 移動監控 | `CheckLowHP()` | ❌ 無 |

---

## 3. `flag_updates` 時間戳更新位置

| 位置 | 行號 | 條件 | 更新的 Key |
|------|------|------|-----------|
| `CheckIf()` 函數 | 1529-1535 | `shortPathOfTarget in ['dungFlag', 'mapFlag', 'chestFlag', 'combatActive', 'worldMap', 'chest_auto', 'AUTO']` | 對應的 target 名稱 |

### 3.1 CheckIf 中的更新邏輯
```python
# script.py 行 1529-1535
if shortPathOfTarget in ['dungFlag', 'mapFlag', 'chestFlag', 'combatActive', 'worldMap', 'chest_auto', 'AUTO']:
    flag_attr = f"flag_{shortPathOfTarget}" if shortPathOfTarget != 'AUTO' else 'flag_auto_text'
    if hasattr(MonitorState, flag_attr):
        setattr(MonitorState, flag_attr, int(best_val * 100))
        # 記錄更新時間
        if hasattr(MonitorState, 'flag_updates'):
            MonitorState.flag_updates[shortPathOfTarget] = time.time()
```

---

## 4. GUI 讀取對應表

| GUI 顯示項目 | 讀取的 Flag | 查詢的 `flag_updates` Key | 閾值 | 超過閾值顏色 |
|-------------|------------|--------------------------|------|-------------|
| 地城移動 | `flag_dungFlag` | `'dungFlag'` | 75% | 紅色 |
| 地圖開啟 | `flag_mapFlag` | `'mapFlag'` | 80% | 紅色 |
| 寶箱開啟 | `flag_chestFlag` | `'chestFlag'` | 80% | 紅色 |
| 戰鬥開始 | `flag_combatActive` | `'combatActive'` | 70% | 紅色 |
| 世界地圖 | `flag_worldMap` | `'worldMap'` | 80% | 紅色 |
| 寶箱移動 | `flag_chest_auto` | `'chest_auto'` | 80% | 紅色 |
| AUTO比對 | `flag_auto_text` | `'AUTO'` | 80% | 紅色 |

---

## 5. 問題分析

### 5.1 核心問題

**DungeonMover 移動監控 (行 4182-4191) 使用 `GetMatchValue` 更新 flag 值，但沒有同步更新 `flag_updates` 時間戳。**

```python
# script.py 行 4182-4191 (問題代碼)
if now - self.last_monitor_update_time >= self.MONITOR_UPDATE_INTERVAL:
    MonitorState.flag_dungFlag = GetMatchValue(screen_pre, 'dungFlag')
    MonitorState.flag_mapFlag = GetMatchValue(screen_pre, 'mapFlag')
    MonitorState.flag_chestFlag = GetMatchValue(screen_pre, 'chestFlag')
    MonitorState.flag_worldMap = GetMatchValue(screen_pre, 'worldmapflag')
    MonitorState.flag_chest_auto = GetMatchValue(screen_pre, 'chest_auto')
    MonitorState.flag_auto_text = GetMatchValue(screen_pre, 'AUTO')
    # ⚠️ 缺少 flag_updates 時間戳更新
    MonitorState.flag_low_hp = CheckLowHP(screen_pre)
    self.last_monitor_update_time = now
```

### 5.2 影響

1. GUI 的過期檢測邏輯 (`current_time - last_update > 2.0`) 無法正確判斷
2. 由於 `flag_updates.get(flag_name, 0)` 返回 0，所有 flag **永遠顯示 `--`**
3. 除非這些 flag 被 `CheckIf()` 函數呼叫過（例如在 IdentifyState 中）

### 5.3 實際行為

| 場景 | Flag 值更新 | 時間戳更新 | GUI 顯示 |
|------|------------|-----------|---------|
| DungeonMover 移動中 | ✅ 有 | ❌ 無 | `--` |
| IdentifyState 執行 `CheckIf('dungFlag')` | ✅ 有 | ✅ 有 | 百分比 |
| StateCombat 執行 | ✅ 有 (combatActive) | ❌ 無 | `--` |

---

## 6. 修復建議

### 6.1 方案：在 DungeonMover 中同步更新時間戳

在 `script.py` 行 4191 之後加入：

```python
# 行 4182 之後
if now - self.last_monitor_update_time >= self.MONITOR_UPDATE_INTERVAL:
    MonitorState.flag_dungFlag = GetMatchValue(screen_pre, 'dungFlag')
    MonitorState.flag_mapFlag = GetMatchValue(screen_pre, 'mapFlag')
    MonitorState.flag_chestFlag = GetMatchValue(screen_pre, 'chestFlag')
    MonitorState.flag_worldMap = GetMatchValue(screen_pre, 'worldmapflag')
    MonitorState.flag_chest_auto = GetMatchValue(screen_pre, 'chest_auto')
    MonitorState.flag_auto_text = GetMatchValue(screen_pre, 'AUTO')

    # [修復] 同步更新時間戳
    update_time = time.time()
    MonitorState.flag_updates['dungFlag'] = update_time
    MonitorState.flag_updates['mapFlag'] = update_time
    MonitorState.flag_updates['chestFlag'] = update_time
    MonitorState.flag_updates['worldMap'] = update_time
    MonitorState.flag_updates['chest_auto'] = update_time
    MonitorState.flag_updates['AUTO'] = update_time

    MonitorState.flag_low_hp = CheckLowHP(screen_pre)
    self.last_monitor_update_time = now
```

### 6.2 其他需要修復的位置

| 位置 | 行號 | Flag | 修復方式 |
|------|------|------|---------|
| IdentifyState 戰鬥預計算 | 2154 | `flag_combatActive` | 加入 `flag_updates['combatActive'] = time.time()` |
| IdentifyState AUTO 檢測 | 2170, 2197 | `flag_auto_text` | 加入 `flag_updates['AUTO'] = time.time()` |
| StateCombat | 3406 | `flag_combatActive` | 加入 `flag_updates['combatActive'] = time.time()` |

---

## 7. 相關文件

- `src/gui.py`: GUI 監控面板定義與更新邏輯
- `src/script.py`: MonitorState 類別定義與 flag 更新位置
- `.agent/skills/identify-state.md`: IdentifyState 狀態識別說明
- `.agent/skills/dungeon-mover.md`: DungeonMover 移動監控說明
