"""
寶箱搜尋優化模組 - 使用滑動計數和區域標記

核心思路：
1. 記錄每次滑動的方向和次數
2. 將地圖劃分為區域（左上、右上、左下、右下、中央）
3. 標記已搜尋的區域，避免重複搜尋
4. 每次進入地城重置記錄

使用方法：
    # 初始化
    optimizer = ChestSearchOptimizer()

    # 進入地城時重置
    optimizer.reset()

    # 搜尋前檢查
    if optimizer.should_search_region("左上"):
        # 執行搜尋
        optimizer.mark_region_searched("左上", found_chest=True)
"""

import json
import os
from datetime import datetime
from typing import Literal, Optional

RegionType = Literal["左上", "右上", "左下", "右下", "中央"]

class ChestSearchOptimizer:
    def __init__(self, data_file="chest_search_history.json"):
        """
        初始化寶箱搜尋優化器

        Args:
            data_file: 數據文件路徑（保存搜尋歷史）
        """
        self.data_file = data_file
        self.current_offset_x = 0  # 當前水平偏移
        self.current_offset_y = 0  # 當前垂直偏移
        self.searched_regions = set()  # 本次已搜尋的區域
        self.history = self.load_history()  # 歷史記錄

    def load_history(self) -> dict:
        """加載歷史記錄"""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def save_history(self):
        """保存歷史記錄"""
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(self.history, f, ensure_ascii=False, indent=2)

    def reset(self):
        """重置當前搜尋狀態（進入新地城時調用）"""
        self.current_offset_x = 0
        self.current_offset_y = 0
        self.searched_regions.clear()

    def record_swipe(self, swipe_dir: list):
        """
        記錄滑動操作，更新當前位置偏移

        Args:
            swipe_dir: 滑動座標 [start_x, start_y, end_x, end_y]
                例如: [100, 250, 700, 1200] 表示從(100,250)滑到(700,1200)
        """
        if not swipe_dir or len(swipe_dir) != 4:
            return

        start_x, start_y, end_x, end_y = swipe_dir

        # 地圖滑動方向與偏移相反
        # 如果手指往右滑，地圖向左移動，表示人物相對往右移動
        dx = end_x - start_x
        dy = end_y - start_y

        # 更新偏移（人物視角）
        self.current_offset_x -= dx
        self.current_offset_y -= dy

    def get_current_region(self) -> RegionType:
        """
        根據當前偏移量判斷所在區域

        Returns:
            當前區域："左上", "右上", "左下", "右下", "中央"
        """
        # 定義閾值（根據實際地圖大小調整）
        THRESHOLD = 300

        x = self.current_offset_x
        y = self.current_offset_y

        # 判斷區域
        if abs(x) < THRESHOLD and abs(y) < THRESHOLD:
            return "中央"
        elif x < -THRESHOLD and y < -THRESHOLD:
            return "左上"
        elif x > THRESHOLD and y < -THRESHOLD:
            return "右上"
        elif x < -THRESHOLD and y > THRESHOLD:
            return "左下"
        elif x > THRESHOLD and y > THRESHOLD:
            return "右下"
        elif x < -THRESHOLD:
            return "左上" if abs(y) < THRESHOLD else ("左上" if y < 0 else "左下")
        elif x > THRESHOLD:
            return "右上" if abs(y) < THRESHOLD else ("右上" if y < 0 else "右下")
        elif y < -THRESHOLD:
            return "左上" if abs(x) < THRESHOLD else ("左上" if x < 0 else "右上")
        else:  # y > THRESHOLD
            return "左下" if abs(x) < THRESHOLD else ("左下" if x < 0 else "右下")

    def should_search_region(self, region: RegionType) -> bool:
        """
        判斷是否應該搜尋該區域

        Args:
            region: 區域名稱

        Returns:
            True 如果應該搜尋，False 如果已搜尋過
        """
        return region not in self.searched_regions

    def mark_region_searched(self, region: RegionType, found_chest: bool = False,
                            dungeon_name: Optional[str] = None):
        """
        標記區域已搜尋

        Args:
            region: 區域名稱
            found_chest: 是否找到寶箱
            dungeon_name: 地城名稱（可選，用於歷史記錄）
        """
        self.searched_regions.add(region)

        # 更新歷史記錄
        if dungeon_name:
            if dungeon_name not in self.history:
                self.history[dungeon_name] = {}

            if region not in self.history[dungeon_name]:
                self.history[dungeon_name][region] = {
                    "found_count": 0,
                    "search_count": 0,
                    "last_search": None
                }

            self.history[dungeon_name][region]["search_count"] += 1
            if found_chest:
                self.history[dungeon_name][region]["found_count"] += 1
            self.history[dungeon_name][region]["last_search"] = datetime.now().isoformat()

            self.save_history()

    def get_region_success_rate(self, dungeon_name: str, region: RegionType) -> float:
        """
        獲取某區域的寶箱出現率

        Args:
            dungeon_name: 地城名稱
            region: 區域名稱

        Returns:
            成功率 (0.0 ~ 1.0)
        """
        if dungeon_name not in self.history:
            return 0.0

        if region not in self.history[dungeon_name]:
            return 0.0

        data = self.history[dungeon_name][region]
        if data["search_count"] == 0:
            return 0.0

        return data["found_count"] / data["search_count"]

    def get_search_priority(self, dungeon_name: str) -> list[RegionType]:
        """
        根據歷史記錄獲取搜尋優先級

        Args:
            dungeon_name: 地城名稱

        Returns:
            按優先級排序的區域列表
        """
        regions: list[RegionType] = ["左上", "右上", "左下", "右下", "中央"]

        # 根據成功率排序
        priority = sorted(
            regions,
            key=lambda r: self.get_region_success_rate(dungeon_name, r),
            reverse=True
        )

        return priority

    def get_statistics(self, dungeon_name: Optional[str] = None) -> dict:
        """
        獲取統計信息

        Args:
            dungeon_name: 地城名稱（None則返回所有）

        Returns:
            統計信息字典
        """
        if dungeon_name:
            if dungeon_name in self.history:
                return {dungeon_name: self.history[dungeon_name]}
            else:
                return {}
        else:
            return self.history

    def direction_to_region(self, direction: str) -> Optional[RegionType]:
        """
        將方向字符串轉換為區域類型

        Args:
            direction: 方向字符串 "左上", "右上", "左下", "右下"

        Returns:
            區域類型，如果無法識別則返回 None
        """
        direction_map = {
            "左上": "左上",
            "右上": "右上",
            "左下": "左下",
            "右下": "右下"
        }
        return direction_map.get(direction, None)


