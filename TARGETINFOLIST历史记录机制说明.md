# TARGETINFOLIST 历史记录机制说明

## 📋 核心问题

**当 `_TARGETINFOLIST` 中有多个目标时（如多个 `["chest", "左上"]`, `["chest", "右上"]`），历史记录是如何工作的？**

---

## 🎯 关键结论

### ✅ **会记录每个方向的搜索历史，并且会重复使用**

**历史记录是基于 "地城名称 + 方向"，不是基于单个目标项。**

这意味着：
- **多个目标项共享同一个历史记录**（如果它们的地城和方向相同）
- **每次搜索都会更新历史记录**
- **下次遇到相同方向时，会检查历史记录决定是否跳过**

---

## 📊 详细机制说明

### 1. 历史记录的存储结构

历史记录存储在 `chest_direction_history.json` 中：

```json
{
  "Dist": {                           // 地城名称（setting._FARMTARGET）
    "chest": {                        // 目标类型
      "左上": {                        // 方向（标准化后的方向名称）
        "attempts": 5,                // 尝试次数
        "found": 2,                   // 找到次数
        "last_search": "2025-10-27T12:34:56"
      },
      "右上": {
        "attempts": 3,
        "found": 3,
        "last_search": "2025-10-27T12:35:12"
      }
    }
  }
}
```

**关键点：**
- **Key 是地城名称**（如 "Dist"），不是任务ID或目标项
- **方向是标准化的**（"左上"、"右上"等），不是原始swipeDir数组

---

### 2. 配置示例分析

#### 配置A：单一目标（默认5方向）

```json
"_TARGETINFOLIST": [
    ["chest"],      // swipeDir=None → 转换为5个方向
    ["harken"]
]
```

**执行流程：**

1. **第一次搜索 `["chest"]`：**
   ```python
   targetInfo = TargetInfo("chest", None, None)
   # swipeDir 被转换为：[None, [左上], [右上], [右下], [左下]]
   
   # StateMap_FindSwipeClick 中遍历所有5个方向
   for i in range(5):
       swipeDir = targetInfo.swipeDir[i]
       
       # 记录到历史记录
       direction_history.record_search_result("Dist", swipeDir, found, "chest")
   ```

2. **历史记录更新：**
   ```json
   {
     "Dist": {
       "chest": {
         "中央": {"attempts": 1, "found": 0},
         "左上": {"attempts": 1, "found": 1},
         "右上": {"attempts": 1, "found": 0},
         "右下": {"attempts": 1, "found": 0},
         "左下": {"attempts": 1, "found": 0}
       }
     }
   }
   ```

3. **第二次搜索（如果 `["chest"]` 还在列表中）：**
   ```python
   # 再次遍历5个方向
   # 检查历史记录
   should_search = direction_history.should_search_direction("Dist", None, "chest")
   # 如果 "中央" attempts >= 3 且 found == 0 → 跳过
   ```

---

#### 配置B：多个目标（每个方向一个目标）

```json
"_TARGETINFOLIST": [
    ["chest", "左上", null],
    ["chest", "右上", null],
    ["chest", "左下", null],
    ["chest", "右下", null],
    ["harken"]
]
```

**执行流程：**

1. **第一次搜索 `["chest", "左上"]`：**
   ```python
   targetInfo = TargetInfo("chest", "左上", null)
   # swipeDir 被转换为：[[100,250,700,1200]]  （只有1个方向）
   
   # StateMap_FindSwipeClick 中只遍历1个方向
   for i in range(1):  # len(swipeDir) = 1
       swipeDir = [100,250,700,1200]
       
       # 检查历史记录
       should_search = direction_history.should_search_direction("Dist", swipeDir, "chest")
       # 第一次：没有记录 → 返回 True（需要搜索）
       
       # 搜索
       targetPos = CheckIf(scn, "chest", roi)
       
       # 记录结果
       direction_history.record_search_result("Dist", swipeDir, found, "chest")
   ```

2. **历史记录更新：**
   ```json
   {
     "Dist": {
       "chest": {
         "左上": {"attempts": 1, "found": 1}  // 假设找到了
       }
     }
   }
   ```

3. **第二次搜索 `["chest", "右上"]`：**
   ```python
   targetInfo = TargetInfo("chest", "右上", null)
   # swipeDir = [[700,250,100,1200]]
   
   # 检查历史记录
   should_search = direction_history.should_search_direction("Dist", swipeDir, "chest")
   # "右上" 没有记录 → 返回 True（需要搜索）
   
   # 搜索并记录
   direction_history.record_search_result("Dist", swipeDir, found, "chest")
   ```

