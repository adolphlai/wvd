# 戰鬥系統簡化計劃

## 目標
簡化戰鬥技能施放邏輯，移除複雜的 AE 手機制和特殊施法序列。

## 新機制設計

### 設定項
| 設定 | 類型 | 說明 |
|------|------|------|
| **自動戰鬥模式** | Combobox（保持不變） | 完全自動/1場後自動/2場後自動/3場後自動/完全手動 |
| **觸發間隔** | 數字 0~99 | 每 N+1 場地城觸發一次（0=每場） |
| **順序 1~6** | 類別+首戰技能+二戰後技能+等級 | 各順序的技能設定 |

### 順序設定欄位
| 欄位 | 說明 |
|------|------|
| 類別 | AOE/單體/控場...（用於技能圖片路徑） |
| 首戰技能 | 第1戰使用的技能（可選 attack 普攻，留空=用單體技能） |
| 首戰等級 | 第1戰技能等級 |
| 二戰後技能 | 第2戰開始使用的技能（留空=用單體技能） |
| 二戰後等級 | 第2戰起技能等級 |

**範例配置：**
| 順序 | 類別 | 首戰技能 | 首戰等級 | 二戰後技能 | 二戰後等級 |
|------|------|----------|----------|------------|------------|
| 1 | AOE | attack | - | LACONES | 9 |
| 2 | 單體 | tzalik | 5 | tzalik | 9 |

- 順序1：第1戰用普攻，第2戰起用 LACONES Lv9
- 順序2：第1戰用 tzalik Lv5，第2戰起用 tzalik Lv9

### GUI 範例（方式 B：兩行設計）

```
┌─ 技能施放設定 ─────────────────────────────────────────────────────────────────┐
│                                                                                │
│  觸發間隔: [__0__]  單位數量: [▼ 6 ]  [儲存]                                    │
│  ※ 0=每場觸發，N=每N+1場觸發一次順序設定                                        │
│                                                                                │
│  ┌───────────────────────────────────────────────────────────────────────────┐ │
│  │ 順序 1:  類別 [▼ AOE     ]                                                │ │
│  │   首戰:    技能 [▼ attack   ]  等級 [▼ -    ]                             │ │
│  │   二戰後:  技能 [▼ LACONES  ]  等級 [▼ LV9  ]                             │ │
│  ├───────────────────────────────────────────────────────────────────────────┤ │
│  │ 順序 2:  類別 [▼ 單體    ]                                                │ │
│  │   首戰:    技能 [▼ tzalik   ]  等級 [▼ LV5  ]                             │ │
│  │   二戰後:  技能 [▼ tzalik   ]  等級 [▼ LV9  ]                             │ │
│  ├───────────────────────────────────────────────────────────────────────────┤ │
│  │ 順序 3:  類別 [▼         ]                                                │ │
│  │   首戰:    技能 [▼          ]  等級 [▼      ]                             │ │
│  │   二戰後:  技能 [▼          ]  等級 [▼      ]                             │ │
│  ├───────────────────────────────────────────────────────────────────────────┤ │
│  │ ... (順序 4~6 相同結構)                                                   │ │
│  └───────────────────────────────────────────────────────────────────────────┘ │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘

┌─ 自動戰鬥 ─────────────────────────────────────────────────────────────────────┐
│                                                                                │
│  自動戰鬥模式: [▼ 1場後自動 ]  (完全自動/1場後自動/2場後自動/3場後自動/完全手動)  │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘
```

**對比舊 GUI：**
```
舊版（單行）:
順序 | 類別     | 技能      | 等級
1:   | [▼ AOE] | [▼ skill] | [▼ LV5]

新版（兩行）:
順序 1:  類別 [▼ AOE]
  首戰:    技能 [▼ attack]   等級 [▼ -  ]
  二戰後:  技能 [▼ LACONES]  等級 [▼ LV9]
```

**說明：**
- 每個順序佔用 3 行：類別行 + 首戰行 + 二戰後行
- 類別用於確定技能圖片路徑（首戰和二戰後共用同一類別）
- 技能選項包含空白（fallback 單體）和 `attack`（普攻）
- 留空 = 使用單體技能 fallback

### 戰鬥流程
```
進入戰鬥
    ↓
觸發間隔匹配? ─否→ 設 _AOE_TRIGGERED=True，開自動戰鬥
    ↓是
第幾戰 <= 自動戰鬥觸發值?
    ├─ 是 → 施放技能（按順序設定，未設定用單體）
    └─ 否 → 設 _AOE_TRIGGERED=True，開自動戰鬥
```

### 單體技能 Fallback（確認不用改）
- `useForcedPhysicalSkill()` 函數已有 fallback 邏輯
- 當 `PHYSICAL_SKILLS` 都找不到時，自動呼叫 `use_normal_attack()` 使用普攻
- **維持現有行為**

### 特殊情況：跳過回城
當觸發「跳過回城」時（沒遇到戰鬥/寶箱 或 連續刷地城）：
- 調用 `reset_ae_caster_flags()` 重置 FLAG
- **立即設置 `_AOE_TRIGGERED = True`**
- 下一個地城直接開自動戰鬥，不啟用黑屏檢測
- **此邏輯保持不變**（維持現有行為）

---

## GUI 整合：旅店休息 → 連續刷地城

### 目標
將「旅店休息」GUI 改成控制「連續刷地城」設定，統一成一個設定入口。

### 修改內容

#### GUI (gui.py)

**移除**：
- 「連續刷地城」LabelFrame（第 567-580 行）

