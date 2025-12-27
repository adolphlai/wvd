---
name: 戰鬥流程邏輯
description: 說明戰鬥狀態的處理流程，包含技能釋放順序、自動戰鬥、AOE 邏輯、強力單體技能、普攻（attack）、敵人座標、AE 手機制等。當使用者詢問戰鬥邏輯、技能設定、普攻、AE 手、或修改 StateCombat 相關程式碼時，應啟用此技能。
---

# 戰鬥流程邏輯

## 執行環境
- **檔案**: `src/script.py`
- **函數**: `StateCombat()`
- **狀態**: `DungeonState.Combat`

## 戰鬥主流程

1. **初始化** - 記錄戰鬥時間，開啟2倍速
2. **檢查施法序列** - `_ACTIVESPELLSEQUENCE`
3. **重啟後前2次戰鬥** - `_FIRST_COMBAT_AFTER_RESTART > 0` → 強力單體技能
4. **村莊返回後前2次戰鬥** - `_FIRST_COMBAT_AFTER_INN > 0` → 強力單體技能
5. **自動戰鬥模式** - 系統自動戰鬥或 AOE 後自動戰鬥
6. **正常技能釋放** - 遍歷 `_SPELLSKILLCONFIG`

## 技能分類

| 分類 | 變數名 | 技能 |
|------|--------|------|
| 控場技能 | `CC_SKILLS` | KANTIOS |
| 秘術 AOE | `SECRET_AOE_SKILLS` | SAoLABADIOS, SAoLAERLIK, SAoLAFOROS |
| 全體 AOE | `FULL_AOE_SKILLS` | LAERLIK, LAMIGAL, LAZELOS, LACONES... |
| 橫排 AOE | `ROW_AOE_SKILLS` | maerlik, mahalito, mamigal... |
| 強力單體 | `PHYSICAL_SKILLS` | unendingdeaths, 全力一击, tzalik... |

## 關鍵參數

| 參數 | 說明 |
|------|------|
| `_SYSTEMAUTOCOMBAT` | 系統自動戰鬥開關 |
| `_AOE_ONCE` | 每場戰鬥只釋放一次全體 AOE |
| `_AUTO_AFTER_AOE` | AOE 後開啟自動戰鬥 |
| `_FORCE_PHYSICAL_FIRST_COMBAT` | 重啟後前2次戰鬥使用強力單體技能 |
| `_FORCE_PHYSICAL_AFTER_INN` | 返回後前2次戰鬥使用強力單體技能 |

## 強力單體技能列表

```python
PHYSICAL_SKILLS = ["unendingdeaths","全力一击","tzalik","居合","精密攻击","锁腹刺","破甲","星光裂","迟钝连携击","强袭","重装一击","眩晕打击","幻影狩猎"]
```

如需新增技能，編輯此列表並確保圖片存在於 `resources/images/spellskill/`。

## AE 手機制

### 概念
利用遊戲的「重複上一次動作」機制，讓指定角色（AE 手）在第一輪使用普攻，第二輪使用 AOE 後開啟自動戰鬥。

### 相關參數

| 參數 | 說明 |
|------|------|
| `_AE_CASTER_1_ORDER` | AE 手 1 的出手順序（1~6 或「關閉」）|
| `_AE_CASTER_1_SKILL` | AE 手 1 的技能（可選 attack 普攻）|
| `_AE_CASTER_1_LEVEL` | AE 手 1 的技能等級 |
| `_AE_CASTER_2_ORDER` | AE 手 2 的出手順序 |
| `_AE_CASTER_2_SKILL` | AE 手 2 的技能 |
| `_AE_CASTER_2_LEVEL` | AE 手 2 的技能等級 |
| `_HAS_PREEMPTIVE` | 隊伍有先制角色（調整 action 計數）|
| `_AOE_TRIGGERED_THIS_DUNGEON` | 本次地城是否已觸發 AOE |
| `_COMBAT_ACTION_COUNT` | 戰鬥行動計數器 |

### 相關函數

| 函數 | 位置 | 說明 |
|------|------|------|
| `get_ae_caster_type()` | StateCombat 內 | 判斷當前行動是否為 AE 手 |
| `use_ae_caster_skill()` | StateCombat 內 | AE 手使用指定技能（含普攻判斷）|
| `use_normal_attack()` | StateCombat 內 | 使用普攻 |
| `enable_auto_combat()` | StateCombat 內 | 開啟自動戰鬥 |

### GUI 位置
- 技能選項：`gui.py` 的 `skill_options = ["", "attack"] + ALL_AOE_SKILLS`
- AE 手設定區塊：`_create_skills_tab()` 函數

## 普攻（attack）

### 使用方式
在 AE 手技能選項中選擇 `attack`，或在代碼中呼叫 `use_normal_attack()`。

### 敵人座標
點擊普攻按鈕後，需點擊六個敵人位置：

```python
Press([150,750])
Press([300,750])
Press([450,750])
Press([550,750])
Press([650,750])
Press([750,750])
```

### 代碼邏輯
```python
def use_normal_attack():
    scn = ScreenShot()
    if Press(CheckIf(scn, 'spellskill/attack')):
        Sleep(0.5)
        # 點擊六個點位選擇敵人
        for pos in [[150,750], [300,750], [450,750], [550,750], [650,750], [750,750]]:
            Press(pos)
            Sleep(0.1)
        return True
    return False
```
