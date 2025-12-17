# Resume + routenotfound 检测逻辑说明

## 修改位置

**文件**: `src/script.py`  
**函数**: `StateDungeon()`  
**分支**: `case DungeonState.Dungeon:`  
**行号**: 约 1854-1887 行（`########### OPEN MAP` 注释下方）

---

## 处理逻辑

当状态为 `DungeonState.Dungeon` 时，执行以下逻辑：

```
1. 检查是否有 Resume 按钮
   │
   ├─ 【没有 Resume】
   │    → 打开地图 → 进入 DungeonState.Map 状态
   │
   └─ 【有 Resume】
        → 点击 Resume 按钮
        → 等待 1 秒
        → 检查 routenotfound 是否出现
            │
            ├─ 【出现 routenotfound】
            │    → 表示已到达目的地（路径无效）
            │    → 等待 1 秒（routenotfound 会自动消失）
            │    → 打开地图 → 进入 DungeonState.Map 状态
            │
            └─ 【没出现 routenotfound】
                 → 表示还在路上，路径有效
                 → 调用 StateMoving_CheckFrozen() 监控移动
```

---

## 具体代码

```python
########### OPEN MAP
# Resume优化: 检查Resume按钮决定下一步动作
if setting._ENABLE_RESUME_OPTIMIZATION:
    Sleep(1)
    screen = ScreenShot()
    resume_pos = CheckIf(screen, 'resume', threshold=0.95)  # 95% 阈值
    
    if resume_pos:
        # Resume存在，点击Resume
        logger.info(f"Resume优化: 检测到Resume按钮，点击继续 位置:{resume_pos}")
        Press(resume_pos)
        Sleep(1)  # 等待 routenotfound 可能出现
        
        # 检查 routenotfound 是否出现
        screen_after = ScreenShot()
        if CheckIf(screen_after, 'routenotfound'):
            # routenotfound 出现 = 已到达目的地
            logger.info("Resume优化: 检测到routenotfound，已到达目的地，打开地图")
            Sleep(1)  # routenotfound 会自动消失，稍等一下
            Press([777,150])  # 打开地图
            dungState = DungeonState.Map
        else:
            # 没有 routenotfound = 还在路上，继续移动
            logger.info("Resume优化: 未检测到routenotfound，继续移动监控")
            dungState = StateMoving_CheckFrozen()
    else:
        # 没有Resume，打开地图
        logger.info("Resume优化: 未检测到Resume按钮，打开地图")
        Press([777,150])
        dungState = DungeonState.Map
else:
    Sleep(1)
    Press([777,150])
    dungState = DungeonState.Map
```

---

## 关键说明

| 情况 | 含义 | 处理方式 |
|------|------|----------|
| 无 Resume 按钮 | 第一次进入或无路径 | 打开地图搜索目标 |
| 有 Resume + 有 routenotfound | 已到达目的地 | 打开地图搜索下一个目标 |
| 有 Resume + 无 routenotfound | 正在路上 | 监控移动状态 |

---

## 依赖的图片资源

- `resume.png` - Resume 按钮图片（位于 `resources/images/`）
- `routenotfound.png` - 路径无效提示图片（位于 `resources/images/`）

---

## CheckIf 函数修改

为了支持单独调整图片匹配阈值，修改了 `CheckIf` 函数。

### 修改位置

**文件**: `src/script.py`  
**行号**: 610

### 修改内容

函数签名添加可选参数 `threshold`，默认值 `0.80`：

```python
# 修改前
def CheckIf(screenImage, shortPathOfTarget, roi = None, outputMatchResult = False):
    threshold = 0.80

# 修改后
def CheckIf(screenImage, shortPathOfTarget, roi = None, outputMatchResult = False, threshold = 0.80):
```

### Resume 阈值设置

`resume` 检测使用 **0.95（95%）** 阈值，比默认 80% 更严格：

```python
resume_pos = CheckIf(screen, 'resume', threshold=0.95)
```

**使用位置**:
- `StateMoving_CheckFrozen()` 第 1566 行
- `StateDungeon()` 第 1859 行

---

## 设置开关

此功能受 `setting._ENABLE_RESUME_OPTIMIZATION` 控制。

### GUI 控制

**位置**: GUI 面板中的复选框  
**文本**: "启用Resume按钮优化(减少地图操作)"  
**默认值**: 启用（勾选）

| 设置 | 效果 |
|------|------|
| ✅ 启用 | 使用 Resume + routenotfound 检测逻辑 |
| ❌ 禁用 | 直接打开地图（原始逻辑） |

### 相关代码位置

| 组件 | 文件 | 行号 |
|------|------|------|
| GUI 复选框 | `src/gui.py` | 255-262 |
| 变量定义 | `src/script.py` | 45 |
| StateDungeon 使用 | `src/script.py` | 1856 |
| StateMoving_CheckFrozen 使用 | `src/script.py` | 1565 |
| StateSearch 使用 | `src/script.py` | 1641 |