4. **历史记录更新：**
   ```json
   {
     "Dist": {
       "chest": {
         "左上": {"attempts": 1, "found": 1},
         "右上": {"attempts": 1, "found": 0}  // 假设没找到
       }
     }
   }
   ```

5. **第三次搜索 `["chest", "左下"]`：**
   ```python
   # 同样流程，记录 "左下" 的结果
   ```

6. **第四次搜索 `["chest", "右下"]`：**
   ```python
   # 同样流程，记录 "右下" 的结果
   ```

7. **循环回到第一个目标 `["chest", "左上"]`：**
   ```python
   # 检查历史记录
   should_search = direction_history.should_search_direction("Dist", swipeDir, "chest")
   # "左上" attempts = 1, found = 1
   # found > 0 → 返回 True（继续搜索，因为曾经找到过）
   
   # 搜索并更新记录
   direction_history.record_search_result("Dist", swipeDir, found, "chest")
   # attempts: 1 → 2, found: 1 → 2（如果找到）或保持1（如果没找到）
   ```

---

### 3. 关键机制

#### 机制1：历史记录共享

**所有相同地城、相同方向的目标项共享同一个历史记录。**

```python
# 配置中有多个 ["chest", "左上"]
["chest", "左上"],
["chest", "左上"],  // 再次出现

# 它们都会：
# 1. 检查同一个历史记录项："Dist" -> "chest" -> "左上"
# 2. 更新同一个历史记录项
# 3. attempts 会累加（不管是哪个目标项触发的）
```

**示例：**
```json
// 初始
{"Dist": {"chest": {"左上": {"attempts": 0, "found": 0}}}}

// 第一个 ["chest", "左上"] 搜索后
{"Dist": {"chest": {"左上": {"attempts": 1, "found": 1}}}}

// 第二个 ["chest", "左上"] 搜索后（如果找到）
{"Dist": {"chest": {"左上": {"attempts": 2, "found": 2}}}}

// 第二个 ["chest", "左上"] 搜索后（如果没找到）
{"Dist": {"chest": {"左上": {"attempts": 2, "found": 1}}}}  // found 不变
```

#### 机制2：方向标准化

**历史记录使用标准化的方向名称，不是原始 swipeDir 数组。**

```python
# swipeDir = [100,250,700,1200]
direction_key = _normalize_direction(swipeDir)
# → "左上"

# swipeDir = [700,250,100,1200]
direction_key = _normalize_direction(swipeDir)
# → "右上"

# swipeDir = None
direction_key = _normalize_direction(None)
# → "中央"
```

**这意味着：**
- 不同的 swipeDir 数组可能被标准化为同一个方向名称
- 历史记录是基于标准化后的方向名称的

#### 机制3：跳过逻辑

**如果某个方向 attempts >= 3 且 found == 0，会跳过该方向。**

```python
def should_search_direction(dungeon_name, direction, target='chest', min_attempts=3):
    direction_key = _normalize_direction(direction)
    record = chest_data[direction_key]
    
    if attempts >= min_attempts and found == 0:
        return False  # 跳过
    else:
        return True   # 继续搜索
```

**对于配置B（多个目标项）的影响：**

```json
"_TARGETINFOLIST": [
    ["chest", "左上", null],   // 如果3次都没找到，会被跳过
    ["chest", "右上", null],   // 独立的历史记录
    ["chest", "左下", null],   // 独立的历史记录
    ["chest", "右下", null]    // 独立的历史记录
]
```

- **每个目标项有独立的历史记录**（因为它们方向不同）
- **如果 `["chest", "左上"]` 3次都没找到，后续遇到这个目标项时会跳过**
- **但不会影响其他方向的目标项**

---

## 🔄 完整执行流程对比

### 场景1：配置A（单一目标 `["chest"]`）

```json
"_TARGETINFOLIST": [
    ["chest"],
    ["harken"]
]
```

**循环1（第1次）：**
1. 搜索 `["chest"]` → 遍历5个方向
2. 记录5个方向的历史
3. 找到宝箱 → 开箱 → **不移除目标**
4. 继续下一个循环

**循环2（第2次）：**
1. 再次搜索 `["chest"]` → 遍历5个方向
2. **检查历史记录**：如果某些方向3次都没找到，会跳过
3. 记录结果

**循环N（第N次）：**
1. 某些方向可能已经被跳过（如果3次都没找到）
2. 继续搜索未被跳过的方向

---

### 场景2：配置B（多个目标）

