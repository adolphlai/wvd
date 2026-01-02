# IdentifyState 优化计划

## 目标
- 降低每轮图片比对次数，消除重复检查。
- 行为稳定、分步实施、每一步都能验证。
- 先用数据证明收益，再做更大范围的整理。

## 范围
- src/script.py 的 IdentifyState 循环。
- CheckIf 与模板匹配工具。
- GUI 读取的 MonitorState.flag_* 更新逻辑。

## 约束
- 一次只改一个点，避免混杂风险。
- 优先做「同帧缓存」，少改全局行为。
- 不引入新依赖。

## Step 1: 基线量测（不改逻辑）
预计加速：0%（只是建立对照）
要做的事：
- 在 IdentifyState 与 CheckIf 加入轻量计时与计数器。
- 记录每轮总匹配数、combatActive 模板数量、每轮耗时 ms。
你会看到的 LOG：
- [StatePerf] loop_ms=xxx matches=xx combat_templates=xx
- [StatePerf] checkif_calls=xx cache_hit=xx (后续步骤才会有 hit)

## Step 2: 同帧匹配缓存
预计加速：15% - 35%（取决于重复 CheckIf 次数）
要做的事：
- 针对同一张 screen，缓存 (template+roi+threshold) 的 best_val/best_pos。
- IdentifyState 一轮内重复 CheckIf 直接命中缓存。
判断加速的 LOG：
- [StatePerf] loop_ms 降低
- [StatePerf] checkif_calls 不变但 cache_hit 上升

## Step 3: MonitorState 更新节流
预计加速：10% - 25%（取决于 GUI 更新频率）
要做的事：
- MonitorState.flag_* 只在每 500-1000ms 更新一次。
- 逻辑判定仍照常，但监控更新不再每轮全扫。
判断加速的 LOG：
- [StatePerf] loop_ms 降低
- [StatePerf] monitor_updates 降低（新增统计）

## Step 4: combatActive 早停 + ROI
预计加速：10% - 30%（combat 模板越多越明显）
要做的事：
- 限定战斗提示区 ROI，减少像素量。
- 优先检查上次命中的 combatActive 模板。
- 达到阈值立即 break。
判断加速的 LOG：
- [StatePerf] combat_checks 降低
- [StatePerf] loop_ms 进一步下降

## Step 5: 减少 IdentifyState 重复检查
预计加速：5% - 15%
要做的事：
- 互动前后避免重复 ScreenShot。
- 合并重复分支，减少同样模板重复比对。
判断加速的 LOG：
- [StatePerf] loop_ms 降低
- [StatePerf] checkif_calls 降低

## Step 6: 验证方式
跑一段正常刷图流程，对比：
- 状态切换次数是否一致（Dungeon/Combat/Chest/Map）
- 平均 loop_ms 是否下降
- combat/chest 计数是否一致

## 交付物
- Step 1: 新增计时与计数 LOG
- Step 2: CheckIf 同帧缓存
- Step 3: 监控更新节流
- Step 4: combatActive ROI+早停
- Step 5: IdentifyState 简化

## 备注
- 每一步独立 diff，方便回退。