# 使用示例
if __name__ == "__main__":
    # 創建優化器
    optimizer = ChestSearchOptimizer("test_history.json")

    print("=== 寶箱搜尋優化器測試 ===\n")

    # 模擬進入地城
    print("1. 進入地城，重置狀態")
    optimizer.reset()
    print(f"   當前區域: {optimizer.get_current_region()}")
    print(f"   當前偏移: ({optimizer.current_offset_x}, {optimizer.current_offset_y})\n")

    # 模擬向左上滑動
    print("2. 向左上滑動")
    optimizer.record_swipe([100, 250, 700, 1200])  # 左上方向
    print(f"   當前區域: {optimizer.get_current_region()}")
    print(f"   當前偏移: ({optimizer.current_offset_x}, {optimizer.current_offset_y})")

    # 檢查是否應該搜尋
    region = optimizer.get_current_region()
    if optimizer.should_search_region(region):
        print(f"   ✓ 應該搜尋區域: {region}")
        optimizer.mark_region_searched(region, found_chest=True, dungeon_name="水路一號街")
    else:
        print(f"   ✗ 區域已搜尋過: {region}\n")

    # 再次滑動到同一區域
    print("\n3. 再次嘗試搜尋同一區域")
    if optimizer.should_search_region(region):
        print(f"   ✓ 應該搜尋")
    else:
        print(f"   ✗ 已搜尋過，跳過\n")

    # 查看統計
    print("4. 查看統計信息")
    stats = optimizer.get_statistics("水路一號街")
    print(json.dumps(stats, ensure_ascii=False, indent=2))

    print("\n測試完成！")
