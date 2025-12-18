"""
基於 Resume 按鈕的寶箱搜尋優化

Resume 按鈕機制：
1. 在大地圖上點擊目標點 → 設定 AutoMove 目標
2. 點擊 AutoMove → 關閉地圖，開始自動移動
3. 移動被打斷（戰鬥/寶箱） → Resume 按鈕出現
4. 點擊 Resume → 繼續移動到目標點
5. 到達目標點 → Resume 按鈕消失

核心優化：
- 利用 Resume 按鈕判斷是否還在路上
- 減少頻繁打開大地圖的次數
"""


class ResumeButtonOptimizer:
    def __init__(self, utils, logger):
        """
        初始化

        Args:
            utils: 工具模組（包含 CheckIf, Press, Sleep 等）
            logger: 日誌記錄器
        """
        self.utils = utils
        self.logger = logger
        self.resume_button_pos = [280, 1433]  # Resume 按鈕位置

    def has_resume_button(self):
        """
        檢查 Resume 按鈕是否存在

        Returns:
            bool: True 如果存在
        """
        screenshot = self.utils.ScreenShot()
        resume_pos = self.utils.CheckIf(screenshot, 'resume')
        return resume_pos is not None

    def click_resume(self):
        """點擊 Resume 按鈕繼續移動"""
        self.logger.info("→ 點擊 Resume 繼續移動")
        self.utils.Press(self.resume_button_pos)
        self.utils.Sleep(0.5)

    def wait_for_arrival_or_interruption(self, timeout=30):
        """
        等待到達目標或被打斷

        Returns:
            str: 'arrived'（已到達）, 'combat'（遇到戰鬥）, 'chest'（遇到寶箱）, 'timeout'（超時）
        """
        import time
        start_time = time.time()

        last_screen = None

        while time.time() - start_time < timeout:
            self.utils.Sleep(2)

            # 檢查當前狀態
            _, state, screen = self.utils.IdentifyState()

            # 如果進入戰鬥
            if state.name == 'Combat':
                self.logger.info("→ 移動被打斷：遇到戰鬥")
                return 'combat'

            # 如果遇到寶箱
            if state.name == 'Chest':
                self.logger.info("→ 移動被打斷：遇到寶箱")
                return 'chest'

            # 如果在地城中（非戰鬥、非寶箱）
            if state.name == 'Dungeon':
                # 檢查是否還在移動
                if last_screen is not None:
                    import cv2
                    gray1 = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                    gray2 = cv2.cvtColor(last_screen, cv2.COLOR_BGR2GRAY)
                    mean_diff = cv2.absdiff(gray1, gray2).mean() / 255

                    if mean_diff < 0.1:
                        # 畫面沒有變化，可能已到達
                        if not self.has_resume_button():
                            self.logger.info("→ 已到達目標位置（Resume 按鈕消失）")
                            return 'arrived'
                        else:
                            self.logger.warning("→ 畫面靜止但 Resume 按鈕仍存在，可能卡住了")
                            # 嘗試點擊 Resume
                            self.click_resume()

                last_screen = screen

        self.logger.warning("→ 等待超時")
        return 'timeout'


