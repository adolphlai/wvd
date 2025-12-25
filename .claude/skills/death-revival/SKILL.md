---
name: 死亡復活處理
description: 說明角色死亡和復活邏輯，包含 RiseAgainReset、自殺機制、死亡檢測。當使用者詢問角色死亡、復活、或 _SUICIDE 相關問題時，應啟用此技能。
---

# 死亡復活處理 (Death & Revival System)

## 檔案位置
`src/script.py`

## 核心函數

### RiseAgainReset() - 復活重置
- **位置**: line 1440
- **參數**: `reason` - 觸發原因（'combat', 'chest' 等）
- **功能**:
  1. 點擊復活按鈕
  2. 重置施法序列計數器
  3. 設置戰鬥後處理標誌

```python
def RiseAgainReset(reason='unknown'):
    # 點擊復活
    Press([復活按鈕座標])
    Sleep(1)

    # 重置計數器
    runtimeContext._CASTSPELLSEQUENCECOUNT = 0
    runtimeContext._FORCE_PHYSICAL_CURRENT_COMBAT = True
```

## 死亡檢測

### IdentifyState 中的檢測
- **someonedead**: 有人死亡（可復活）
- **multipeopledead**: 多人死亡（觸發自殺）
- **riseagain**: 復活界面

## 自殺機制

### _SUICIDE 標誌
- **用途**: 強制讓角色死亡以重置狀態
- **觸發條件**:
  - 多人死亡（multipeopledead）
  - 特定異常情況

```python
if CheckIf(screen, 'multipeopledead'):
    runtimeContext._SUICIDE = True
```

### 自殺執行
在 StateCombat 中：
```python
if runtimeContext._SUICIDE:
    # 選擇逃跑或等待死亡
    # 死亡後重置標誌
```

## 復活流程

```
角色死亡
    │
    ▼
┌─────────────────┐
│ 檢測死亡類型    │
└────────┬────────┘
         │
    ┌────┴────┐
    │單人     │多人
    ▼         ▼
  復活界面    設置 _SUICIDE
    │              │
    ▼              ▼
 RiseAgainReset   等待全滅
    │              │
    ▼              ▼
  重置計數器    返回旅店
```

## RuntimeContext 相關變數

| 變數 | 說明 |
|------|------|
| `_SUICIDE` | 自殺模式標誌 |
| `_CASTSPELLSEQUENCECOUNT` | 施法序列計數（復活後重置） |
| `_FORCE_PHYSICAL_CURRENT_COMBAT` | 復活後強制物理技能 |

## 相關圖片資源

- `someonedead.png` - 單人死亡
- `multipeopledead.png` - 多人死亡
- `riseagain.png` - 復活界面
