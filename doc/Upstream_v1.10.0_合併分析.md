# Upstream v1.10.0 合併分析

> 分析日期：2025-12-25
> 本地版本：v1.10.1
> Upstream 版本：v1.10.0
> Upstream 倉庫：https://github.com/arnold2957/wvd

---

## 一、Upstream v1.10.0 更新內容

### 1.1 新功能

| 功能 | 說明 |
|------|------|
| 狼洞2f (AWD) | 新地圖，使用 `chest_auto` 目標 |
| `chest_auto` 目標類型 | 跳過地圖直接使用遊戲內建自動寶箱按鈕 |
| 跳過回城優化 | 沒有戰鬥或寶箱時完全跳過回城 |
| `_AOE_TIME` 配置 | 自定義每場戰鬥 AOE 釋放次數 |
| 新戰鬥標識 | `combatActive_4.png` |
| 深雪教堂區 | 新地圖，使用 `Bharken` |
| 魔女洞窟 (TWC) | 新地圖 |
| 水洞 (DOS) | 新礦石地圖 |

### 1.2 Changelog 摘要

```
==v1.10.0==
新增了狼洞2f.
修复了脚本寻路无法使用的问题.
新增了目标地点"auto_chest", 该目标会跳过地图直接使用面板上的自动宝箱.
现在当没有发生战斗或宝箱, 会跳过完全跳过回城.

==v1.9.31==
修复了无法读取blessing的问题.
现在会尝试直接进行resume.
新增了自定义每场战斗中的aoe释放.

==v1.9.30==
加入了深雪7f左半和右半.
加入了教堂区.
现在特殊对话选项将使用反射.
```

---

## 二、功能相容性分析

### 2.1 `_MEET_CHEST_OR_COMBAT` 跳過回城功能

**現況：** 部分存在

我們已有：
- `RuntimeContext._MEET_CHEST_OR_COMBAT = False` (line 210)
- 寶箱/戰鬥後設為 True (line 2417, 2426, 3216, 3225)
- Inn 階段的跳過邏輯 (line 2904-2912)

**缺少：** returntoTown 和 openworldmap 的提前跳過邏輯

Upstream 新增邏輯 (需整合)：
```python
# IdentifyState() 中
if CheckIf(screen, "returntoTown"):
    if runtimeContext._MEET_CHEST_OR_COMBAT:
        # 有遇到 → 正常回城
        FindCoordsOrElseExecuteFallbackAndWait('Inn', ['return',[1,1]], 1)
        return State.Inn, DungeonState.Quit, screen
    else:
        # 沒遇到 → 跳過回城，直接去 EoT
        logger.info("由于没有遇到任何宝箱或发生任何战斗, 跳过回城.")
        return State.EoT, DungeonState.Quit, screen

if pos := CheckIf(screen, "openworldmap"):
    if runtimeContext._MEET_CHEST_OR_COMBAT:
        Press(pos)
        return IdentifyState()
    else:
        logger.info("由于没有遇到任何宝箱或发生任何战斗, 跳过回城.")
        return State.EoT, DungeonState.Quit, screen
```

**整合難度：** 低
**影響範圍：** IdentifyState() 函數

---

### 2.2 `chest_auto` 目標類型

**現況：** 不存在

這是全新的目標類型，處理邏輯在 `DungeonState.Map` 中，在進入 `StateSearch` 之前攔截。

Upstream 實現 (需整合)：
```python
case DungeonState.Map:
    # 特殊處理：不打開地圖，直接用遊戲自動寶箱
    if targetInfoList[0] and (targetInfoList[0].target == "chest_auto"):
        lastscreen = ScreenShot()
        if not Press(CheckIf(lastscreen, "chest_auto", [[710,250,180,180]])):
            Press(CheckIf(lastscreen, "mapflag"))
            Press([664,329])
            Sleep(1)
            lastscreen = ScreenShot()
            if not Press(CheckIf(lastscreen, "chest_auto", [[710,250,180,180]])):
                dungState = None
                continue
        Sleep(0.5)
        while 1:
            Sleep(3)
            _, dungState, screen = IdentifyState()
            if dungState != DungeonState.Dungeon:
                break
            elif lastscreen is not None:
                gray1 = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                gray2 = cv2.cvtColor(lastscreen, cv2.COLOR_BGR2GRAY)
                mean_diff = cv2.absdiff(gray1, gray2).mean()/255
                if mean_diff < 0.05:
                    if dungState == DungeonState.Dungeon:
                        targetInfoList.pop(0)
                    break
                lastscreen = screen
    else:
        # 正常流程
        ...
```

**整合難度：** 中
**影響範圍：** StateDungeon() 的 DungeonState.Map 處理
**依賴資源：** `chest_auto.png`