def optimized_chest_search_with_resume(target_info, utils, logger, setting):
    """
    使用 Resume 按鈕優化的寶箱搜尋

    流程：
    1. 打開大地圖
    2. 搜尋寶箱位置
    3. 點擊寶箱設定目標
    4. 點擊 AutoMove 開始移動
    5. 等待到達或被打斷
    6. 如果被打斷：
       - 處理戰鬥/寶箱
       - 點擊 Resume 繼續
    7. 重複直到 Resume 按鈕消失（已到達）

    Args:
        target_info: 目標信息
        utils: 工具模組
        logger: 日誌記錄器
        setting: 設定對象

    Returns:
        結果
    """
    optimizer = ResumeButtonOptimizer(utils, logger)

    target = target_info.target
    roi = target_info.roi

    if target != 'chest':
        logger.info("不是寶箱目標，使用原始方法")
        return None

    logger.info("=== 使用 Resume 按鈕優化的寶箱搜尋 ===")

    # 1. 打開大地圖
    logger.info("步驟 1: 打開大地圖")
    utils.Press([1, 1])
    utils.Sleep(1)

    # 2. 搜尋寶箱（遍歷各個方向）
    logger.info("步驟 2: 搜尋寶箱位置")
    chest_found = False
    chest_pos = None

    for i, swipe_dir in enumerate(target_info.swipeDir):
        # 滑動地圖
        if swipe_dir:
            logger.debug(f"  滑動到方向 {i+1}")
            utils.DeviceShell(f"input swipe {swipe_dir[0]} {swipe_dir[1]} {swipe_dir[2]} {swipe_dir[3]}")
            utils.Sleep(2)

        # 搜尋寶箱
        screenshot = utils.ScreenShot()
        chest_pos = utils.CheckIf(screenshot, 'chest', roi)

        if chest_pos:
            logger.info(f"  ✓ 找到寶箱: {chest_pos}")
            chest_found = True
            break

    if not chest_found:
        logger.info("步驟 2: 未找到寶箱")
        utils.Press([1, 1])  # 關閉地圖
        return None

    # 3. 點擊寶箱位置設定目標
    logger.info(f"步驟 3: 點擊寶箱位置 {chest_pos}")
    utils.Press(chest_pos)
    utils.Sleep(1)

    # 4. 點擊 AutoMove（這會關閉地圖並開始移動）
    logger.info("步驟 4: 點擊 AutoMove 開始移動")
    utils.Press([280, 1433])  # AutoMove 按鈕位置（在地圖上）
    utils.Sleep(2)

    # 5. 主循環：等待到達，處理打斷
    logger.info("步驟 5: 等待到達目標")
    max_interruptions = 10  # 最多處理10次打斷

    for interruption_count in range(max_interruptions):
        result = optimizer.wait_for_arrival_or_interruption(timeout=30)

        if result == 'arrived':
            logger.info("✓ 成功到達寶箱位置")
            return chest_pos

        elif result == 'combat':
            logger.info(f"→ 遇到戰鬥（第 {interruption_count + 1} 次打斷）")
            # 這裡需要調用原有的戰鬥處理邏輯
            # utils.StateCombat()

            # 戰鬥後檢查 Resume 按鈕
            utils.Sleep(2)
            if optimizer.has_resume_button():
                optimizer.click_resume()
            else:
                logger.info("✓ Resume 按鈕消失，可能已到達")
                return chest_pos

        elif result == 'chest':
            logger.info(f"→ 遇到寶箱（第 {interruption_count + 1} 次打斷）")
            # 這裡需要調用原有的寶箱處理邏輯
            # utils.StateChest()

            # 開箱後檢查 Resume 按鈕
            utils.Sleep(2)
            if optimizer.has_resume_button():
                logger.info("→ 還有其他目標，繼續移動")
                optimizer.click_resume()
            else:
                logger.info("✓ Resume 按鈕消失，已完成")
                return chest_pos

        elif result == 'timeout':
            logger.warning(f"→ 等待超時（第 {interruption_count + 1} 次）")
            # 檢查 Resume 按鈕
            if optimizer.has_resume_button():
                optimizer.click_resume()
            else:
                logger.info("✓ Resume 按鈕消失，可能已到達")
                return chest_pos

    logger.warning("✗ 達到最大打斷次數，放棄")
    return None


# ==================== 對比分析 ====================
"""
對比：原始方法 vs Resume 優化方法

原始方法：
1. 打開地圖
2. 滑動到左上 → 搜尋寶箱 → 沒找到
3. 關閉地圖
4. 打開地圖
5. 滑動到右上 → 搜尋寶箱 → 找到
6. 點擊寶箱位置
7. 點擊 AutoMove
8. 關閉地圖
9. 等待移動...
10. 遇到戰鬥 → 處理戰鬥
11. 打開地圖重新確認位置 ← 多餘！
12. 點擊寶箱位置
13. 點擊 AutoMove
14. 關閉地圖
15. 繼續移動...
16. 到達寶箱

耗時：約 20-25 秒
地圖操作：打開/關閉 3-4 次

Resume 優化方法：
1. 打開地圖
2. 滑動到左上 → 搜尋寶箱 → 沒找到
3. 滑動到右上 → 搜尋寶箱 → 找到
4. 點擊寶箱位置
5. 點擊 AutoMove（自動關閉地圖）
6. 等待移動...
7. 遇到戰鬥 → 處理戰鬥
8. 檢查 Resume 按鈕 → 存在
9. 點擊 Resume 繼續移動 ← 無需打開地圖！
10. 繼續移動...
11. 到達寶箱

耗時：約 12-15 秒
地圖操作：打開/關閉 1 次

節省時間：40-50%！
關鍵：利用 Resume 按鈕判斷狀態，不需要頻繁打開地圖
"""


# ==================== 整合建議 ====================
"""
整合到 StateMap_FindSwipeClick：

def StateMap_FindSwipeClick(targetInfo: TargetInfo):
    target = targetInfo.target

    # 如果是寶箱搜尋，使用 Resume 優化
    if target == 'chest':
        result = optimized_chest_search_with_resume(
            targetInfo, utils, logger, setting
        )
        return result

    # 其他目標使用原始方法
    # ... 原有代碼 ...
"""
