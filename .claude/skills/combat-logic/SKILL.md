---
name: 戰鬥流程邏輯
description: 說明戰鬥狀態的處理流程，包含技能釋放順序、自動戰鬥、AOE 邏輯、強力單體技能等。當使用者詢問戰鬥邏輯、技能設定、或修改 StateCombat 相關程式碼時，應啟用此技能。
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