---

### 2.3 `_AOE_TIME` 自定義 AOE 次數

**現況：** 不存在

需要新增：
1. CONFIG 變數：`["custom_aoe_time_var", tk.IntVar, "_AOE_TIME", 1]`
2. RuntimeContext 變數：`_AOE_CAST_TIME = 0`
3. GUI 控件（可選）
4. 戰鬥邏輯修改

Upstream 實現：
```python
# StateCombat() 中
if castAndPressOK and setting._AOE_ONCE and ((skillspell in SECRET_AOE_SKILLS) or (skillspell in FULL_AOE_SKILLS)):
    runtimeContext._AOE_CAST_TIME += 1
    if runtimeContext._AOE_CAST_TIME >= setting._AOE_TIME:
        runtimeContext._ENOUGH_AOE = True
        runtimeContext._AOE_CAST_TIME = 0
    logger.info(f"已经释放了首次全体aoe.")
```

**整合難度：** 中
**影響範圍：** CONFIG_VAR_LIST, RuntimeContext, StateCombat()

---

## 三、資源圖片分析

### 3.1 需要新增的圖片

| 路徑 | 用途 | 必要性 |
|------|------|--------|
| `resources/images/chest_auto.png` | 自動寶箱按鈕 | chest_auto 功能必須 |
| `resources/images/combatActive_4.png` | 新戰鬥標識 | 建議新增 |
| `resources/images/Bharken.png` | 新 Harken 圖片 | 教堂區必須 |
| `resources/images/AWD/AWD.png` | 狼洞入口 | 狼洞任務必須 |
| `resources/images/AWD/AWD2F.png` | 狼洞2F | 狼洞任務必須 |
| `resources/images/TWC/TWC.png` | 魔女洞窟入口 | 魔女洞窟任務必須 |
| `resources/images/TWC/TWCB1F.png` | 魔女洞窟B1F | 魔女洞窟任務必須 |
| `resources/images/DOS/DOS.png` | 水洞入口 | 水洞任務必須 |
| `resources/images/DOS/DOSB1F.png` | 水洞B1F | 水洞任務必須 |
| `resources/images/DOS_quit.png` | 水洞退出 | 水洞任務必須 |
| `resources/images/stair_DH_Church.png` | 深雪教堂樓梯 | 教堂區任務必須 |
| `resources/images/stair_DH_R7.png` | 深雪R7樓梯 | 深雪R7任務必須 |
| `resources/images/DH-R7.png` | 深雪R7地圖 | 深雪R7任務必須 |
| `resources/images/DHS.png` | 深雪相關 | 建議新增 |
| `resources/images/dialogueChoices/hammer.png` | 對話選項 | 建議新增 |
| `resources/images/dialogueChoices/spareit.png` | 對話選項 | 建議新增 |

### 3.2 Upstream 刪除但我們需保留的圖片

| 路徑 | 用途 | 原因 |
|------|------|------|
| `resources/images/routenotfound.png` | Resume 優化 | 我們的 Resume 優化功能依賴此圖 |
| `resources/images/visibliityistoopoor.png` | 能見度檢測 | 我們的 Resume 優化功能依賴此圖 |
| `resources/images/gohome.png` | 回城按鈕 | 我們的 gohome 功能依賴此圖 |

### 3.3 對話選項資料夾重整

Upstream 將部分對話選項移至 `dialogueChoices/` 資料夾：
- `!adventurersbones.png` → `dialogueChoices/!adventurersbones.png`
- `!halfBone.png` → `dialogueChoices/!halfBone.png`
- `blessing.png` → `dialogueChoices/blessing.png`
- `DontBuyIt.png` → `dialogueChoices/DontBuyIt.png`
- 等等...

**注意：** 如果合併資料夾結構，需要同步修改 `IdentifyState()` 中對這些圖片的引用路徑。

---

## 四、程式碼衝突分析

### 4.1 我們獨有的功能（需保護）

| 功能 | 位置 | 說明 |
|------|------|------|
| pyscrcpy 串流 | ScrcpyStreamManager 類 | 快速截圖 |
| Resume 按鈕優化 | StateDungeon, StateMoving_CheckFrozen | 含 routenotfound 檢測 |
| minimap_stair | CheckIf_minimapFloor | 小地圖樓層檢測 |
| 背包整理 | StateOrganizeBackpack | 自動整理背包 |
| 重啟後強制物理 | _FORCE_PHYSICAL_AFTER_INN | 重啟後前N次戰鬥 |
| Harken 樓層選擇 | _HARKEN_FLOOR_TARGET | 指定 Harken 樓層 |

### 4.2 潛在衝突點