```json
"_TARGETINFOLIST": [
    ["chest", "左上", null],
    ["chest", "右上", null],
    ["chest", "左下", null],
    ["chest", "右下", null],
    ["harken"]
]
```

**循环1：**
1. 搜索 `["chest", "左上"]` → 只搜索"左上"方向
   - 记录："左上" attempts=1, found=1
2. 搜索 `["chest", "右上"]` → 只搜索"右上"方向
   - 记录："右上" attempts=1, found=0
3. 搜索 `["chest", "左下"]` → 只搜索"左下"方向
   - 记录："左下" attempts=1, found=0
4. 搜索 `["chest", "右下"]` → 只搜索"右下"方向
   - 记录："右下" attempts=1, found=0
5. 搜索 `["harken"]` → 退出

**循环2（重新进入地下城）：**
1. 搜索 `["chest", "左上"]`
   - 检查历史："左上" attempts=1, found=1 → **继续搜索**（因为曾经找到过）
   - 更新：attempts=2, found=2（如果找到）或 found=1（如果没找到）
2. 搜索 `["chest", "右上"]`
   - 检查历史："右上" attempts=1, found=0 → **继续搜索**（attempts < 3）
   - 更新：attempts=2, found=0（如果没找到）
3. 搜索 `["chest", "左下"]`
   - 检查历史："左下" attempts=1, found=0 → **继续搜索**
   - 更新：attempts=2, found=0
4. 搜索 `["chest", "右下"]`
   - 检查历史："右下" attempts=1, found=0 → **继续搜索**
   - 更新：attempts=2, found=0

**循环3：**
1. 搜索 `["chest", "右上"]`
   - 检查历史："右上" attempts=2, found=0 → **继续搜索**（attempts < 3）
   - 更新：attempts=3, found=0

**循环4：**
1. 搜索 `["chest", "右上"]`
   - 检查历史："右上" attempts=3, found=0 → **跳过！**（attempts >= 3 且 found == 0）
   - 日志输出：`"chest優化: 方向 [右上] 已確認無目標，跳過"`
   - **但目标项还在列表中，只是这次搜索被跳过了**

---

## ⚠️ 重要区别

### 配置A vs 配置B 的关键区别

| 特性 | 配置A: `["chest"]` | 配置B: `["chest", "左上"]` × 4 |
|------|-------------------|-------------------------------|
| **目标项数量** | 1个 | 4个 |
| **每个目标的方向数** | 5个（中央+4方向） | 1个（指定方向） |
| **历史记录粒度** | 5个方向共享 | 每个方向独立 |
| **找到就停止** | ✅ 找到第一个就停止，其他方向不搜索 | ❌ 每个目标项独立处理 |
| **目标项移除** | ❌ 找不到时才移除 | ✅ 找不到时移除该目标项 |
| **跳过影响** | 整个目标项的所有方向 | 只影响该目标项的该方向 |

---

## 📝 实际行为总结

### 配置A：`["chest"]`

1. **每次都会检查历史记录**，可能跳过某些方向
2. **找到宝箱后，目标项不会被移除**，会持续循环搜索
3. **如果某个方向3次都没找到，后续会被跳过**
4. **但其他方向仍然会搜索**（只要目标项还在）

### 配置B：`["chest", "左上"]` × 4

1. **每个目标项独立处理**，有自己的历史记录
2. **找到宝箱后，该目标项不会被移除**，会继续循环
3. **如果某个方向3次都没找到，遇到该目标项时会跳过搜索**
4. **但目标项还在列表中**（只是这次搜索被跳过）
5. **其他方向的目标项不受影响**

---

## 🎯 回答您的问题

### Q: 会记录每个方向是否已经没宝箱了吗？

**A: 是的！** 

历史记录会记录：
- 每个方向的尝试次数（`attempts`）
- 每个方向的找到次数（`found`）
- 如果 `attempts >= 3` 且 `found == 0`，会跳过该方向

### Q: 还是每次都会再次重新查一次？

**A: 取决于历史记录的状态！**

- **首次搜索**：会重新检查（没有历史记录）
- **有历史记录时**：
  - `attempts < 3` → **会重新检查**（还在收集数据）
  - `attempts >= 3` 且 `found == 0` → **跳过，不检查**
  - `found > 0` → **会重新检查**（曾经找到过，可能刷新）

### 关键点：

- **历史记录会累积**（不管是哪个目标项触发的）
- **每个方向的历史记录是独立的**
- **跳过逻辑是基于"地城 + 方向"，不是基于目标项**

