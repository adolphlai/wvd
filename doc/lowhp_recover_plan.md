# 低血量恢復功能

## 功能說明
在地城移動時偵測到低血量 (紅色 10%~20%) 自動觸發恢復流程。

## 實作完成

### 1. 配置變數 (script.py 第 272 行)
```python
["lowhp_recover_var", tk.BooleanVar, "_LOWHP_RECOVER", False],
```

### 2. GUI (gui.py 第 885-890 行)
位置：進階設定 > **恢復設定**（與「跳過戰後恢復」、「跳過開箱後恢復」並排）

### 3. 執行邏輯 (script.py _monitor_move 第 3634-3639 行)
```python
if setting._LOWHP_RECOVER and MonitorState.flag_low_hp:
    logger.info("[DungeonMover] 偵測到低血量，觸發恢復流程...")
    return self._cleanup_exit(DungeonState.Map)
```

## 現有恢復設定

| 設定名稱 | 變數 | 說明 |
|---------|------|------|
| 跳過戰後恢復 | `_SKIPCOMBATRECOVER` | 戰鬥結束後跳過恢復 |
| 跳過開箱後恢復 | `_SKIPCHESTRECOVER` | 開寶箱後跳過恢復 |
| **低血量恢復** | `_LOWHP_RECOVER` | 移動時偵測低血量自動恢復 |