| 位置 | 衝突類型 | 解決方案 |
|------|----------|----------|
| `IdentifyState()` returntoTown 處理 | 我們有 `_HARKEN_FLOOR_TARGET` 檢查 | 在現有檢查後新增跳過邏輯 |
| `StateDungeon()` Map 狀態 | 我們有大量 Resume 優化邏輯 | 在 Resume 優化之前新增 chest_auto 檢查 |
| `CONFIG_VAR_LIST` | 我們有額外配置項 | 直接新增，不衝突 |

---

## 五、整合執行計劃

### 5.1 第一階段：資源圖片

```bash
# 從 upstream 複製新圖片
git checkout upstream/master -- resources/images/chest_auto.png
git checkout upstream/master -- resources/images/combatActive_4.png
git checkout upstream/master -- resources/images/Bharken.png
git checkout upstream/master -- resources/images/AWD/
git checkout upstream/master -- resources/images/TWC/
git checkout upstream/master -- resources/images/DOS/
git checkout upstream/master -- resources/images/DOS_quit.png
git checkout upstream/master -- resources/images/stair_DH_Church.png
git checkout upstream/master -- resources/images/stair_DH_R7.png
git checkout upstream/master -- resources/images/DH-R7.png
git checkout upstream/master -- resources/images/DHS.png
git checkout upstream/master -- resources/images/dialogueChoices/

# 確保不刪除我們需要的圖片
# routenotfound.png, visibliityistoopoor.png, gohome.png 保持不變
```

### 5.2 第二階段：程式碼修改

#### 5.2.1 新增 `_AOE_TIME` 配置

位置：`src/script.py` CONFIG_VAR_LIST
```python
["custom_aoe_time_var", tk.IntVar, "_AOE_TIME", 1],
```

位置：`src/script.py` RuntimeContext
```python
_AOE_CAST_TIME = 0
```

#### 5.2.2 新增 `chest_auto` 目標處理

位置：`src/script.py` StateDungeon() DungeonState.Map 分支
在 Resume 優化邏輯之前新增：
```python
# chest_auto 特殊處理
if targetInfoList and targetInfoList[0] and (targetInfoList[0].target == "chest_auto"):
    # ... (參考 2.2 節的程式碼)
```

#### 5.2.3 補充跳過回城邏輯

位置：`src/script.py` IdentifyState() returntoTown 處理
在現有 `if CheckIf(screen,"returntoTown"):` 中新增 `_MEET_CHEST_OR_COMBAT` 檢查

位置：`src/script.py` IdentifyState() openworldmap 處理
新增 `_MEET_CHEST_OR_COMBAT` 檢查

#### 5.2.4 修改 AOE 計數邏輯

位置：`src/script.py` StateCombat()
修改現有 `_ENOUGH_AOE` 邏輯，加入 `_AOE_CAST_TIME` 計數

### 5.3 第三階段：quest.json

**由用戶手動處理**

新增任務：
- AWD (狼洞2f)
- TWC (魔女洞窟)
- DOS (水洞)
- DH-Church (深雪教堂區)
- DH-7f-left (深雪R7左)
- DH-7f-right (深雪R7右)

---

## 六、測試計劃

### 6.1 功能測試

| 測試項目 | 測試方法 |
|----------|----------|
| chest_auto | 使用狼洞任務測試 |
| 跳過回城 | 進入地城不觸發戰鬥/寶箱，觀察是否跳過回城 |
| _AOE_TIME | 設置 AOE 次數，觀察戰鬥中 AOE 釋放次數 |
| Resume 優化 | 確認現有功能不受影響 |
| pyscrcpy | 確認串流截圖正常 |

### 6.2 回歸測試

- 現有地城任務（水路、鳥洞等）
- 背包整理功能
- 重啟恢復功能
- Harken 樓層選擇

---

## 七、風險評估

| 風險 | 等級 | 緩解措施 |
|------|------|----------|
| 圖片路徑變更導致識別失敗 | 中 | 逐步測試，保留原有圖片 |
| 新邏輯與 Resume 優化衝突 | 低 | chest_auto 在 Resume 優化之前處理 |
| quest.json 格式不相容 | 低 | 用戶手動處理 |

---

## 八、回滾計劃

如果合併後出現問題：

```bash
# 回滾到合併前的版本
git reset --hard v1.10.1

# 或者回滾特定文件
git checkout v1.10.1 -- src/script.py
git checkout v1.10.1 -- resources/
```

---

## 九、待確認事項

1. [ ] 用戶確認是否執行合併
2. [ ] 用戶確認 quest.json 處理方式
3. [ ] 用戶確認新增的 GUI 控件（_AOE_TIME）是否需要
4. [ ] 用戶確認對話選項資料夾重整是否採用

---

**文件版本：** 1.0
**最後更新：** 2025-12-25