**修改**「旅店休息」區塊（第 718-731 行）：
- 標題改為「連續刷地城」或保留「旅店休息」
- 移除「啟用旅店休息」Checkbox (`active_rest_var`)
- 將「間隔」Entry 改用 `dungeon_repeat_limit_var` 變數
- 更新說明文字

#### CONFIG_VAR_LIST (script.py)

**移除**：
- `_ACTIVE_REST`
- `_RESTINTERVEL`

#### 判斷邏輯 (script.py)

**修改第 4644 行**：
```python
# 舊邏輯
elif ((runtimeContext._COUNTERDUNG-1) % (setting._RESTINTERVEL+1) != 0):

# 新邏輯：使用 _DUNGEON_REPEAT_LIMIT
# 直接依賴 should_skip_return_to_town() 的判斷結果
# 如果回城了就一定執行 StateInn()
```

**保持不動**：
- `StateInn()` 函數本身（豪華房、整理背包、自動補給等功能）

---

## 修改項目

### 1. CONFIG_VAR_LIST (script.py:239-279)

**移除**：
- `_UNCONFIGURED_DEFAULT` (第 263 行)
- `_ACTIVE_REST`
- `_RESTINTERVEL`
- `_AE_CASTER_1_ORDER` ~ `_AE_CASTER_2_ORDER`（AE 手順序，不再需要）

**修改**：
- `_AE_CASTER_{1-6}_SKILL` → `_AE_CASTER_{1-6}_SKILL_FIRST`（首戰技能）
- `_AE_CASTER_{1-6}_LEVEL` → `_AE_CASTER_{1-6}_LEVEL_FIRST`（首戰等級）
- 新增 `_AE_CASTER_{1-6}_SKILL_AFTER`（二戰後技能）
- 新增 `_AE_CASTER_{1-6}_LEVEL_AFTER`（二戰後等級）

### 2. GUI - 戰鬥設定分頁 (gui.py:511-582)

**移除**：
- 「未設定順序預設」區塊 (第 531-546 行)
- 「連續刷地城」LabelFrame（第 567-580 行）
- AE 手「出手順序」Combobox（改為固定順序 1~6）

**修改**順序 1~6 設定：
- 原本：類別 + 技能 + 等級
- 改為：類別 + 首戰技能 + 二戰後技能 + 等級

**保持不變**：
- 自動戰鬥模式 Combobox（完全自動/1場後自動/2場後自動/3場後自動/完全手動）

### 2.1 GUI - 進階設定分頁 (gui.py:713-731)

**修改**「旅店休息」區塊：
- 移除「啟用旅店休息」Checkbox
- 間隔 Entry 改用 `dungeon_repeat_limit_var`
- 更新說明文字為「刷 N 次後回城休息」

### 3. StateCombat 函數 (script.py:2900-3258)

**簡化邏輯**：
```python
# 1. 檢查觸發間隔
if not ae_interval_match:
    runtimeContext._AOE_TRIGGERED_THIS_DUNGEON = True
    enable_auto_combat()
    return

# 2. 檢查是否需要手動施放（使用現有的 should_enable_auto_combat）
battle_num = runtimeContext._COMBAT_BATTLE_COUNT
if should_enable_auto_combat(battle_num, setting._AUTO_COMBAT_MODE):
    runtimeContext._AOE_TRIGGERED_THIS_DUNGEON = True
    enable_auto_combat()
    return

# 3. 施放技能（根據戰鬥場次選擇首戰或二戰後技能）
position = ((action_count - 1) % 6) + 1
category = getattr(setting, f"_AE_CASTER_{position}_CATEGORY", "")

if battle_num == 1:
    skill = getattr(setting, f"_AE_CASTER_{position}_SKILL_FIRST", "")
    level = getattr(setting, f"_AE_CASTER_{position}_LEVEL_FIRST", "")
else:
    skill = getattr(setting, f"_AE_CASTER_{position}_SKILL_AFTER", "")
    level = getattr(setting, f"_AE_CASTER_{position}_LEVEL_AFTER", "")

if skill == "attack":
    use_normal_attack()
elif skill:
    cast_skill_by_category(category, skill, level)
else:
    # 未設定：使用單體技能
    useForcedPhysicalSkill(screen, doubleConfirmCastSpell, f"順序{position}")
```

**移除**：
- AE 手特殊邏輯（第1戰用普攻、第2戰用AOE）(3092-3154)
- `_SPELLSEQUENCE` 處理邏輯 (3173-3221)

### 4. 輔助函數

**保持不變**：
- `get_auto_combat_battles()` (2650-2665)
- `should_enable_auto_combat()` (2667-2679)

**移除**：
- `use_unconfigured_default_skill()` (2813-2862) - 改用 `useForcedPhysicalSkill`

### 5. RuntimeContext (script.py:417-429)

**移除**：
- `_ACTIVESPELLSEQUENCE` (第 417 行)
- `_SHOULDAPPLYSPELLSEQUENCE` (第 418 行)

### 6. FarmQuest (script.py:445)

**移除**：
- `_SPELLSEQUENCE` (第 445 行)

### 7. quest.json 處理

**移除**：
- 載入 `_SPELLSEQUENCE` 的相關邏輯 (4510-4514)

---

## 關鍵文件
- `src/script.py` - 主要邏輯
- `src/gui.py` - GUI 設定介面

## 執行順序
1. 修改 CONFIG_VAR_LIST（變數定義）
2. 修改 GUI（戰鬥設定分頁）
3. 簡化 StateCombat（核心邏輯）
4. 移除相關輔助函數
5. 清理 RuntimeContext 和 FarmQuest
6. 測試
