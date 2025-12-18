"""
基於 AutoMove 按鈕的寶箱搜尋優化

核心思路：
1. 利用 AutoMove 按鈕判斷移動狀態
2. 減少打開大地圖的次數
3. 更智能地判斷是否需要搜尋寶箱

AutoMove 按鈕邏輯：
- 按鈕可見 → 已設定目標點，可以移動
- 點擊按鈕 → 人物開始自動移動
- 移動被打斷（戰鬥/寶箱） → 可再次點擊繼續
- 到達目標 → 按鈕可能消失或變化
"""

import time
import cv2
import numpy as np

class AutoMoveBasedChestSearch:
    def __init__(self, utils):
        """
        初始化

        Args:
            utils: 包含 CheckIf, ScreenShot, Press, Sleep 等函數的模組
        """
        self.utils = utils
        self.last_position_check_time = 0
        self.position_check_interval = 5  # 每5秒檢查一次位置

    def is_automove_available(self):
        """
        檢查 AutoMove 按鈕是否可用

        Returns:
            bool: True 如果按鈕存在
        """
        screenshot = self.utils.ScreenShot()
        # 檢查 AutoMove 按鈕（位置約在 [280, 1433]）
        # 可以檢測按鈕圖像或特定區域
        automove_pos = self.utils.CheckIf(screenshot, 'AutoMove')
        return automove_pos is not None

    def click_automove(self):
        """點擊 AutoMove 按鈕"""
        self.utils.Press([280, 1433])
        self.utils.Sleep(0.5)

    def is_moving(self, check_duration=3):
        """
        判斷人物是否正在移動

        Args:
            check_duration: 檢查持續時間（秒）

        Returns:
            bool: True 如果正在移動
        """
        screen1 = self.utils.ScreenShot()
        self.utils.Sleep(check_duration)
        screen2 = self.utils.ScreenShot()

        # 計算畫面差異
        gray1 = cv2.cvtColor(screen1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(screen2, cv2.COLOR_BGR2GRAY)
        mean_diff = cv2.absdiff(gray1, gray2).mean() / 255

        # 如果差異大於閾值，說明在移動
        return mean_diff > 0.1

    def wait_until_stop_moving(self, timeout=30):
        """
        等待直到停止移動

        Args:
            timeout: 超時時間（秒）

        Returns:
            bool: True 如果正常停止，False 如果超時
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            if not self.is_moving(check_duration=2):
                return True
            self.utils.Sleep(1)

        return False

    def optimized_chest_search_with_automove(self, target_info_list, logger, setting):
        """
        使用 AutoMove 優化的寶箱搜尋

        策略：
        1. 設定目標點（在大地圖上點擊寶箱位置）
        2. 點擊 AutoMove 讓人物自動移動
        3. 等待移動完成或被打斷
        4. 如果被打斷：
           - 可能是戰鬥 → 處理戰鬥
           - 可能是寶箱 → 開啟寶箱
        5. 繼續點擊 AutoMove 直到所有寶箱搜尋完成

        Args:
            target_info_list: 目標列表
            logger: 日誌記錄器
            setting: 設定對象

        Returns:
            搜尋結果
        """
        logger.info("使用 AutoMove 優化的寶箱搜尋")

        # 這個方法需要配合主循環使用
        # 以下是概念性代碼

        # 1. 打開地圖
        # Press(map_button)

        # 2. 在地圖上找到所有寶箱位置
        # chest_positions = find_all_chests_on_map()

        # 3. 對每個寶箱位置
        # for chest_pos in chest_positions:
        #     # 點擊寶箱位置設定目標
        #     Press(chest_pos)
        #
        #     # 關閉地圖
        #     Press(close_map_button)
        #
        #     # 點擊 AutoMove
        #     click_automove()
        #
        #     # 等待移動完成或被打斷
        #     while True:
        #         if not is_moving():
        #             # 檢查當前狀態
        #             state = IdentifyState()
        #
        #             if state == Combat:
        #                 # 處理戰鬥
        #                 handle_combat()
        #                 # 戰鬥後繼續移動
        #                 click_automove()
        #
        #             elif state == Chest:
        #                 # 開啟寶箱
        #                 open_chest()
        #                 # 完成，跳到下一個寶箱
        #                 break
        #
        #             elif state == Dungeon:
        #                 # 已到達但沒有寶箱，繼續下一個
        #                 break

        pass

    def should_recheck_map(self):
        """
        判斷是否需要重新檢查地圖

        策略：不頻繁打開地圖，利用 AutoMove 持續移動

        Returns:
            bool: True 如果需要重新檢查地圖
        """
        current_time = time.time()

        # 距離上次檢查超過間隔時間
        if current_time - self.last_position_check_time > self.position_check_interval:
            self.last_position_check_time = current_time
            return True

        return False


# ==================== 整合到現有代碼的建議 ====================

def enhanced_chest_search_flow(logger, setting, utils):
    """
    增強的寶箱搜尋流程（概念示例）

    對比：
    原始流程：
    1. 打開地圖
    2. 滑動到左上 → 搜尋寶箱 → 沒找到
    3. 關閉地圖
    4. 打開地圖
    5. 滑動到右上 → 搜尋寶箱 → 找到
    6. 點擊寶箱位置
    7. 關閉地圖
    8. 人物移動過去
    9. 開啟寶箱
    10. 重複 1-9...

    優化流程：
    1. 打開地圖一次
    2. 記錄所有可見寶箱位置
    3. 關閉地圖
    4. 對每個寶箱：
       a. 打開地圖
       b. 點擊寶箱位置（設定 AutoMove 目標）
       c. 關閉地圖
       d. 點擊 AutoMove
       e. 等待到達或被打斷
       f. 處理戰鬥/寶箱
       g. 繼續下一個
    """

    automove_helper = AutoMoveBasedChestSearch(utils)

    logger.info("=== 開始增強的寶箱搜尋 ===")

    # 1. 打開地圖，收集所有寶箱位置
    logger.info("步驟 1: 打開地圖，掃描所有方向")
    utils.Press([1, 1])  # 打開地圖
    utils.Sleep(1)

    all_chest_positions = []
    directions = ["左上", "右上", "左下", "右下"]

    for direction in directions:
        # 滑動到該方向
        swipe_dir = get_swipe_direction(direction)
        utils.DeviceShell(f"input swipe {swipe_dir[0]} {swipe_dir[1]} {swipe_dir[2]} {swipe_dir[3]}")
        utils.Sleep(2)

        # 搜尋寶箱
        screenshot = utils.ScreenShot()
        chest_pos = utils.CheckIf(screenshot, 'chest')

        if chest_pos:
            logger.info(f"  在 {direction} 找到寶箱: {chest_pos}")
            all_chest_positions.append({
                'position': chest_pos,
                'direction': direction
            })

    if not all_chest_positions:
        logger.info("未找到任何寶箱")
        utils.Press([1, 1])  # 關閉地圖
        return

    logger.info(f"步驟 2: 共找到 {len(all_chest_positions)} 個寶箱")

    # 2. 逐個前往寶箱位置
    for i, chest_info in enumerate(all_chest_positions, 1):
        logger.info(f"步驟 3.{i}: 前往第 {i} 個寶箱 ({chest_info['direction']})")

        # 打開地圖（如果還沒打開）
        if not utils.CheckIf(utils.ScreenShot(), 'mapFlag'):
            utils.Press([1, 1])
            utils.Sleep(1)

        # 滑動到該方向
        swipe_dir = get_swipe_direction(chest_info['direction'])
        utils.DeviceShell(f"input swipe {swipe_dir[0]} {swipe_dir[1]} {swipe_dir[2]} {swipe_dir[3]}")
        utils.Sleep(2)

        # 點擊寶箱位置（設定 AutoMove 目標）
        utils.Press(chest_info['position'])
        utils.Sleep(0.5)

        # 關閉地圖
        utils.Press([1, 1])
        utils.Sleep(0.5)

        # 點擊 AutoMove
        if automove_helper.is_automove_available():
            logger.info("  → 點擊 AutoMove，開始移動")
            automove_helper.click_automove()

            # 等待到達或被打斷
            max_attempts = 5
            for attempt in range(max_attempts):
                logger.info(f"  → 等待移動完成... (嘗試 {attempt + 1}/{max_attempts})")

                if not automove_helper.wait_until_stop_moving(timeout=10):
                    logger.warning("  → 移動超時")
                    break

                # 檢查當前狀態
                _, state, _ = utils.IdentifyState()

                if state == 'Chest':
                    logger.info("  → 到達寶箱！開始開啟")
                    # 這裡調用原有的 StateChest() 處理
                    break

                elif state == 'Combat':
                    logger.info("  → 遇到戰鬥！處理中...")
                    # 這裡調用原有的 StateCombat() 處理
                    # 戰鬥後繼續移動
                    if automove_helper.is_automove_available():
                        automove_helper.click_automove()
                    continue

                elif state == 'Dungeon':
                    # 可能已到達但沒有觸發寶箱，或者寶箱已被開啟
                    logger.info("  → 已到達區域")
                    break

                else:
                    logger.warning(f"  → 未知狀態: {state}")
                    break
        else:
            logger.warning("  → AutoMove 按鈕不可用，使用傳統方法")

    logger.info("=== 寶箱搜尋完成 ===")


def get_swipe_direction(direction_name):
    """
    獲取滑動方向座標

    Args:
        direction_name: "左上", "右上", "左下", "右下"

    Returns:
        [start_x, start_y, end_x, end_y]
    """
    direction_map = {
        "左上": [100, 250, 700, 1200],
        "右上": [700, 250, 100, 1200],
        "左下": [100, 1200, 700, 250],
        "右下": [700, 1200, 100, 250]
    }
    return direction_map.get(direction_name, [100, 250, 700, 1200])


# ==================== 使用說明 ====================
"""
使用方式：

1. 在 StateDungeon 中調用：

    def StateDungeon(targetInfoList):
        # ... 原有代碼 ...

        # 如果目標是 chest，使用優化流程
        if targetInfo.target == 'chest':
            enhanced_chest_search_flow(logger, setting, utils)
            targetInfoList.pop(0)
            return DungeonState.Map, targetInfoList

        # ... 原有代碼 ...

2. 優勢：
   - 減少打開/關閉地圖的次數
   - 利用 AutoMove 自動移動，不需要手動控制
   - 更智能地處理戰鬥打斷
   - 減少整體耗時

3. 注意事項：
   - 需要確保 AutoMove 按鈕圖像識別準確
   - 需要處理 AutoMove 不可用的情況（fallback 到傳統方法）
   - 需要測試不同地城的兼容性
"""
