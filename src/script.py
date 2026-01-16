import functools
from ppadb.client import Client as AdbClient
from win10toast import ToastNotifier

from enum import Enum
from datetime import datetime
import os
import subprocess
from utils import *
import random
from threading import Thread,Event
from pathlib import Path
import numpy as np
import copy

# pyscrcpy 串流支援
try:
    from pyscrcpy import Client as ScrcpyClient
    PYSCRCPY_AVAILABLE = True
    logger.info("pyscrcpy 可用，將使用視頻串流模式")
except ImportError:
    PYSCRCPY_AVAILABLE = False
    ScrcpyClient = None
    logger.info("pyscrcpy 不可用，將使用傳統 ADB 截圖")

class ScrcpyStreamManager:
    """pyscrcpy 串流管理器"""

    def __init__(self, max_fps=60, max_size=1600, bitrate=32000000):
        self.max_fps = max_fps
        self.max_size = max_size
        self.bitrate = bitrate  # 比特率，預設 32Mbps（提高圖像質量）
        self.client = None
        self.latest_frame = None
        self.frame_count = 0
        self.running = False
        self._lock = Event()
    
    def _on_frame(self, client, frame):
        """幀回調"""
        if frame is not None:
            self.latest_frame = frame.copy()
            self.frame_count += 1
    
    def start(self):
        """啟動串流"""
        if not PYSCRCPY_AVAILABLE:
            logger.warning("pyscrcpy 不可用，無法啟動串流")
            return False
        
        if self.running:
            return True
        
        try:
            logger.info(f"啟動 pyscrcpy 串流 (max_fps={self.max_fps}, max_size={self.max_size}, bitrate={self.bitrate})")
            self.client = ScrcpyClient(
                max_fps=self.max_fps,
                max_size=self.max_size,
                bitrate=self.bitrate,
            )
            self.client.on_frame(self._on_frame)
            self.client.start(threaded=True)
            
            # 等待第一幀
            for i in range(50):  # 最多等 5 秒
                if self.client.last_frame is not None:
                    self.latest_frame = self.client.last_frame.copy()
                    self.frame_count += 1
                    self.running = True
                    logger.info(f"✓ pyscrcpy 串流已啟動！")
                    return True
                time.sleep(0.1)
            
            logger.warning("pyscrcpy 串流啟動超時")
            return False
            
        except Exception as e:
            logger.error(f"pyscrcpy 串流啟動失敗: {e}")
            return False
    
    def get_frame(self):
        """獲取最新幀"""
        try:
            if self.client and self.client.last_frame is not None:
                frame = self.client.last_frame.copy()
                return frame
        except Exception as e:
            # 串流可能已斷開
            logger.warning(f"pyscrcpy 獲取幀失敗: {e}，標記為不可用")
            self.running = False
        return None
    
    def stop(self):
        """停止串流"""
        self.running = False
        if self.client:
            try:
                self.client.stop()
                logger.info("pyscrcpy 串流已停止")
            except:
                pass
        self.client = None
    
    def is_available(self):
        """檢查串流是否可用"""
        if not self.running or self.client is None:
            return False
        try:
            # 檢查客戶端是否仍在運行（pyscrcpy 內部狀態）
            if hasattr(self.client, 'alive') and not self.client.alive:
                logger.debug("pyscrcpy 客戶端已停止")
                self.running = False
                return False
            return self.client.last_frame is not None
        except:
            self.running = False
            return False
    
    def restart(self):
        """重新啟動串流（斷開後重連）"""
        logger.info("嘗試重新啟動 pyscrcpy 串流...")
        self.stop()
        return self.start()

# 全局串流管理器
_scrcpy_stream = None

def get_scrcpy_stream():
    """獲取或創建串流管理器"""
    global _scrcpy_stream
    if _scrcpy_stream is None and PYSCRCPY_AVAILABLE:
        _scrcpy_stream = ScrcpyStreamManager()
    return _scrcpy_stream

def cleanup_scrcpy_stream():
    """清理 pyscrcpy 串流資源
    
    在程序關閉時調用，確保視頻串流正確停止，
    避免因為 pyscrcpy 內部線程阻塞導致程序卡死。
    """
    global _scrcpy_stream
    if _scrcpy_stream is not None:
        try:
            logger.info("正在停止 pyscrcpy 串流...")
            _scrcpy_stream.stop()
            logger.info("pyscrcpy 串流已清理")
        except Exception as e:
            logger.warning(f"清理 pyscrcpy 串流時發生異常: {e}")
        finally:
            _scrcpy_stream = None


# ==================== 技能分類與載入 ====================

# 技能類別與施放方式對應
SKILL_CATEGORIES = {
    "普攻": {"cast_type": "target", "folder": "普攻"},
    "單體": {"cast_type": "target", "folder": "單體"},
    "橫排": {"cast_type": "target", "folder": "橫排"},
    "全體": {"cast_type": "ok", "folder": "全體"},
    "秘術": {"cast_type": "ok", "folder": "秘術"},
    "群控": {"cast_type": "target", "folder": "群控"},
    "輔助": {"cast_type": "support", "folder": "輔助"},
    "防禦": {"cast_type": "none", "folder": "防禦"},
}

def load_skills_from_folder():
    """從資料夾結構載入技能列表
    
    掃描 resources/images/spellskill/ 下的分類資料夾，
    按數字前綴排序返回技能名稱列表。
    
    Returns:
        dict: {類別名: [技能名列表], ...}
    """
    skills_by_category = {}
    spellskill_dir = ResourcePath("resources/images/spellskill")
    
    for category, info in SKILL_CATEGORIES.items():
        folder_path = os.path.join(spellskill_dir, info["folder"])
        skills = []
        
        if os.path.isdir(folder_path):
            files = os.listdir(folder_path)
            # 過濾只取 .png 檔案
            png_files = [f for f in files if f.lower().endswith('.png')]
            # 依檔名排序（數字前綴會自然排序）
            png_files.sort()
            
            for filename in png_files:
                # 移除數字前綴和副檔名，取得技能名稱
                # 例：01_attack.png → attack
                skill_name = filename.rsplit('.', 1)[0]  # 移除副檔名
                if '_' in skill_name:
                    skill_name = skill_name.split('_', 1)[1]  # 移除數字前綴
                skills.append(skill_name)
        
        skills_by_category[category] = skills
        logger.debug(f"[技能載入] {category}: {len(skills)} 個技能")
    
    return skills_by_category

def get_skill_cast_type(category):
    """取得技能類別的施放方式
    
    Args:
        category: 技能類別名稱
        
    Returns:
        str: "target" (需選目標), "ok" (OK 確認), 或 "none" (直接施放)
    """
    return SKILL_CATEGORIES.get(category, {}).get("cast_type", "target")

def get_skill_image_path(category, skill_name):
    """取得技能圖片的完整路徑
    
    Args:
        category: 技能類別名稱
        skill_name: 技能名稱（不含前綴）
        
    Returns:
        str: 圖片路徑，若找不到則返回 None
    """
    folder = SKILL_CATEGORIES.get(category, {}).get("folder", "")
    if not folder:
        return None
    
    spellskill_dir = ResourcePath("resources/images/spellskill")
    folder_path = os.path.join(spellskill_dir, folder)
    
    if os.path.isdir(folder_path):
        for filename in os.listdir(folder_path):
            if filename.lower().endswith('.png'):
                # 檢查是否匹配技能名稱
                name_part = filename.rsplit('.', 1)[0]
                if '_' in name_part:
                    name_part = name_part.split('_', 1)[1]
                if name_part == skill_name:
                    return os.path.join(folder_path, filename)
    
    return None

# 載入技能列表（程式啟動時執行）
SKILLS_BY_CATEGORY = load_skills_from_folder()

def scan_characters_from_folder():
    """從資料夾掃描角色列表

    掃描 resources/images/character/ 資料夾，
    返回所有角色名稱（不含副檔名）。

    Returns:
        list: [角色名稱, ...]
    """
    character_dir = ResourcePath("resources/images/character")
    characters = []

    if os.path.isdir(character_dir):
        for filename in os.listdir(character_dir):
            if filename.lower().endswith('.png'):
                # 移除副檔名取得角色名稱
                char_name = os.path.splitext(filename)[0]
                characters.append(char_name)
        characters.sort()  # 按名稱排序

    logger.debug(f"[角色載入] 找到 {len(characters)} 個角色: {characters}")
    return characters

# 載入角色列表（程式啟動時執行）
AVAILABLE_CHARACTERS = scan_characters_from_folder()

# 相容性：維持舊常數供現有程式碼使用（之後會移除）
CC_SKILLS = SKILLS_BY_CATEGORY.get("群控", ["KANTIOS"])
SECRET_AOE_SKILLS = SKILLS_BY_CATEGORY.get("秘術", ["SAoLABADIOS", "SAoLAERLIK", "SAoLAFOROS"])
FULL_AOE_SKILLS = SKILLS_BY_CATEGORY.get("全體", ["LAERLIK", "LAMIGAL", "LAZELOS", "LACONES", "LAFOROS", "LAHALITO", "LAFERU"])
ROW_AOE_SKILLS = SKILLS_BY_CATEGORY.get("橫排", ["maerlik", "mahalito", "mamigal", "mazelos", "maferu", "macones", "maforos"])
PHYSICAL_SKILLS = SKILLS_BY_CATEGORY.get("單體", ["unendingdeaths", "動靜斬", "地裂斬", "全力一擊", "tzalik", "居合"])
ALL_AOE_SKILLS = SECRET_AOE_SKILLS + FULL_AOE_SKILLS + ROW_AOE_SKILLS
ALL_SKILLS = CC_SKILLS + SECRET_AOE_SKILLS + FULL_AOE_SKILLS + ROW_AOE_SKILLS + PHYSICAL_SKILLS

# 輔助技能（需要點我方角色）
SUPPORT_SKILLS = SKILLS_BY_CATEGORY.get("輔助", ["霧消", "法系霧消"])

# 隊伍位置座標映射（使用開鎖時的座標，輔助技能點擊我方角色用）
PARTY_POSITIONS = {
    1: [258, 1161],   # 前排左 (whowillopenit=0)
    2: [516, 1161],   # 前排中 (whowillopenit=1)
    3: [774, 1161],   # 前排右 (whowillopenit=2)
    4: [258, 1345],   # 後排左 (whowillopenit=3)
    5: [516, 1345],   # 後排中 (whowillopenit=4)
    6: [774, 1345],   # 後排右 (whowillopenit=5)
}


DUNGEON_TARGETS = BuildQuestReflection()

####################################
CONFIG_VAR_LIST = [
            #var_name,                      type,          config_name,                  default_value
            ["farm_target_text_var",        tk.StringVar,  "_FARMTARGET_TEXT",           list(DUNGEON_TARGETS.keys())[0] if DUNGEON_TARGETS else ""],
            ["farm_target_var",             tk.StringVar,  "_FARMTARGET",                ""],
            ["who_will_open_it_var",        tk.IntVar,     "_WHOWILLOPENIT",             0],
            ["skip_recover_var",            tk.BooleanVar, "_SKIPCOMBATRECOVER",         False],
            ["skip_chest_recover_var",      tk.BooleanVar, "_SKIPCHESTRECOVER",          False],
            ["lowhp_recover_var",           tk.BooleanVar, "_LOWHP_RECOVER",             False],
            # 異常狀態自動恢復
            ["recover_poison_var",          tk.BooleanVar, "_RECOVER_POISON",            False],
            ["recover_venom_var",           tk.BooleanVar, "_RECOVER_VENOM",             False],
            ["recover_stone_var",           tk.BooleanVar, "_RECOVER_STONE",             False],
            ["recover_paralysis_var",       tk.BooleanVar, "_RECOVER_PARALYSIS",         False],
            ["recover_cursed_var",          tk.BooleanVar, "_RECOVER_CURSED",            False],
            ["recover_fear_var",            tk.BooleanVar, "_RECOVER_FEAR",              False],
            ["recover_skilllock_var",       tk.BooleanVar, "_RECOVER_SKILLLOCK",         False],
            # 角色技能施放設定
            ["ae_caster_interval_var", tk.IntVar, "_AE_CASTER_INTERVAL", 0],  # 觸發間隔：0=每場觸發
            # 自動戰鬥模式設定
            ["auto_combat_mode_var",        tk.StringVar,  "_AUTO_COMBAT_MODE",          "2 場後自動"],  # 完全自動/1場後自動/2場後自動/完全手動
            ["dungeon_repeat_limit_var",    tk.IntVar,     "_DUNGEON_REPEAT_LIMIT",      0],             # 連續刷地城次數：0=每次回村
            # 系統設定
            ["active_royalsuite_rest_var",  tk.BooleanVar, "_ACTIVE_ROYALSUITE_REST",    False],
            ["active_triumph_var",          tk.BooleanVar, "_ACTIVE_TRIUMPH",            False],
            ["karma_adjust_var",            tk.StringVar,  "_KARMAADJUST",               "+0"],
            ["emu_path_var",                tk.StringVar,  "_EMUPATH",                   ""],
            ["adb_port_var",                tk.StringVar,  "_ADBPORT",                   5555],
            ["last_version",                tk.StringVar,  "LAST_VERSION",               ""],
            ["latest_version",              tk.StringVar,  "LATEST_VERSION",             None],
            ["active_csc_var",              tk.BooleanVar, "ACTIVE_CSC",                 True],
            ["organize_backpack_enabled_var", tk.BooleanVar, "_ORGANIZE_BACKPACK_ENABLED", False],
            ["organize_backpack_count_var",  tk.IntVar,     "_ORGANIZE_BACKPACK_COUNT",   0],
            ["auto_refill_var",              tk.BooleanVar, "_AUTO_REFILL",               True],  # 自動補給
            ["current_skill_preset_index_var", tk.IntVar,    "_CURRENT_SKILL_PRESET_INDEX", 0],
            ["skill_preset_names_var",       tk.Variable,   "_SKILL_PRESET_NAMES",        ["配置 " + str(i+1) for i in range(10)]],
            # Debug 截圖（測試用）
            ["debug_screenshot_var",         tk.BooleanVar, "_DEBUG_SCREENSHOT",          False],
            ]


class FarmConfig:
    for attr_name, var_type, var_config_name, var_default_value in CONFIG_VAR_LIST:
        locals()[var_config_name] = var_default_value

    # 角色技能配置列表（動態載入）
    # 格式: [{character, skill_first, level_first, skill_after, level_after}, ...]
    _CHARACTER_SKILL_CONFIG = []

    # 技能配置預設列表（10 組）
    _SKILL_PRESETS = []
    _SKILL_PRESET_NAMES = []
    _CURRENT_SKILL_PRESET_INDEX = 0

    def __init__(self):
        #### 面板配置其他
        self._FORCESTOPING = None
        self._FINISHINGCALLBACK = None
        self._MSGQUEUE = None
        #### 底層接口
        self._ADBDEVICE = None

    def get_skill_for_character(self, char_name, battle_num):
        """取得角色的技能配置

        Args:
            char_name: 角色名稱
            battle_num: 第幾戰 (1=首戰, 2+=二戰後)

        Returns:
            tuple: (skill, level) 或 ("attack", "關閉") 若未配置
        """
        # 配置結構: [{character, skill_first, level_first, skill_after, level_after}, ...]
        config_list = self._CHARACTER_SKILL_CONFIG if isinstance(self._CHARACTER_SKILL_CONFIG, list) else []

        skill = ""
        level = "關閉"

        # 遍歷列表查找匹配的角色
        for char_config in config_list:
            if char_config.get("character") == char_name:
                if battle_num == 1:
                    skill = char_config.get("skill_first", "")
                    level = char_config.get("level_first", "關閉")
                    target = char_config.get("target_first")
                else:
                    skill = char_config.get("skill_after", "")
                    level = char_config.get("level_after", "關閉")
                    target = char_config.get("target_after")
                break

        # 未配置時返回普攻
        if not skill:
            skill = "attack"
            level = "關閉"
            target = None

        return skill, level, target

    def __getattr__(self, name):
        # 當訪問不存在的屬性時，拋出AttributeError
        raise AttributeError(f"FarmConfig對象沒有屬性'{name}'")
class MonitorState:
    """即時監控狀態類別，供 GUI 讀取顯示"""
    # 當前狀態
    current_state: str = "Idle"           # Inn/Dungeon/EoT/Quit
    current_dungeon_state: str = ""   # Map/Combat/Chest/Dungeon
    current_target: str = ""          # chest_auto/position/harken/gohome
    target_detail: str = ""           # 目標詳情

    # 時間追蹤
    state_start_time: float = 0       # 狀態開始時間
    soft_timeout_progress: float = 0  # 0-100%
    hard_timeout_progress: float = 0  # 0-100%

    # 卡死偵測
    still_count: int = 0
    still_max: int = 10
    resume_count: int = 0
    resume_max: int = 5
    is_gohome_mode: bool = False
    turn_attempt_count: int = 0

    # 戰鬥資訊
    battle_count: int = 0
    action_count: int = 0
    aoe_triggered: bool = False

    # 統計
    dungeon_count: int = 0
    combat_count: int = 0
    chest_count: int = 0
    death_count: int = 0              # 死亡次數
    karma_adjust: str = ""            # 善惡調整剩餘
    total_time: float = 0
    chest_time_total: float = 0       # 寶箱累計時間
    combat_time_total: float = 0      # 戰鬥累計時間
    adb_retry_count: int = 0          # ADB 重連次數
    crash_counter: int = 0            # 崩潰計數

    # Flag 相似度 (0-100%)
    flag_dungFlag: int = 0
    flag_mapFlag: int = 0
    flag_chestFlag: int = 0
    flag_combatActive: int = 0
    flag_worldMap: int = 0
    flag_chest_auto: int = 0
    flag_auto_text: int = 0
    flag_low_hp: bool = False             # 是否偵測到低血量角色

    # 角色比對
    current_character: str = "未找到"  # 當前比對到的角色名稱
    
    # Flag 更新時間戳
    flag_updates: dict = {}

    # 警告列表
    warnings: list = []

    @classmethod
    def reset(cls):
        """重置所有監控狀態"""
        cls.current_state = "Idle"
        cls.current_dungeon_state = ""
        cls.current_target = ""
        cls.target_detail = ""
        cls.state_start_time = 0
        cls.soft_timeout_progress = 0
        cls.hard_timeout_progress = 0
        cls.still_count = 0
        cls.resume_count = 0
        cls.is_gohome_mode = False
        cls.turn_attempt_count = 0
        cls.battle_count = 0
        cls.action_count = 0
        cls.aoe_triggered = False
        cls.dungeon_count = 0
        cls.combat_count = 0
        cls.chest_count = 0
        cls.death_count = 0
        cls.karma_adjust = ""
        cls.total_time = 0
        cls.adb_retry_count = 0
        cls.crash_counter = 0
        cls.flag_dungFlag = 0
        cls.flag_mapFlag = 0
        cls.flag_chestFlag = 0
        cls.flag_combatActive = 0
        cls.flag_worldMap = 0
        cls.flag_chest_auto = 0
        cls.flag_auto_text = 0
        cls.flag_updates = {}
        cls.current_character = "未找到"
        cls.warnings = []

    @classmethod
    def update_warnings(cls):
        """根據當前狀態更新警告列表"""
        cls.warnings = []
        if cls.is_gohome_mode:
            cls.warnings.append("⚠️ 軟超時觸發，正在撤離")
        if cls.resume_count >= 3:
            cls.warnings.append("⚠️ Resume 多次失敗")
        if cls.still_count >= 8:
            cls.warnings.append("⚠️ 畫面長時間靜止")
        if cls.adb_retry_count > 0:
            cls.warnings.append(f"⚠️ ADB 重連 {cls.adb_retry_count} 次")
        if cls.crash_counter > 3:
            cls.warnings.append(f"🔴 連續崩潰 {cls.crash_counter} 次")

class RuntimeContext:
    #### 統計信息
    _LAPTIME = 0
    _TOTALTIME = 0
    _COUNTERDUNG = 0
    _COUNTERCOMBAT = 0
    _COUNTERCHEST = 0
    _COUNTERADBRETRY = 0      # ADB 重啓次數（閃退/連接失敗）
    _COUNTEREMULATORCRASH = 0 # 模擬器崩潰次數（需完全重啓模擬器）
    _TIME_COMBAT= 0
    _TIME_COMBAT_TOTAL = 0
    _TIME_CHEST = 0
    _TIME_CHEST_TOTAL = 0
    _COUNTERDEATH = 0         # 死亡次數（隊伍全滅/someonedead）
    #### 其他臨時參數
    _MEET_CHEST_OR_COMBAT = False
    _COMBATSPD = False
    _SUICIDE = False # 當有兩個人死亡的時候(multipeopledead), 在戰鬥中嘗試自殺.
    _MAXRETRYLIMIT = 20
    _RECOVERAFTERREZ = False
    _ZOOMWORLDMAP = False
    _CRASHCOUNTER = 0
    _IMPORTANTINFO = ""
    _FIRST_DUNGEON_ENTRY = True  # 第一次進入地城標誌，進入後打開地圖時重置
    _DUNGEON_CONFIRMED = False  # 已確認進入地城（偵測到地城狀態後設為 True）
    _STEPAFTERRESTART = True  # 重啓後左右平移標誌，False=需要執行防轉圈，True=已執行或無需執行
    _COMBAT_ACTION_COUNT = 0  # 每場戰鬥的行動次數（進入 StateCombat +1，戰鬥結束重置）
    _COMBAT_BATTLE_COUNT = 0  # 當前第幾戰 (1=第一戰, 2=第二戰...)
    _AOE_TRIGGERED_THIS_DUNGEON = False  # 本次地城是否已觸發自動戰鬥
    _AE_CASTER_FIRST_ATTACK_DONE = False  # AE 手是否已完成首次普攻
    _HARKEN_FLOOR_TARGET = None  # harken 樓層選擇目標（字符串圖片名），None 表示返回村莊
    _HARKEN_TELEPORT_JUST_COMPLETED = False  # harken 樓層傳送剛剛完成標記
    _MINIMAP_STAIR_FLOOR_TARGET = None  # minimap_stair 目標樓層圖片名稱
    _MINIMAP_STAIR_IN_PROGRESS = False  # minimap_stair 移動中標記
    _RESTART_OPEN_MAP_PENDING = False  # 重啓後待打開地圖標誌，跳過Resume優化
    _RESTART_PENDING_BATTLE_RESET = False  # 重啓後待重置戰鬥計數器標誌
    _MID_DUNGEON_START = False  # 地城內啟動標記，用於跳過黑屏打斷（因為不知道已打幾戰）
    _DUNGEON_REPEAT_COUNT = 0  # 連續刷地城次數計數器，達到設定值後回村
    _IS_FIRST_COMBAT_IN_DUNGEON = True  # 本次地城的首戰標記 (打斷邏輯使用)
    _FORCE_ABNORMAL_RECOVER = False # 強制異常狀態恢復標誌
    _FORCE_LOWHP_RECOVER = False # 強制低血量恢復標誌
    _RESET_BATTLE_COUNT_AFTER_RECOVER = False # 麻痺/封技恢復後重置戰鬥計數器標誌
    _RESTART_SKIP_INTERVAL_THIS_DUNGEON = False  # 重啟後跳過間隔判斷標誌，讓 _AUTO_COMBAT_MODE 正常運作
    _IN_RESTART = False # [新增] 標記是否正在執行重啟流程
    _RESET_TARGETS_PENDING = False # [新增] 跳過回村時標記需要重新初始化目標列表
    
    # === 打王模式相關 ===
    _AUTO_SKILL_PRESET_INDEX = -1  # 打王模式預設索引 (-1=正常模式, 0-9=打王模式)
    _BOSS_CHARACTER_ACTION_COUNT = {}  # 打王模式中每個角色的行動次數 {角色名: 行動次數}
class FarmQuest:
    _DUNGWAITTIMEOUT = 0
    _TARGETINFOLIST = None
    _EOT = None
    _preEOTcheck = None
    _SPECIALDIALOGOPTION = None
    _SPECIALFORCESTOPINGSYMBOL = None
    _TYPE = None
    def __getattr__(self, name):
        # 當訪問不存在的屬性時，拋出AttributeError
        raise AttributeError(f"FarmQuest對象沒有屬性'{name}'")
class TargetInfo:
    def __init__(self, target: str, swipeDir: list = None, roi=None, extra=None, wait=1):
        # 安全處理：如果第一個參數是 list，自動展開
        if isinstance(target, list) and len(target) >= 1:
            row = target
            target = row[0]
            swipeDir = row[1] if len(row) > 1 else None
            roi = row[2] if len(row) > 2 else None
            extra = row[3] if len(row) > 3 else None
            wait = row[4] if len(row) > 4 else 1
        
        self.target = target
        self.swipeDir = swipeDir
        # 注意 roi校驗需要target的值. 請嚴格保證roi在最後.
        self.roi = roi
        self.extra = extra  # 用於打王預設索引 (swipe) 或樓層圖片 (harken)
        self.wait = wait
    @property
    def swipeDir(self):
        return self._swipeDir

    @swipeDir.setter
    def swipeDir(self, inputValue):
        value = None
        match inputValue:
            case None:
                value = [None,
                        [100,100,700,1200],
                        [400,1200,400,100],
                        [700,800,100,800],
                        [400,100,400,1200],
                        [100,800,700,800],
                        ]
            case "左上":
                value = [[100,250,700,1200]]
            case "右上":
                value = [[700,250,100,1200]]
            case "右下":
                value = [[700,1200,100,250]]
            case "左下":
                value = [[100,1200,700,250]]
            case _:
                value = inputValue
        
        self._swipeDir = value

    @property
    def roi(self):
        return self._roi

    @roi.setter
    def roi(self, value):
        # 1. 處理預設與特殊值
        if value == 'default':
            value = [[0,0,900,1600],[0,0,900,208],[0,1265,900,335],[0,636,137,222],[763,636,137,222], [336,208,228,77],[336,1168,228,97]]
        elif self.target == 'chest' and value is None:
            value = [[0,0,900,1600]]

        # 2. 自動偵測坐標格式並轉換 ([x1, y1, x2, y2] -> [x, y, w, h])
        # 如果起始點加上第三、四個參數超過了 900x1600 的邊界，則判定為絕對座標點
        normalized_value = []
        if isinstance(value, list):
            for rect in value:
                if isinstance(rect, list) and len(rect) == 4:
                    x, y, w, h = rect
                    # 啟發式判定：如果 w > x 且 h > y，且之和超出標準螢幕長寬，則必為座標點
                    if (x + w > 900 or y + h > 1600) and (w >= x and h >= y):
                        rect = [x, y, w - x, h - y]
                    normalized_value.append(rect)
                else:
                    normalized_value.append(rect)
            value = normalized_value

        # 3. 針對寶箱目標追加預設屏蔽區
        if self.target == 'chest':
            value += [[0,0,900,208],[0,1265,900,335],[0,636,137,222],[763,636,137,222], [336,208,228,77],[336,1168,228,97]]

        self._roi = value

##################################################################
def KillAdb(setting : FarmConfig):
    adb_path = GetADBPath(setting)
    try:
        logger.info(f"正在檢查並關閉adb...")
        # Windows 系統使用 taskkill 命令
        if os.name == 'nt':
            subprocess.run(
                f"taskkill /f /im adb.exe", 
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False  # 不檢查命令是否成功（進程可能不存在）
            )
            # NOTE: 使用分段 sleep 確保能響應停止信號
            for _ in range(2):
                if hasattr(setting, '_FORCESTOPING') and setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                    return
                time.sleep(0.5)
            subprocess.run(
                f"taskkill /f /im HD-Adb.exe", 
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False  # 不檢查命令是否成功（進程可能不存在）
            )
        else:
            subprocess.run(
                f"pkill -f {adb_path}", 
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False
            )
        logger.info(f"已嘗試終止adb")
    except Exception as e:
        logger.error(f"終止模擬器進程時出錯: {str(e)}")
    
def KillEmulator(setting : FarmConfig):
    emulator_name = os.path.basename(setting._EMUPATH)
    emulator_SVC = "MuMuVMMSVC.exe"
    try:
        logger.info(f"正在檢查並關閉已運行的模擬器實例{emulator_name}...")
        # Windows 系統使用 taskkill 命令
        if os.name == 'nt':
            subprocess.run(
                f"taskkill /f /im {emulator_name}", 
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False  # 不檢查命令是否成功（進程可能不存在）
            )
            # NOTE: 使用分段 sleep 確保能響應停止信號
            for _ in range(2):
                if hasattr(setting, '_FORCESTOPING') and setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                    return
                time.sleep(0.5)
            subprocess.run(
                f"taskkill /f /im {emulator_SVC}", 
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False  # 不檢查命令是否成功（進程可能不存在）
            )
            # NOTE: 使用分段 sleep 確保能響應停止信號
            for _ in range(2):
                if hasattr(setting, '_FORCESTOPING') and setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                    return
                time.sleep(0.5)

        # Unix/Linux 系統使用 pkill 命令
        else:
            subprocess.run(
                f"pkill -f {emulator_name}", 
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False
            )
            subprocess.run(
                f"pkill -f {emulator_headless}", 
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False
            )
        logger.info(f"已嘗試終止模擬器進程: {emulator_name}")
    except Exception as e:
        logger.error(f"終止模擬器進程時出錯: {str(e)}")
def StartEmulator(setting):
    hd_player_path = setting._EMUPATH
    if not os.path.exists(hd_player_path):
        logger.error(f"模擬器啓動程序不存在: {hd_player_path}")
        return False

    try:
        logger.info(f"啓動模擬器: {hd_player_path}")
        subprocess.Popen(
            hd_player_path, 
            shell=True,
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL,
            cwd=os.path.dirname(hd_player_path))
    except Exception as e:
        logger.error(f"啓動模擬器失敗: {str(e)}")
        return False
    
    logger.info("等待模擬器啓動...")
    # NOTE: 使用分段 sleep 確保能響應停止信號（15秒 = 30 x 0.5秒）
    for _ in range(30):
        if hasattr(setting, '_FORCESTOPING') and setting._FORCESTOPING and setting._FORCESTOPING.is_set():
            logger.info("模擬器啓動等待中收到停止信號")
            return False
        time.sleep(0.5)
def GetADBPath(setting):
    adb_path = setting._EMUPATH
    adb_path = adb_path.replace("HD-Player.exe", "HD-Adb.exe") # 藍疊
    adb_path = adb_path.replace("MuMuPlayer.exe", "adb.exe") # mumu
    adb_path = adb_path.replace("MuMuNxDevice.exe", "adb.exe") # mumu
    if not os.path.exists(adb_path):
        logger.error(f"adb程序序不存在: {adb_path}")
        return None
    
    return adb_path

def CMDLine(cmd):
    logger.debug(f"cmd line: {cmd}")
    return subprocess.run(cmd,shell=True, capture_output=True, text=True, timeout=10,encoding='utf-8')

def CheckRestartConnectADB(setting: FarmConfig):
    MAXRETRIES = 20

    adb_path = GetADBPath(setting)

    for attempt in range(MAXRETRIES):
        # 檢查停止信號
        if hasattr(setting, '_FORCESTOPING') and setting._FORCESTOPING and setting._FORCESTOPING.is_set():
            logger.info("CheckRestartConnectADB 檢測到停止信號，中斷 ADB 連接")
            return None

        logger.info(f"-----------------------\n開始嘗試連接adb. 次數:{attempt + 1}/{MAXRETRIES}...")

        if attempt == 3:
            logger.info(f"失敗次數過多, 嘗試關閉adb.")
            KillAdb(setting)

            # 我們不起手就關, 但是如果2次鏈接還是嘗試失敗, 那就觸發一次強制重啓.

        try:
            logger.info("檢查adb服務...")
            result = CMDLine(f"\"{adb_path}\" devices")
            logger.debug(f"adb鏈接返回(輸出信息):{result.stdout}")
            logger.debug(f"adb鏈接返回(錯誤信息):{result.stderr}")

            if ("daemon not running" in result.stderr) or ("offline" in result.stdout):
                logger.info("adb服務未啓動!\n啓動adb服務...")
                CMDLine(f"\"{adb_path}\" kill-server")
                CMDLine(f"\"{adb_path}\" start-server")

                # 檢查停止信號的 sleep
                for _ in range(4):  # 2秒拆成4次0.5秒
                    if hasattr(setting, '_FORCESTOPING') and setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                        logger.info("啟動 ADB 服務時檢測到停止信號")
                        return None
                    time.sleep(0.5)

            logger.debug(f"嘗試連接到adb...")
            result = CMDLine(f"\"{adb_path}\" connect 127.0.0.1:{setting._ADBPORT}")
            logger.debug(f"adb鏈接返回(輸出信息):{result.stdout}")
            logger.debug(f"adb鏈接返回(錯誤信息):{result.stderr}")

            if result.returncode == 0 and ("connected" in result.stdout or "already" in result.stdout):
                logger.info("成功連接到模擬器")
                break
            if ("refused" in result.stderr) or ("cannot connect" in result.stdout):
                logger.info("模擬器未運行，嘗試啓動...")
                StartEmulator(setting)
                logger.info("模擬器(應該)啓動完畢.")
                logger.info("嘗試連接到模擬器...")
                result = CMDLine(f"\"{adb_path}\" connect 127.0.0.1:{setting._ADBPORT}")
                if result.returncode == 0 and ("connected" in result.stdout or "already" in result.stdout):
                    logger.info("成功連接到模擬器")
                    break
                logger.info("無法連接. 檢查adb端口.")

            logger.info(f"連接失敗: {result.stderr.strip()}")

            # 檢查停止信號的 sleep（2秒拆成4次）
            for _ in range(4):
                if hasattr(setting, '_FORCESTOPING') and setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                    logger.info("重試等待時檢測到停止信號")
                    return None
                time.sleep(0.5)

            KillEmulator(setting)
            KillAdb(setting)

            # 再次檢查停止信號的 sleep（2秒拆成4次）
            for _ in range(4):
                if hasattr(setting, '_FORCESTOPING') and setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                    logger.info("清理後等待時檢測到停止信號")
                    return None
                time.sleep(0.5)
        except Exception as e:
            logger.error(f"重啓ADB服務時出錯: {e}")

            # 檢查停止信號的 sleep（2秒拆成4次）
            for _ in range(4):
                if hasattr(setting, '_FORCESTOPING') and setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                    logger.info("異常處理時檢測到停止信號")
                    return None
                time.sleep(0.5)

            KillEmulator(setting)
            KillAdb(setting)

            # 再次檢查停止信號的 sleep（2秒拆成4次）
            for _ in range(4):
                if hasattr(setting, '_FORCESTOPING') and setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                    logger.info("異常清理後等待時檢測到停止信號")
                    return None
                time.sleep(0.5)
            return None
    else:
        logger.info("達到最大重試次數，連接失敗")
        return None

    try:
        client = AdbClient(host="127.0.0.1", port=5037)
        devices = client.devices()

        # 查找匹配的設備
        target_device = f"127.0.0.1:{setting._ADBPORT}"
        for device in devices:
            if device.serial == target_device:
                logger.info(f"成功獲取設備對象: {device.serial}")
                return device
    except Exception as e:
        logger.error(f"獲取ADB設備時出錯: {e}")

    return None
##################################################################
def CutRoI(screenshot,roi):
    if roi is None:
        return screenshot

    img_height, img_width = screenshot.shape[:2]
    roi_copy = roi.copy()
    roi1_rect = roi_copy.pop(0)  # 第一個矩形 (x, y, width, height)

    x1, y1, w1, h1 = roi1_rect

    roi1_y_start_clipped = max(0, y1)
    roi1_y_end_clipped = min(img_height, y1 + h1)
    roi1_x_start_clipped = max(0, x1)
    roi1_x_end_clipped = min(img_width, x1 + w1)

    pixels_not_in_roi1_mask = np.ones((img_height, img_width), dtype=bool)
    if roi1_x_start_clipped < roi1_x_end_clipped and roi1_y_start_clipped < roi1_y_end_clipped:
        pixels_not_in_roi1_mask[roi1_y_start_clipped:roi1_y_end_clipped, roi1_x_start_clipped:roi1_x_end_clipped] = False

    screenshot[pixels_not_in_roi1_mask] = 255

    if (roi is not []):
        for roi2_rect in roi_copy:
            x2, y2, w2, h2 = roi2_rect

            roi2_y_start_clipped = max(0, y2)
            roi2_y_end_clipped = min(img_height, y2 + h2)
            roi2_x_start_clipped = max(0, x2)
            roi2_x_end_clipped = min(img_width, x2 + w2)

            if roi2_x_start_clipped < roi2_x_end_clipped and roi2_y_start_clipped < roi2_y_end_clipped:
                pixels_in_roi2_mask_for_current_op = np.zeros((img_height, img_width), dtype=bool)
                pixels_in_roi2_mask_for_current_op[roi2_y_start_clipped:roi2_y_end_clipped, roi2_x_start_clipped:roi2_x_end_clipped] = True

                # 將位於 roi2 中的像素設置爲0
                # (如果這些像素之前因爲不在roi1中已經被設爲0，則此操作無額外效果)
                screenshot[pixels_in_roi2_mask_for_current_op] = 0

    # cv2.imwrite(f'CutRoI_{time.time()}.png', screenshot)
    return screenshot
##################################################################

def Factory():
    toaster = ToastNotifier()
    setting =  None
    quest = None
    runtimeContext = None
    
    # [新增] 模板緩存字典，避免重複從磁碟讀取圖片
    _template_cache = {}
    
    # ==================== 停止信號異常機制 ====================
    class StopSignalException(Exception):
        """用戶請求停止時拋出的異常，會自動向上冒泡到主循環"""
        pass

    def check_stop_signal():
        """檢查停止信號，若已設置則拋出 StopSignalException"""
        if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
            raise StopSignalException()

    def stoppable(func):
        """裝飾器：每次進入函數時自動檢查停止信號
        
        使用方式：
            @stoppable
            def IdentifyState():
                ...
        """
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            check_stop_signal()
            return func(*args, **kwargs)
        return wrapper
    # ==================== 停止信號異常機制 END ====================
    
    def _get_cached_template(template_name):
        """從緩存獲取模板，如果不存在則從磁碟讀取並緩存"""
        if template_name not in _template_cache:
            template = LoadTemplateImage(template_name)
            _template_cache[template_name] = template
            if template is not None:
                logger.trace(f"[TemplateCache] 緩存模板: {template_name}")
        return _template_cache.get(template_name)
    
    def LoadQuest(farmtarget):
        # 構建文件路徑
        jsondict = LoadJson(ResourcePath(QUEST_FILE))
        if setting._FARMTARGET in jsondict:
            data = jsondict[setting._FARMTARGET]
        else:
            logger.error("任務列表已更新.請重新手動選擇地下城任務.")
            return
        
        
        # 創建 Quest 實例並填充屬性
        quest = FarmQuest()
        for key, value in data.items():
            if key == '_TARGETINFOLIST':
                setattr(quest, key, [TargetInfo(*args) for args in value])
            elif hasattr(FarmQuest, key):
                setattr(quest, key, value)
            elif key in ["type","questName","questId",'extraConfig']:
                pass
            else:
                logger.info(f"'{key}'並不存在於FarmQuest中.")
        
        if 'extraConfig' in data and isinstance(data['extraConfig'], dict):
            for key, value in data['extraConfig'].items():
                if hasattr(setting, key):
                    setattr(setting, key, value)
                else:
                    logger.info(f"Warning: Config has no attribute '{key}' to override")
        return quest
    ##################################################################
    def ResetADBDevice():
        nonlocal setting # 修改device
        MonitorState.current_state = "Connecting"
        if device := CheckRestartConnectADB(setting):
            setting._ADBDEVICE = device
            logger.info("ADB服務成功啓動，設備已連接.")

            # ADB 重連後，嘗試重啟 pyscrcpy 串流
            stream = get_scrcpy_stream()
            if stream:
                if stream.restart():
                    logger.info("pyscrcpy 串流重啟成功")
                else:
                    logger.warning("pyscrcpy 串流重啟失敗，將使用傳統 ADB 截圖")
            
            # NOTE: ADB 重連後，檢查並啟動遊戲進程
            # 修復：模擬器可能因崩潰重啟，遊戲進程需要重新啟動
            package_name = "jp.co.drecom.wizardry.daphne"
            try:
                result = setting._ADBDEVICE.shell(f"pidof {package_name}", timeout=3)
                if not result.strip():
                    logger.info("遊戲未在前台運行，正在啟動遊戲...")
                    try:
                        mainAct = setting._ADBDEVICE.shell(f"cmd package resolve-activity --brief {package_name}").strip().split('\n')[-1]
                    except Exception:
                        mainAct = f"{package_name}/.MainActivity"
                    setting._ADBDEVICE.shell(f"am start -n {mainAct}")
                    logger.info("巫術, 啓動!")
                    time.sleep(5)  # 等待遊戲啟動
            except Exception as e:
                logger.warning(f"檢查/啟動遊戲失敗: {e}")
    def DeviceShell(cmdStr):
        logger.trace(f"[DeviceShell] {cmdStr}")
        MAX_ADB_RETRIES = 5  # 最大重試次數
        adb_retry_count = 0

        while True:
            if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                return ""
            exception = None
            result = None
            completed = Event()

            def adb_command_thread():
                nonlocal exception, result
                try:
                    result = setting._ADBDEVICE.shell(cmdStr, timeout=5)
                except Exception as e:
                    exception = e
                finally:
                    completed.set()

            thread = Thread(target=adb_command_thread)
            thread.daemon = True
            thread.start()

            try:
                if not completed.wait(timeout=7):
                    # 線程超時未完成
                    logger.warning(f"ADB命令執行超時: {cmdStr}")
                    raise TimeoutError(f"ADB命令在{7}秒內未完成")

                if exception is not None:
                    raise exception

                return result
            except (TimeoutError, RuntimeError, ConnectionResetError, cv2.error) as e:
                adb_retry_count += 1
                logger.warning(f"ADB操作失敗 ({type(e).__name__}): {e} (重試 {adb_retry_count}/{MAX_ADB_RETRIES})")

                if adb_retry_count >= MAX_ADB_RETRIES:
                    logger.error(f"ADB 連續失敗 {MAX_ADB_RETRIES} 次，放棄重試")
                    raise RuntimeError(f"ADB 連續失敗 {MAX_ADB_RETRIES} 次: {cmdStr}")

                logger.info("嘗試重啓ADB服務...")
                ResetADBDevice()
                time.sleep(1)

                continue
            except Exception as e:
                # 非預期異常直接拋出
                logger.error(f"非預期的ADB異常: {type(e).__name__}: {e}")
                raise
    
    def Sleep(t=1):
        """可響應停止信號和遊戲崩潰的 sleep 函數"""
        # 將長時間 sleep 分割成小段，每段檢查停止標誌
        interval = 0.1  # 每 0.1 秒檢查一次，確保快速響應停止信號
        elapsed = 0
        while elapsed < t:
            if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                logger.debug(f"Sleep 中檢測到停止信號，提前退出")
                return
            # 檢查遊戲進程是否崩潰（但如果正在停止或正在重啟則忽略）
            if hasattr(setting, '_GAME_CRASHED') and setting._GAME_CRASHED.is_set():
                if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                    setting._GAME_CRASHED.clear()  # 停止時清除崩潰標記
                    return
                
                # 如果正處於重啟流程中，忽略崩潰標記，避免無限遞迴
                if getattr(runtimeContext, '_IN_RESTART', False):
                    logger.debug("[Sleep] 重啟流程中，忽略舊的崩潰標記")
                    setting._GAME_CRASHED.clear()
                    elapsed += interval # 繼續 sleep
                    time.sleep(min(interval, t - (elapsed-interval)))
                    continue

                logger.warning("[Sleep] 檢測到遊戲崩潰，觸發重啟")
                setting._GAME_CRASHED.clear()
                restartGame(skipScreenShot=True)
                return  # restartGame 會拋出 RestartSignal
            sleep_time = min(interval, t - elapsed)
            time.sleep(sleep_time)
            elapsed += sleep_time
            
            # 更新監控狀態（每次 sleep 循環都更新）
            try:
                MonitorState.dungeon_count = runtimeContext._COUNTERDUNG
                MonitorState.combat_count = runtimeContext._COUNTERCOMBAT
                MonitorState.chest_count = runtimeContext._COUNTERCHEST
                
                # 計算即時運行時間：累計時間 + 當前這輪的時間
                if runtimeContext._LAPTIME > 0:
                    current_lap = time.time() - runtimeContext._LAPTIME
                    MonitorState.total_time = runtimeContext._TOTALTIME + current_lap
                else:
                    MonitorState.total_time = runtimeContext._TOTALTIME
                
                # 寶箱/戰鬥累計時間
                MonitorState.chest_time_total = runtimeContext._TIME_CHEST_TOTAL
                MonitorState.combat_time_total = runtimeContext._TIME_COMBAT_TOTAL
                
                MonitorState.adb_retry_count = runtimeContext._COUNTERADBRETRY
                MonitorState.crash_counter = runtimeContext._CRASHCOUNTER
                MonitorState.battle_count = runtimeContext._COMBAT_BATTLE_COUNT
                MonitorState.action_count = runtimeContext._COMBAT_ACTION_COUNT
                MonitorState.aoe_triggered = runtimeContext._AOE_TRIGGERED_THIS_DUNGEON
                MonitorState.death_count = runtimeContext._COUNTERDEATH
                MonitorState.update_warnings()
            except:
                pass  # 忽略更新錯誤

    _adb_mode_logged = False  # 追蹤是否已輸出 ADB 模式日誌

    def ScreenShot():
        """截圖函數：優先使用 pyscrcpy 串流，失敗時退回 ADB 截圖"""
        nonlocal _adb_mode_logged

        # 檢查停止信號
        if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
            logger.info("ScreenShot 檢測到停止信號，停止截圖")
            raise RuntimeError("截圖已停止")
        
        final_img = None
        
        # 嘗試使用 pyscrcpy 串流（極快：~1ms）
        stream = get_scrcpy_stream()
        if stream:
            # 如果串流存在但不可用，嘗試重連（放寬條件：只要不可用就嘗試重連）
            if not stream.is_available():
                logger.info("串流不可用，嘗試重新連接...")
                stream.restart()

            if stream.is_available():
                frame = stream.get_frame()
                if frame is not None:
                    h, w = frame.shape[:2]

                    # 檢查是否接近預期尺寸 (允許 ±10 像素差異)
                    if abs(h - 1600) <= 10 and abs(w - 900) <= 10:
                        # 如果尺寸完全正確，直接返回
                        if h == 1600 and w == 900:
                            # 首次使用串流或從 ADB 切換回來時輸出日誌
                            if stream.frame_count == 1 or _adb_mode_logged:
                                logger.info("[截圖模式] 使用 pyscrcpy 串流 (~1ms)")
                                _adb_mode_logged = False  # 重置 ADB 模式標誌
                            final_img = frame
                        else:
                            # 否則用補黑邊方式調整
                            pad_bottom = max(0, 1600 - h)
                            pad_right = max(0, 900 - w)
                            if pad_bottom > 0 or pad_right > 0:
                                frame = cv2.copyMakeBorder(frame, 0, pad_bottom, 0, pad_right, cv2.BORDER_CONSTANT, value=[0,0,0])
                            final_img = frame[:1600, :900]
                    elif abs(h - 900) <= 10 and abs(w - 1600) <= 10:
                        # 橫屏，旋轉後處理
                        frame = cv2.transpose(frame)
                        h, w = frame.shape[:2]
                        if h == 1600 and w == 900:
                            final_img = frame
                        else:
                            pad_bottom = max(0, 1600 - h)
                            pad_right = max(0, 900 - w)
                            if pad_bottom > 0 or pad_right > 0:
                                frame = cv2.copyMakeBorder(frame, 0, pad_bottom, 0, pad_right, cv2.BORDER_CONSTANT, value=[0,0,0])
                            final_img = frame[:1600, :900]
                    else:
                        logger.warning(f"串流幀尺寸異常: {frame.shape}，使用 ADB 截圖")
        
        # 退回 ADB 截圖（較慢：~150-570ms）
        if final_img is None:
            final_img = _ScreenShot_ADB()

        return final_img
    
    def _ScreenShot_ADB():
        """使用 ADB 截圖（原始方式）"""
        nonlocal _adb_mode_logged
        max_retries = 5
        retry_count = 0

        while retry_count < max_retries:
            # 檢查停止信號
            if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                logger.info("ScreenShot 檢測到停止信號，停止截圖")
                raise RuntimeError("截圖已停止")

            try:
                logger.trace(f'[ScreenShot] 開始截圖 (嘗試 {retry_count + 1}/{max_retries})')

                # 關鍵點：ADB screencap 調用，使用超時機制防止無限阻塞
                logger.trace('[ScreenShot] 調用 ADB screencap...')
                screenshot = None
                exception = None
                completed = Event()

                def screencap_thread():
                    nonlocal exception, screenshot
                    try:
                        screenshot = setting._ADBDEVICE.screencap()
                    except Exception as e:
                        exception = e
                    finally:
                        completed.set()

                thread = Thread(target=screencap_thread, daemon=True)
                thread.start()

                # 等待最多 10 秒
                if not completed.wait(timeout=10):
                    logger.error('ADB screencap 超時（10秒），可能連接有問題')
                    raise RuntimeError("screencap 超時")

                if exception is not None:
                    raise exception

                if screenshot is None:
                    raise RuntimeError("screencap 返回 None")

                logger.trace(f'[ScreenShot] ADB 完成，{len(screenshot)} bytes')

                screenshot_np = np.frombuffer(screenshot, dtype=np.uint8)
                logger.trace(f'[ScreenShot] numpy 陣列大小: {screenshot_np.size}')

                if screenshot_np.size == 0:
                    logger.error("截圖數據爲空！")
                    raise RuntimeError("截圖數據爲空")

                logger.trace('[ScreenShot] 解碼圖像...')
                image = cv2.imdecode(screenshot_np, cv2.IMREAD_COLOR)

                if image is None:
                    logger.error("OpenCV解碼失敗：圖像數據損壞")
                    raise RuntimeError("圖像解碼失敗")

                logger.trace(f'[ScreenShot] 解碼完成，尺寸: {image.shape}')

                if image.shape != (1600, 900, 3):  # OpenCV格式爲(高, 寬, 通道)
                    if image.shape == (900, 1600, 3):
                        logger.error(f"截圖尺寸錯誤: 當前{image.shape}, 爲橫屏.")
                        image = cv2.transpose(image)
                        restartGame(skipScreenShot = True) # 這裏直接重啓, 會被外部接收到重啓的exception
                    else:
                        logger.error(f"截圖尺寸錯誤: 期望(1600,900,3), 實際{image.shape}.")
                        raise RuntimeError("截圖尺寸異常")

                #cv2.imwrite('screen.png', image)
                logger.trace('[ScreenShot] 成功')
                # 首次使用 ADB 截圖時輸出日誌
                if not _adb_mode_logged:
                    logger.info("[截圖模式] 使用 ADB 截圖 (~150-570ms)")
                    _adb_mode_logged = True
                return image
            except RestartSignal:
                # RestartSignal 不應被截圖捕獲，直接拋出讓外層處理
                raise
            except Exception as e:
                retry_count += 1
                logger.warning(f"截圖失敗: {e}")
                if isinstance(e, (AttributeError,RuntimeError, ConnectionResetError, cv2.error)):
                    if retry_count < max_retries:
                        logger.info(f"adb重啓中... (重試 {retry_count}/{max_retries})")
                        runtimeContext._COUNTERADBRETRY += 1
                        ResetADBDevice()
                        logger.info("ADB 重置完成，準備重試")
                    else:
                        logger.error(f"截圖失敗，已達到最大重試次數 ({max_retries})")
                        raise RuntimeError(f"截圖失敗: {e}")
                else:
                    logger.error(f"截圖遇到未預期的錯誤: {type(e).__name__}: {e}")
                    raise
    # 多模板映射：某些目標需要嘗試多個模板，選擇匹配度最高的
    # 使用函數動態獲取模板列表，支持自動掃描資料夾
    def get_multi_templates(target_name):
        """獲取目標的所有可用模板，支持動態掃描 harken, harken2, harken3... 等"""
        import glob
        import re
        
        # 對於 harken，動態掃描所有 harken 或 harken+數字 的檔案
        if target_name == 'harken':
            harken_path = ResourcePath(os.path.join(IMAGE_FOLDER, 'harken*.png'))
            harken_files = glob.glob(harken_path)
            if harken_files:
                templates = []
                # 只匹配 harken.png 或 harken+數字.png（如 harken2.png, harken3.png）
                pattern = re.compile(r'^harken\d*$')
                for f in harken_files:
                    name = os.path.splitext(os.path.basename(f))[0]
                    if pattern.match(name):
                        templates.append(name)
                if templates:
                    return templates
        
        # 對於 spellskill 路徑，掃描對應資料夾的所有技能圖片
        if target_name.startswith('spellskill/'):
            parts = target_name.split('/')
            if len(parts) == 2:  # 例如: spellskill/單體 (僅當只指定類別時才掃描整個資料夾)
                category_folder = parts[1]  # 取得類別資料夾名稱
                skill_folder_path = ResourcePath(os.path.join(IMAGE_FOLDER, 'spellskill', category_folder))
                
                if os.path.isdir(skill_folder_path):
                    templates = []
                    # 掃描資料夾內所有 .png 檔案
                    for filename in sorted(os.listdir(skill_folder_path)):
                        if filename.lower().endswith('.png'):
                            # 構建相對路徑: spellskill/類別/檔名(不含.png)
                            name_without_ext = filename.rsplit('.', 1)[0]
                            template_path = f'spellskill/{category_folder}/{name_without_ext}'
                            templates.append(template_path)
                    
                    if templates:
                        logger.debug(f"[多模板] 找到 {len(templates)} 個技能模板於 {category_folder} 資料夾")
                        return templates
        
        # 預設只返回原始目標
        return [target_name]

    # [新增] 本地緩存包裝函數，確保腳本能正確調用 utils 的緩存邏輯
    def _get_cached_template(shortPathOfTarget):
        return LoadTemplateImage(shortPathOfTarget)

    def IsScreenBlack(screen, threshold=15):
        """檢測螢幕是否全黑（或接近全黑）

        用於偵測戰鬥過場的黑屏，以便提前打斷自動戰鬥。

        Args:
            screen: 截圖圖片 (OpenCV BGR 格式)
            threshold: 平均亮度閾值，低於此值視為黑屏 (預設 15)

        Returns:
            bool: 是否為黑屏
        """
        mean_brightness = np.mean(screen)
        is_black = mean_brightness < threshold
        return is_black

    def GetMatchValue(screenImage, shortPathOfTarget, roi=None):
        """獲取模板匹配的相似度值（0-100%）
        
        用於監控面板即時顯示 Flag 匹配度
        """
        templates_to_try = get_multi_templates(shortPathOfTarget)
        best_val = 0
        
        for template_name in templates_to_try:
            template = _get_cached_template(template_name)
            if template is None:
                continue
            
            screenshot = screenImage.copy()
            search_area = CutRoI(screenshot, roi)
            try:
                result = cv2.matchTemplate(search_area, template, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(result)
                if max_val > best_val:
                    best_val = max_val
            except:
                continue
        
        return int(best_val * 100)

    def CheckLowHP(screenImage):
        """檢查是否有角色處於低血量狀態 (紅色 10%~20%)
        
        ROI 座標 (6個角色):
        Row 1: [(130,1300),(190,1330)], [(420,1300),(480,1330)], [(700,1300),(760,1330)]
        Row 2: [(130,1485),(190,1505)], [(420,1485),(480,1505)], [(700,1485),(760,1505)]
        
        Returns:
            bool: True if any character has low HP (red 10%~20%)
        """
        rois = [
            (130, 1300, 60, 30),  # 角色0: x, y, w, h
            (420, 1300, 60, 30),  # 角色1
            (700, 1300, 60, 30),  # 角色2
            (130, 1485, 60, 20),  # 角色3
            (420, 1485, 60, 20),  # 角色4
            (700, 1485, 60, 20),  # 角色5
        ]
        
        for (x, y, w, h) in rois:
            # 確保 ROI 在圖片範圍內
            if y + h > screenImage.shape[0] or x + w > screenImage.shape[1]:
                continue
                
            roi = screenImage[y:y+h, x:x+w]
            hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
            
            # 紅色偵測 (HSV 範圍)
            red_lower1 = np.array([0, 100, 100])
            red_upper1 = np.array([10, 255, 255])
            red_lower2 = np.array([160, 100, 100])
            red_upper2 = np.array([180, 255, 255])
            
            red_mask1 = cv2.inRange(hsv, red_lower1, red_upper1)
            red_mask2 = cv2.inRange(hsv, red_lower2, red_upper2)
            red_mask = cv2.bitwise_or(red_mask1, red_mask2)
            
            total = roi.shape[0] * roi.shape[1]
            red_pct = (cv2.countNonZero(red_mask) / total) * 100
            
            if 10 <= red_pct <= 20:
                logger.debug(f"[血量偵測] 偵測到低血量，紅色比例: {red_pct:.1f}%")
                return True
        
        return False


    def CheckAbnormalStatus(screenImage, setting):
        """檢查是否偵測到需要恢復的異常狀態
        
        根據使用者設定的開關，檢測 6 個角色 ROI 區域。
        偵測邏輯包含顏色 (HSV) 與垂直梯度過濾，確保高準確率。
        
        Returns:
            tuple: (detected: bool, status_types: list)
                - detected: 是否偵測到任何異常狀態
                - status_types: 偵測到的狀態類型列表 (e.g., ['麻痺', '封技'])
        """
        # 如果所有開關都關閉，提早返回
        if not (setting._RECOVER_POISON or setting._RECOVER_VENOM or 
                setting._RECOVER_STONE or setting._RECOVER_PARALYSIS or 
                setting._RECOVER_CURSED or setting._RECOVER_FEAR or
                setting._RECOVER_SKILLLOCK):
            return (False, [])

        # ROI 定義：更新為寬域偵測 (x, y, w, h)
        rois = [
            (120, 1210, 250, 80), (380, 1210, 250, 80), (640, 1210, 250, 80),
            (120, 1390, 250, 80), (380, 1390, 250, 80), (640, 1390, 250, 80)
        ]
        
        # 狀態定義：(設定開關, 模板名稱, 偵測類型, 顯示名稱)
        # 類型: 0=普通, 1=劇毒, 2=中毒, 3=石化, 4=恐懼, 5=封技
        check_list = []
        if setting._RECOVER_POISON:    check_list.append((1, "Poison_icon", 2, "中毒"))
        if setting._RECOVER_VENOM:     check_list.append((1, "poisonous_icon", 1, "劇毒"))
        if setting._RECOVER_STONE:     check_list.append((1, "stone_icon", 3, "石化"))
        if setting._RECOVER_PARALYSIS: check_list.append((1, "paralysis_icon", 0, "麻痺"))
        if setting._RECOVER_CURSED:    check_list.append((1, "cursed_icon", 0, "詛咒"))
        if setting._RECOVER_FEAR:      check_list.append((1, "fear_icon", 4, "寶箱恐懼"))
        if setting._RECOVER_SKILLLOCK: check_list.append((1, "skilllock_icon", 5, "封技"))

        detected_types = []  # 記錄偵測到的狀態類型
        
        for idx, (x, y, w, h) in enumerate(rois):
            # 確保 ROI 合法
            if y+h > screenImage.shape[0] or x+w > screenImage.shape[1]: continue
            roi_img = screenImage[y:y+h, x:x+w]
            
            for _, tmpl_name, check_type, display_name in check_list:
                # 載入模板 (嘗試從 detect 資料夾載入)
                template = LoadTemplateImage(f"detect/{tmpl_name}")
                if template is None: continue

                try:
                    res = cv2.matchTemplate(roi_img, template, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, max_loc = cv2.minMaxLoc(res)
                    
                    if max_val >= 0.75:
                        # 基礎匹配成功，進入進階驗證
                        
                        # 取得匹配區域
                        top_left = max_loc
                        h_t, w_t = template.shape[:2]
                        matched_area = roi_img[top_left[1]:top_left[1]+h_t, top_left[0]:top_left[0]+w_t]
                        
                        is_valid = False
                        
                        if check_type == 0: # 普通 (麻痺/詛咒)
                            is_valid = True
                            
                        elif check_type == 1: # 劇毒 (Venom)
                        # Hue ~130 紫色, Sat > 50
                            hsv = cv2.cvtColor(matched_area, cv2.COLOR_BGR2HSV)
                            avg_hue = np.mean(hsv[:,:,0])
                            avg_sat = np.mean(hsv[:,:,1])
                            if abs(avg_hue - 130) < 20 and avg_sat > 50:
                                is_valid = True
                                
                        elif check_type == 2: # 中毒 (Poison)
                        # Hue: 118±20, Sat > 30 (Center 127 -> 118 for better coverage)
                            hsv = cv2.cvtColor(matched_area, cv2.COLOR_BGR2HSV)
                            avg_hue = np.mean(hsv[:,:,0])
                            avg_sat = np.mean(hsv[:,:,1])
                            if abs(avg_hue - 118) < 20 and avg_sat > 30:
                                is_valid = True
                                
                        elif check_type == 3: # 石化 (Stone)
                        # 使用 HSV 檢測上半部白色像素 (50 < n < 130)
                            top_half = matched_area[:h_t//2, :]
                            top_hsv = cv2.cvtColor(top_half, cv2.COLOR_BGR2HSV)
                            white_mask = cv2.inRange(top_hsv, np.array([0, 0, 180]), np.array([180, 40, 255]))
                            white_count = cv2.countNonZero(white_mask)
                            if 50 < white_count < 130:
                                is_valid = True

                        elif check_type == 4: # 恐懼 (Fear)
                        # 使用像素差異比對 (避免與劇毒/詛咒混淆)
                        # 由於形狀極度相似，HSV 無法區分，改用像素差異平均值
                            if matched_area.shape == template.shape:
                                diff_img = cv2.absdiff(matched_area, template)
                                diff_val = np.mean(diff_img)
                                # 寶箱恐懼等變體差異值可能較大 (實測約 33)，放寬門檻
                                if diff_val < 40.0:
                                    is_valid = True
                        
                        elif check_type == 5: # 封技 (SkillLock)
                            # 基於高匹配率即可
                            is_valid = True
                        
                        if is_valid:
                            logger.info(f"[異常恢復] 偵測到異常狀態 {display_name} (匹配度 {max_val:.2f})")

                            # [Debug] 偵測到異常狀態時，保存截圖證據（需開啟 debug截圖 選項）
                            if setting._DEBUG_SCREENSHOT:
                                try:
                                    debug_dir = "debug_screens"
                                    if not os.path.exists(debug_dir):
                                        os.makedirs(debug_dir)
                                    ts = datetime.now().strftime("%H%M%S_%f")[:9] 
                                    save_path = f"{debug_dir}/abnormal_detected_{tmpl_name}_{idx}_{ts}.png"
                                    abs_path = os.path.abspath(save_path)
                                    success, n = cv2.imencode('.png', screenImage)
                                    if success:
                                        with open(save_path, mode='wb') as f:
                                            n.tofile(f)
                                    else:
                                        logger.error(f"編碼圖片失敗")
                                    logger.debug(f"[異常恢復] 已保存異常狀態截圖: {abs_path}")
                                except Exception as e:
                                    logger.error(f"[異常恢復] 保存截圖失敗: {e}")

                            # 記錄偵測到的狀態類型（避免重複）
                            if display_name not in detected_types:
                                detected_types.append(display_name)
                            # NOTE: 不再立即返回，繼續掃描以收集所有異常狀態

                except Exception as e:
                    logger.debug(f"[異常恢復] 偵測錯誤: {e}")
                    continue
        
        # 返回偵測結果與狀態類型列表
        return (len(detected_types) > 0, detected_types)


    def DetectCharacter(screenImage):
        """偵測當前角色，比對 resources/images/character 資料夾內的圖片
        
        比對範圍: (0,0) 到 (242,133)
        
        Returns:
            str: 比對到的角色名稱（不含副檔名），若未找到則返回 "未找到"
        """
        # ROI 區域: x=0, y=0, width=242, height=133
        roi_x, roi_y = 0, 0
        roi_w, roi_h = 242, 133
        
        # 裁切 ROI 區域
        cropped = screenImage[roi_y:roi_y+roi_h, roi_x:roi_x+roi_w]
        
        # 取得角色圖片資料夾
        character_dir = ResourcePath("resources/images/character")
        if not os.path.isdir(character_dir):
            return "未找到"
        
        # 掃描角色圖片
        best_match = "未找到"
        best_val = 0.80  # 最低門檻
        
        for filename in os.listdir(character_dir):
            if not filename.lower().endswith('.png'):
                continue
            
            template_path = os.path.join(character_dir, filename)
            # 使用 numpy 讀取以支援中文檔名
            try:
                template = cv2.imdecode(np.fromfile(template_path, dtype=np.uint8), cv2.IMREAD_COLOR)
            except:
                continue
            if template is None:
                continue
            
            try:
                result = cv2.matchTemplate(cropped, template, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(result)
                
                if max_val > best_val:
                    best_val = max_val
                    best_match = os.path.splitext(filename)[0]
            except:
                continue
        
        return best_match


    def CheckIf(screenImage, shortPathOfTarget, roi = None, outputMatchResult = False, threshold = 0.80):
        # 檢查是否需要多模板匹配
        templates_to_try = get_multi_templates(shortPathOfTarget)
        
        best_pos = None
        best_val = 0
        best_template_name = None
        match_details = []  # 收集匹配詳情用於摘要
        
        for template_name in templates_to_try:
            template = _get_cached_template(template_name)  # [優化] 使用緩存
            if template is None:
                # 如果模板加載失敗（例如文件不存在），跳過該模板
                logger.trace(f"[CheckIf] 模板加載失敗或為 None: {template_name}，跳過")
                continue

            screenshot = screenImage.copy()
            search_area = CutRoI(screenshot, roi)
            try:
                result = cv2.matchTemplate(search_area, template, cv2.TM_CCOEFF_NORMED)
            except Exception as e:
                logger.error(f"[CheckIf] 匹配異常 (Template: {template_name}): {e}")
                logger.info(f"{e}")
                if isinstance(e, (cv2.error)):
                    logger.info(f"cv2異常.")
                    continue  # 嘗試下一個模板

            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            
            # 詳細日誌放到 TRACE（只輸出到詳細文件）
            logger.trace(f"[CheckIf] {template_name}: {max_val*100:.2f}%")
            match_details.append(f"{template_name}:{max_val*100:.0f}%")
            
            # 記錄最佳匹配
            if max_val > best_val:
                best_val = max_val
                best_pos = [max_loc[0] + template.shape[1]//2, max_loc[1] + template.shape[0]//2]
                best_template_name = template_name

        # [Monitor Update] 循環結束後，確保 MonitorState 存的是最佳匹配值 (如果是目標 Flag)
        if shortPathOfTarget in ['dungFlag', 'mapFlag', 'chestFlag', 'combatActive', 'worldMap', 'chest_auto', 'AUTO']:
            flag_attr = f"flag_{shortPathOfTarget}" if shortPathOfTarget != 'AUTO' else 'flag_auto_text'
            if hasattr(MonitorState, flag_attr):
                setattr(MonitorState, flag_attr, int(best_val * 100))
                # 記錄更新時間
                if hasattr(MonitorState, 'flag_updates'):
                    MonitorState.flag_updates[shortPathOfTarget] = time.time()

        if outputMatchResult and best_pos:
            cv2.imwrite("origin.png", screenImage)
            screenshot_copy = screenImage.copy()
            template = _get_cached_template(best_template_name)  # [優化] 使用緩存
            cv2.rectangle(screenshot_copy, 
                         (best_pos[0] - template.shape[1]//2, best_pos[1] - template.shape[0]//2),
                         (best_pos[0] + template.shape[1]//2, best_pos[1] + template.shape[0]//2), 
                         (0, 255, 0), 2)
            cv2.imwrite("matched.png", screenshot_copy)

        if best_val < threshold:
            logger.trace(f"[CheckIf] {shortPathOfTarget} 未匹配 (最佳:{best_val*100:.0f}% < 閾值:{threshold*100:.0f}%)")
            return None
        
        # 匹配成功時輸出摘要到 DEBUG
        if best_val <= 0.9:
            logger.debug(f"[CheckIf] ✓ {shortPathOfTarget}:{best_val*100:.0f}% (邊界值)")
        else:
            logger.debug(f"[CheckIf] ✓ {shortPathOfTarget}:{best_val*100:.0f}%")
        
        if len(templates_to_try) > 1:
            logger.trace(f"[CheckIf] 多模板匹配: 選擇 {best_template_name} (匹配度 {best_val*100:.2f}%)")

        return best_pos
    def CheckIf_MultiRect(screenImage, shortPathOfTarget):
        template = LoadTemplateImage(shortPathOfTarget)
        screenshot = screenImage
        result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)

        threshold = 0.8
        ys, xs = np.where(result >= threshold)
        h, w = template.shape[:2]
        rectangles = list([])

        for (x, y) in zip(xs, ys):
            rectangles.append([x, y, w, h])
            rectangles.append([x, y, w, h]) # 複製兩次, 這樣groupRectangles可以保留那些單獨的矩形.
        rectangles, _ = cv2.groupRectangles(rectangles, groupThreshold=1, eps=0.5)
        pos_list = []
        for rect in rectangles:
            x, y, rw, rh = rect
            center_x = x + rw // 2
            center_y = y + rh // 2
            pos_list.append([center_x, center_y])
            # cv2.rectangle(screenshot, (x, y), (x + w, y + h), (0, 255, 0), 2)
        # cv2.imwrite("Matched_Result.png", screenshot)
        return pos_list
    def CheckIf_FocusCursor(screenImage, shortPathOfTarget):
        template = LoadTemplateImage(shortPathOfTarget)
        screenshot = screenImage
        result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)

        threshold = 0.80
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        logger.trace(f"[CheckIf_FocusCursor] {shortPathOfTarget}: {max_val*100:.2f}%")
        if max_val >= threshold:
            if max_val<=0.9:
                logger.trace(f"[CheckIf_FocusCursor] {shortPathOfTarget} 邊界值 (80-90%)")

            cropped = screenshot[max_loc[1]:max_loc[1]+template.shape[0], max_loc[0]:max_loc[0]+template.shape[1]]
            SIZE = 15 # size of cursor 光標就是這麼大
            left = (template.shape[1] - SIZE) // 2
            right =  left+ SIZE
            top = (template.shape[0] - SIZE) // 2
            bottom =  top + SIZE
            midimg_scn = cropped[top:bottom, left:right]
            miding_ptn = template[top:bottom, left:right]
            # cv2.imwrite("miding_scn.png", midimg_scn)
            # cv2.imwrite("miding_ptn.png", miding_ptn)
            gray1 = cv2.cvtColor(midimg_scn, cv2.COLOR_BGR2GRAY)
            gray2 = cv2.cvtColor(miding_ptn, cv2.COLOR_BGR2GRAY)
            mean_diff = cv2.absdiff(gray1, gray2).mean()/255
            logger.trace(f"[CheckIf_FocusCursor] 中心匹配:{mean_diff:.2f}")

            if mean_diff<0.2:
                return True
        return False
    def CheckIf_ReachPosition(screenImage,targetInfo : TargetInfo):
        screenshot = screenImage
        position = targetInfo.roi
        cropped = screenshot[position[1]-33:position[1]+33, position[0]-33:position[0]+33]

        for i in range(4):
            template = LoadTemplateImage(f"cursor_{i}")
        
            result = cv2.matchTemplate(cropped, template, cv2.TM_CCOEFF_NORMED)
            threshold = 0.80
            _, max_val, _, _ = cv2.minMaxLoc(result)

            logger.trace(f"[CheckIf_ReachPosition] {position}: {max_val*100:.2f}%")
            if max_val > threshold:
                logger.trace("[CheckIf_ReachPosition] 已達到閞值")
                return None 
        return position
    def CheckIf_throughStair(screenImage,targetInfo : TargetInfo):
        stair_img = ["stair_up","stair_down","stair_teleport"]
        screenshot = screenImage
        position = targetInfo.roi
        cropped = screenshot[position[1]-33:position[1]+33, position[0]-33:position[0]+33]
        
        if (targetInfo.target not in stair_img):
            # 驗證樓層
            template = LoadTemplateImage(targetInfo.target)
            result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
            threshold = 0.80
            _, max_val, _, _ = cv2.minMaxLoc(result)

            logger.trace(f"[樓層檢測] {targetInfo.target}: {max_val*100:.2f}%")
            if max_val > threshold:
                logger.info("樓層正確, 判定爲已通過")
                return None
            return position
            
        else: #equal: targetInfo.target IN stair_img
            template = LoadTemplateImage(targetInfo.target)
            result = cv2.matchTemplate(cropped, template, cv2.TM_CCOEFF_NORMED)
            threshold = 0.80
            _, max_val, _, _ = cv2.minMaxLoc(result)

            logger.trace(f"[樓梯檢測] {targetInfo.target}: {max_val*100:.2f}%")
            if max_val > threshold:
                logger.info("判定爲樓梯存在, 尚未通過.")
                return position
            return None

    # 小地圖區域 ROI (右上角): 左上角(651,24) 右下角(870,244)
    MINIMAP_ROI = [651, 24, 870, 244]  # [x1, y1, x2, y2]
    
    def CheckIf_minimapFloor(screenImage, floorImage):
        """偵測主畫面小地圖中的樓層標識
        
        Args:
            screenImage: 主畫面截圖（非地圖畫面）
            floorImage: 樓層標識圖片名稱
        
        Returns:
            dict: 包含是否找到、匹配度、位置等資訊
        """
        template = LoadTemplateImage(floorImage)
        if template is None:
            logger.error(f"無法載入圖片: {floorImage}")
            return {"found": False, "match_val": 0, "pos": None, "error": "圖片不存在"}
        
        # 使用固定的小地圖 ROI 區域 [x1, y1, x2, y2]
        x1, y1, x2, y2 = MINIMAP_ROI
        search_area = screenImage[y1:y2, x1:x2].copy()
        
        try:
            result = cv2.matchTemplate(search_area, template, cv2.TM_CCOEFF_NORMED)
        except Exception as e:
            logger.error(f"匹配失敗: {e}")
            return {"found": False, "match_val": 0, "pos": None, "error": str(e)}
        
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        threshold = 0.80
        
        pos = None
        if max_val >= threshold:
            pos = [max_loc[0] + template.shape[1]//2, max_loc[1] + template.shape[0]//2]
        
        return {
            "found": max_val >= threshold,
            "match_val": max_val,
            "pos": pos,
            "threshold": threshold
        }

    def CheckIf_fastForwardOff(screenImage):
        position = [240,1490]
        template =  LoadTemplateImage(f"fastforward_off")
        screenshot =  screenImage
        cropped = screenshot[position[1]-50:position[1]+50, position[0]-50:position[0]+50]
        
        result = cv2.matchTemplate(cropped, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        threshold = 0.80
        pos=[position[0]+max_loc[0] - cropped.shape[1]//2, position[1]+max_loc[1] -cropped.shape[0]//2]

        if max_val > threshold:
            logger.info(f"快進未開啓, 即將開啓.{pos}")
            return pos
        return None
    def Press(pos):
        if pos!=None:
            DeviceShell(f"input tap {pos[0]} {pos[1]}")
            return True
        return False
    def Swipe(start, end, duration=300):
        if start and end:
            DeviceShell(f"input swipe {start[0]} {start[1]} {end[0]} {end[1]} {duration}")
            return True
        return False
    def PressReturn():
        DeviceShell('input keyevent KEYCODE_BACK')
    def WrapImage(image,r,g,b):
        scn_b = image * np.array([b, g, r])
        return np.clip(scn_b, 0, 255).astype(np.uint8)
    def TryPressRetry(scn):
        if Press(CheckIf(scn,'retry')):
            logger.info("發現並點擊了\"重試\". 你遇到了網絡波動.")
            return True
        if pos:=(CheckIf(scn,'retry_blank')):
            Press([pos[0], pos[1]+103])
            logger.info("發現並點擊了\"重試\". 你遇到了網絡波動.")
            return True
        return False
    def AddImportantInfo(str):
        nonlocal runtimeContext
        if runtimeContext._IMPORTANTINFO == "":
            runtimeContext._IMPORTANTINFO = "👆向上滑動查看重要信息👆\n"
        time_str = datetime.now().strftime("%Y%m%d-%H%M%S") 
        runtimeContext._IMPORTANTINFO = f"{time_str} {str}\n{runtimeContext._IMPORTANTINFO}"
    ##################################################################
    @stoppable
    def FindCoordsOrElseExecuteFallbackAndWait(targetPattern, fallback,waitTime):
        # fallback可以是座標[x,y]或者字符串. 當爲字符串的時候, 視爲圖片地址
        while True:
            check_stop_signal()  # 每次迭代開始時檢查停止信號
            for _ in range(runtimeContext._MAXRETRYLIMIT):
                check_stop_signal()  # 每次重試前也檢查
                scn = ScreenShot()
                if isinstance(targetPattern, (list, tuple)):
                    for pattern in targetPattern:
                        # combatActive* 使用較低閾值，避免 74% 匹配無法觸發
                        thresh = 0.70 if pattern.startswith('combatActive') else 0.80
                        p = CheckIf(scn, pattern, threshold=thresh)
                        if p:
                            return p
                else:
                    pos = CheckIf(scn,targetPattern)
                    if pos:
                        return pos # FindCoords
                # OrElse
                if TryPressRetry(scn):
                    Sleep(1)
                    continue
                if Press(CheckIf_fastForwardOff(scn)):
                    Sleep(1)
                    continue
                def pressTarget(target):
                    if target.lower() == 'return':
                        PressReturn()
                    elif target.startswith("input swipe"):
                        DeviceShell(target)
                    else:
                        Press(CheckIf(scn, target))
                if fallback: # Execute
                    if isinstance(fallback, (list, tuple)):
                        if (len(fallback) == 2) and all(isinstance(x, (int, float)) for x in fallback):
                            Press(fallback)
                        else:
                            for p in fallback:
                                if isinstance(p, str):
                                    pressTarget(p)
                                elif isinstance(p, (list, tuple)) and len(p) == 2:
                                    t = time.time()
                                    Press(p)
                                    if (waittime:=(time.time()-t)) < 0.1:
                                        Sleep(0.1-waittime)
                                else:
                                    logger.debug(f"錯誤: 非法的目標{p}.")
                                    setting._FORCESTOPING.set()
                                    return None
                    else:
                        if isinstance(fallback, str):
                            pressTarget(fallback)
                        else:
                            logger.debug("錯誤: 非法的目標.")
                            setting._FORCESTOPING.set()
                            return None
                Sleep(waitTime) # and wait

            logger.info(f"{runtimeContext._MAXRETRYLIMIT}次截圖依舊沒有找到目標{targetPattern}, 疑似卡死. 重啓遊戲.")
            Sleep()
            restartGame()
            return None # restartGame會拋出異常 所以直接返回none就行了

    # 遊戲進程監控
    _game_monitor_thread = None

    def _monitor_game_process(grace_period=15):
        """守護線程：監控遊戲進程是否存活
        
        Args:
            grace_period: 啟動後的寬限期（秒），期間不進行監控
        """
        # NOTE: 使用分段 sleep 確保能快速響應停止信號
        if grace_period > 0:
            logger.debug(f"[GameMonitor] 寬限期中 ({grace_period}s)...")
            # 分段 sleep，每 0.5 秒檢查停止信號
            for _ in range(int(grace_period * 2)):
                if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                    logger.debug("[GameMonitor] 寬限期中收到停止信號")
                    return
                time.sleep(0.5)
            
        package_name = "jp.co.drecom.wizardry.daphne"
        while not (setting._FORCESTOPING and setting._FORCESTOPING.is_set()):
            try:
                result = setting._ADBDEVICE.shell(f"pidof {package_name}", timeout=3)
                if not result.strip():
                    logger.warning("[GameMonitor] 遊戲進程已死亡，設置崩潰標記")
                    setting._GAME_CRASHED.set()
                    return
            except Exception as e:
                # ADB 異常時不誤判（可能是暫時斷線）
                logger.debug(f"[GameMonitor] ADB 檢查異常: {e}")
            # NOTE: 分段 sleep，每 0.5 秒檢查停止信號（2秒 = 4 x 0.5秒）
            for _ in range(4):
                if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                    logger.debug("[GameMonitor] 監控線程收到停止信號")
                    return
                time.sleep(0.5)
        logger.debug("[GameMonitor] 監控線程結束（收到停止信號）")

    def _start_game_monitor():
        """啟動遊戲進程監控線程"""
        nonlocal _game_monitor_thread
        # 確保 Event 存在
        if not hasattr(setting, '_GAME_CRASHED'):
            setting._GAME_CRASHED = Event()
        setting._GAME_CRASHED.clear()

        # 停止舊的監控線程（如果存在）
        if _game_monitor_thread and _game_monitor_thread.is_alive():
            logger.debug("[GameMonitor] 舊監控線程仍在運行，等待其結束...")

        # 啟動新的監控線程
        _game_monitor_thread = Thread(target=_monitor_game_process, daemon=True, name="GameMonitor")
        _game_monitor_thread.start()
        logger.info("[GameMonitor] 遊戲進程監控已啟動")

    def restartGame(skipScreenShot = False):
        nonlocal runtimeContext
        runtimeContext._IN_RESTART = True # [關鍵] 標記開始重啟
        if hasattr(setting, '_GAME_CRASHED'):
            setting._GAME_CRASHED.clear() # 啟動前先清除

        runtimeContext._COMBATSPD = False # 重啓會重置2倍速, 所以重置標識符以便重新打開.
        runtimeContext._MAXRETRYLIMIT = min(50, runtimeContext._MAXRETRYLIMIT + 5) # 每次重啓後都會增加5次嘗試次數, 以避免不同電腦導致的反覆重啓問題.
        runtimeContext._TIME_CHEST = 0
        runtimeContext._TIME_COMBAT = 0 # 因爲重啓了, 所以清空戰鬥和寶箱計時器.
        runtimeContext._ZOOMWORLDMAP = False
        runtimeContext._STEPAFTERRESTART = False  # 重啓後重置防止轉圈標誌，確保會執行左右平移
        runtimeContext._RESTART_OPEN_MAP_PENDING = True  # 重啓後待打開地圖，跳過Resume優化
        runtimeContext._DUNGEON_CONFIRMED = False  # 重啓後重置地城確認標記
        runtimeContext._RESTART_PENDING_BATTLE_RESET = True  # 重啓後待重置戰鬥計數器
        reset_ae_caster_flags()  # 重啓後重置 AE 手旗標
        runtimeContext._RESTART_SKIP_INTERVAL_THIS_DUNGEON = True  # [關鍵] 必須在重置後設置，否則會被 reset_ae_caster_flags 清除

        if not skipScreenShot:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")  # 格式：20230825_153045
            file_path = os.path.join(LOGS_FOLDER_NAME, f"{timestamp}.png")
            cv2.imwrite(file_path, ScreenShot())
            logger.info(f"重啓前截圖已保存在{file_path}中.")
        else:
            runtimeContext._CRASHCOUNTER +=1
            logger.info(f"跳過了重啓前截圖.\n崩潰計數器: {runtimeContext._CRASHCOUNTER}\n崩潰計數器超過5次後會重啓模擬器.")
            if runtimeContext._CRASHCOUNTER > 5:
                runtimeContext._CRASHCOUNTER = 0
                runtimeContext._COUNTEREMULATORCRASH += 1
                KillEmulator(setting)
                CheckRestartConnectADB(setting)

        package_name = "jp.co.drecom.wizardry.daphne"
        # 再次檢查是否連接 ADB
        if setting._ADBDEVICE is None:
            CheckRestartConnectADB(setting)
            
        try:
            mainAct = DeviceShell(f"cmd package resolve-activity --brief {package_name}").strip().split('\n')[-1]
        except:
            mainAct = f"{package_name}/.MainActivity" # 回退
            
        DeviceShell(f"am force-stop {package_name}")
        if hasattr(setting, '_GAME_CRASHED'):
            setting._GAME_CRASHED.clear() # 停止後再次清除標記
        Sleep(2)
        logger.info("巫術, 啓動!")
        DeviceShell(f"am start -n {mainAct}")
        if hasattr(setting, '_GAME_CRASHED'):
            setting._GAME_CRASHED.clear() # 啟動後再次清除標記
        
        # [修正] 等待遊戲進程啟動（使用 pidof，和 GameMonitor 相同方式）
        # 僅固定等待 15 秒不足以應對模擬器冷啟動的情況
        logger.info("等待遊戲載入...")
        max_wait = 60  # 最多等待 60 秒
        wait_interval = 3
        waited = 0
        while waited < max_wait:
            Sleep(wait_interval)
            waited += wait_interval
            try:
                result = DeviceShell(f"pidof {package_name}")
                if result.strip():  # 有 PID 表示遊戲已啟動
                    logger.info(f"遊戲進程已啟動 (等待了 {waited} 秒)")
                    break
            except:
                pass  # ADB 錯誤時繼續等待
        else:
            logger.warning(f"等待遊戲超時 ({max_wait}s)，繼續執行...")

        
        # [修正] 不在 restartGame 中啟動 GameMonitor
        # GameMonitor 應在主循環 (RestartableSequenceExecution) 開始時才啟動
        # 這樣可以避免遊戲尚未完全啟動時就被誤判為「進程已死亡」
        raise RestartSignal()
    class RestartSignal(Exception):
        pass
    def RestartableSequenceExecution(*operations):
        MonitorState.current_state = "Starting"
        MAX_RESTART_RETRIES = 100# 最大重啟次數
        restart_count = 0
        while restart_count < MAX_RESTART_RETRIES:
            # NOTE: 每次循環開始時都檢查 GameMonitor 是否存活
            # 修復：之前只在循環外檢查一次，導致重啟後 GameMonitor 沒有重新啟動
            if not hasattr(setting, '_GAME_CRASHED') or not (_game_monitor_thread and _game_monitor_thread.is_alive()):
                _start_game_monitor()
            # 每一輪開始前，將重啟標記清空，表示已進入正式執行階段
            runtimeContext._IN_RESTART = False
            try:
                for op in operations:
                    # 在每個操作之前檢查停止信號（使用統一機制）
                    check_stop_signal()
                    op()
                return
            except RestartSignal:
                restart_count += 1
                logger.info(f"任務進度重置中... (第 {restart_count}/{MAX_RESTART_RETRIES} 次)")
                # 重置前也檢查停止信號
                check_stop_signal()
                continue
            except StopSignalException:
                logger.info("RestartableSequenceExecution 收到停止信號，優雅退出")
                return
        logger.error(f"RestartableSequenceExecution 連續重啟 {MAX_RESTART_RETRIES} 次，放棄執行")
        raise RuntimeError(f"任務序列執行失敗：連續重啟 {MAX_RESTART_RETRIES} 次")
    ##################################################################

    class State(Enum):
        Dungeon = 'dungeon'
        Inn = 'inn'
        EoT = 'edge of Town'
        Quit = 'quit'
    class DungeonState(Enum):
        Dungeon = 'dungeon'
        Map = 'map'
        Chest = 'chest'
        Combat = 'combat'
        Quit = 'quit'

    def TeleportFromCityToWorldLocation(target, swipe):
        nonlocal runtimeContext
        FindCoordsOrElseExecuteFallbackAndWait(['intoWorldMap','dungFlag','worldmapflag'],['closePartyInfo','closePartyInfo_fortress',[550,1]],1)
        
        if CheckIf(scn:=ScreenShot(), 'dungflag'):
            # 如果已經在副本里了 直接結束.
            # 因爲該函數預設了是從城市開始的.
            return
        elif Press(CheckIf(scn,'intoWorldMap')):
            # 如果在城市, 嘗試進入世界地圖
            Sleep(0.5)
            FindCoordsOrElseExecuteFallbackAndWait('worldmapflag','intoWorldMap',1)
        elif CheckIf(scn,'worldmapflag'):
            # 如果在世界地圖, 下一步.
            pass

        # 往下都是確保了現在能看見'worldmapflag', 並嘗試看見'target'
        Sleep(0.5)
        if not runtimeContext._ZOOMWORLDMAP:
            for _ in range(3):
                Press([100,1500])
                Sleep(0.5)
            Press([250,1500])
            runtimeContext._ZOOMWORLDMAP = True
        pos = FindCoordsOrElseExecuteFallbackAndWait(target,[swipe,[550,1]],1)

        # 現在已經確保了可以看見target, 那麼確保可以點擊成功
        Sleep(1)
        Press(pos)
        Sleep(1)
        FindCoordsOrElseExecuteFallbackAndWait(['Inn','openworldmap','dungFlag'],[target,[550,1]],1)
        
    def CursedWheelTimeLeap(tar=None, CSC_symbol=None,CSC_setting = None):
        # CSC_symbol: 是否開啓因果? 如果開啓因果, 將用這個作爲是否點開ui的檢查標識
        # CSC_setting: 默認會先選擇不接所有任務. 這個列表中儲存的是想要打開的因果.
        # 其中的RGB用於縮放顏色維度, 以增加識別的可靠性.
        if setting.ACTIVE_CSC == False:
            logger.info(f"因爲面板設置, 跳過了調整因果.")
            CSC_symbol = None

        target = "GhostsOfYore"
        if tar != None:
            target = tar
        if setting._ACTIVE_TRIUMPH:
            target = "Triumph"

        logger.info(f"開始時間跳躍, 本次跳躍目標:{target}")

        # 調整條目以找到跳躍目標
        Press(FindCoordsOrElseExecuteFallbackAndWait('cursedWheel',['ruins',[1,1]],1))
        Press(FindCoordsOrElseExecuteFallbackAndWait('cursedwheel_impregnableFortress',['cursedWheelTapRight','cursedWheel',[1,1]],1))
        if not Press(CheckIf(ScreenShot(),target)):
            DeviceShell(f"input swipe 450 1200 450 200")
            Sleep(2)
            Press(FindCoordsOrElseExecuteFallbackAndWait(target,'input swipe 50 1200 50 1300',1))
        Sleep(1)

        # 跳躍前嘗試調整因果
        MAX_CSC_SWIPES = 30  # 最大滑動次數，防止無限循環
        while CheckIf(ScreenShot(), 'leap'):
            if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                return
            if CSC_symbol != None:
                FindCoordsOrElseExecuteFallbackAndWait(CSC_symbol,'CSC',1)
                last_scn = CutRoI(ScreenShot(), [[77,349,757,1068]])
                # 先關閉所有因果
                csc_swipe_count = 0
                while csc_swipe_count < MAX_CSC_SWIPES:
                    if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                        return
                    
                    # [網路重試] 檢測網路波動
                    if TryPressRetry(ScreenShot()):
                        logger.info("[因果調整] 關閉因果時偵測到 Retry 選項，點擊重試")
                        Sleep(2)
                        continue
                    Press(CheckIf(WrapImage(ScreenShot(),2,0,0),'didnottakethequest'))
                    DeviceShell(f"input swipe 150 500 150 400")
                    Sleep(1)
                    scn = CutRoI(ScreenShot(), [[77,349,757,1068]])
                    logger.debug(f"因果: 滑動後的截圖誤差={cv2.absdiff(scn, last_scn).mean()/255:.6f}")
                    if cv2.absdiff(scn, last_scn).mean()/255 < 0.006:
                        break
                    else:
                        last_scn = scn
                    csc_swipe_count += 1
                if csc_swipe_count >= MAX_CSC_SWIPES:
                    logger.warning(f"因果關閉循環超過 {MAX_CSC_SWIPES} 次，強制退出")
                # 然後調整每個因果
                if CSC_setting!=None:
                    last_scn = CutRoI(ScreenShot(), [[77,349,757,1068]])
                    csc_adjust_count = 0
                    while csc_adjust_count < MAX_CSC_SWIPES:
                        if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                            return
                        
                        # [網路重試] 檢測網路波動
                        if TryPressRetry(ScreenShot()):
                            logger.info("[因果調整] 調整因果時偵測到 Retry 選項，點擊重試")
                            Sleep(2)
                            continue
                        for option, r, g, b in CSC_setting:
                            Press(CheckIf(WrapImage(ScreenShot(),r,g,b),option))
                            Sleep(1)
                        DeviceShell(f"input swipe 150 400 150 500")
                        Sleep(1)
                        scn = CutRoI(ScreenShot(), [[77,349,757,1068]])
                        logger.debug(f"因果: 滑動後的截圖誤差={cv2.absdiff(scn, last_scn).mean()/255:.6f}")
                        if cv2.absdiff(scn, last_scn).mean()/255 < 0.006:
                            break
                        else:
                            last_scn = scn
                        csc_adjust_count += 1
                    if csc_adjust_count >= MAX_CSC_SWIPES:
                        logger.warning(f"因果調整循環超過 {MAX_CSC_SWIPES} 次，強制退出")
                PressReturn()
                Sleep(0.5)
            Press(CheckIf(ScreenShot(),'leap'))
            Sleep(2)
            Press(CheckIf(ScreenShot(),target))

    def RiseAgainReset(reason):
        nonlocal runtimeContext
        runtimeContext._SUICIDE = False # 死了 自殺成功 設置爲false
        runtimeContext._RECOVERAFTERREZ = True
        if reason == 'chest':
            runtimeContext._COUNTERCHEST -=1
        else:
            runtimeContext._COUNTERCOMBAT -=1
        logger.info("快快請起.")
        AddImportantInfo("面具死了但沒死.")
        # logger.info("REZ.")
        Press([450,750])
        Sleep(10)
    @stoppable
    def IdentifyState():
        nonlocal setting # 修改因果
        counter = 0
        while 1:
            check_stop_signal()  # 每次迭代開始時檢查停止信號
            # [串流優化] 節流延遲，避免檢測太快導致遊戲來不及響應
            if PYSCRCPY_AVAILABLE:
                Sleep(0.5)  # 串流模式下每次檢測間隔 500ms
            
            state_check_start = time.time()
            screen = ScreenShot()
            logger.debug(f'狀態機檢查中...(第{counter+1}次)')

            if setting._FORCESTOPING.is_set():
                return State.Quit, DungeonState.Quit, screen

            # [黑屏偵測] 只在需要手動的戰鬥場次打斷自動戰鬥
            # 條件：已確認進入地城 + AOE 尚未觸發 + 行動計數為 0 + 非地城內啟動 + 黑屏 + 需要手動場次
            is_black = IsScreenBlack(screen)
            auto_combat_mode = setting._AUTO_COMBAT_MODE
            manual_battles = {
                "完全自動": 0,
                "1 場後自動": 1,
                "2 場後自動": 2,
                "3 場後自動": 3,
                "完全手動": -1
            }.get(auto_combat_mode, 2)
            should_interrupt_auto = (manual_battles == -1) or (runtimeContext._COMBAT_BATTLE_COUNT < manual_battles)
            if runtimeContext._DUNGEON_CONFIRMED and not runtimeContext._AOE_TRIGGERED_THIS_DUNGEON and runtimeContext._COMBAT_ACTION_COUNT == 0 and not runtimeContext._MID_DUNGEON_START and is_black and should_interrupt_auto:
                # 檢查是否需要首戰打斷（有設定任何角色的首戰技能）
                skill_config_list = setting._CHARACTER_SKILL_CONFIG if isinstance(setting._CHARACTER_SKILL_CONFIG, list) else []
                need_first_combat_interrupt = any(
                    cfg.get("character") and cfg.get("skill_first")
                    for cfg in skill_config_list
                )

                if need_first_combat_interrupt:
                    logger.info("[黑屏偵測] 偵測到戰鬥過場黑屏，開始提前打斷自動戰鬥...")
                    click_count = 0
                    # 在黑屏期間持續點擊打斷
                    while IsScreenBlack(ScreenShot()):
                        if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                            return State.Quit, DungeonState.Quit, screen
                        Press([1, 1])
                        click_count += 1
                        Sleep(0.1)  # 快速點擊
                        if click_count > 100:  # 防止無限迴圈（最多 10 秒）
                            logger.warning("[黑屏偵測] 黑屏持續過久，中斷點擊")
                            break
                    # 黑屏結束後額外點擊，確保打斷過渡期的自動戰鬥
                    for i in range(10):
                        Press([1, 1])
                        Sleep(0.1)
                    logger.info(f"[黑屏偵測] 完成，共點擊 {click_count + 10} 次打斷")
                    continue  # 重新開始狀態識別迴圈

            if TryPressRetry(screen):
                    Sleep(2)

            # harken 樓層選擇：優先處理，當設置了 _HARKEN_FLOOR_TARGET 時檢查樓層選擇界面
            if runtimeContext._HARKEN_FLOOR_TARGET is not None:
                floor_target = runtimeContext._HARKEN_FLOOR_TARGET
                logger.info(f"哈肯樓層選擇: 正在檢查樓層 {floor_target}...")
                
                # 檢查是否出現樓層選擇按鈕
                floor_pos = CheckIf(screen, floor_target)
                if floor_pos and Press(floor_pos):
                    logger.info(f"哈肯樓層選擇: 點擊樓層 {floor_target}")
                    runtimeContext._HARKEN_FLOOR_TARGET = None  # 清除 flag
                    runtimeContext._HARKEN_TELEPORT_JUST_COMPLETED = True  # 設置傳送完成標記
                    MonitorState.current_state = "Harken"
                    Sleep(2)
                    counter += 1
                    continue
                
                # 如果沒找到樓層按鈕，檢查 returnText（可能選擇界面還沒出現）
                returntext_pos = CheckIf(screen, "returnText")
                if returntext_pos:
                    # returnText 出現但樓層按鈕還沒出現，先點擊等待
                    logger.info(f"哈肯樓層選擇: 發現 returnText，等待樓層 {floor_target} 出現...")
                    Press(returntext_pos)
                    Sleep(2)
                    counter += 1
                    continue
                
                # 如果都沒找到，看看是否在移動中（不應該立即返回 Dungeon 狀態）
                logger.debug(f"哈肯樓層選擇: 未找到 {floor_target} 或 returnText，繼續等待...")

            # [Optimization] 預先計算 combatActive (戰鬥偵測)
            # 這是最耗時的部分，透過只計算一次並同時用於 Monitor 和 邏輯判斷 來優化效能
            combat_templates = get_combat_active_templates()
            max_combat_val = 0
            best_combat_pos = None
            
            if combat_templates:
                for t in combat_templates:
                    template = _get_cached_template(t)
                    if template is None: continue
                    
                    try:
                        res = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
                        _, val, _, loc = cv2.minMaxLoc(res)
                        if val > max_combat_val:
                            max_combat_val = val
                            best_combat_pos = [loc[0] + template.shape[1]//2, loc[1] + template.shape[0]//2]
                    except:
                        continue
            

            MonitorState.flag_combatActive = int(max_combat_val * 100)
            MonitorState.flag_updates['combatActive'] = time.time()


            # 如果預先計算發現是戰鬥狀態 (>0.7)，直接返回，不用再跑後面的迴圈
            if max_combat_val >= 0.70:
                 elapsed_ms = (time.time() - state_check_start) * 1000
                 logger.debug(f"[狀態識別] 匹配成功(預計算): combatActive -> Combat (耗時 {elapsed_ms:.0f} ms)")
                 
                 if not runtimeContext._DUNGEON_CONFIRMED:
                     runtimeContext._DUNGEON_CONFIRMED = True
                     logger.info("[狀態識別] 已確認進入地城")
                 
                 MonitorState.current_state = "Dungeon"
                 MonitorState.current_dungeon_state = "Combat"
                 return State.Dungeon, DungeonState.Combat, screen

            # [Fix] 檢查復活相關狀態 (恢復原Upstream順序: 戰鬥檢測後)
            if CheckIf(screen, 'RiseAgain'):
                logger.info("[狀態識別] 偵測到 RiseAgain")
                RiseAgainReset(reason='combat')
                counter += 1
                continue

            if CheckIf(screen, 'someonedead'):
                AddImportantInfo("他們活了,活了!")
                runtimeContext._COUNTERDEATH += 1
                MonitorState.death_count = runtimeContext._COUNTERDEATH
                for _ in range(5):
                    # 點擊隨機位置嘗試互動
                    Press([400+random.randint(0,100),750+random.randint(0,100)])
                    Sleep(1)
                # 點擊後繼續循環，重新截圖判斷狀態
                continue

            # 偵測到 AUTO 時，持續點擊直到消失
            MonitorState.flag_auto_text = GetMatchValue(screen, 'AUTO')
            MonitorState.flag_updates['AUTO'] = time.time()
            if MonitorState.flag_auto_text >= 70: # 門檻降低至 70
                logger.info("[AUTO] 偵測到 AUTO，開始連續點擊")
                click_count = 0
                while click_count < 5:
                    if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                        return State.Quit, DungeonState.Quit, screen
                    # 連點 3 下清戰利品
                    for _ in range(3):
                        Press([1, 1])
                        Sleep(0.05)
                    Sleep(0.1)
                    shot_start = time.time()
                    screen = ScreenShot()
                    shot_ms = (time.time() - shot_start) * 1000
                    logger.debug(f"[AUTO] 截圖耗時: {shot_ms:.0f}ms ({'串流' if shot_ms < 50 else 'ADB'})")

                    # [穿插異常檢測] 避免 AUTO 卡住時延遲處理
                    if Press(CheckIf(screen, "returnText")) or Press(CheckIf(screen, "ReturnText")):
                        logger.info("[AUTO] 偵測到 returnText，中斷並處理")
                        Sleep(1)
                        counter += 1
                        continue
                    if CheckIf(screen, 'RiseAgain'):
                        logger.info("[AUTO] 偵測到 RiseAgain，中斷並處理")
                        RiseAgainReset(reason='combat')
                        counter += 1
                        continue

                    MonitorState.flag_auto_text = GetMatchValue(screen, 'AUTO')
                    MonitorState.flag_updates['AUTO'] = time.time()
                    if MonitorState.flag_auto_text < 80:
                        logger.info("[AUTO] AUTO 已消失，停止點擊")

                        # [恢復判斷] AUTO 消失後，檢查是否需要恢復（只設置標誌，不執行動作）
                        logger.debug("[AUTO] 執行恢復條件判斷...")
                        scn_recover = ScreenShot()
                        
                        # [Debug] 進入檢查即刻拍照（需開啟 debug截圖 選項）
                        if setting._DEBUG_SCREENSHOT:
                            try:
                                debug_dir = "debug_screens"
                                if not os.path.exists(debug_dir): os.makedirs(debug_dir)
                                ts = datetime.now().strftime("%H%M%S_%f")[:9] 
                                save_path = f"{debug_dir}/auto_vanish_check_{ts}.png"
                                cv2.imwrite(save_path, scn_recover)
                                logger.debug(f"[AUTO] 恢復檢查前截圖: {save_path}")
                            except Exception as e: logger.error(f"截圖失敗: {e}")
                        
                        # 1. 異常狀態
                        if (setting._RECOVER_POISON or setting._RECOVER_VENOM or 
                            setting._RECOVER_STONE or setting._RECOVER_PARALYSIS or 
                            setting._RECOVER_CURSED or setting._RECOVER_FEAR or
                            setting._RECOVER_SKILLLOCK):
                            detected, status_types = CheckAbnormalStatus(scn_recover, setting)
                            if detected:
                                logger.info(f"[AUTO] 偵測到異常狀態: {status_types}，標記強制恢復")
                                runtimeContext._FORCE_ABNORMAL_RECOVER = True
                                # 如果偵測到麻痺或封技，標記恢復後重置戰鬥計數
                                if '麻痺' in status_types or '封技' in status_types:
                                    runtimeContext._RESET_BATTLE_COUNT_AFTER_RECOVER = True
                                    logger.info("[AUTO] 偵測到麻痺/封技，將在恢復後重置戰鬥計數器")

                        # 2. 低血量恢復
                        if setting._LOWHP_RECOVER:
                            if CheckLowHP(scn_recover):
                                logger.debug("[AUTO] 偵測到低血量，啟用低血量恢復檢查標誌")
                                runtimeContext._FORCE_LOWHP_RECOVER = True
                            else:
                                logger.debug("[AUTO] 低血量檢查: 未偵測到低血量")

                        break
                    click_count += 1
                else:
                    # AUTO 循環 5 次後仍存在，直接進入異常處理
                    logger.warning("[AUTO] 5 次點擊後 AUTO 仍在，執行異常處理")

                    # [恢復判斷] AUTO 持續存在（可能卡住或消失失敗），同樣執行一次檢查
                    logger.debug("[AUTO] 執行恢復條件判斷 (Timeout)...")
                    scn_recover = ScreenShot()
                    
                    # [Debug] 進入檢查即刻拍照（需開啟 debug截圖 選項）
                    if setting._DEBUG_SCREENSHOT:
                        try:
                            debug_dir = "debug_screens"
                            if not os.path.exists(debug_dir): os.makedirs(debug_dir)
                            ts = datetime.now().strftime("%H%M%S_%f")[:9] 
                            save_path = f"{debug_dir}/auto_timeout_check_{ts}.png"
                            cv2.imwrite(save_path, scn_recover)
                            logger.debug(f"[AUTO] 恢復檢查前截圖: {save_path}")
                        except Exception as e: logger.error(f"截圖失敗: {e}")
                    
                    # 1. 異常狀態
                    if (setting._RECOVER_POISON or setting._RECOVER_VENOM or 
                        setting._RECOVER_STONE or setting._RECOVER_PARALYSIS or 
                        setting._RECOVER_CURSED or setting._RECOVER_FEAR or
                        setting._RECOVER_SKILLLOCK):
                        detected, status_types = CheckAbnormalStatus(scn_recover, setting)
                        if detected:
                            logger.info(f"[AUTO-Timeout] 偵測到異常狀態: {status_types}，標記強制恢復")
                            runtimeContext._FORCE_ABNORMAL_RECOVER = True
                            # 如果偵測到麻痺或封技，標記恢復後重置戰鬥計數
                            if '麻痺' in status_types or '封技' in status_types:
                                runtimeContext._RESET_BATTLE_COUNT_AFTER_RECOVER = True
                                logger.info("[AUTO-Timeout] 偵測到麻痺/封技，將在恢復後重置戰鬥計數器")

                    # 2. 低血量恢復
                    if setting._LOWHP_RECOVER:
                        if CheckLowHP(scn_recover):
                            logger.debug("[AUTO-Timeout] 偵測到低血量，啟用低血量恢復檢查標誌")
                            runtimeContext._FORCE_LOWHP_RECOVER = True
                        else:
                            logger.debug("[AUTO-Timeout] 低血量檢查: 未偵測到低血量")
                    # 檢測各種對話框選項
                    dialogOption = [
                        'adventurersbones', 'halfBone', 'nothanks', 'strange_things',
                        'blessing', 'DontBuyIt', 'donthelp', 'buyNothing', 'Nope',
                        'ignorethequest', 'dontGiveAntitoxin', 'pass',
                    ]
                    found_any_option = False
                    
                    # NOTE: 優先處理善惡選擇，根據 _KARMAADJUST 設定決定行為
                    # 偵測到 ambush（伏擊）且設定為負數 → 點擊伏擊（變惡）
                    if (pos := CheckIf(screen, 'ambush')) and setting._KARMAADJUST.startswith('-'):
                        num_str = setting._KARMAADJUST[1:]
                        if num_str.isdigit():
                            num = int(num_str)
                            if num != 0:
                                new_str = f"-{num - 1}"
                            else:
                                new_str = "+0"
                            logger.info(f"[AUTO] 善惡調整: 選擇伏擊. 剩餘次數:{new_str}")
                            AddImportantInfo(f"善惡調整:{new_str}")
                            setting._KARMAADJUST = new_str
                            SetOneVarInConfig("_KARMAADJUST", setting._KARMAADJUST)
                            Press(pos)
                            Sleep(2)
                            found_any_option = True
                    # 偵測到 ignore（忽略）且設定為正數 → 點擊忽略（變善）
                    elif (pos := CheckIf(screen, 'ignore')) and setting._KARMAADJUST.startswith('+'):
                        num_str = setting._KARMAADJUST[1:]
                        if num_str.isdigit():
                            num = int(num_str)
                            if num != 0:
                                new_str = f"+{num - 1}"
                            else:
                                new_str = "-0"
                            logger.info(f"[AUTO] 善惡調整: 選擇忽略. 剩餘次數:{new_str}")
                            AddImportantInfo(f"善惡調整:{new_str}")
                            setting._KARMAADJUST = new_str
                            SetOneVarInConfig("_KARMAADJUST", setting._KARMAADJUST)
                            Press(pos)
                            Sleep(2)
                            found_any_option = True
                    # 偵測到善惡選項但設定為 0，選擇預設行為（忽略優先）
                    elif (pos := CheckIf(screen, 'ignore')):
                        logger.info("[AUTO] 善惡調整: 設定為 0，選擇忽略")
                        Press(pos)
                        Sleep(2)
                        found_any_option = True
                    elif (pos := CheckIf(screen, 'ambush')):
                        logger.info("[AUTO] 善惡調整: 設定為 0，選擇伏擊")
                        Press(pos)
                        Sleep(2)
                        found_any_option = True
                    
                    if not found_any_option:
                        for op in dialogOption:
                            if Press(CheckIf(screen, op)):
                                logger.info(f"[AUTO] 偵測到對話選項 {op}，點擊處理")
                                Sleep(2)
                                counter += 1
                                found_any_option = True
                                break
                    
                    if found_any_option:
                        continue

                    # 如果都沒匹配到，點擊螢幕中心嘗試關閉對話框
                    logger.info("[AUTO] 未匹配到已知對話框，點擊螢幕中心")
                    Press([450, 800])
                    Sleep(0.5)
                    counter += 1
                    continue

            # 移除 combatActive 相關的配置，因為上面已經檢查過了
            identifyConfig = [
                ('chestFlag',     DungeonState.Chest),   # 寶箱優先
                ('whowillopenit', DungeonState.Chest),   # 寶箱優先
                ('dungFlag',      DungeonState.Dungeon),
                ('mapFlag',       DungeonState.Map),
                ]

            for pattern, state in identifyConfig:
                # combatActive 和 dungFlag 使用較低閾值（串流品質問題）
                if pattern.startswith('combatActive'):
                    result = CheckIf(screen, pattern, threshold=0.70)
                elif pattern == 'dungFlag':
                    result = CheckIf(screen, pattern, threshold=0.75)
                else:
                    result = CheckIf(screen, pattern)
                if result:
                    elapsed_ms = (time.time() - state_check_start) * 1000
                    logger.debug(f"[狀態識別] 匹配成功: {pattern} -> {state} (耗時 {elapsed_ms:.0f} ms)")
                    # 如果設置了樓層選擇但檢測到 dungFlag，不要立即返回，繼續等待傳送完成
                    if runtimeContext._HARKEN_FLOOR_TARGET is not None and pattern == 'dungFlag':
                        logger.debug(f"哈肯樓層選擇: 檢測到 dungFlag 但正在等待傳送，繼續等待...")
                        continue
                    # 確認已進入地城（用於黑屏偵測）
                    if not runtimeContext._DUNGEON_CONFIRMED:
                        runtimeContext._DUNGEON_CONFIRMED = True
                        logger.info("[狀態識別] 已確認進入地城")
                    
                    if not runtimeContext._DUNGEON_CONFIRMED:
                        runtimeContext._DUNGEON_CONFIRMED = True
                        logger.info("[狀態識別] 已確認進入地城")
                    
                    MonitorState.current_state = "Dungeon"
                    MonitorState.current_dungeon_state = state.name if state else None
                    return State.Dungeon, state, screen

            if CheckIf(screen,'someonedead'):
                AddImportantInfo("他們活了,活了!")
                runtimeContext._COUNTERDEATH += 1  # 增加死亡計數
                MonitorState.death_count = runtimeContext._COUNTERDEATH
                for _ in range(5):
                    Press([400+random.randint(0,100),750+random.randint(0,100)])
                    Sleep(1)

            # 正常的 returnText 和 returntoTown 處理（當沒有設置樓層選擇時）
            if runtimeContext._HARKEN_FLOOR_TARGET is None:
                if Press(CheckIf(screen, "returnText")):
                    Sleep(2)
                    counter += 1
                    continue

                if CheckIf(screen,"returntoTown"):
                    if not should_skip_return_to_town():
                        # 回城
                        FindCoordsOrElseExecuteFallbackAndWait('Inn',['return',[1,1]],1)
                        # 回城
                        FindCoordsOrElseExecuteFallbackAndWait('Inn',['return',[1,1]],1)
                        MonitorState.current_state = "Inn"
                        MonitorState.current_dungeon_state = "Quit"
                        return State.Inn,DungeonState.Quit, screen
                    else:
                        # 跳過回城，繼續刷地城
                        # 跳過回城時，執行 _EOT 中非 intoWorldMap 的步驟（例如選樓層）
                        for info in quest._EOT:
                            if info[1] == "intoWorldMap":
                                logger.info(f"跳過 intoWorldMap 步驟")
                                continue
                            else:
                                pos = FindCoordsOrElseExecuteFallbackAndWait(info[1], info[2], info[3])
                                if info[0] == "press":
                                    Press(pos)
                        Sleep(2)
                        reset_ae_caster_flags()  # 重新進入地城，重置 AE 手旗標
                        runtimeContext._AOE_TRIGGERED_THIS_DUNGEON = True  # 跳過黑屏檢測
                        runtimeContext._RESET_TARGETS_PENDING = True  # [關鍵修復] 標記需要重置目標列表
                        runtimeContext._RESTART_OPEN_MAP_PENDING = True  # [新增] 跳過 Resume 優化，強制重新開地圖
                        runtimeContext._DUNGEON_CONFIRMED = False  # [新增] 重置地城確認標記
                        logger.info(f"[DEBUG] 跳過回城(returntoTown): RESET_TARGETS_PENDING={runtimeContext._RESET_TARGETS_PENDING}, RESTART_OPEN_MAP_PENDING={runtimeContext._RESTART_OPEN_MAP_PENDING}")
                        MonitorState.current_state = "Dungeon"
                        MonitorState.current_dungeon_state = None
                        return State.Dungeon, None, ScreenShot()



            if pos:=CheckIf(screen,"openworldmap"):
                if runtimeContext._DUNGEON_CONFIRMED:
                    runtimeContext._DUNGEON_CONFIRMED = False
                    logger.info("[狀態識別] 偵測到世界地圖，視為離開地城，回傳 Quit")
                    MonitorState.current_state = "Dungeon"
                    MonitorState.current_dungeon_state = "Quit"
                    return State.Dungeon, DungeonState.Quit, screen
                
                # 處理世界地圖回程邏輯，不遞歸調用 IdentifyState 以免 double-count
                if not should_skip_return_to_town():
                    # 回城
                    Press(pos)
                    # 讓主循環下一次迭代處理新狀態
                    counter += 1
                    continue
                else:
                    # 跳過回城，繼續刷地城
                    # 提前重置旗標，避免進入地城過場黑屏時誤觸發首戰打斷
                    reset_ae_caster_flags()
                    runtimeContext._AOE_TRIGGERED_THIS_DUNGEON = True  # 跳過黑屏檢測
                    # 跳過回城時，執行 _EOT 中非 intoWorldMap 的步驟（例如選樓層）
                    for info in quest._EOT:
                        if info[1] == "intoWorldMap":
                            logger.info(f"跳過 intoWorldMap 步驟")
                            continue
                        else:
                            pos = FindCoordsOrElseExecuteFallbackAndWait(info[1], info[2], info[3])
                            if info[0] == "press":
                                Press(pos)
                    Sleep(2)
                    runtimeContext._RESET_TARGETS_PENDING = True  # [關鍵修復] 標記需要重置目標列表
                    runtimeContext._RESTART_OPEN_MAP_PENDING = True  # [新增] 跳過 Resume 優化，強制重新開地圖
                    runtimeContext._DUNGEON_CONFIRMED = False  # [新增] 重置地城確認標記
                    logger.info(f"[DEBUG] 跳過回城(openworldmap): RESET_TARGETS_PENDING={runtimeContext._RESET_TARGETS_PENDING}, RESTART_OPEN_MAP_PENDING={runtimeContext._RESTART_OPEN_MAP_PENDING}")
                    MonitorState.current_state = "Dungeon"
                    MonitorState.current_dungeon_state = None
                    return State.Dungeon, None, ScreenShot()

            if CheckIf(screen,"RoyalCityLuknalia"):
                FindCoordsOrElseExecuteFallbackAndWait(['Inn','dungFlag'],['RoyalCityLuknalia',[1,1]],1)
                if CheckIf(scn:=ScreenShot(),'Inn'):
                    MonitorState.current_state = "Inn"
                    MonitorState.current_dungeon_state = "Quit"
                    return State.Inn,DungeonState.Quit, screen
                elif CheckIf(scn,'dungFlag'):
                    MonitorState.current_state = "Dungeon"
                    MonitorState.current_dungeon_state = None
                    return State.Dungeon,None, screen

            if CheckIf(screen,"fortressworldmap"):
                FindCoordsOrElseExecuteFallbackAndWait(['Inn','dungFlag'],['fortressworldmap',[1,1]],1)
                if CheckIf(scn:=ScreenShot(),'Inn'):
                    return State.Inn,DungeonState.Quit, screen
                elif CheckIf(scn,'dungFlag'):
                    return State.Dungeon,None, screen

            if CheckIf(screen, "Deepsnow", threshold=0.7):
                logger.info(f"[狀態識別] 發現 Deepsnow (低閾值觸發), 嘗試進入...")
                FindCoordsOrElseExecuteFallbackAndWait(['Inn','dungFlag'],['Deepsnow',[1,1]],1)
                if CheckIf(scn:=ScreenShot(),'Inn'):
                    MonitorState.current_state = "Inn"
                    MonitorState.current_dungeon_state = "Quit"
                    return State.Inn, DungeonState.Quit, screen
                elif CheckIf(scn,'dungFlag'):
                    MonitorState.current_state = "Dungeon"
                    MonitorState.current_dungeon_state = None
                    return State.Dungeon, None, screen

            # [新增] 通用世界地圖處理 (放在特定城鎮判斷之後)
            # 這段邏輯是為了防止 openworldmap 判斷失敗時的長時間等待
            # 它模仿了 fallback 的縮放與確認邏輯，但改為在第一時間執行
            if CheckIf(screen, "worldmapflag"):
                if runtimeContext._DUNGEON_CONFIRMED:
                    runtimeContext._DUNGEON_CONFIRMED = False
                    logger.info("[狀態識別] 偵測到 worldmapflag，視為離開地城，回傳 Quit")
                    MonitorState.current_state = "Dungeon"
                    MonitorState.current_dungeon_state = "Quit"
                    return State.Dungeon, DungeonState.Quit, screen
                else:
                    logger.info("[狀態識別] 偵測到 worldmapflag (無地城確認)，嘗試處理回城或接續")
                    
                    if not should_skip_return_to_town():
                         # [關鍵] 複製 fallback 的縮放與確認邏輯
                         logger.info("檢測到世界地圖, 嘗試縮放並返回城市...")
                         for _ in range(3):
                             Press([100,1500])
                             Sleep(0.5)
                         Press([250,1500])
                         Sleep(1)
                         
                         # 強制使用 ADB 截圖
                         scn = _ScreenShot_ADB()
                         if pos := CheckIf(scn, 'Deepsnow'):
                             logger.info(f"點擊 Deepsnow 返回城市 (位置: {pos})")
                             Press(pos)
                             Sleep(2)
                             return IdentifyState()
                         else:
                             # 找不到 Deepsnow
                             logger.info("找不到 Deepsnow, 嘗試關閉世界地圖")
                             PressReturn()
                             Sleep(1)
                             return IdentifyState()
                    else:
                        # 跳過回城，繼續刷地城
                        reset_ae_caster_flags()
                        runtimeContext._AOE_TRIGGERED_THIS_DUNGEON = True
                        for info in quest._EOT:
                            if info[1] == "intoWorldMap": continue
                            else:
                                pos = FindCoordsOrElseExecuteFallbackAndWait(info[1], info[2], info[3])
                                if info[0] == "press": Press(pos)
                        Sleep(2)
                        MonitorState.current_state = "Dungeon"
                        MonitorState.current_dungeon_state = None
                        return State.Dungeon, None, ScreenShot()

            if (CheckIf(screen,'Inn')):
                return State.Inn, None, screen

            if quest._SPECIALFORCESTOPINGSYMBOL != None:
                for symbol in quest._SPECIALFORCESTOPINGSYMBOL:
                        if CheckIf(screen,symbol):
                            return State.Quit,DungeonState.Quit,screen
                        
            if quest._SPECIALDIALOGOPTION != None:
                for option in quest._SPECIALDIALOGOPTION:
                    if Press(CheckIf(screen,option)):
                        return IdentifyState()

            if counter>=4:
                logger.info("看起來遇到了一些不太尋常的情況...")
                # [異常截圖] 只在首次進入異常狀態時截圖
                if counter == 4:
                    try:
                        record_dir = os.path.join(LOGS_FOLDER_NAME, "record")
                        os.makedirs(record_dir, exist_ok=True)
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filename = os.path.join(record_dir, f"unusual_{timestamp}.png")
                        cv2.imwrite(filename, screen)
                        logger.info(f"[異常截圖] 已保存異常狀態截圖: {filename}")
                    except Exception as e:
                        logger.error(f"[異常截圖] 保存失敗: {e}")
                # [最高優先級] 檢測 returnText，避免誤觸 harken 導致傳送
                if Press(CheckIf(screen, "returnText")):
                    logger.info("[異常處理] 偵測到 returnText，點擊返回")
                    Sleep(2)
                    return IdentifyState()
                if Press(CheckIf(screen, "ReturnText")):
                    logger.info("[異常處理] 偵測到 ReturnText，點擊返回")
                    Sleep(2)
                    return IdentifyState()
                if (CheckIf(screen,'RiseAgain')):
                    RiseAgainReset(reason = 'combat')
                    return IdentifyState()
                if CheckIf(screen, 'worldmapflag'):
                    logger.info("檢測到世界地圖, 嘗試縮放並返回城市...")
                    for _ in range(3):
                        Press([100,1500])
                        Sleep(0.5)
                    Press([250,1500])
                    Sleep(1)
                    # [關鍵操作] 強制使用 ADB 截圖，避免串流幀延遲
                    scn = _ScreenShot_ADB()
                    if pos:=CheckIf(scn, 'Deepsnow'):
                        logger.info(f"點擊 Deepsnow 返回城市 (位置: {pos})")
                        Press(pos)
                        Sleep(2)
                        return IdentifyState()
                    else:
                        logger.info("找不到 Deepsnow, 嘗試關閉世界地圖")
                        PressReturn()
                        Sleep(1)
                        return IdentifyState()
                if Press(CheckIf(screen, 'sandman_recover')):
                    return IdentifyState()
                if (CheckIf(screen,'cursedWheel_timeLeap')):
                    setting._MSGQUEUE.put(('turn_to_7000G',""))
                    raise SystemExit
                if (pos:=CheckIf(screen,'ambush')) and setting._KARMAADJUST.startswith('-'):
                    new_str = None
                    num_str = setting._KARMAADJUST[1:]
                    if num_str.isdigit():
                        num = int(num_str)
                        if num != 0:
                            new_str = f"-{num - 1}"
                        else:
                            new_str = f"+0"
                    if new_str is not None:
                        logger.info(f"即將進行善惡值調整. 剩餘次數:{new_str}")
                        AddImportantInfo(f"新的善惡:{new_str}")
                        setting._KARMAADJUST = new_str
                        SetOneVarInConfig("_KARMAADJUST",setting._KARMAADJUST)
                        Press(pos)
                        logger.info("伏擊起手!")
                        # logger.info("Ambush! Always starts with Ambush.")
                        Sleep(2)
                if (pos:=CheckIf(screen,'ignore')) and setting._KARMAADJUST.startswith('+'):
                    new_str = None
                    num_str = setting._KARMAADJUST[1:]
                    if num_str.isdigit():
                        num = int(num_str)
                        if num != 0:
                            new_str = f"+{num - 1}"
                        else:
                            new_str = f"-0"
                    if new_str is not None:
                        logger.info(f"即將進行善惡值調整. 剩餘次數:{new_str}")
                        AddImportantInfo(f"新的善惡:{new_str}")
                        setting._KARMAADJUST = new_str
                        SetOneVarInConfig("_KARMAADJUST",setting._KARMAADJUST)
                        Press(pos)
                        logger.info("積善行德!")
                        # logger.info("")
                        Sleep(2)

                dialogOption = [
                    'adventurersbones',
                    'halfBone',
                    'nothanks',
                    'strange_things',
                    'blessing',
                    'DontBuyIt',
                    'donthelp',
                    'buyNothing',
                    'Nope',
                    'ignorethequest',
                    'dontGiveAntitoxin',
                    'pass',
                                ]
                for op in dialogOption:
                    if Press(CheckIf(screen, op)):
                        Sleep(2)
                        if op == 'adventurersbones':
                            AddImportantInfo("購買了骨頭.")
                        if op == 'halfBone':
                            AddImportantInfo("購買了屍油.")
                        return IdentifyState()
                
                if (CheckIf(screen,'multipeopledead')):
                    runtimeContext._SUICIDE = True # 準備嘗試自殺
                    logger.info("死了好幾個, 慘哦")
                    # logger.info("Corpses strew the screen")
                    Press(CheckIf(screen,'skull'))
                    Sleep(2)
                if Press(CheckIf(screen,'startdownload')):
                    logger.info("確認, 下載, 確認.")
                    # logger.info("")
                    Sleep(2)
                if Press(CheckIf(screen,'totitle')):
                    logger.info("網絡故障警報! 網絡故障警報! 返回標題, 重複, 返回標題!")
                    return IdentifyState()
                PressReturn()
                Sleep(0.5)
                PressReturn()
            if counter>15:
                black = LoadTemplateImage("blackScreen")
                mean_diff = cv2.absdiff(black, screen).mean()/255
                if mean_diff<0.02:
                    logger.info(f"警告: 遊戲畫面長時間處於黑屏中, 即將重啓({25-counter})")
            if counter>= 25:
                logger.info("看起來遇到了一些非同尋常的情況...重啓遊戲.")
                restartGame()
                counter = 0
            if counter>=4:
                Press([1,1])
                Sleep(0.25)
                Press([1,1])
                Sleep(0.25)
                Press([1,1])

            elapsed_ms = (time.time() - state_check_start) * 1000
            logger.debug(f"[狀態識別] 本輪未匹配 (耗時 {elapsed_ms:.0f} ms)")
            Sleep(1)
            counter += 1
        return None, None, screen
    def GameFrozenCheck(queue, scn):
        if scn is None:
            raise ValueError("GameFrozenCheck被傳入了一個空值.")
        logger.info("卡死檢測截圖")
        LENGTH = 10
        if len(queue) > LENGTH:
            queue = []
        queue.append(scn)
        totalDiff = 0
        t = time.time()
        if len(queue)==LENGTH:
            for i in range(1,LENGTH):
                grayThis = cv2.cvtColor(queue[i], cv2.COLOR_BGR2GRAY)
                grayLast = cv2.cvtColor(queue[i-1], cv2.COLOR_BGR2GRAY)
                mean_diff = cv2.absdiff(grayThis, grayLast).mean()/255
                totalDiff += mean_diff
            logger.info(f"卡死檢測耗時: {time.time()-t:.5f}秒")
            logger.info(f"卡死檢測結果: {totalDiff:.5f}")
            if totalDiff<=0.15:
                return queue, True
        return queue, False
    
    def get_organize_items():
        """動態讀取 Organize 資料夾中的物品圖片"""
        import glob
        # 使用 ResourcePath 和 IMAGE_FOLDER 來取得正確路徑
        organize_path = ResourcePath(os.path.join(IMAGE_FOLDER, 'Organize'))
        items = []
        for ext in ['*.png', '*.jpg']:
            items.extend(glob.glob(os.path.join(organize_path, ext)))
        # 返回相對路徑名稱（不含副檔名）
        return [os.path.splitext(os.path.basename(f))[0] for f in items]
    
    def StateOrganizeBackpack(num_characters):
        """整理背包功能：將 Organize 資料夾中的物品放入倉庫

        流程：
        0. 點選 Inn 打開角色選擇畫面（等待看到 inventory 按鈕）
        1. 點選角色
        2. 點選 inventory，彈出 inventory 視窗
        3. 找尋要整理的設備
           3.1 點選設備後，在彈出框中點選 putinstorage
           3.2 點選 putinstorage 後自動關閉回到 inventory 視窗
           3.3 繼續找尋符合的設備，直到畫面中沒有符合的設備
        4. 按下 X 關閉 inventory 視窗
        5. 如果還有下一位，點選下一位角色，重複 1-4
        6. 關閉角色選擇畫面回到 Inn 主畫面
        """
        if num_characters <= 0:
            return

        items_to_organize = get_organize_items()
        if not items_to_organize:
            logger.info("Organize 資料夾為空，跳過整理")
            return

        logger.info(f"開始整理 {num_characters} 人的背包，物品: {items_to_organize}")

        for char_index in range(num_characters):
            logger.info(f"整理第 {char_index} 號角色背包")
            
            # 角色座標（固定值）
            char_positions = [
                [162, 1333],   # 角色 0
                [465, 1333],   # 角色 1
                [750, 1333],   # 角色 2
                [162, 1515],   # 角色 3
                [465, 1515],   # 角色 4
                [750, 1515],   # 角色 5
            ]
            char_pos = char_positions[char_index]
            
            # 步驟1: 點選角色
            logger.info(f"步驟1: 點選角色 {char_index} 位置 {char_pos}")
            Press(char_pos)
            Sleep(5)  # 等待角色詳情載入
            
            # 步驟2: 點選 inventory 打開背包
            logger.info("步驟2: 點選 inventory 打開背包")
            scn = ScreenShot()
            inv_pos = CheckIf(scn, 'inventory')
            if inv_pos:
                Press(inv_pos)
                Sleep(5)
            else:
                logger.warning("找不到 inventory 按鈕，跳過此角色")
                PressReturn()
                Sleep(5)
                continue
            
            # 步驟3: 對每個物品執行整理
            logger.info("步驟3: 開始整理物品")
            for item in items_to_organize:
                item_path = f'Organize/{item}'
                MAX_ITEM_ORGANIZE = 50  # 單個物品最多整理次數
                item_organize_count = 0

                # 可能需要多次嘗試（如果有多個相同物品）
                while item_organize_count < MAX_ITEM_ORGANIZE:
                    if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                        return
                    scn = ScreenShot()
                    item_pos = CheckIf(scn, item_path)

                    if not item_pos:
                        logger.info(f"沒有找到物品: {item}")
                        break  # 沒有找到物品，跳到下一個物品類型

                    logger.info(f"找到物品: {item}，位置: {item_pos}")
                    Press(item_pos)
                    Sleep(5)

                    # 點擊 putinstorage
                    scn = ScreenShot()
                    put_pos = CheckIf(scn, 'putinstorage')
                    if put_pos:
                        Press(put_pos)
                        Sleep(5)
                        logger.info(f"已將 {item} 放入倉庫")
                        item_organize_count += 1
                    else:
                        logger.warning("找不到 putinstorage 按鈕")
                        PressReturn()
                        Sleep(5)
                        break
                if item_organize_count >= MAX_ITEM_ORGANIZE:
                    logger.warning(f"物品 {item} 整理次數達到上限 {MAX_ITEM_ORGANIZE}，跳過")
            
            # 步驟4: 關閉 inventory 視窗
            logger.info("步驟4: 關閉 inventory")
            scn = ScreenShot()
            close_pos = CheckIf(scn, 'closeInventory')
            if close_pos:
                Press(close_pos)
            else:
                PressReturn()
            Sleep(5)

        # 關閉角色選擇畫面回到 Inn 主畫面
        logger.info("關閉角色選擇畫面")
        PressReturn()
        Sleep(5)

        logger.info("背包整理完成")

    @stoppable
    def StateInn():
        MonitorState.current_state = "Inn"
        MonitorState.current_target = ""
        # 1. 住宿
        if not setting._ACTIVE_ROYALSUITE_REST:
            FindCoordsOrElseExecuteFallbackAndWait('OK',['Inn','Stay','Economy',[1,1]],2)
        else:
            FindCoordsOrElseExecuteFallbackAndWait('OK',['Inn','Stay','royalsuite',[1,1]],2)
        FindCoordsOrElseExecuteFallbackAndWait('Stay',['OK',[299,1464]],2)

        # 2. 自動補給（可選）
        if setting._AUTO_REFILL:
            FindCoordsOrElseExecuteFallbackAndWait('refilled', ['box', 'refill', 'OK', [1, 1]], 2)
            Press([1, 1])
            Sleep(2)

        # 3. 整理背包（可選）
        if setting._ORGANIZE_BACKPACK_ENABLED and setting._ORGANIZE_BACKPACK_COUNT > 0:
            try:
                StateOrganizeBackpack(setting._ORGANIZE_BACKPACK_COUNT)
                # StateOrganizeBackpack 內部已有 PressReturn 離開旅館
            except Exception as e:
                logger.error(f"整理背包失敗: {e}")
                for _ in range(3):
                    PressReturn()
                    Sleep(1)
        else:
            # 沒有整理背包時，在這裡離開旅館
            logger.info("離開旅館")
            PressReturn()
            Sleep(2)
    @stoppable
    def StateEoT():
        MonitorState.current_state = "EoT"
        MonitorState.current_target = ""
        if quest._preEOTcheck:
            if Press(CheckIf(ScreenShot(),quest._preEOTcheck)):
                pass
        for idx, info in enumerate(quest._EOT):
            logger.info(f"[StateEoT] 執行 EOT 步驟 {idx+1}/{len(quest._EOT)}: {info[1]}")
            
            if info[1]=="intoWorldMap":
                TeleportFromCityToWorldLocation(info[2][0],info[2][1])
            else:
                pos = FindCoordsOrElseExecuteFallbackAndWait(info[1],info[2],info[3])
                if info[0]=="press":
                    # 連續嘗試最多 3 次點擊
                    MAX_CLICK_ATTEMPTS = 3
                    click_success = False
                    
                    for attempt in range(MAX_CLICK_ATTEMPTS):
                        Press(pos)
                        logger.info(f"[StateEoT] 點擊了 {info[1]} (嘗試 {attempt+1}/{MAX_CLICK_ATTEMPTS})")
                        Sleep(2)  # 等待過渡動畫
                        
                        # 檢查是否還能找到剛才點擊的圖（如果還在，說明點擊沒生效）
                        scn = ScreenShot()
                        still_there = CheckIf(scn, info[1])
                        
                        if not still_there:
                            # 成功跳轉
                            logger.info(f"[StateEoT] ✓ 成功跳轉，{info[1]} 已消失")
                            click_success = True
                            break
                        else:
                            logger.warning(f"[StateEoT] 點擊 {info[1]} 後畫面沒有跳轉 (嘗試 {attempt+1}/{MAX_CLICK_ATTEMPTS})")
                            # 重新獲取位置，準備下次點擊
                            if attempt < MAX_CLICK_ATTEMPTS - 1:
                                pos = CheckIf(scn, info[1])
                                if not pos:
                                    logger.error(f"[StateEoT] 無法再次找到 {info[1]}，終止重試")
                                    break
                    
                    if not click_success:
                        # 3 次都失敗，返回村莊
                        logger.error(f"[StateEoT] 點擊 {info[1]} 失敗 {MAX_CLICK_ATTEMPTS} 次，返回村莊")
                        PressReturn()
                        Sleep(1)
                        # 由村莊邏輯接手，直接返回讓 IdentifyState 重新識別
                        return
                        
            Sleep(1)  # 每個操作後等待遊戲響應
        Sleep(1)
        Press(CheckIf(ScreenShot(), 'GotoDung'))
    def useForcedPhysicalSkill(screen, doubleConfirmCastSpell_func, reason=""):
        """
        強制使用強力單體技能（用於 AE 手非 AE 角色）
        Args:
            screen: 當前截圖
            doubleConfirmCastSpell_func: 確認施法的函數
            reason: 觸發原因（用於日誌）
        Returns:
            bool: 是否成功使用了技能
        """
        logger.info(f"[強制單體] {reason}，開始執行")
        logger.info(f"[強制單體] 當前戰鬥狀態: battle={runtimeContext._COMBAT_BATTLE_COUNT}, action={runtimeContext._COMBAT_ACTION_COUNT}")
        
        # 先截圖檢查當前狀態
        scn = ScreenShot()
        
        # 檢測 combatAuto 按鈕來判斷是否在手動模式
        # 如果能看到 combatAuto 按鈕，表示目前是手動模式（技能欄應該已經顯示）
        auto_btn = CheckIf(WrapImage(scn, 0.1, 0.3, 1), 'combatAuto', [[700, 1000, 200, 200]])
        auto_btn_2 = CheckIf(scn, 'combatAuto_2', [[700, 1000, 200, 200]])
        is_manual_mode = auto_btn or auto_btn_2
        
        logger.info(f"[強制單體] 自動戰鬥按鈕偵測: combatAuto={auto_btn}, combatAuto_2={auto_btn_2}, 手動模式={is_manual_mode}")
        
        if is_manual_mode:
            # 已經是手動模式，只需輕點一次確保技能欄顯示
            logger.info("[強制單體] 已在手動模式，輕點確保技能欄顯示")
            Press([1, 1])
            Sleep(0.5)
        else:
            # 可能是自動戰鬥模式，需要打斷
            logger.info("[強制單體] 可能在自動戰鬥模式，點擊打斷...")
            for i in range(3):  # 減少到 3 次
                Press([1, 1])
                Sleep(0.3)
                logger.info(f"[強制單體] 打斷點擊 {i+1}/3")
            Sleep(1)  # 等待技能欄顯示
        
        scn = ScreenShot()
        
        # 偵錯：確認是否仍在戰鬥畫面
        flee_pos = CheckIf(scn, 'flee')
        logger.info(f"[強制單體] flee 按鈕偵測: {flee_pos}")
        if not flee_pos:
            logger.warning("[強制單體] 未偵測到 flee 按鈕，可能已離開戰鬥!")
            return False
        
        logger.debug(f"[強制單體] 開始檢測技能，共 {len(PHYSICAL_SKILLS)} 個")
        found_skills = []
        not_found_skills = []
        for skillspell in PHYSICAL_SKILLS:
            # 使用 get_skill_image_path 取得帶數字前綴的實際檔名
            full_path = get_skill_image_path("單體", skillspell)
            if full_path and os.path.exists(full_path):
                filename_no_ext = os.path.basename(full_path).rsplit('.', 1)[0]
                image_path = f'spellskill/單體/{filename_no_ext}'
            else:
                image_path = f'spellskill/單體/{skillspell}'
            
            skill_pos = CheckIf(scn, image_path, threshold=0.70)
            if skill_pos:
                found_skills.append(skillspell)
                logger.info(f"[強制單體] 使用技能: {skillspell}")
                Press(skill_pos)
                doubleConfirmCastSpell_func()
                return True
            else:
                not_found_skills.append(skillspell)
        
        # 保存偵錯截圖
        # import os - removed to fix UnboundLocalError
        debug_dir = os.path.join(os.path.dirname(__file__), "debug_screenshots")
        os.makedirs(debug_dir, exist_ok=True)
        debug_path = os.path.join(debug_dir, f"skill_not_found_pos{runtimeContext._COMBAT_ACTION_COUNT}_{int(time.time())}.png")
        cv2.imwrite(debug_path, scn)
        logger.warning(f"[強制單體] 未找到可用的強力單體技能! 已檢查: {len(not_found_skills)} 個技能")
        logger.warning(f"[強制單體] 偵錯截圖已保存: {debug_path}")
        
        # 找不到強力單體技能時，改用普攻
        logger.info("[強制單體] 改用普攻")
        return use_normal_attack()
    def useForcedAOESkill(screen, doubleConfirmCastSpell_func, reason=""):
        """
        強制使用全體技能
        Args:
            screen: 當前截圖
            doubleConfirmCastSpell_func: 確認施法的函數
            reason: 觸發原因（用於日誌）
        Returns:
            bool: 是否成功使用了技能
        """
        logger.info(f"{reason}，強制使用全體技能")

        # 先打斷自動戰鬥（點擊畫面空白處）
        logger.info("點擊打斷自動戰鬥...")
        for _ in range(3):
            Press([1, 1])
            Sleep(0.5)
        scn = ScreenShot()

        for skillspell in ALL_AOE_SKILLS:
            # 找到技能所屬類別並取得正確路徑
            skill_cat = None
            for cat in ["全體", "秘術", "橫排"]:
                if skillspell in SKILLS_BY_CATEGORY.get(cat, []):
                    skill_cat = cat
                    break
            
            if skill_cat:
                full_path = get_skill_image_path(skill_cat, skillspell)
                if full_path and os.path.exists(full_path):
                    folder = SKILL_CATEGORIES.get(skill_cat, {}).get("folder", skill_cat)
                    filename_no_ext = os.path.basename(full_path).rsplit('.', 1)[0]
                    skill_path = f'spellskill/{folder}/{filename_no_ext}'
                else:
                    folder = SKILL_CATEGORIES.get(skill_cat, {}).get("folder", skill_cat)
                    skill_path = f'spellskill/{folder}/{skillspell}'
            else:
                skill_path = 'spellskill/' + skillspell
                
            if Press(CheckIf(scn, skill_path, threshold=0.70)):
                logger.info(f"強制使用全體技能: {skillspell}")
                doubleConfirmCastSpell_func()
                return True
        logger.info("未找到可用的全體技能")
        return False

    # === AE 手獨立函數 ===
    def get_ae_caster_type(action_count, setting):
        """判斷當前行動是否為設定的順序
        Args:
            action_count: 當前行動次數
            setting: 設定物件
        Returns:
            0: 非設定順序
            1~6: 對應順序（如果該順序有設定技能）
        """
        # 計算當前是第幾個角色（1~6）
        position = ((action_count - 1) % 6) + 1
        
        # 檢查該順序是否有設定技能
        count = setting._AE_CASTER_COUNT
        if position <= count:
            skill = getattr(setting, f"_AE_CASTER_{position}_SKILL", "")
            if skill:  # 有設定技能
                logger.info(f"[技能施放] action={action_count}, position={position}, skill={skill}")
                return position
        
        logger.info(f"[技能施放] action={action_count}, position={position}, 非設定順序")
        return 0

    def use_normal_attack():
        """使用普攻（動態目標判定）"""
        scn = ScreenShot()
        # 使用新的資料夾結構取得普攻路徑
        full_path = get_skill_image_path("普攻", "attack")
        if full_path and os.path.exists(full_path):
            filename_no_ext = os.path.basename(full_path).rsplit('.', 1)[0]
            attack_path = f'spellskill/普攻/{filename_no_ext}'
        else:
            attack_path = 'spellskill/普攻/attack'
        
        if Press(CheckIf(scn, attack_path)):
            logger.info("[順序] 使用普攻")
            Sleep(0.5)
            scn = ScreenShot()
            # 採用與單體技能相同的目標判定邏輯
            next_pos = CheckIf(scn, 'next', threshold=0.70)
            if next_pos:
                # 點擊多個位置覆蓋不同大小敵人
                target_x1 = next_pos[0] - 15
                target_x2 = next_pos[0]
                target_y1 = next_pos[1] + 100
                target_y2 = next_pos[1] + 170
                target_y3 = next_pos[1] + 260
                logger.info("[普攻] 根據 next 座標點擊敵人")
                Press([target_x1, target_y1])
                Sleep(0.1)
                Press([target_x1, target_y2])
                Sleep(0.1)
                Press([target_x1, target_y3])
                Sleep(0.1)
                Press([target_x2, target_y1])
                Sleep(0.1)
                Press([target_x2, target_y2])
                Sleep(0.1)
                Press([target_x2, target_y3])
            else:
                # 找不到 next 時的固定座標保底
                logger.info("[普攻] 找不到 next，使用固定座標保底")
                Press([450, 750])
                Sleep(0.2)
                Press([450, 800])
                Sleep(0.2)
                Press([450, 900])
            
            Sleep(0.5)
            return True
        return False

    def use_ae_caster_skill(caster_type, setting):
        """AE 手使用指定技能（包括普攻）
        Args:
            caster_type: 1 或 2，對應 AE 手 1 或 AE 手 2
            setting: 設定物件
        Returns:
            bool: 是否成功使用技能
        """
        # 根據順序取得技能和等級設定
        skill = getattr(setting, f"_AE_CASTER_{caster_type}_SKILL", "")
        level = getattr(setting, f"_AE_CASTER_{caster_type}_LEVEL", "關閉")

        if not skill:
            logger.info(f"[順序 {caster_type}] 未設定技能")
            return False

        # 如果是普攻，使用普攻邏輯
        if skill == "attack":
            logger.info(f"[順序 {caster_type}] 使用普攻")
            return use_normal_attack()

        # 偵測是否已在手動模式
        scn = ScreenShot()
        auto_btn = CheckIf(WrapImage(scn, 0.1, 0.3, 1), 'combatAuto', [[700, 1000, 200, 200]])
        auto_btn_2 = CheckIf(scn, 'combatAuto_2', [[700, 1000, 200, 200]])
        is_manual_mode = auto_btn or auto_btn_2
        
        logger.info(f"[順序 {caster_type}] 自動戰鬥按鈕偵測: 手動模式={is_manual_mode}")
        
        if is_manual_mode:
            # 已經是手動模式，只輕點一次確保技能欄顯示
            logger.info(f"[順序 {caster_type}] 已在手動模式，輕點確保技能欄顯示")
            Press([1, 1])
            Sleep(0.5)
        else:
            # 需要打斷自動戰鬥
            logger.info(f"[順序 {caster_type}] 打斷自動戰鬥...")
            for _ in range(3):
                Press([1, 1])
                Sleep(0.5)
            Sleep(1)  # 等待技能欄顯示

        scn = ScreenShot()
        
        # 根據技能名稱找到所屬類別並取得正確路徑
        skill_category = None
        for cat, skills in SKILLS_BY_CATEGORY.items():
            if skill in skills:
                skill_category = cat
                break
        
        if skill_category:
            full_path = get_skill_image_path(skill_category, skill)
            if full_path and os.path.exists(full_path):
                folder = SKILL_CATEGORIES.get(skill_category, {}).get("folder", skill_category)
                filename_no_ext = os.path.basename(full_path).rsplit('.', 1)[0]
                skill_path = f'spellskill/{folder}/{filename_no_ext}'
            else:
                folder = SKILL_CATEGORIES.get(skill_category, {}).get("folder", skill_category)
                skill_path = f'spellskill/{folder}/{skill}'
        else:
            skill_path = 'spellskill/' + skill  # fallback for unknown skills
        
        logger.info(f"[順序 {caster_type}] 搜尋技能: {skill_path}")
        if Press(CheckIf(scn, skill_path, threshold=0.70)):
            logger.info(f"[順序 {caster_type}] 使用技能: {skill}")
            Sleep(1)
            scn = ScreenShot()

            # 如果設定了技能等級，自動升級
            SKILL_LEVEL_X = {"LV2": 251, "LV3": 378, "LV4": 500, "LV5": 625}
            if level != "關閉" and level in SKILL_LEVEL_X:
                lv1_pos = CheckIf(scn, 'lv1_selected', roi=[[0, 1188, 900, 112]])
                if lv1_pos:
                    logger.info(f"[順序 {caster_type}] 升級技能到 {level}")
                    Press([SKILL_LEVEL_X[level], lv1_pos[1]])
                    Sleep(0.3)
                    scn = ScreenShot()

            # 判斷技能類型

            # 判斷技能類型
            is_single_target = skill not in ALL_AOE_SKILLS
            
            if is_single_target:
                # 單體技能：直接點擊目標敵人（不需要 OK）
                logger.info(f"[順序 {caster_type}] 單體技能，點擊目標敵人")
                # 找 next 按鈕位置作為參考
                next_pos = CheckIf(scn, 'next', threshold=0.70)
                if next_pos:
                    # 點擊 4 個目標位置（覆蓋更多可能的敵人位置）
                    target_x1 = next_pos[0] - 15  # X 軸偏移 -15
                    target_x2 = next_pos[0]       # X 軸不偏移
                    target_x3 = next_pos[0]       # X 軸不偏移
                    target_y1 = next_pos[1] + 100
                    target_y2 = next_pos[1] + 170
                    target_y3= next_pos[1] + 260
                    logger.info(f"[順序 {caster_type}] 點擊 4 個目標位置")
                    Press([target_x1, target_y1])
                    Sleep(0.1)
                    Press([target_x1, target_y2])
                    Sleep(0.1)
                    Press([target_x1, target_y3])
                    Sleep(0.1)
                    Press([target_x2, target_y1])
                    Sleep(0.1)
                    Press([target_x2, target_y2])
                    Sleep(0.1)
                    Press([target_x2, target_y3])
                else:
                    # 如果找不到 next，使用固定座標
                    logger.info(f"[順序 {caster_type}] 找不到 next 按鈕，使用固定座標點擊敵人")
                    Press([450, 750])
                    Sleep(0.2)
                    Press([450, 800])
                    Sleep(0.2)
                    Press([450, 900])
                logger.info(f"[順序 {caster_type}] 等待技能動畫完成...")
                Sleep(2)  # 增加等待時間，讓遊戲完成動畫並切換角色
            else:
                # AOE 技能：可能需要點擊 OK 確認
                ok_pos = CheckIf(scn, 'OK')
                if ok_pos:
                    logger.info(f"[順序 {caster_type}] 點擊 OK 確認")
                    Press(ok_pos)
                    Sleep(1)
            return True

        logger.info(f"[順序 {caster_type}] 找不到技能: {skill}")
        return False

    def enable_auto_combat():
        """開啟自動戰鬥"""
        logger.info("[順序] 開啟自動戰鬥")
        scn = ScreenShot()
        if not Press(CheckIf(WrapImage(scn, 0.1, 0.3, 1), 'combatAuto', [[700, 1000, 200, 200]])):
            Press(CheckIf(scn, 'combatAuto_2', [[700, 1000, 200, 200]]))
        Sleep(2)

    def reset_ae_caster_flags():
        """重置戰鬥相關旗標，用於新地城開始時"""
        nonlocal runtimeContext

        # [修正] 使用 _DUNGEON_REPEAT_COUNT 作為間隔計數基準
        # 因為跳過回城時 _COUNTERDUNG 不會增加，只有 _DUNGEON_REPEAT_COUNT 會遞增
        # 第 0 場 (首場) 符合觸發條件，第 1~N 場不符合
        eff_counter = runtimeContext._DUNGEON_REPEAT_COUNT
        ae_interval_match = (eff_counter % (setting._AE_CASTER_INTERVAL + 1) == 0)
        if setting._AE_CASTER_INTERVAL == 0:
            ae_interval_match = True

        # [關鍵修復] 如果間隔不匹配，則代表本場地城為自動戰鬥場次
        # 我們必須在初始化時就立起 flag，否則 IdentifyState 會在第一場戰鬥前打斷黑屏
        if not ae_interval_match and not runtimeContext._RESTART_SKIP_INTERVAL_THIS_DUNGEON:
            runtimeContext._AOE_TRIGGERED_THIS_DUNGEON = True
            logger.info(f"[技能施放] 地城循環第 {eff_counter + 1} 場，間隔不匹配 -> 預設自動戰鬥（跳過黑屏）")
        else:
            runtimeContext._AOE_TRIGGERED_THIS_DUNGEON = False
            logger.info(f"[技能施放] 地城循環第 {eff_counter + 1} 場，符合觸發週期 -> 重置旗標")

        runtimeContext._AE_CASTER_FIRST_ATTACK_DONE = False
        runtimeContext._COMBAT_ACTION_COUNT = 0
        runtimeContext._COMBAT_BATTLE_COUNT = 0
        runtimeContext._DUNGEON_CONFIRMED = False  # 重置地城確認標誌，避免返回時誤觸黑屏檢測
        runtimeContext._IS_FIRST_COMBAT_IN_DUNGEON = True  # 重置首戰標記
        runtimeContext._MID_DUNGEON_START = False  # 重置地城內啟動標記，讓新地城可觸發黑屏偵測
        runtimeContext._RESTART_SKIP_INTERVAL_THIS_DUNGEON = False  # 新地城清除重啟跳過標誌

    def should_skip_return_to_town():
        """判斷是否應該跳過回城（用於連續刷地城功能）
        
        Returns:
            bool: True = 跳過回城繼續刷，False = 需要回城
        """
        nonlocal runtimeContext
        
        # 如果沒有遇到寶箱或戰鬥，總是跳過回城
        if not runtimeContext._MEET_CHEST_OR_COMBAT:
            logger.info("由於沒有遇到任何寶箱或發生任何戰鬥, 跳過回城.")
            return True
        
        # 如果設置了連續刷地城次數
        repeat_limit = setting._DUNGEON_REPEAT_LIMIT
        if repeat_limit > 0:
            # 只在第一次調用時遞增計數器（避免重複調用時重複遞增）
            # 使用 _MEET_CHEST_OR_COMBAT 作為標記，因為完成地城後這個flag為True
            # 回城後會在 State.Inn 中重置為 False
            current_count = runtimeContext._DUNGEON_REPEAT_COUNT + 1
            
            if current_count < repeat_limit:
                logger.info(f"[連續刷地城] 第 {current_count}/{repeat_limit} 次，跳過回城")
                runtimeContext._DUNGEON_REPEAT_COUNT = current_count  # 更新計數器
                return True
            else:
                logger.info(f"[連續刷地城] 已達上限 {repeat_limit} 次，回城休息")
                # 不在這裡重置計數器，而是在 State.Inn 中重置
                runtimeContext._DUNGEON_REPEAT_COUNT = current_count  # 先更新到上限值
                return False
        
        # 預設：需要回城
        return False

    def get_auto_combat_battles(auto_combat_mode):
        """根據自動戰鬥模式返回需要手動的戰鬥場數
        
        Args:
            auto_combat_mode: 自動戰鬥模式字串
        Returns:
            int: 需要手動的戰鬥場數，-1 表示完全手動
        """
        mode_map = {
            "完全自動": 0,    # 不需要手動場次
            "1 場後自動": 1,  # 第 1 場手動
            "2 場後自動": 2,  # 第 1-2 場手動
            "3 場後自動": 3,  # 第 1-3 場手動
            "完全手動": -1    # 永遠手動
        }
        return mode_map.get(auto_combat_mode, 2)  # 預設為 2 場後自動

    def should_enable_auto_combat(battle_count, auto_combat_mode):
        """判斷是否應該開啟自動戰鬥
        
        Args:
            battle_count: 當前第幾戰
            auto_combat_mode: 自動戰鬥模式字串
        Returns:
            bool: 是否應該開啟自動戰鬥
        """
        manual_battles = get_auto_combat_battles(auto_combat_mode)
        if manual_battles == -1:  # 完全手動
            return False
        return battle_count > manual_battles

    def cast_skill_by_category(category, skill_name, level="關閉", target_pos=None):
        """統一的技能施放函數
        
        根據技能類別自動判斷施放方式 (target/ok)，並處理技能等級升級。
        
        Args:
            category: 技能類別 (普攻/單體/橫排/全體/秘術/群控)
            skill_name: 技能名稱
            level: 技能等級 (關閉/LV2~LV5)
        Returns:
            bool: 是否成功施放技能
        """
        if not skill_name:
            logger.warning(f"[技能施放] 技能名稱為空")
            return False
            
        # 如果是普攻，使用普攻邏輯
        if skill_name == "attack" or category == "普攻":
            logger.info(f"[技能施放] 使用普攻")
            return use_normal_attack()
        
        # 取得圖片路徑 - 使用 get_skill_image_path 找到帶數字前綴的實際檔名
        full_image_path = get_skill_image_path(category, skill_name)
        if full_image_path and os.path.exists(full_image_path):
            # 提取相對路徑: 從完整路徑中提取 spellskill/類別/檔名(不含副檔名)
            folder = SKILL_CATEGORIES.get(category, {}).get("folder", category)
            filename_no_ext = os.path.basename(full_image_path).rsplit('.', 1)[0]
            image_path = f'spellskill/{folder}/{filename_no_ext}'
        else:
            # 直接使用類別/技能名格式 (fallback)
            folder = SKILL_CATEGORIES.get(category, {}).get("folder", category)
            image_path = f'spellskill/{folder}/{skill_name}'
        logger.info(f"[順序 {runtimeContext._COMBAT_ACTION_COUNT}] 搜尋技能: {image_path}")

        
        # 確保技能欄可見
        scn = ScreenShot()
        auto_btn = CheckIf(WrapImage(scn, 0.1, 0.3, 1), 'combatAuto', [[700, 1000, 200, 200]])
        auto_btn_2 = CheckIf(scn, 'combatAuto_2', [[700, 1000, 200, 200]])
        is_manual_mode = auto_btn or auto_btn_2
        
        if not is_manual_mode:
            # 可能在自動戰鬥模式，需要打斷
            logger.info(f"[技能施放] 打斷自動戰鬥以顯示技能欄")
            for _ in range(3):
                Press([1, 1])
                Sleep(0.3)
            Sleep(0.5)
        else:
            # 輕點確保技能欄顯示
            Press([1, 1])
            Sleep(0.3)
        
        scn = ScreenShot()
        
        # 搜尋技能按鈕
        # CheckIf 內部會透過 get_multi_templates 自動掃描整個資料夾的所有技能
        skill_pos = CheckIf(scn, image_path, threshold=0.70)
        
        if skill_pos:
            logger.info(f"[技能施放-DEBUG] 找到技能圖片 {image_path} 於 {skill_pos}")
            logger.info(f"[技能施放] 使用技能: {skill_name} ({category})")
            Press(skill_pos)
            Sleep(0.5)
            scn = ScreenShot()
            
            # 處理技能等級
            # 處理技能等級
            # 處理技能等級
            SKILL_LEVEL_X = {"LV2": 251, "LV3": 378, "LV4": 500, "LV5": 625}
            if level != "關閉" and level in SKILL_LEVEL_X:
                # 使用 spellskill/lv1，移除 ROI 以適應不同解析度 (原 ROI y只到1300，實際可能在1301+)
                lv1_pos = CheckIf(scn, 'spellskill/lv1', threshold=0.8)
                if lv1_pos:
                    logger.info(f"[技能施放] 升級技能到 {level}")
                    Press([SKILL_LEVEL_X[level], lv1_pos[1]])
                    Sleep(0.5)
                    scn = ScreenShot()
            
            # 根據施放方式確認技能
            cast_type = get_skill_cast_type(category)
            
            if cast_type == "none":
                # 直接施放技能 (如：防禦)
                logger.info(f"[技能施放] {skill_name} 為直接施放技能，完成行動")
                return True
            elif cast_type == "support":
                # 輔助技能：點擊指定我方位置 (1~6)
                if target_pos and 1 <= target_pos <= 6:
                    pos = PARTY_POSITIONS.get(target_pos)
                    if pos:
                        logger.info(f"[技能施放] 輔助技能 {skill_name}，點擊目標位置 {target_pos}: {pos}")
                        # 等待技能選擇介面完全顯示（參考其他技能的等待時間）
                        Sleep(1)
                        Press(pos)
                        Sleep(0.5)
                        return True
                logger.warning(f"[技能施放] 輔助技能 {skill_name} 未指定有效目標位置 ({target_pos})，不點擊目標")
                return True
            elif cast_type == "ok":
                # AOE 類技能：等待並點擊 OK 確認
                ok_pos = None
                for wait_ok in range(6):  # 最多等待 3 秒 (6 × 0.5s)
                    ok_pos = CheckIf(scn, 'OK')
                    if ok_pos:
                        break
                    Sleep(0.5)
                    scn = ScreenShot()

                if ok_pos:
                    logger.info(f"[技能施放] 點擊 OK 確認 (等待 {wait_ok} 次)")
                    Press(ok_pos)
                    Sleep(1)
                    # 檢查 MP/SP 不足
                    scn = ScreenShot()
                    if CheckIf(scn, 'notenoughsp') or CheckIf(scn, 'notenoughmp'):
                        logger.info("[技能施放] SP/MP 不足，改用普攻")
                        Press(CheckIf(scn, 'notenough_close'))
                        Sleep(0.5)
                        return use_normal_attack()
                else:
                    logger.warning(f"[技能施放] OK 按鈕等待超時，可能技能施放失敗")
            else:
                # 單體/橫排/群控技能：點擊敵人
                next_pos = CheckIf(scn, 'next', threshold=0.70)
                if next_pos:
                    # 點擊多個位置覆蓋不同大小敵人
                    target_x1 = next_pos[0] - 15
                    target_x2 = next_pos[0]
                    target_y1 = next_pos[1] + 100
                    target_y2 = next_pos[1] + 170
                    target_y3 = next_pos[1] + 260
                    logger.info(f"[技能施放] 點擊目標敵人")
                    Press([target_x1, target_y1])
                    Sleep(0.1)
                    Press([target_x1, target_y2])
                    Sleep(0.1)
                    Press([target_x1, target_y3])
                    Sleep(0.1)
                    Press([target_x2, target_y1])
                    Sleep(0.1)
                    Press([target_x2, target_y2])
                    Sleep(0.1)
                    Press([target_x2, target_y3])
                else:
                    # 使用固定座標
                    logger.info(f"[技能施放] 找不到 next，使用固定座標點擊敵人")
                    Press([450, 750])
                    Sleep(0.2)
                    Press([450, 800])
                    Sleep(0.2)
                    Press([450, 900])
                
            Sleep(0.5)
            # scn = ScreenShot() # 移除多餘截圖
            
            Sleep(0.5)
            return True
        
        logger.warning(f"[技能施放] 找不到技能: {skill_name}，改用普攻")
        return use_normal_attack()

    @stoppable
    def StateCombat():
        MonitorState.current_state = "Combat"
        last_character_update = 0
        def update_combat_flag(scn):
            combat_templates = get_combat_active_templates()
            if combat_templates:
                MonitorState.flag_combatActive = max(GetMatchValue(scn, t) for t in combat_templates)
                MonitorState.flag_updates['combatActive'] = time.time()
        def doubleConfirmCastSpell(skill_name=None):
            is_success_aoe = False
            Sleep(0.5)
            scn = ScreenShot()
            update_combat_flag(scn)

            # 等待 OK 按鈕出現 (最多 3 秒)
            ok_pos = None
            for wait_ok in range(6):
                # [網路重試] 檢測網路波動
                if TryPressRetry(scn):
                    logger.info("[戰鬥] 等待 OK 按鈕時偵測到 Retry 選項，點擊重試")
                    Sleep(2)
                    scn = ScreenShot()  # 重新截圖
                    continue
                
                ok_pos = CheckIf(scn, 'OK')
                if ok_pos:
                    break
                Sleep(0.5)
                scn = ScreenShot()

            if ok_pos:
                logger.info(f"[戰鬥] 找到 OK 按鈕，點擊確認")
                Press(ok_pos)
                is_success_aoe = True
                Sleep(2)
                scn = ScreenShot()
                if CheckIf(scn,'notenoughsp') or CheckIf(scn,'notenoughmp'):
                    # SP/MP 不足，關閉提示後點擊 attack 普攻
                    logger.info("[戰鬥] SP/MP 不足，改用普攻")
                    Press(CheckIf(scn,'notenough_close'))
                    Sleep(0.5)
                    scn = ScreenShot()
                    Press(CheckIf(scn, 'spellskill/普攻/attack'))
                    Sleep(0.5)
                    # 點擊六個點位選擇敵人
                    Press([150,750])
                    Sleep(0.1)
                    Press([300,750])
                    Sleep(0.1)
                    Press([450,750])
                    Sleep(0.1)
                    Press([550,750])
                    Sleep(0.1)
                    Press([650,750])
                    Sleep(0.1)
                    Press([750,750])
                    Sleep(0.1)
                    Sleep(1)
            elif pos:=(CheckIf(scn,'next')):
                # 多點幾個位置，覆蓋不同大小的敵人
                Press([pos[0]-15+random.randint(0,30),pos[1]+100+random.randint(0,20)])
                Sleep(0.2)
                Press([pos[0]-15+random.randint(0,30),pos[1]+170+random.randint(0,30)])
                Sleep(0.2)
                Press([pos[0]-15+random.randint(0,30),pos[1]+260+random.randint(0,30)])
                Sleep(1)
                scn = ScreenShot()
                if CheckIf(scn,'notenoughsp') or CheckIf(scn,'notenoughmp'):
                    # SP/MP 不足，關閉提示後點擊 attack 普攻
                    logger.info("[戰鬥] SP/MP 不足，改用普攻")
                    Press(CheckIf(scn,'notenough_close'))
                    Sleep(0.5)
                    scn = ScreenShot()
                    Press(CheckIf(scn, 'spellskill/普攻/attack'))
                    Sleep(0.5)
                    # 點擊六個點位選擇敵人
                    Press([150,750])
                    Sleep(0.1)
                    Press([300,750])
                    Sleep(0.1)
                    Press([450,750])
                    Sleep(0.1)
                    Press([550,750])
                    Sleep(0.1)
                    Press([650,750])
                    Sleep(0.1)
                    Press([750,750])
                    Sleep(0.1)
                    Sleep(1)
            else:
                Press([150,750])
                Sleep(0.1)
                Press([300,750])
                Sleep(0.1)
                Press([450,750])
                Sleep(0.1)
                Press([550,750])
                Sleep(0.1)
                Press([650,750])
                Sleep(0.1)
                Press([750,750])
                Sleep(0.1)
                Sleep(2)
            Sleep(1)
            return (is_success_aoe)

        # ==================== 打王模式獨立處理 ====================
        def BossCombat():
            """
            獨立的打王戰鬥邏輯，從指定預設讀取技能並施放。
            此函數完全獨立，不影響原有戰鬥邏輯。
            """
            nonlocal runtimeContext
            preset_idx = runtimeContext._AUTO_SKILL_PRESET_INDEX
            
            logger.info(f"[打王模式] 進入打王戰鬥，使用預設: {preset_idx + 1}")
            
            # 戰鬥計數器 (與原有邏輯一致)
            if runtimeContext._COMBAT_ACTION_COUNT == 0:
                runtimeContext._COMBAT_BATTLE_COUNT += 1
                logger.info(f"[打王模式] 第 {runtimeContext._COMBAT_BATTLE_COUNT} 戰開始")
            runtimeContext._COMBAT_ACTION_COUNT += 1
            
            # 等待 flee 出現
            logger.info("[打王模式] 等待 flee 出現...")
            flee_seen = False
            for wait_count in range(30):
                screen = ScreenShot()
                update_combat_flag(screen)
                
                # 檢查戰鬥是否已結束（偵測到其他狀態標誌）
                end_markers = ['Inn', 'dungFlag', 'mapFlag', 'chestFlag']
                if any(CheckIf(screen, marker) for marker in end_markers):
                    logger.info(f"[打王模式] 偵測到戰鬥結束標誌，戰鬥已結束")
                    runtimeContext._COMBAT_ACTION_COUNT = 0
                    runtimeContext._AUTO_SKILL_PRESET_INDEX = -1
                    logger.info("[打王模式] 已重置打王模式")
                    return
                
                # 特殊情況檢測
                if CheckIf(screen, 'RiseAgain'):
                    logger.info("[打王模式] 偵測到 RiseAgain，處理復活")
                    RiseAgainReset(reason='boss_combat')
                    return
                
                if CheckIf(screen, 'someonedead'):
                    logger.info("[打王模式] 偵測到有人死亡，嘗試多次點擊以推進對話...")
                    # 仿照 Upstream: 隨機偏移點擊 5 次，確保過場動畫/對話被跳過
                    for _ in range(5):
                        Press([400+random.randint(0,100), 750+random.randint(0,100)])
                        Sleep(1)
                    continue
                
                # 偵測黑屏 (戰鬥結束)
                # [關鍵修正] 只有在已經看到過戰鬥介面 (flee_seen) 之後，黑屏才代表戰鬥結束
                is_black = IsScreenBlack(screen)
                if is_black and flee_seen:
                    logger.info(f"[打王模式] 偵測到轉場黑屏，第 {runtimeContext._COMBAT_BATTLE_COUNT} 戰結束")
                    runtimeContext._COMBAT_ACTION_COUNT = 0
                    
                    # [重要] 戰鬥結束後重置打王模式索引
                    runtimeContext._AUTO_SKILL_PRESET_INDEX = -1
                    logger.info("[打王模式] 戰鬥結束，已重置打王模式")
                    
                    # 黑屏打斷：持續點擊直到黑屏結束
                    logger.info("[打王模式] 開始黑屏打斷，持續點擊...")
                    click_count = 0
                    while IsScreenBlack(ScreenShot()):
                        check_stop_signal()
                        Press([1, 1])
                        click_count += 1
                        Sleep(0.1)
                        if click_count > 100:  # 防止無限迴圈（最多 10 秒）
                            logger.warning("[打王模式] 黑屏持續過久，中斷點擊")
                            break
                    
                    # 黑屏結束後額外點擊，確保完全過場
                    logger.info(f"[打王模式] 黑屏結束（點擊了 {click_count} 次），繼續加速過場...")
                    for _ in range(10):
                        check_stop_signal()
                        Press([1, 1])
                        Sleep(0.3)
                    return
                
                if CheckIf(screen, 'flee'):
                    logger.info(f"[打王模式] flee 出現，等待 {wait_count + 1} 次")
                    flee_seen = True # 標記已看到介面，後續的黑屏才有效
                    break
                Sleep(0.5)
            else:
                logger.warning("[打王模式] flee 等待超時，跳過本次行動")
                return
            
            # 從預設配置讀取技能
            screen = ScreenShot()
            current_char = DetectCharacter(screen)
            
            # [打王模式] 追蹤每個角色的行動次數
            if current_char not in runtimeContext._BOSS_CHARACTER_ACTION_COUNT:
                runtimeContext._BOSS_CHARACTER_ACTION_COUNT[current_char] = 0
            runtimeContext._BOSS_CHARACTER_ACTION_COUNT[current_char] += 1
            char_action_num = runtimeContext._BOSS_CHARACTER_ACTION_COUNT[current_char]
            
            logger.info(f"[打王模式] 角色={current_char}, 第 {char_action_num} 次行動")
            
            # 獲取預設配置（從配置文件直接讀取，因為 setting._SKILL_PRESETS 未被載入）
            skill = "attack"
            level = "關閉"
            target_pos = None
            
            try:
                from utils import LoadConfigFromFile
                config = LoadConfigFromFile()
                skill_presets = config.get("_SKILL_PRESETS", [])
                
                if 0 <= preset_idx < len(skill_presets):
                    config_list = skill_presets[preset_idx]
                    for cfg in config_list:
                        if cfg.get("character") == current_char:
                            # [關鍵修改] 改用角色行動次數而非戰鬥場次
                            if char_action_num == 1:
                                skill = cfg.get("skill_first", "attack")
                                level = cfg.get("level_first", "關閉")
                                target_pos = cfg.get("target_first")
                            else:  # 第 2 次及以後都用 skill_after
                                skill = cfg.get("skill_after", "attack")
                                level = cfg.get("level_after", "關閉")
                                target_pos = cfg.get("target_after")
                            break
            except Exception as e:
                logger.error(f"[打王模式] 讀取預設配置失敗: {e}")
            
            logger.info(f"[打王模式] 技能={skill}, 目標位置={target_pos}")
            
            # 判斷技能類別並施放
            category = None
            is_support_skill = skill in SUPPORT_SKILLS
            
            if skill and skill != "attack":
                for cat, skills in SKILLS_BY_CATEGORY.items():
                    if skill in skills:
                        category = cat
                        break
            
            if skill == "attack" or not category:
                use_normal_attack()
            elif skill and category:
                # 統一呼叫技能施放函數，傳入目標位置（輔助技能會用到）
                cast_skill_by_category(category, skill, level, target_pos)
        
        # ==================== 打王模式判定 (最高優先級) ====================
        if getattr(runtimeContext, '_AUTO_SKILL_PRESET_INDEX', -1) != -1:
            BossCombat()
            return  # 打王模式處理完畢，不進入原有邏輯
        # ==================== 以下為原有邏輯，完全不變 ====================

        # [重啟後重置] 如果是重啟後的第一場戰鬥，強制重置計數器
        if runtimeContext._RESTART_PENDING_BATTLE_RESET:
            logger.info("[戰鬥] 重啟後首次進入戰鬥，重置計數器")
            runtimeContext._COMBAT_ACTION_COUNT = 0
            runtimeContext._COMBAT_BATTLE_COUNT = 0
            runtimeContext._RESTART_PENDING_BATTLE_RESET = False

        # 新戰鬥開始時，增加戰鬥計數器並重置首次普攻標誌
        if runtimeContext._COMBAT_ACTION_COUNT == 0:
            runtimeContext._COMBAT_BATTLE_COUNT += 1
            runtimeContext._AE_CASTER_FIRST_ATTACK_DONE = False  # 每戰重置
            logger.info(f"[技能施放] 第 {runtimeContext._COMBAT_BATTLE_COUNT} 戰開始")

        # 每次進入 StateCombat 增加行動計數器
        runtimeContext._COMBAT_ACTION_COUNT += 1
        logger.info(f"[戰鬥] 行動次數: {runtimeContext._COMBAT_ACTION_COUNT}")

        # [計時器] 戰鬥開始計時（只在首次進入時設置）
        if runtimeContext._TIME_COMBAT == 0:
            runtimeContext._TIME_COMBAT = time.time()
            logger.trace("[計時器] 戰鬥計時開始")

        # 等待 flee 出現，確認玩家可控制角色（所有戰鬥邏輯的前提）
        logger.info("[戰鬥] 等待 flee 出現...")
        for wait_count in range(30):  # 最多等待 15 秒
            screen = ScreenShot()
            update_combat_flag(screen)

            # [異常檢測] 穿插檢測復活/對話/死亡，避免卡在等待 flee
            if CheckIf(screen, 'RiseAgain'):
                logger.info("[戰鬥] flee 等待中偵測到 RiseAgain，中斷並處理復活")
                RiseAgainReset(reason='combat')
                return IdentifyState()
            if CheckIf(screen, 'someonedead'):
                logger.info("[戰鬥] flee 等待中偵測到 someonedead，嘗試多次點擊以推進對話")
                # 仿照 Upstream: 隨機偏移點擊 5 次，確保過場動畫/對話被跳過
                for _ in range(5):
                    Press([400+random.randint(0,100), 750+random.randint(0,100)])
                    Sleep(1)
                return IdentifyState()
            if Press(CheckIf(screen, 'returnText')) or Press(CheckIf(screen, 'ReturnText')):
                logger.info("[戰鬥] flee 等待中偵測到 returnText，中斷並處理對話")
                Sleep(1)
                return IdentifyState()
            
            # [網路重試] 檢測網路波動
            if TryPressRetry(screen):
                logger.info("[戰鬥] flee 等待中偵測到 Retry 選項，點擊重試")
                Sleep(2)
                continue

            # [新增] 檢查是否已經脫離戰鬥 (例如瞬殺或過場過快)
            # 如果出現 寶箱/地城/地圖 標誌，代表戰鬥已結束
            if CheckIf(screen, 'chestFlag'):
                logger.info("[戰鬥] 等待 flee 時發現 chestFlag，判定戰鬥已結束")
                return DungeonState.Chest
            if CheckIf(screen, 'dungFlag') or CheckIf(screen, 'mapFlag'):
                logger.info("[戰鬥] 等待 flee 時發現 dungFlag/mapFlag，判定戰鬥已結束")
                return DungeonState.Dungeon
            
            # [新增] 避免誤判：如果已經進入戰鬥介面 (combatActive) 就不用等 flee 了
            if CheckIf(screen, 'combatActive', threshold=0.75):
                 # logger.debug("[戰鬥] 發現 combatActive，標記戰鬥進行中")
                 pass

            # 偵測黑屏：如果已有行動且偵測到黑屏，表示戰鬥結束，準備進入下一戰
            is_black = IsScreenBlack(screen)
            if runtimeContext._COMBAT_ACTION_COUNT > 0 and is_black:
                logger.info(f"[戰鬥] 偵測到黑屏，第 {runtimeContext._COMBAT_BATTLE_COUNT} 戰結束，等待下一戰...")
                # 只重置 action_count，讓 StateCombat 開頭統一處理 battle_count
                runtimeContext._COMBAT_ACTION_COUNT = 0
                # 等待黑屏結束
                # [戰後加速] 黑屏期間點擊 (1,1) 加速過場，並提前偵測下一狀態
                # 限制最多點擊 20 次 (約 6 秒)，或偵測到明確狀態時退出
                spam_click_count = 0
                MAX_SPAM_CLICKS = 20
                
                while spam_click_count < MAX_SPAM_CLICKS:
                    # 檢查停止信號
                    if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                        return

                    # 1. 點擊加速
                    Press([1, 1])
                    spam_click_count += 1
                    Sleep(0.3)
                    
                    # 2. 截圖檢查狀態
                    scn = ScreenShot()
                    update_combat_flag(scn)
                    
                    # 如果還在黑屏，繼續點擊
                    if IsScreenBlack(scn):
                        continue
                        
                    # 3. 檢查下一狀態標誌 (優先級: 戰鬥 > 寶箱 > 地城 > 其它)
                    # 這些標誌出現意味著過場結束，應立即交回主循環處理
                    next_state_markers = ['chestFlag', 'dungFlag', 'combatActive', 'mapFlag']
                    if any(CheckIf(scn, marker) for marker in next_state_markers):
                        logger.info(f"[戰後加速] 偵測到下一狀態標誌 (點擊 {spam_click_count} 次)，結束等待")
                        break
                    
                    # [網路重試] 檢測網路波動
                    if TryPressRetry(scn):
                        logger.info("[戰鬥] 黑屏加速時偵測到 Retry 選項，點擊重試")
                        Sleep(2)
                        break  # 退出黑屏加速循環，重新識別狀態
                
                logger.info(f"[戰後加速] 完成，共點擊 {spam_click_count} 次")
                # 黑屏結束後，回到 StateCombat 開頭重新計數
                return
            
            if CheckIf(screen, 'flee'):
                logger.info(f"[戰鬥] flee 出現，等待 {wait_count + 1} 次")
                # 角色比對（flee 偵測成功後執行，節流避免過於頻繁）
                now = time.time()
                if now - last_character_update >= 1.0:
                    MonitorState.current_character = DetectCharacter(screen)
                    last_character_update = now
                break
            Sleep(0.5)
        else:
            logger.warning("[戰鬥] flee 等待超時，共等待 30 次，跳過本次行動")
            return

        if not runtimeContext._COMBATSPD:
            # 檢查並啟用 2 倍速 (使用較低閾值以適應串流)
            if Press(CheckIf(screen, 'combatSpd', threshold=0.70)):
                runtimeContext._COMBATSPD = True
                logger.info("[戰鬥] 啟用 2 倍速")
                Sleep(0.5)
                # 點擊後重新截圖，以免影響後續判斷
                screen = ScreenShot()

        # === 技能施放設定 ===
        # 檢查是否有任何角色設定了技能（首戰或二戰後）
        # 配置結構: [{character, skill_first, level_first, skill_after, level_after}, ...]
        skill_config_list = setting._CHARACTER_SKILL_CONFIG if isinstance(setting._CHARACTER_SKILL_CONFIG, list) else []
        has_skill_config = any(
            cfg.get("character") and (cfg.get("skill_first") or cfg.get("skill_after"))
            for cfg in skill_config_list
        )
        # 觸發間隔判斷
        # [修正] 使用 _DUNGEON_REPEAT_COUNT 與 reset_ae_caster_flags 保持一致
        eff_counter = runtimeContext._DUNGEON_REPEAT_COUNT
        ae_interval_match = (eff_counter % (setting._AE_CASTER_INTERVAL + 1) == 0)
        if setting._AE_CASTER_INTERVAL == 0:
            ae_interval_match = True

        # 調試 log
        logger.debug(f"[技能施放調試] has_skill_config={has_skill_config}, ae_interval_match={ae_interval_match}, "
                     f"_DUNGEON_REPEAT_COUNT={runtimeContext._DUNGEON_REPEAT_COUNT}, _AE_CASTER_INTERVAL={setting._AE_CASTER_INTERVAL}")

        # === 間隔不匹配時的處理 ===
        # 間隔不匹配時，直接開啟自動戰鬥（重啟後跳過此判斷）
        if has_skill_config and not ae_interval_match and not runtimeContext._RESTART_SKIP_INTERVAL_THIS_DUNGEON:
            logger.info(f"[技能施放] 觸發間隔不匹配（地城循環第 {eff_counter + 1} 場，間隔設定 {setting._AE_CASTER_INTERVAL}），開啟自動戰鬥")
            runtimeContext._AOE_TRIGGERED_THIS_DUNGEON = True
            enable_auto_combat()
            Sleep(3)
            return


        screen = ScreenShot()
        # combatSpd 檢查已移至 StateCombat 開頭

        # === 新的自動戰鬥模式邏輯 ===
        battle_num = runtimeContext._COMBAT_BATTLE_COUNT
        action_count = runtimeContext._COMBAT_ACTION_COUNT
        auto_combat_mode = setting._AUTO_COMBAT_MODE
        
        # 判斷是否應該開啟自動戰鬥
        if should_enable_auto_combat(battle_num, auto_combat_mode):
            logger.info(f"[技能施放] 第 {battle_num} 戰，根據設定 ({auto_combat_mode}) 開啟自動戰鬥")
            runtimeContext._AOE_TRIGGERED_THIS_DUNGEON = True
            enable_auto_combat()
            Sleep(3)
            return

        if not CheckIf(screen,'flee'):
            return
        if runtimeContext._SUICIDE:
            Press(CheckIf(screen,'spellskill/'+'defend'))
        else:
            # === 技能施放邏輯（按角色識別）===
            # 偵測當前角色
            current_char = DetectCharacter(screen)
            skill_type = "首戰" if battle_num == 1 else "二戰後"

            # 取得角色技能配置
            if current_char == "未找到":
                # 識別失敗：使用單體技能
                logger.warning(f"[技能施放] 角色識別失敗，使用單體技能")
                # 使用第一個可用的單體技能
                skill = PHYSICAL_SKILLS[0] if PHYSICAL_SKILLS else "attack"
                level = "關閉"
                target_pos = None  # [修復] 初始化 target_pos 避免 UnboundLocalError
            else:
                # 從配置取得技能
                skill, level, target_pos = setting.get_skill_for_character(current_char, battle_num)

            # 判斷技能類別
            category = None
            if skill and skill != "attack":
                for cat, skills in SKILLS_BY_CATEGORY.items():
                    if skill in skills:
                        category = cat
                        break

            logger.info(f"[角色 {current_char}] 第{battle_num}戰（{skill_type}），技能: {skill or '普攻'}")

            if skill == "attack" or not category:
                # 使用普攻
                use_normal_attack()
            elif skill and category:
                # 有設定技能，使用設定的技能 (傳入目標位置)
                cast_skill_by_category(category, skill, level, target_pos)

    # ==================== DungeonMover 類別 ====================
    # 統一的地城移動管理器，整合 chest_auto, position, harken, gohome 邏輯
    class DungeonMover:
        """
        統一的地城移動管理器
        - 整合 chest_auto, position, harken, gohome 的處理邏輯
        - 實現分層超時機制 (Soft 60s -> GoHome, Hard 90s -> Restart)
        - 統一 Resume 和 Chest_Resume 處理
        """
        
        # 超時設定
        SOFT_TIMEOUT = 60  # 軟超時：觸發 GoHome
        HARD_TIMEOUT = 90  # 硬超時：觸發重啟
        
        # 輪詢設定
        POLL_INTERVAL = 0.5
        STILL_REQUIRED = 10  # 約 5 秒靜止判定
        
        # Resume 設定
        MAX_RESUME_RETRIES = 3
        RESUME_CLICK_INTERVAL = 3  # 每 3 秒主動檢查
        CHEST_AUTO_CLICK_INTERVAL = 5  # chest_auto 每 5 秒檢查
        CHEST_AUTO_STILL_THRESHOLD = 3  # chest_auto 靜止判定次數
        MONITOR_UPDATE_INTERVAL = 0.8  # 監控數值節流 (秒)

        # 轉向解卡設定
        MAX_TURN_ATTEMPTS = 6
        
        def __init__(self):
            self.consecutive_map_open_failures = 0
            self.global_retry_count = 0  # 新增：全域重試計數
            self.global_retry_start_time = None  # 新增：全域計時起點
            self.reset()
        
        def reset(self):
            """重置單次移動狀態（不重置全域計數）"""
            self.move_start_time = time.time()
            self.last_screen = None
            self.still_count = 0
            self.turn_attempt_count = 0
            self.resume_consecutive_count = 0
            self.last_resume_click_time = time.time()
            self.last_chest_auto_click_time = time.time()
            self.last_monitor_update_time = 0
            self.is_gohome_mode = False
            self.current_target = None
            self.waiting_for_arrival_after_resume = False
            
            # 同步到 MonitorState
            MonitorState.state_start_time = self.move_start_time
            MonitorState.still_count = 0
            MonitorState.resume_count = 0
        
        def _cleanup_exit(self, next_state):
            """退出移動監控時的統一清理
            
            所有 _monitor_move 的退出點都應調用此方法
            """
            # 重置本地狀態
            self.is_gohome_mode = False
            
            # 重置 MonitorState（GUI 顯示）
            MonitorState.current_target = ""
            MonitorState.state_start_time = 0
            MonitorState.is_gohome_mode = False
            MonitorState.still_count = 0
            MonitorState.resume_count = 0
            
            return next_state
        
        def initiate_move(self, targetInfoList: list, ctx):
            """
            啟動移動流程
            Args:
                targetInfoList: 目標列表
                ctx: RuntimeContext
            Returns:
                DungeonState: 下一個狀態
            """
            # ==================== 1. 預檢與清理遺留彈窗 ====================
            self.reset() # [關鍵修正] 確保在任何分支前先重設計時器
            
            TryPressRetry(ScreenShot())
            
            # [深度優化] 解決戰利品/對話/屬性視窗殘留問題
            # 啟動前若看到 AUTO/Resume 或 returnText 箭頭，先執行清理連點
            pre_screen = ScreenShot()
            if CheckIf(pre_screen, 'dungFlag') and not CheckIf(pre_screen, 'mapFlag'):
                # 1. 檢查返回按鈕 (許多結算窗附帶這個)
                return_pos = CheckIf(pre_screen, 'returnText', threshold=0.7)
                if not return_pos:
                    return_pos = CheckIf(pre_screen, 'ReturnText', threshold=0.7)
                
                if return_pos:
                    logger.info(f"[DungeonMover] 啟動前偵測到返回視窗 (returnText)，清理點擊: {return_pos}")
                    Press(return_pos)
                    Sleep(0.5)
                    pre_screen = ScreenShot() # 重新抓圖確認是否還有 AUTO

            if not targetInfoList:
                logger.info("[DungeonMover] 無待執行目標，執行 GoHome 流程以退出地城")
                self.is_gohome_mode = True
                MonitorState.is_gohome_mode = True
                return self._fallback_gohome(targetInfoList, ctx)
            
            target_info = targetInfoList[0]
            self.current_target = target_info.target
            
            # 更新監控狀態
            MonitorState.current_target = self.current_target
            MonitorState.state_start_time = self.move_start_time
            MonitorState.is_gohome_mode = False
            
            logger.info(f"[DungeonMover] 啟動移動: 目標={self.current_target}")
            
            # ========== 異常狀況預先檢查 (暫時性補丁) ==========
            # 防止因對話框擋住導致無法進入移動狀態 (如無法開啟地圖)
            screen_pre = ScreenShot()
            
            # 1. 網路重試 / 異常彈窗
            if TryPressRetry(screen_pre):
                logger.info("[DungeonMover] 偵測到 Retry 選項，點擊重試")
                Sleep(2)
                # 直接返回 IdentifyState 以便重新識別狀態
                return DungeonState.Map

            # 2. ReturnText (對話框卡住)
            if Press(CheckIf(screen_pre, "returnText")):
                logger.info("[DungeonMover] 偵測到 returnText (可能是對話框)，點擊返回")
                Sleep(0.5)
                return DungeonState.Map
            
            # 3. 特殊對話選項
            if getattr(quest, '_SPECIALDIALOGOPTION', None):
                for option in quest._SPECIALDIALOGOPTION:
                    if Press(CheckIf(screen_pre, option)):
                        logger.info(f"[DungeonMover] 點擊特殊對話選項: {option}")
                        Sleep(0.5)
                        return DungeonState.Map
            
            try:
                if self.current_target == 'chest_auto':
                    return self.chest_search(targetInfoList, ctx)
                elif self.current_target == 'chest':
                    return self.chest_navigation(targetInfoList, ctx)
                elif self.current_target == 'gohome':
                    self.is_gohome_mode = True
                    return self._fallback_gohome(targetInfoList, ctx)
                elif self.current_target == 'swipe':
                    return self.swipe_move(targetInfoList, ctx)
                else:
                    # position, harken, stair 等
                    return self.resume_navigation(targetInfoList, ctx)
            except Exception as e:
                logger.error(f"[DungeonMover] 啟動移動發生例外: {e}")
                return None

        @stoppable
        def swipe_move(self, targetInfoList: list, ctx):
            """
            執行單次滑動或點擊移動，並可選擇性切換技能配置。
            此方法不開地圖，直接執行動作。
            """
            target_info = targetInfoList[0]
            action = target_info.swipeDir
            extra = target_info.extra
            wait_time = getattr(target_info, 'wait', 1)
            
            # 1. 處理技能預設切換 (打王支援)
            if isinstance(extra, int) and 0 <= extra < 10:
                ctx._AUTO_SKILL_PRESET_INDEX = extra
                ctx._COMBAT_BATTLE_COUNT = 0  # 重置戰鬥計數器，確保從第 1 戰開始
                ctx._BOSS_CHARACTER_ACTION_COUNT = {}  # 清空角色行動計數器
                logger.info(f"[DungeonMover] 檢測到打王標記，戰鬥技能將切換至預設: {extra + 1}，已重置戰鬥計數與角色行動計數")
            
            # 2. 座標映射
            coords_map = {
                "前": {"type": "swipe", "from": [450, 700], "to": [450, 500]},
                "後": {"type": "swipe", "from": [450, 700], "to": [450, 900]},
                "左": {"type": "press", "pos": [27,  950]},
                "右": {"type": "press", "pos": [853, 950]}
            }
            
            try:
                if isinstance(action, str) and action in coords_map:
                    cfg = coords_map[action]
                    if cfg["type"] == "swipe":
                        logger.info(f"[DungeonMover] 執行 Swipe ({action}): {cfg['from']} -> {cfg['to']}")
                        Swipe(cfg["from"], cfg["to"])
                    else:
                        logger.info(f"[DungeonMover] 執行 Press ({action}): {cfg['pos']}")
                        Press(cfg["pos"])
                elif isinstance(action, list):
                    # 自定義座標
                    if len(action) == 2 and isinstance(action[0], list):
                        logger.info(f"[DungeonMover] 執行自定義 Swipe: {action[0]} -> {action[1]}")
                        Swipe(action[0], action[1])
                    elif len(action) == 2 and isinstance(action[0], int):
                        logger.info(f"[DungeonMover] 執行自定義 Press: {action}")
                        Press(action)
                    else:
                        logger.warning(f"[DungeonMover] swipe 目標格式解析失敗: {action}")
                else:
                    logger.warning(f"[DungeonMover] 未知的 swipe 動作類型: {action}")
                
                # 執行自定義等待
                # 執行自定義等待並持續偵測黑屏
                logger.info(f"[DungeonMover] 開始等待監控黑屏(戰鬥轉場)，預設時長: {wait_time}s")
                start_wait = time.time()
                while (time.time() - start_wait) < wait_time:
                    check_stop_signal()
                    
                    # 獲取當前畫面
                    scn = ScreenShot()
                    
                    # 使用標準全屏亮度偵測 (不修改 IsScreenBlack)
                    avg_brightness = np.mean(scn)
                    
                    if avg_brightness < 20: 
                        logger.info(f"[DungeonMover] 監控中偵測到轉場黑屏 (亮度: {avg_brightness:.2f})！判定進入戰鬥")
                        
                        # 黑屏打斷：持續點擊直到黑屏結束
                        logger.info("[DungeonMover] 開始黑屏打斷，持續點擊...")
                        click_count = 0
                        while IsScreenBlack(ScreenShot()):
                            check_stop_signal()
                            Press([1, 1])
                            click_count += 1
                            Sleep(0.1)
                            if click_count > 100:  # 防止無限迴圈（最多 10 秒）
                                logger.warning("[DungeonMover] 黑屏持續過久，中斷點擊")
                                break
                        
                        # 黑屏結束後額外點擊，確保完全打斷
                        logger.info(f"[DungeonMover] 黑屏結束（點擊了 {click_count} 次），繼續加速進入戰鬥...")
                        for _ in range(10):
                            check_stop_signal()
                            Press([1, 1])
                            Sleep(0.3)
                        
                        # 移除目標並返回戰鬥狀態
                        if targetInfoList:
                            targetInfoList.pop(0)
                        ctx._RESTART_OPEN_MAP_PENDING = True
                        return self._cleanup_exit(DungeonState.Combat)
                    
                    time.sleep(0.1)
                
                # 正常完成處理 (若循環中未因黑屏 return)
                logger.info(f"[DungeonMover] 監控結束，未偵測到黑屏")
                
            except Exception as e:
                logger.error(f"[DungeonMover] 執行 swipe 動作時出錯: {e}")

            # 3. 完成目標 (移出 try 塊，確保無論成功與否都嘗試 pop)
            if targetInfoList:
                targetInfoList.pop(0)
                logger.info(f"[DungeonMover] 已完成目標，剩餘目標數: {len(targetInfoList)}")
            
            # 設置標誌，確保下一個目標如果不也是 swipe，則重新開地圖
            ctx._RESTART_OPEN_MAP_PENDING = True
            
            return self._cleanup_exit(DungeonState.Map)
        
        def chest_search(self, targetInfoList, ctx):
            """啟動 chest_auto 移動"""
            screen = ScreenShot()
            pos = CheckIf(screen, "chest_auto", [[710,250,180,180]])
            
            if pos:
                logger.info(f"[DungeonMover] 找到 chest_auto 按鈕: {pos}")
                Press(pos)
            else:
                # 先檢查地圖是否已打開
                map_already_open = CheckIf(screen, 'mapFlag')
                
                if not map_already_open:
                    # 地圖未打開，嘗試打開
                    logger.info("[DungeonMover] 主畫面找不到 chest_auto，嘗試打開地圖")
                    Press([777, 150])
                    Sleep(1)
                    screen = ScreenShot()
                else:
                    logger.info("[DungeonMover] 地圖已打開但找不到 chest_auto")
                
                pos = CheckIf(screen, "chest_auto", [[710,250,180,180]])
                if pos:
                    Press(pos)
                else:
                    # 檢查是否無寶箱
                    if CheckIf(screen, 'notresure'):
                        logger.info("[DungeonMover] 偵測到 notresure，無寶箱")
                        targetInfoList.pop(0)
                        return DungeonState.Map
                    # 圖片匹配失敗，直接點擊預設座標
                    logger.info("[DungeonMover] chest_auto 圖片匹配失敗，點擊預設座標 [459, 1248]")
                    Press([459, 1248])

            return self._monitor_move(targetInfoList, ctx)
        
        def _fallback_gohome(self, targetInfoList, ctx):
            """啟動 gohome 移動（內部 Fallback 機制）"""
            screen = ScreenShot()
            pos = CheckIf(screen, "gohome")
            
            if pos:
                logger.info(f"[DungeonMover] 找到 gohome 按鈕: {pos}")
                Press(pos)
            else:
                # 嘗試打開地圖面板尋找
                logger.info("[DungeonMover] 主畫面找不到 gohome，嘗試打開地圖")
                Press([777, 150])
                Sleep(1)
                screen = ScreenShot()
                pos = CheckIf(screen, "gohome")
                if pos:
                    Press(pos)
                else:
                    # 緊急撤離：盲點 gohome 常見位置
                    logger.warning("[DungeonMover] 無法找到 gohome，嘗試盲點")
                    Press([252, 1433])  # 盲點 gohome 座標 (根據用戶文件)
            
            return self._monitor_move(targetInfoList, ctx)
        
        def chest_navigation(self, targetInfoList, ctx):
            """啟動 chest 類型移動（開地圖搜尋寶箱圖示）"""
            target_info = targetInfoList[0]
            
            # 檢查戰鬥/寶箱狀態（避免在錯誤狀態下開地圖）
            screen = ScreenShot()
            if detected_state := self._check_combat_or_chest(screen):
                return detected_state
            
            # 確保地圖開啟
            if not CheckIf(screen, 'mapFlag'):
                logger.info("[DungeonMover] chest: 打開地圖")
                Press([777, 150])
                Sleep(1)
                screen = ScreenShot()
                
                if detected_state := self._check_combat_or_chest(screen):
                    return detected_state
                
                if not CheckIf(screen, 'mapFlag'):
                    logger.warning("[DungeonMover] chest: 無法開啟地圖")
                    self.consecutive_map_open_failures += 1
                    
                    if self.consecutive_map_open_failures >= 3:
                        logger.error(f"[DungeonMover] chest: 連續 {self.consecutive_map_open_failures} 次無法打開地圖，觸發 GoHome")
                        self.consecutive_map_open_failures = 0
                        self.is_gohome_mode = True
                        return self._fallback_gohome(targetInfoList, ctx)
                    
                    return DungeonState.Dungeon
            
            # 使用 StateMap_FindSwipeClick 搜索寶箱
            try:
                chest_pos = StateMap_FindSwipeClick(target_info)
                if chest_pos:
                    logger.info(f"[DungeonMover] chest: 找到寶箱位置 {chest_pos}")
                    self.consecutive_map_open_failures = 0
                    Press(chest_pos)
                    Press([138, 1432])  # automove
                    return self._monitor_move(targetInfoList, ctx)
                else:
                    logger.info(f"[DungeonMover] 找不到寶箱圖示")
                    targetInfoList.pop(0)
                    logger.info(f"[DungeonMover] 已移除未發現之 chest 目標, 剩餘目標數: {len(targetInfoList)}")
                    ctx._RESTART_OPEN_MAP_PENDING = True
                    return self._cleanup_exit(DungeonState.Map)
            except KeyError as e:
                logger.error(f"[DungeonMover] chest: 地圖操作錯誤 {e}")
                return self._cleanup_exit(DungeonState.Dungeon)
        
        def resume_navigation(self, targetInfoList, ctx):
            """啟動一般移動 (position, harken, stair)"""
            target_info = targetInfoList[0]
            
            # [Resume 優化] 條件（所有條件需同時滿足）：
            # 1. 已完成防轉圈或不需要 (ctx._STEPAFTERRESTART = True)
            # 2. 非重啟後待開地圖狀態 (not ctx._RESTART_OPEN_MAP_PENDING)
            # 3. 曾經遇到過戰鬥/寶箱 (ctx._MEET_CHEST_OR_COMBAT)
            # 這樣確保：
            # - 重啟後第一次：不執行（需要防轉圈）
            # - 地城內啟動：不執行（沒遇到過戰鬥/寶箱）
            # - 開箱/戰鬥後：執行（正常恢復移動）
            if ctx._STEPAFTERRESTART and (not ctx._RESTART_OPEN_MAP_PENDING) and ctx._MEET_CHEST_OR_COMBAT:
                logger.info("[DungeonMover] 嘗試 Resume 優化...")
                # 嘗試檢測 Resume 按鈕 (最多 3 次)
                for retry in range(3):
                    screen = ScreenShot()
                    
                    # 同時檢查戰鬥/寶箱 (避免錯過剛出現的狀態)
                    if detected_state := self._check_combat_or_chest(screen):
                        return detected_state

                    resume_pos = CheckIf(screen, 'resume')
                    if resume_pos:
                        logger.info(f"[DungeonMover] 發現 Resume 按鈕 {resume_pos}，點擊恢復移動")
                        Press(resume_pos)
                        Sleep(1)
                        
                        # Resume 按鈕點擊後不會消失，直接進入監控
                        logger.info("[DungeonMover] Resume 點擊完成，進入監控循環")
                        self.consecutive_map_open_failures = 0
                        return self._monitor_move(targetInfoList, ctx)
                    else:
                        logger.debug(f"[DungeonMover] 未找到 Resume 按鈕 (嘗試 {retry+1}/3)")
                    
                    Sleep(0.5)
            
            logger.info("[DungeonMover] Resume 優化結束或不適用，執行標準導航流程")

            # 在嘗試打開地圖前，先檢查是否在戰鬥或寶箱（無法打開地圖的狀態）
            screen = ScreenShot()
            
            if detected_state := self._check_combat_or_chest(screen):
                return detected_state
            
            # 確保地圖開啟
            if not CheckIf(screen, 'mapFlag'):
                logger.info("[DungeonMover] 打開地圖")
                Press([777, 150])
                Sleep(1)
                screen = ScreenShot()
                
                if detected_state := self._check_combat_or_chest(screen):
                    return detected_state

                if not CheckIf(screen, 'mapFlag'):
                    # 檢查是否為黑屏/過場動畫（戰鬥轉場的典型特徵）
                    gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                    avg_brightness = np.mean(gray)
                    
                    if avg_brightness < 30:  # 黑屏閾值
                        logger.info("[DungeonMover] 檢測到黑屏（可能是戰鬥過場），等待狀態穩定...")
                        Sleep(2)  # 等待過場動畫完成
                        screen = ScreenShot()
                        
                        # 重新檢測戰鬥/寶箱
                        if detected_state := self._check_combat_or_chest(screen):
                            logger.info("[DungeonMover] 黑屏後確認進入戰鬥/寶箱")
                            self.consecutive_map_open_failures = 0
                            return detected_state
                    
                    # [自癒優化] 檢查是否被遺留的結算窗口 (AUTO/Resume) 或返回鈕擋住了
                    # 門檻放寬至 0.7 以應對各種 UI 變體
                    screen_retry = ScreenShot()
                    
                    # 優先檢查返回鈕
                    return_stray = CheckIf(screen_retry, 'returnText', threshold=0.7)
                    if not return_stray: return_stray = CheckIf(screen_retry, 'ReturnText', threshold=0.7)
                    
                    if return_stray:
                        logger.info(f"[DungeonMover] 地圖開啟失敗，偵測到返回鈕殘留，點擊清理: {return_stray}")
                        Press(return_stray)
                        Sleep(0.5)
                        return DungeonState.Dungeon

                    auto_retry_count = 0
                    while auto_retry_count < 15:
                        screen_retry = ScreenShot()
                        if CheckIf(screen_retry, 'AUTO'):
                            logger.info(f"[DungeonMover] 地圖重試中偵測到 AUTO，瘋狂連點清理中 (嘗試 {auto_retry_count+1}/15)...")
                            Press([515, 934])
                            Sleep(0.3)
                            auto_retry_count += 1
                        else:
                            break
                    
                    if auto_retry_count >= 15:
                        # 失敗：連點 15 次後 AUTO 還在，交給 IdentifyState 處理
                        logger.warning("[DungeonMover] AUTO 連點清理失敗，交還 IdentifyState 處理")
                        return None
                    elif auto_retry_count > 0:
                        # 成功：AUTO 已消失
                        return DungeonState.Dungeon
                    
                    self.consecutive_map_open_failures += 1
                    Sleep(1)  # 等待遊戲畫面穩定
                    
                    if self.consecutive_map_open_failures >= 3:
                        logger.warning(f"[DungeonMover] 連續 {self.consecutive_map_open_failures} 次無法打開地圖，觸發 GoHome 脫困")
                        self.consecutive_map_open_failures = 0
                        self.is_gohome_mode = True
                        return self._fallback_gohome(targetInfoList, ctx)
                    
                    # [重要] 優先檢查是否是因為暴風雪/能見度低，觸發 Resume
                    if CheckIf(screen, 'visibliityistoopoor'):
                         logger.warning("[DungeonMover] 能見度過低，嘗試點擊 Resume 恢復")
                         resume_pos = CheckIf(screen, 'resume')
                         if resume_pos:
                             Press(resume_pos)
                             Sleep(1)
                             self.consecutive_map_open_failures = 0 # 恢復成功，重置計數
                             # 點擊後直接進入監控
                             return self._monitor_move(targetInfoList, ctx)
                         else:
                             # 找不到 resume 才 GoHome
                             logger.warning("[DungeonMover] 能見度過低且無 Resume，觸發 GoHome")
                             self.consecutive_map_open_failures = 0
                             self.is_gohome_mode = True
                             return self._fallback_gohome(targetInfoList, ctx)
                    
                    return DungeonState.Dungeon
            
            # 搜索並點擊目標
            try:
                search_result = StateMap_FindSwipeClick(target_info)
                if search_result:
                    self.consecutive_map_open_failures = 0
                    # 設定特殊 Flag
                    if target_info.target == 'harken' and target_info.floorImage:
                        ctx._HARKEN_FLOOR_TARGET = target_info.floorImage
                    if target_info.target == 'minimap_stair' and target_info.floorImage:
                        ctx._MINIMAP_STAIR_FLOOR_TARGET = target_info.floorImage
                        ctx._MINIMAP_STAIR_IN_PROGRESS = True
                    
                    Press(search_result)
                    Press([138, 1432])  # automove
                    logger.info(f"[DungeonMover] 點擊目標並開始移動")
                    # 成功開啟地圖並點擊目標後，才允許 Resume 優化
                    ctx._RESTART_OPEN_MAP_PENDING = False
                else:
                    logger.info(f"[DungeonMover] 找不到目標 {target_info.target}")
                    if target_info.target in ['position', 'minimap_stair'] or target_info.target.startswith('stair'):
                        targetInfoList.pop(0)
                        logger.info(f"[DungeonMover] 已移除未發現之目標 {target_info.target}, 剩餘目標數: {len(targetInfoList)}")
                        ctx._RESTART_OPEN_MAP_PENDING = True
                    return self._cleanup_exit(DungeonState.Map)
            except KeyError as e:
                logger.error(f"[DungeonMover] 地圖操作錯誤: {e}")
                return self._cleanup_exit(DungeonState.Dungeon)
            
            return self._monitor_move(targetInfoList, ctx)
        
        def _monitor_move(self, targetInfoList, ctx):
            """
            統一的移動監控循環
            Returns:
                DungeonState: 下一個狀態
            """
            target_info = targetInfoList[0] if targetInfoList else None
            target = target_info.target if target_info else None
            is_chest_auto = (target == 'chest_auto')
            
            logger.info(f"[DungeonMover] 進入監控循環: target={target}, is_gohome={self.is_gohome_mode}")
            
            # 初始化全域計時（如果是第一次進入）
            if self.global_retry_start_time is None:
                self.global_retry_start_time = time.time()
            
            while True:
                # 檢查停止信號（使用統一機制）
                try:
                    check_stop_signal()
                except StopSignalException:
                    return self._cleanup_exit(DungeonState.Quit)
                
                Sleep(self.POLL_INTERVAL)

                # === 新增：全域硬超時檢查 ===
                global_elapsed = time.time() - self.global_retry_start_time
                if global_elapsed > 180:  # 3 分鐘全域超時
                    logger.error(f"[DungeonMover] 全域硬超時 (180s)，強制重啟")
                    restartGame()

                # [新增] 臨時導航完成檢測 (Only for chest_search visibility resume)
                # waiting_for_arrival_after_resume 是一個臨時標誌，表示我們點擊了 Resume
                # 正在等待到達目標 (routenotfound) 或再次靜止
                if getattr(self, 'waiting_for_arrival_after_resume', False):
                    screen_temp = ScreenShot()
                    # 1. 檢測到達
                    if CheckIf(screen_temp, 'routenotfound'):
                        logger.info("[DungeonMover] 臨時導航已到達 (routenotfound)，跳出監控以重啟 chest_search")
                        self.waiting_for_arrival_after_resume = False
                        # 返回 None 或特定狀態讓 chest_search 重啟 (這裡返回 None 會導致 initiate_move 結束)
                        # 但 chest_search 是一個 loop，我們需要讓 _monitor_move 結束，這樣 chest_search 內部的 return 會觸發
                        # 根據 script.py 邏輯，chest_search 直接 return _monitor_move
                        # 如果 _monitor_move 返回 None，initiate_move 返回 None，StateDungeon 會重新 IdentifyState
                        # IdentifyState 再次進入 StateDungeon，StateDungeon 再次調用 initiate_move，
                        # initiate_move 再次調用 chest_search，這符合 "重啟流程" 的定義 (重新找按鈕/開地圖)
                        return None
                    
                    # 2. 檢測再次靜止 (稍後在靜止判定區塊處理)
                
                # ========== A. 硬超時檢查 (60s) ==========
                elapsed = time.time() - self.move_start_time
                if elapsed > self.HARD_TIMEOUT:
                    logger.error(f"[DungeonMover] 硬超時 ({self.HARD_TIMEOUT}s)，觸發重啟")
                    restartGame()
                
                # ========== B. 軟超時檢查 (30s) ==========
                if elapsed > self.SOFT_TIMEOUT and not self.is_gohome_mode:
                    logger.warning(f"[DungeonMover] 軟超時 ({self.SOFT_TIMEOUT}s)，切換至 GoHome 模式")
                    self.is_gohome_mode = True
                    MonitorState.is_gohome_mode = True
                    # 不重置計時器，讓硬超時繼續計時
                    return self._fallback_gohome(targetInfoList, ctx)
                
                # ========== C. 狀態檢查 ==========
                # ========== C. 異常狀況預先檢查 (防止 IdentifyState 卡死) ==========
                screen_pre = ScreenShot()

                # 只在移動時更新監控相似度 (節流)
                now = time.time()
                if now - self.last_monitor_update_time >= self.MONITOR_UPDATE_INTERVAL:
                    MonitorState.flag_dungFlag = GetMatchValue(screen_pre, 'dungFlag')
                    MonitorState.flag_mapFlag = GetMatchValue(screen_pre, 'mapFlag')
                    MonitorState.flag_chestFlag = GetMatchValue(screen_pre, 'chestFlag')
                    MonitorState.flag_worldMap = GetMatchValue(screen_pre, 'worldmapflag')
                    MonitorState.flag_chest_auto = GetMatchValue(screen_pre, 'chest_auto')
                    MonitorState.flag_auto_text = GetMatchValue(screen_pre, 'AUTO')
                    # 同步更新時間戳 (讓 GUI 過期檢測正常運作)
                    MonitorState.flag_updates['dungFlag'] = now
                    MonitorState.flag_updates['mapFlag'] = now
                    MonitorState.flag_updates['chestFlag'] = now
                    MonitorState.flag_updates['worldMap'] = now
                    MonitorState.flag_updates['chest_auto'] = now
                    MonitorState.flag_updates['AUTO'] = now
                    # 血量偵測 (只在地城移動時更新)
                    MonitorState.flag_low_hp = CheckLowHP(screen_pre)
                    self.last_monitor_update_time = now
                    
                    # [新增] Visibility Resume Check
                    # 在監控中途如果遇到能見度過低
                    if CheckIf(screen_pre, 'visibliityistoopoor'):
                        logger.warning("[DungeonMover] 移動中偵測到能見度過低")
                    
                    # [新增] 移動中死亡偵測
                    if CheckIf(screen_pre, 'RiseAgain'):
                        logger.info("[DungeonMover] 移動中偵測到 RiseAgain (死亡)")
                        RiseAgainReset(reason='combat')
                        return None
                        resume_pos = CheckIf(screen_pre, 'resume')
                        if resume_pos:
                            logger.info(f"[DungeonMover] 點擊 Resume 嘗試脫困: {resume_pos}")
                            Press(resume_pos)
                            Sleep(1)
                            
                            # 如果是 chest_auto 模式，啟用 "等待到達" 邏輯
                            if is_chest_auto:
                                logger.info("[DungeonMover] chest_search 模式下觸發 Resume，進入臨時導航等待模式 (等待 routenotfound)")
                                self.waiting_for_arrival_after_resume = True
                                # 重置靜止計數，給予移動時間
                                self.still_count = 0
                            
                            continue
                        else:
                             # 無 Resume，不處理，讓它自然落入 GoHome (如果靜止)
                             pass
                    
                    # 低血量恢復檢查（啟用時觸發）
                    if setting._LOWHP_RECOVER and MonitorState.flag_low_hp:
                        logger.info("[DungeonMover] 偵測到低血量，觸發強制恢復流程...")
                        runtimeContext._FORCE_LOWHP_RECOVER = True
                        # 返回 Dungeon 狀態，讓 StateDungeon 處理恢復
                        return self._cleanup_exit(DungeonState.Dungeon)
                
                # 1. 網路重試 / 異常彈窗
                if TryPressRetry(screen_pre):
                    logger.info("[DungeonMover] 偵測到 Retry 選項，點擊重試")
                    Sleep(2)
                    continue

                # 2. ReturnText (對話框卡住)
                if Press(CheckIf(screen_pre, "returnText")):
                    logger.info("[DungeonMover] 偵測到 returnText (可能是對話框)，點擊返回")
                    Sleep(0.5)
                    continue
                
                # 3. 特殊對話選項
                if getattr(quest, '_SPECIALDIALOGOPTION', None):
                    handled_dialog = False
                    for option in quest._SPECIALDIALOGOPTION:
                        if Press(CheckIf(screen_pre, option)):
                            logger.info(f"[DungeonMover] 點擊特殊對話選項: {option}")
                            handled_dialog = True
                            break
                    if handled_dialog:
                        Sleep(0.5)
                        continue

                # ========== D. 狀態檢查 ==========
                # 記錄調用前的 _DUNGEON_CONFIRMED 狀態
                was_dungeon_confirmed = ctx._DUNGEON_CONFIRMED
                
                main_state, state, screen = IdentifyState()
                
                # [關鍵修復] 檢測重新進入地城：如果 _DUNGEON_CONFIRMED 從 False 變為 True，
                # 表示已經「跳過回村並重新進入」。此時應該退出，讓主循環重新載入目標列表。
                if not was_dungeon_confirmed and ctx._DUNGEON_CONFIRMED:
                    logger.info("[DungeonMover] 偵測到重新進入地城，退出以重新載入目標")
                    return self._cleanup_exit(DungeonState.Map)  # 返回 Map 讓主循環重新讀取目標

                
                # 首先檢查是否離開了地城（回到 Inn 或其他主狀態）
                if main_state == State.Inn or main_state == State.EoT:
                    logger.info(f"[DungeonMover] 偵測到離開地城 (State={main_state})，退出移動監控")
                    return self._cleanup_exit(DungeonState.Quit)
                
                # 檢查是否進入世界地圖（離開地城）
                if CheckIf(screen, 'openworldmap') or CheckIf(screen, 'openWorldMap'):
                    logger.info("[DungeonMover] 偵測到世界地圖，退出移動監控")
                    return self._cleanup_exit(DungeonState.Quit)
                
                # Harken 傳送完成檢測
                if ctx._HARKEN_FLOOR_TARGET is None and state == DungeonState.Dungeon:
                    if hasattr(ctx, '_HARKEN_TELEPORT_JUST_COMPLETED') and ctx._HARKEN_TELEPORT_JUST_COMPLETED:
                        logger.info("[DungeonMover] Harken 傳送完成")
                        ctx._HARKEN_TELEPORT_JUST_COMPLETED = False
                        if target == 'harken':
                            if targetInfoList:
                                targetInfoList.pop(0)
                                logger.info(f"[DungeonMover] 已移除已完成目標 {target}, 剩餘目標數: {len(targetInfoList)}")
                                ctx._RESTART_OPEN_MAP_PENDING = True
                        return self._cleanup_exit(DungeonState.Map)
                

                
                # 狀態轉換
                if state == DungeonState.Combat:
                    logger.info("[DungeonMover] 進入戰鬥")
                    self.global_retry_count = 0  # 新增：成功，重置計數
                    self.global_retry_start_time = None
                    return self._cleanup_exit(DungeonState.Combat)
                if state == DungeonState.Chest:
                    logger.info("[DungeonMover] 進入寶箱")
                    self.global_retry_count = 0  # 新增：成功，重置計數
                    self.global_retry_start_time = None
                    return self._cleanup_exit(DungeonState.Chest)
                if state == DungeonState.Quit:
                    return self._cleanup_exit(DungeonState.Quit)
                
                # ========== D. chest_resume (chest_auto 專用) ==========
                if is_chest_auto:
                    if time.time() - self.last_chest_auto_click_time > self.CHEST_AUTO_CLICK_INTERVAL:
                        pos = CheckIf(screen, "chest_auto", [[710,250,180,180]])
                        if pos:
                            logger.info(f"[DungeonMover] chest_resume: 點擊 {pos}")
                            Press(pos)
                            Sleep(0.5)  # 點擊後等待
                            # 重新截圖檢查 notresure
                            screen = ScreenShot()
                            if CheckIf(screen, 'notresure'):
                                logger.info("[DungeonMover] chest_auto: 無寶箱 (notresure)")
                                Press([1, 1])
                                if targetInfoList and targetInfoList[0].target == 'chest_auto':
                                    targetInfoList.pop(0)
                                return self._cleanup_exit(DungeonState.Map)
                        self.last_chest_auto_click_time = time.time()
                
                # ========== E. gohome Keep-Alive ==========
                if self.is_gohome_mode:
                    # E1. 離開地城檢測（世界地圖、Inn、或地城標誌消失）
                    if CheckIf(screen, 'worldmapflag'):
                        logger.info("[DungeonMover] gohome: 偵測到世界地圖，已離開地城")
                        return self._cleanup_exit(DungeonState.Quit)
                    if CheckIf(screen, 'Inn'):
                        logger.info("[DungeonMover] gohome: 偵測到 Inn，已回城")
                        return self._cleanup_exit(DungeonState.Quit)
                    
                    # 雙重檢查：如果連 dungFlag 都沒了，也視為離開 (可能在黑屏過場)
                    if not CheckIf(screen, 'dungFlag', threshold=0.7) and not CheckIf(screen, 'mapFlag', threshold=0.7):
                        logger.info("[DungeonMover] gohome: dungFlag/mapFlag 消失，視為已離開地城")
                        return self._cleanup_exit(DungeonState.Quit)
                    
                    # E2. Keep-Alive 點擊
                    if time.time() - self.last_resume_click_time > self.RESUME_CLICK_INTERVAL:
                        pos = CheckIf(screen, "gohome")
                        if pos:
                            logger.info(f"[DungeonMover] gohome Keep-Alive: 點擊 {pos}")
                            Press(pos)
                        self.last_resume_click_time = time.time()
                elif not is_chest_auto:
                    # 非 chest_auto 時，固定間隔嘗試 Resume（不管靜止狀態）
                    if time.time() - self.last_resume_click_time > self.RESUME_CLICK_INTERVAL:
                        resume_pos_periodic = CheckIf(screen, 'resume')
                        if resume_pos_periodic:
                            logger.info(f"[DungeonMover] 定期檢查 Resume，點擊: {resume_pos_periodic}")
                            Press(resume_pos_periodic)
                            # 點擊後短暫等待並多次檢查是否已到達
                            Sleep(0.5)
                            for _ in range(3):
                                if CheckIf(ScreenShot(), 'routenotfound'):
                                    logger.info("[DungeonMover] Resume 後檢測到 RouteNotFound，到達目的地")
                                    if target in ['position', 'minimap_stair'] or (target and target.startswith('stair')):
                                        if targetInfoList:
                                            targetInfoList.pop(0)
                                            logger.info(f"[DungeonMover] 已移除已完成目標 {target}, 剩餘目標數: {len(targetInfoList)}")
                                            # 強制下一個目標必須重新開啟地圖（防止對新目標執行無效的 Resume）
                                            ctx._RESTART_OPEN_MAP_PENDING = True
                                    return self._cleanup_exit(DungeonState.Map)
                                Sleep(0.2)
                        self.last_resume_click_time = time.time()
                
                # ========== Minimap Stair 即時檢測 ==========
                if hasattr(ctx, '_MINIMAP_STAIR_IN_PROGRESS') and ctx._MINIMAP_STAIR_IN_PROGRESS and hasattr(ctx, '_MINIMAP_STAIR_FLOOR_TARGET') and ctx._MINIMAP_STAIR_FLOOR_TARGET:
                    result = CheckIf_minimapFloor(screen, ctx._MINIMAP_STAIR_FLOOR_TARGET)
                    if result["found"]:
                        logger.info(f"[DungeonMover] 到達目標樓層 (MiniMap: {ctx._MINIMAP_STAIR_FLOOR_TARGET})")
                        ctx._MINIMAP_STAIR_IN_PROGRESS = False
                        # 確保彈出的是 minimap_stair 目標
                        if targetInfoList and targetInfoList[0].target == 'minimap_stair':
                            targetInfoList.pop(0)
                            logger.info(f"[DungeonMover] 已移除已完成目標 minimap_stair, 剩餘目標數: {len(targetInfoList)}")
                            ctx._RESTART_OPEN_MAP_PENDING = True
                        return self._cleanup_exit(DungeonState.Map)

                # ========== F. 靜止與 Resume 偵測 ==========
                if self.last_screen is not None:
                    gray1 = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                    gray2 = cv2.cvtColor(self.last_screen, cv2.COLOR_BGR2GRAY)
                    diff = cv2.absdiff(gray1, gray2).mean() / 255
                    
                    if diff < 0.05:
                        self.still_count += 1
                        MonitorState.still_count = self.still_count  # 同步到監控
                        if is_chest_auto:
                            logger.info(f"[DungeonMover] chest_auto 靜止 {self.still_count}/{self.CHEST_AUTO_STILL_THRESHOLD} (diff={diff:.3f})")
                        else:
                            logger.debug(f"[DungeonMover] 靜止 {self.still_count}/{self.STILL_REQUIRED}")

                        # chest_auto 特殊處理：靜止達閾值
                        if is_chest_auto and self.still_count >= self.CHEST_AUTO_STILL_THRESHOLD:
                            logger.info(f"[DungeonMover] chest_auto 靜止達 {self.still_count} 次，檢查狀態")
                            # 先檢查 notresure（無寶箱）
                            if CheckIf(screen, 'notresure'):
                                logger.info(f"[DungeonMover] chest_auto: 靜止且無寶箱 (notresure)")
                                Press([1, 1])
                                if targetInfoList and targetInfoList[0].target == 'chest_auto':
                                    targetInfoList.pop(0)
                                return self._cleanup_exit(DungeonState.Map)
                            elif CheckIf(screen, 'mapFlag'):
                                # 已在地圖狀態
                                logger.warning("[DungeonMover] chest_auto: 卡在地圖，導航失敗，重試")
                                PressReturn()
                                Sleep(0.5)
                                self.global_retry_count += 1
                                if self.global_retry_count >= 10:
                                    logger.error("[DungeonMover] 重試達上限，觸發 GoHome")
                                    self.is_gohome_mode = True
                                    return self._fallback_gohome(targetInfoList, ctx)
                                self.still_count = 0
                                continue  # 不 pop，繼續監控
                            else:
                                # === 在地城中 (dungflag)，未檢測到 notresure，不 pop，打開地圖 ===
                                logger.info(f"[DungeonMover] chest_auto: 靜止 {self.still_count} 次但無 notresure，不 pop，打開地圖檢查")
                                Press([777, 150])  # 打開地圖
                                Sleep(1)
                                map_screen = ScreenShot()
                                
                                if CheckIf(map_screen, 'mapFlag'):
                                    # 偵測到 mapflag (同 STEP1)
                                    logger.info("[DungeonMover] chest_auto: 地圖已打開，再找 chest_auto")
                                    pos = CheckIf(map_screen, "chest_auto", [[710,250,180,180]])
                                    if pos:
                                        Press(pos)
                                    else:
                                        # 盲點座標
                                        logger.info("[DungeonMover] chest_auto: 再次找不到，點擊盲點座標 [459, 1248]")
                                        Press([459, 1248])
                                    # 重置靜止計數，繼續監控
                                    self.still_count = 0
                                    continue
                                else:
                                    # 沒偵測到 mapflag - 檢查 visibility
                                    if CheckIf(map_screen, 'visibliityistoopoor'):
                                        logger.warning("[DungeonMover] chest_auto: 無法打開地圖，偵測到能見度過低")
                                        resume_pos = CheckIf(map_screen, 'resume')
                                        if resume_pos:
                                            logger.info(f"[DungeonMover] 點擊 Resume 嘗試脫困: {resume_pos}")
                                            Press(resume_pos)
                                            Sleep(1)
                                            # 進入臨時導航監控
                                            logger.info("[DungeonMover] chest_search 觸發 Resume，進入臨時導航等待模式")
                                            self.waiting_for_arrival_after_resume = True
                                            self.still_count = 0
                                            continue
                                    # 未檢測到 visibility，返回 Dungeon
                                    self.global_retry_count += 1
                                    logger.warning(f"[DungeonMover] 無法打開地圖 ({self.global_retry_count}/10)")
                                    if self.global_retry_count >= 10:
                                        logger.error("[DungeonMover] 重試達上限，觸發 GoHome")
                                        self.is_gohome_mode = True
                                        return self._fallback_gohome(targetInfoList, ctx)
                                    self.still_count = 0
                                    continue

                        if self.still_count >= self.STILL_REQUIRED:
                            logger.info(f"[DungeonMover] 連續靜止 {self.STILL_REQUIRED} 次")

                            # 檢查是否已在地圖
                            if CheckIf(screen, 'mapFlag'):
                                logger.warning("[DungeonMover] 卡在地圖，嘗試關閉地圖並重試")
                                PressReturn()
                                Sleep(0.5)
                                self.global_retry_count += 1
                                if self.global_retry_count >= 10:
                                    logger.error("[DungeonMover] 重試達上限，觸發 GoHome")
                                    if targetInfoList:
                                        targetInfoList.pop(0)
                                    self.is_gohome_mode = True
                                    MonitorState.is_gohome_mode = True
                                    return self._fallback_gohome(targetInfoList, ctx)
                                self.still_count = 0
                                continue
                            
                            # Resume 檢查 (非 chest_auto)
                            if not is_chest_auto:
                                resume_pos = CheckIf(screen, 'resume')
                                if resume_pos:
                                    if self.resume_consecutive_count < self.MAX_RESUME_RETRIES:
                                        self.resume_consecutive_count += 1
                                        MonitorState.resume_count = self.resume_consecutive_count  # 同步到監控
                                        logger.info(f"[DungeonMover] 點擊 Resume ({self.resume_consecutive_count}/{self.MAX_RESUME_RETRIES})")
                                        Press(resume_pos)
                                        Sleep(1)
                                        
                                        # 檢查 RouteNotFound
                                        if CheckIf(ScreenShot(), 'routenotfound'):
                                            logger.info("[DungeonMover] RouteNotFound，到達目的地")
                                            if target in ['position', 'minimap_stair'] or (target and target.startswith('stair')):
                                                targetInfoList.pop(0)
                                            return self._cleanup_exit(DungeonState.Map)
                                        
                                        self.still_count = 0
                                        self.last_screen = None
                                        continue
                                    else:
                                        logger.warning(f"[DungeonMover] Resume 無效 ({self.MAX_RESUME_RETRIES}次)，等待軟超時")
                            
                            # 轉向解卡
                            if self.turn_attempt_count < self.MAX_TURN_ATTEMPTS and not self.is_gohome_mode:
                                self.turn_attempt_count += 1
                                logger.info(f"[DungeonMover] 轉向解卡 ({self.turn_attempt_count}/{self.MAX_TURN_ATTEMPTS})")
                                Swipe([450, 700], [250, 700])
                                Sleep(2)
                                self.still_count = 0
                                self.last_screen = None
                                continue
                            

                            
                            # 判定停止（無 Resume 且靜止，且非 GoHome 模式）
                            if not self.is_gohome_mode and not is_chest_auto and not CheckIf(screen, 'resume'):
                                logger.info("[DungeonMover] 靜止且無 Resume，判定到達")
                                if target in ['position', 'harken'] or (target and target.startswith('stair')):
                                    targetInfoList.pop(0)
                                return self._cleanup_exit(DungeonState.Map)
                    else:
                        # 畫面有變化
                        if is_chest_auto and self.still_count > 0:
                            logger.info(f"[DungeonMover] chest_auto 畫面變化 (diff={diff:.3f})，靜止計數重置")
                        if self.still_count > 0:
                            self.still_count = max(0, self.still_count - 1)
                        if self.resume_consecutive_count > 0:
                            self.resume_consecutive_count = 0
                        if self.turn_attempt_count > 0:
                            self.turn_attempt_count = 0
                
                self.last_screen = screen

        def _check_combat_or_chest(self, screen):
            """
            檢查是否在戰鬥或寶箱狀態（這些狀態下無法打開地圖）
            Returns:
                bool: True=在戰鬥或寶箱狀態, False=否
            """
            # 檢查戰鬥狀態
            combat_templates = get_combat_active_templates()
            max_combat_val = 0
            if combat_templates:
                for t in combat_templates:
                    template = _get_cached_template(t)
                    if template is None:
                        continue
                    try:
                        res = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
                        _, val, _, _ = cv2.minMaxLoc(res)
                        if val > max_combat_val:
                            max_combat_val = val
                    except:
                        continue
            
            if max_combat_val >= 0.70:
                logger.info(f"[DungeonMover] 偵測到戰鬥狀態 (匹配度 {max_combat_val*100:.2f}%)")
                return DungeonState.Combat
            
            # [新增] 檢查死亡狀態
            if CheckIf(screen, 'RiseAgain'):
                logger.info("[DungeonMover] 偵測到死亡狀態 (RiseAgain)")
                RiseAgainReset(reason='combat')
                return None
            
            # 檢查寶箱狀態
            if CheckIf(screen, 'chestFlag') or CheckIf(screen, 'whowillopenit'):
                logger.info("[DungeonMover] 偵測到寶箱狀態")
                return DungeonState.Chest
                
            return None
    
    # 全域 DungeonMover 實例
    dungeon_mover = DungeonMover()

    def StateMap_FindSwipeClick(targetInfo : TargetInfo):
        ### return = None: 視爲沒找到, 大約等於目標點結束.
        ### return = [x,y]: 視爲找到, [x,y]是座標.
        target = targetInfo.target
        roi = targetInfo.roi
        for i in range(len(targetInfo.swipeDir)):
            scn = ScreenShot()
            if not CheckIf(scn,'mapFlag'):
                raise KeyError("地圖不可用.")

            swipeDir = targetInfo.swipeDir[i]
            if swipeDir!=None:
                logger.debug(f"拖動地圖:{swipeDir[0]} {swipeDir[1]} {swipeDir[2]} {swipeDir[3]}")
                DeviceShell(f"input swipe {swipeDir[0]} {swipeDir[1]} {swipeDir[2]} {swipeDir[3]}")
                Sleep(2)
                scn = ScreenShot()
            
            targetPos = None
            if target == 'position':
                logger.info(f"當前目標: 地點{roi}")
                targetPos = CheckIf_ReachPosition(scn,targetInfo)
            elif target == 'minimap_stair':
                # minimap_stair: 直接使用座標，不搜索圖片（偵測在 StateMoving_CheckFrozen 中進行）
                logger.info(f"當前目標: 小地圖樓梯 座標{roi} 目標圖片{targetInfo.floorImage}")
                targetPos = roi  # 直接返回座標
                break
            elif target.startswith("stair"):
                logger.info(f"當前目標: 樓梯{target}")
                targetPos = CheckIf_throughStair(scn,targetInfo)
            else:
                logger.info(f"搜索{target}...")
                # harken: roi 正常用於搜索區域限制，floorImage 用於樓層選擇
                if targetPos:=CheckIf(scn,target,roi):
                    logger.info(f'找到了 {target}! {targetPos}')
                    if (target == 'chest') and (swipeDir!= None):
                        logger.debug(f"寶箱熱力圖: 地圖:{setting._FARMTARGET} 方向:{swipeDir} 位置:{targetPos}")
                    if not roi:
                        # 如果沒有指定roi 我們使用二次確認
                        # logger.debug(f"拖動: {targetPos[0]},{targetPos[1]} -> 450,800")
                        # DeviceShell(f"input swipe {targetPos[0]} {targetPos[1]} {(targetPos[0]+450)//2} {(targetPos[1]+800)//2}")
                        # 二次確認也不拖動了 太容易觸發bug
                        Sleep(2)
                        Press([1,1255])
                        targetPos = CheckIf(ScreenShot(),target,roi)
                    break
        return targetPos
    def StateSearch(waitTimer, targetInfoList : list[TargetInfo]):
        normalPlace = ['harken','chest','leaveDung','position']
        targetInfo = targetInfoList[0]
        target = targetInfo.target
        # 地圖已經打開.
        map = ScreenShot()
        if not CheckIf(map,'mapFlag'):
                return None,targetInfoList # 發生了錯誤

        try:
            searchResult = StateMap_FindSwipeClick(targetInfo)
        except KeyError as e:
            logger.info(f"錯誤: {e}") # 一般來說這裏只會返回"地圖不可用"
            return None,  targetInfoList
    
        if not CheckIf(map,'mapFlag'):
                return None,targetInfoList # 發生了錯誤, 應該是進戰鬥了

        if searchResult == None:
            if target == 'chest':
                # 結束, 彈出.
                targetInfoList.pop(0)
                logger.info(f"沒有找到寶箱.\n停止檢索寶箱.")
            elif (target == 'position' or target.startswith('stair')):
                # 結束, 彈出.
                targetInfoList.pop(0)
                logger.info(f"已經抵達目標地點或目標樓層.")
            else:
                # 這種時候我們認爲真正失敗了. 所以不彈出.
                # 當然, 更好的做法時傳遞finish標識()
                logger.info(f"未找到目標{target}.")

            return DungeonState.Map,  targetInfoList
        else:
            if target in normalPlace or target.endswith("_quit") or target.startswith('stair') or target == 'minimap_stair':
                # harken 樓層選擇：在移動之前設置 flag，讓傳送完成後 IdentifyState 能處理
                if target == 'harken' and targetInfo.floorImage is not None:
                    logger.info(f"哈肯樓層選擇: 設置目標樓層 {targetInfo.floorImage}")
                    runtimeContext._HARKEN_FLOOR_TARGET = targetInfo.floorImage
                
                # minimap_stair：在移動之前設置 flag，讓 StateMoving_CheckFrozen 持續監控小地圖
                if target == 'minimap_stair' and targetInfo.floorImage is not None:
                    logger.info(f"小地圖樓梯偵測: 設置目標樓層圖片 {targetInfo.floorImage}")
                    runtimeContext._MINIMAP_STAIR_FLOOR_TARGET = targetInfo.floorImage
                    runtimeContext._MINIMAP_STAIR_IN_PROGRESS = True
                
                Press(searchResult)
                Press([138,1432]) # automove
                # 改用 DungeonMover 監控，避免舊超時邏輯
                dungeon_mover.reset()
                dungeon_mover.current_target = target
                MonitorState.current_target = target
                MonitorState.state_start_time = dungeon_mover.move_start_time
                MonitorState.is_gohome_mode = False
                result_state = dungeon_mover._monitor_move(targetInfoList, runtimeContext)
                
                # 只有在非戰鬥/寶箱狀態下才移除目標（防止被打斷後誤判完成）
                if result_state is None or result_state == DungeonState.Map or result_state == DungeonState.Dungeon:
                    # harken 成功後彈出當前目標，切換到下一個目標
                    if target == 'harken':
                        targetInfoList.pop(0)
                        logger.info(f"哈肯目標完成，切換到下一個目標")
                    
                    # minimap_stair 成功後彈出當前目標（由 StateMoving_CheckFrozen 清除 flag）
                    if target == 'minimap_stair' and not runtimeContext._MINIMAP_STAIR_IN_PROGRESS:
                        targetInfoList.pop(0)
                        logger.info(f"小地圖樓梯目標完成，切換到下一個目標")
                    
                    # position 和 stair 目標點擊移動後彈出（避免重複處理）
                    if target == 'position' or (target.startswith('stair') and target != 'minimap_stair'):
                        targetInfoList.pop(0)
                        logger.info(f"目標 {target} 已點擊並移動，切換到下一個目標")
                else:
                    logger.info(f"移動中途遇到 {result_state}，保留當前目標 {target} 待戰鬥/寶箱結束後繼續")
                
                # 如果成功到達(返回None)，返回Dungeon狀態避免重新打開地圖
                if result_state is None:
                    logger.debug("移動完成，返回 Dungeon 狀態")
                    return DungeonState.Dungeon, targetInfoList
                else:
                    return result_state, targetInfoList
            else:
                if (CheckIf_FocusCursor(ScreenShot(),target)): #注意 這裏通過二次確認 我們可以看到目標地點 而且是未選中的狀態
                    logger.info("經過對比中心區域, 確認沒有抵達.")
                    Press(searchResult)
                    Press([138,1432]) # automove
                    # 改用 DungeonMover 監控，避免舊超時邏輯
                    dungeon_mover.reset()
                    dungeon_mover.current_target = target
                    MonitorState.current_target = target
                    MonitorState.state_start_time = dungeon_mover.move_start_time
                    MonitorState.is_gohome_mode = False
                    return dungeon_mover._monitor_move(targetInfoList, runtimeContext), targetInfoList
                else:
                    if setting._DUNGWAITTIMEOUT == 0:
                        logger.info("經過對比中心區域, 判斷爲抵達目標地點.")
                        logger.info("無需等待, 當前目標已完成.")
                        targetInfoList.pop(0)
                        return DungeonState.Map,  targetInfoList
                    else:
                        logger.info("經過對比中心區域, 判斷爲抵達目標地點.")
                        logger.info('開始等待...等待...')
                        PressReturn()
                        Sleep(0.5)
                        PressReturn()
                        while 1:
                            if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                                return None, targetInfoList
                            if setting._DUNGWAITTIMEOUT-time.time()+waitTimer<0:
                                logger.info("等得夠久了. 目標地點完成.")
                                targetInfoList.pop(0)
                                Sleep(1)
                                Press([777,150])
                                return None,  targetInfoList
                            logger.info(f'還需要等待{setting._DUNGWAITTIMEOUT-time.time()+waitTimer}秒.')
                            if CheckIf(ScreenShot(),'combatActive') or CheckIf(ScreenShot(),'combatActive_2'):
                                return DungeonState.Combat,targetInfoList
        return DungeonState.Map,  targetInfoList
    @stoppable
    def StateChest():
        nonlocal runtimeContext
        MonitorState.current_state = "Chest"
        availableChar = [0, 1, 2, 3, 4, 5]
        disarm = [515,934]  # 527,920會按到接受死亡 450 1000會按到技能 445,1050還是會按到技能
        haveBeenTried = False

        if runtimeContext._TIME_CHEST==0:
            runtimeContext._TIME_CHEST = time.time()

        logger.info("[StateChest] 進入寶箱處理流程 (Refactored & Optimized)")
        MAX_CHEST_WAIT_LOOPS = 200  # 最大等待循環次數
        chest_wait_count = 0
        dungflag_consecutive_count = 0
        dungflag_fail_count = 0  # [新增] 連續失敗計數器
        DUNGFLAG_CONFIRM_REQUIRED = 3  # [優化] 從 5 改為 3
        DUNGFLAG_FAIL_THRESHOLD = 3  # 連續失敗 3 次才重置
        
        # 異常狀態定義
        abnormal_states = [
            'ambush', 'ignore', 'sandman_recover', 'cursedWheel_timeLeap',
            'multipeopledead', 'startdownload', 'totitle', 'Deepsnow',
            'adventurersbones', 'halfBone', 'nothanks', 'strange_things', 'blessing',
            'DontBuyIt', 'donthelp', 'buyNothing', 'Nope', 'ignorethequest',
            'dontGiveAntitoxin', 'pass', 'returnText', 'ReturnText'
        ]

        while True:
            # 檢查停止信號
            if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                return None

            chest_wait_count += 1
            logger.debug(f"[StateChest] === 循環 #{chest_wait_count} 開始 === dungFlag計數={dungflag_consecutive_count}")
            if chest_wait_count > MAX_CHEST_WAIT_LOOPS:
                logger.warning(f"[StateChest] 超時：等待循環超過 {MAX_CHEST_WAIT_LOOPS} 次，強制退出")
                return None

            scn = ScreenShot()

            # 1. 優先中斷條件 (Interrupts) - [優化] 分頻檢查
            # 異常狀態：每 20 次循環檢查一次 (約 2-4 秒一次)
            # 戰鬥/死亡：每 5 次循環檢查一次 (約 0.5-1 秒一次)
            
            # 異常狀態
            if chest_wait_count % 20 == 0:
                if any(CheckIf(scn, t) for t in abnormal_states):
                    logger.info(f"[StateChest] 偵測到異常狀態，交由 IdentifyState 處理")
                    return None
            
            # 戰鬥與死亡
            if chest_wait_count % 5 == 0:
                # 戰鬥
                if any(CheckIf(scn, t, threshold=0.70) for t in get_combat_active_templates()):
                    logger.info("[StateChest] 偵測到戰鬥，進入戰鬥狀態")
                    return DungeonState.Combat
                # 死亡
                if CheckIf(scn, 'RiseAgain'):
                    logger.info("[StateChest] 偵測到死亡")
                    RiseAgainReset(reason='chest')
                    return None

            # [網路重試] 檢測網路波動 (每 10 次循環)
            if chest_wait_count % 10 == 0:
                if TryPressRetry(scn):
                    logger.info("[StateChest] 偵測到 Retry 選項，點擊重試")
                    Sleep(2)
                    continue

            # 2. 結束檢查 (DungFlag) - 帶連續確認 (保持每次檢查)
            dungFlag_result = CheckIf(scn, 'dungFlag', threshold=0.75)
            logger.debug(f"[StateChest] dungFlag 偵測結果: {dungFlag_result}, 當前計數={dungflag_consecutive_count}")
            if dungFlag_result:
                dungflag_consecutive_count += 1
                dungflag_fail_count = 0  # 成功時重置失敗計數
                if dungflag_consecutive_count >= DUNGFLAG_CONFIRM_REQUIRED:
                    logger.info(f"[StateChest] dungFlag 已連續穩定確認 {dungflag_consecutive_count} 次，畫面無彈窗幹擾，開箱流程結束")
                    return DungeonState.Dungeon

                # [優化] 即使看到 dungFlag，也不馬上退出，而是繼續執行下方的 Spam Click
                # 這樣可以利用主循環的點擊能力來消除潛在的殘留彈窗
                logger.debug(f"[StateChest] 檢測到 dungFlag ({dungflag_consecutive_count}/5)，繼續執行清理點擊以確保彈窗關閉...")
                # 注意：這裡不 continue，讓它自然掉落到下方的 Spam Click 邏輯
                pass
                # [Modified] Removed 'continue' to allow fall-through to Spam Click below
                # 這樣即使在確認 dungFlag 期間，也能持續點擊關閉彈窗 
            else:
                # [優化] 延遲重置：只有連續失敗 3 次才重置計數
                dungflag_fail_count += 1
                if dungflag_fail_count >= DUNGFLAG_FAIL_THRESHOLD:
                    logger.debug(f"[StateChest] dungFlag 連續失敗 {dungflag_fail_count} 次，重置計數")
                    dungflag_consecutive_count = 0
                    dungflag_fail_count = 0

            # 3. 寶箱交互 (Interactive States) (保持每次檢查)
            has_interaction = False
            
            # 3.1 選擇開箱角色 (whowillopenit)
            if CheckIf(scn, 'whowillopenit'):
                logger.info("[StateChest] 選擇開箱角色")
                while True:
                    if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                        return None
                    pointSomeone = setting._WHOWILLOPENIT - 1
                    if (pointSomeone != -1) and (pointSomeone in availableChar) and (not haveBeenTried):
                        whowillopenit = pointSomeone 
                    else:
                        whowillopenit = random.choice(availableChar) 
                    pos = [258+(whowillopenit%3)*258, 1161+((whowillopenit)//3)%2*184]
                    
                    if CheckIf(scn,'chestfear',[[pos[0]-125,pos[1]-82,250,164]]):
                        if whowillopenit in availableChar:
                            availableChar.remove(whowillopenit) 
                    else:
                        Press(pos)
                        Sleep(0.5)
                        break
                if not haveBeenTried:
                    haveBeenTried = True
                has_interaction = True

            # 3.2 正在開箱/解鎖 (chestOpening)
            elif CheckIf(scn, 'chestOpening'):
                pass

            # 3.3 點擊寶箱 (chestFlag)
            elif pos := CheckIf(scn, 'chestFlag'):
                logger.info(f"[StateChest] 發現寶箱 (chestFlag)，點擊打開")
                Press(pos)
                Sleep(0.5)
                has_interaction = True

            if has_interaction:
                continue

            # 4. 默認操作：連點跳過對話 (Spam Click)
            # 包含：快進、重試、點擊跳過
            
            # 快進與重試 (保持檢查，但可以稍微降低頻率，比如每 2 次)
            if chest_wait_count % 2 == 0:
                if Press(CheckIf_fastForwardOff(scn)):
                    Sleep(0.3)
                    continue
                if TryPressRetry(scn):
                    Sleep(0.3)
                    continue

            # [優化] 突發連點 (Burst Click) - 減少次數和間隔
            # 從 5次x0.1s 改為 3次x0.05s，節省約 0.35s/循環

            # 黑幕檢測：如果畫面太暗，可能正在進入戰鬥，停止點擊
            screen_brightness = scn.mean()
            if screen_brightness < 30:
                logger.info(f"[StateChest] 偵測到黑幕 (亮度={screen_brightness:.1f})，可能正在進入戰鬥，停止點擊")
                return DungeonState.Combat

            logger.debug(f"[StateChest] 執行 Burst Click (3次) - has_interaction={has_interaction}")
            for _ in range(3):
                Press(disarm)
                Sleep(0.05)

            # AUTO 偵測：偵測到 AUTO 時持續點擊直到消失
            auto_match = GetMatchValue(scn, 'AUTO')
            if auto_match >= 80:
                logger.info(f"[StateChest] 偵測到 AUTO (匹配度={auto_match:.0f}%)，開始連續點擊")
                auto_click_count = 0
                while auto_click_count < 10:
                    if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                        return None
                    # 連點 3 下清對話
                    for _ in range(3):
                        Press(disarm)
                        Sleep(0.05)
                    Sleep(0.1)
                    scn = ScreenShot()
                    auto_match = GetMatchValue(scn, 'AUTO')
                    if auto_match < 80:
                        logger.info("[StateChest] AUTO 已消失，停止點擊")
                        
                        # [恢復判斷] AUTO 消失後，檢查是否需要恢復（只設置標誌，不執行動作）
                        logger.debug("[StateChest] 執行恢復條件判斷...")
                        scn_recover = ScreenShot()
                        
                        # [Debug] 進入檢查即刻拍照（需開啟 debug截圖 選項）
                        if setting._DEBUG_SCREENSHOT:
                            try:
                                debug_dir = "debug_screens"
                                if not os.path.exists(debug_dir): os.makedirs(debug_dir)
                                ts = datetime.now().strftime("%H%M%S_%f")[:9] 
                                save_path = f"{debug_dir}/chest_auto_check_{ts}.png"
                                cv2.imwrite(save_path, scn_recover)
                                logger.debug(f"[StateChest] 恢復檢查前截圖: {save_path}")
                            except Exception as e: logger.error(f"截圖失敗: {e}")
                        
                        # 1. 異常狀態
                        if (setting._RECOVER_POISON or setting._RECOVER_VENOM or 
                            setting._RECOVER_STONE or setting._RECOVER_PARALYSIS or 
                            setting._RECOVER_CURSED or setting._RECOVER_FEAR or
                            setting._RECOVER_SKILLLOCK):
                            detected, status_types = CheckAbnormalStatus(scn_recover, setting)
                            if detected:
                                logger.info(f"[StateChest] 偵測到異常狀態: {status_types}，標記強制恢復")
                                runtimeContext._FORCE_ABNORMAL_RECOVER = True
                                # 如果偵測到麻痺或封技，標記恢復後重置戰鬥計數
                                if '麻痺' in status_types or '封技' in status_types:
                                    runtimeContext._RESET_BATTLE_COUNT_AFTER_RECOVER = True
                                    logger.info("[StateChest] 偵測到麻痺/封技，將在恢復後重置戰鬥計數器")
                                
                        # 2. 低血量恢復
                        if setting._LOWHP_RECOVER:
                            if CheckLowHP(scn_recover):
                                logger.debug("[StateChest] 偵測到低血量，啟用低血量恢復檢查標誌")
                                runtimeContext._FORCE_LOWHP_RECOVER = True
                            else:
                                logger.debug("[StateChest] 低血量檢查: 未偵測到低血量")

                        break
                    auto_click_count += 1

    @stoppable
    def StateDungeon(targetInfoList : list[TargetInfo], initial_dungState = None):
        gameFrozen_none = []
        gameFrozen_map = 0
        dungState = initial_dungState
        shouldRecover = False
        waitTimer = time.time()
        needRecoverBecauseCombat = False
        needRecoverBecauseChest = False
        resume_fail_counter = 0  # Resume 檢測失敗計數器，防止死循環

        nonlocal runtimeContext

        # 更新監控狀態
        MonitorState.current_state = "Dungeon"
        
        while 1:
            check_stop_signal()  # 每次迭代開始時檢查停止信號
            state_handle_start = time.time()
            state_handle_name = dungState
            logger.info("----------------------")
            if setting._FORCESTOPING.is_set():
                logger.info("即將停止腳本...")
                dungState = DungeonState.Quit
            logger.info(f"當前狀態(地下城): {dungState}")
            
            # 更新監控狀態 - 地城子狀態
            MonitorState.current_dungeon_state = str(dungState.value) if dungState else "識別中"

            # NOTE: [硬超時檢測] 移至迴圈開頭，確保每次迭代都執行
            # 原本放在 case None 裡面，導致當 IdentifyState 識別到狀態時不會觸發
            MAXTIMEOUT = 400
            # 顯示當前計時器狀態（debug 用，每 10 秒顯示一次）
            if runtimeContext._TIME_COMBAT != 0:
                combat_elapsed = time.time() - runtimeContext._TIME_COMBAT
                if int(combat_elapsed) % 10 == 0:
                    logger.debug(f"[硬超時] 戰鬥計時: {combat_elapsed:.0f}/{MAXTIMEOUT}秒")
            if runtimeContext._TIME_CHEST != 0:
                chest_elapsed = time.time() - runtimeContext._TIME_CHEST
                if int(chest_elapsed) % 10 == 0:
                    logger.debug(f"[硬超時] 寶箱計時: {chest_elapsed:.0f}/{MAXTIMEOUT}秒")
            # 超時重啟
            if (runtimeContext._TIME_CHEST != 0) and (time.time() - runtimeContext._TIME_CHEST > MAXTIMEOUT):
                logger.info("由於寶箱用時過久, 硬超時重啓.")
                restartGame()
            if (runtimeContext._TIME_COMBAT != 0) and (time.time() - runtimeContext._TIME_COMBAT > MAXTIMEOUT):
                logger.info("由於戰鬥用時過久, 硬超時重啓.")
                restartGame()

            match dungState:
                case None:
                    s, dungState,scn = IdentifyState()
                    if (s == State.Inn) or (dungState == DungeonState.Quit):
                        elapsed_ms = (time.time() - state_handle_start) * 1000
                        logger.debug(f"[耗時] 地城狀態處理 {state_handle_name} (耗時 {elapsed_ms:.0f} ms)")
                        break
                    # 只有在 IdentifyState 沒有識別到狀態時才執行卡死檢測（軟超時）
                    if dungState is None:
                        gameFrozen_none, result = GameFrozenCheck(gameFrozen_none,scn)
                        if result:
                            logger.info("由於畫面卡死, 軟超時重啓.")
                            restartGame()
                case DungeonState.Quit:
                    elapsed_ms = (time.time() - state_handle_start) * 1000
                    logger.debug(f"[耗時] 地城狀態處理 {state_handle_name} (耗時 {elapsed_ms:.0f} ms)")
                    break
                case DungeonState.Dungeon:
                    shouldRecover = False

                    # --- 新增：異常狀態偵測 ---
                    if (setting._RECOVER_POISON or setting._RECOVER_VENOM or 
                        setting._RECOVER_STONE or setting._RECOVER_PARALYSIS or 
                        setting._RECOVER_CURSED or setting._RECOVER_FEAR or
                        setting._RECOVER_SKILLLOCK):
                         # 為了避免頻繁截圖，可以考慮只在某些條件下檢查，但這裡為了即時性先每次檢查
                         # 如果 CheckAbnormalStatus 效能允許 (已優化 ROI)
                         scn_status = ScreenShot()
                         detected, status_types = CheckAbnormalStatus(scn_status, setting)
                         if detected:
                             logger.info(f"[StateDungeon] 偵測到異常狀態: {status_types}，觸發恢復")
                             shouldRecover = True
                             # 如果偵測到麻痺或封技，標記恢復後重置戰鬥計數
                             if '麻痺' in status_types or '封技' in status_types:
                                 runtimeContext._RESET_BATTLE_COUNT_AFTER_RECOVER = True
                                 logger.info("[StateDungeon] 偵測到麻痺/封技，將在恢復後重置戰鬥計數器")

                    if runtimeContext._FORCE_ABNORMAL_RECOVER:
                        logger.info("[StateDungeon] 檢測到異常狀態強制恢復標誌")
                        shouldRecover = True
                        runtimeContext._FORCE_ABNORMAL_RECOVER = False

                    # --- 新增：低血量強制恢復邏輯 ---
                    if runtimeContext._FORCE_LOWHP_RECOVER:
                        logger.info("[StateDungeon] 檢測到低血量強制恢復標誌")
                        
                        # 1. 安全檢查：確認當前不是戰鬥或寶箱
                        # 使用 IdentifyState (較慢但準確) 或 CheckIf (如果確定畫面)
                        # 這裡使用 IdentifyState 來確保安全
                        s, current_real_state, scn = IdentifyState()
                        
                        if current_real_state == DungeonState.Combat:
                            logger.warning("[StateDungeon] 欲恢復但已進入戰鬥，轉移至 Combat 狀態 (恢復將在戰後進行)")
                            dungState = DungeonState.Combat
                            # 注意：保留 _FORCE_LOWHP_RECOVER 標誌，讓戰後恢復邏輯決定是否強制恢復
                            # 或者戰後邏輯會檢查 _SKIPCOMBATRECOVER，如果用戶設置跳過，則這裡可能需要額外處理
                            # 但通常戰鬥優先，戰鬥後是否有空恢復取決於設定。
                            # 為了安全，我們讓戰鬥先打完。
                            continue
                            
                        elif current_real_state == DungeonState.Chest:
                            logger.warning("[StateDungeon] 欲恢復但已進入寶箱，轉移至 Chest 狀態")
                            dungState = DungeonState.Chest
                            continue

                        # 2. 若安全，則執行恢復
                        logger.info("[StateDungeon] 環境安全，準備執行低血量恢復")
                        shouldRecover = True 
                        runtimeContext._FORCE_LOWHP_RECOVER = False # 清除標誌 (本次執行)

                    Press([1,1])
                    ########### COMBAT RESET
                    # 戰鬥結束了, 我們將一些設置復位
                    runtimeContext._COMBAT_ACTION_COUNT = 0  # 重置行動計數器
                    ########### TIMER
                    if (runtimeContext._TIME_CHEST !=0) or (runtimeContext._TIME_COMBAT!=0):
                        spend_on_chest = 0
                        if runtimeContext._TIME_CHEST !=0:
                            spend_on_chest = time.time()-runtimeContext._TIME_CHEST
                            runtimeContext._TIME_CHEST = 0
                        spend_on_combat = 0
                        if runtimeContext._TIME_COMBAT !=0:
                            spend_on_combat = time.time()-runtimeContext._TIME_COMBAT
                            runtimeContext._TIME_COMBAT = 0
                        logger.info(f"粗略統計: 寶箱{spend_on_chest:.2f}秒, 戰鬥{spend_on_combat:.2f}秒.")
                        if (spend_on_chest!=0) and (spend_on_combat!=0):
                            if spend_on_combat>spend_on_chest:
                                runtimeContext._TIME_COMBAT_TOTAL = runtimeContext._TIME_COMBAT_TOTAL + spend_on_combat-spend_on_chest
                                runtimeContext._TIME_CHEST_TOTAL = runtimeContext._TIME_CHEST_TOTAL + spend_on_chest
                            else:
                                runtimeContext._TIME_CHEST_TOTAL = runtimeContext._TIME_CHEST_TOTAL + spend_on_chest-spend_on_combat
                                runtimeContext._TIME_COMBAT_TOTAL = runtimeContext._TIME_COMBAT_TOTAL + spend_on_combat
                        else:
                            runtimeContext._TIME_COMBAT_TOTAL = runtimeContext._TIME_COMBAT_TOTAL + spend_on_combat
                            runtimeContext._TIME_CHEST_TOTAL = runtimeContext._TIME_CHEST_TOTAL + spend_on_chest
                    ########### RECOVER
                    if needRecoverBecauseChest:
                        logger.info("進行開啓寶箱後的恢復.")
                        runtimeContext._COUNTERCHEST+=1
                        needRecoverBecauseChest = False
                        runtimeContext._MEET_CHEST_OR_COMBAT = True
                        if not setting._SKIPCHESTRECOVER:
                            logger.info("由於面板配置, 進行開啓寶箱後恢復.")
                            shouldRecover = True
                        else:
                            logger.info("由於面板配置, 跳過了開啓寶箱後恢復.")
                    if needRecoverBecauseCombat:
                        runtimeContext._COUNTERCOMBAT+=1
                        needRecoverBecauseCombat = False
                        runtimeContext._MEET_CHEST_OR_COMBAT = True
                        if (not setting._SKIPCOMBATRECOVER):
                            logger.info("由於面板配置, 進行戰後恢復.")
                            shouldRecover = True
                        else:
                            logger.info("由於面板配置, 跳過了戰後後恢復.")
                    if runtimeContext._RECOVERAFTERREZ == True:
                        shouldRecover = True
                        runtimeContext._RECOVERAFTERREZ = False
                    if shouldRecover:
                        Press([1,1])
                        counter_trychar = -1
                        while 1:
                            if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                                return
                            counter_trychar += 1
                            dunflag_result = CheckIf(ScreenShot(),'dungflag')
                            logger.debug(f"[圖片偵測] dungflag: {dunflag_result}")
                            if dunflag_result and (counter_trychar <=20):
                                Press([36+(counter_trychar%3)*286,1425])
                                Sleep(0.5)
                            else:
                                logger.info("自動回覆失敗, 暫不進行回覆.")
                                break
                            # NOTE: 連續偵測 trait 最多 10 次，適應慢機器角色頁面打開較慢的情況
                            trait_result = None
                            for trait_attempt in range(10):
                                scn = ScreenShot()
                                trait_result = CheckIf(scn, 'trait')
                                logger.debug(f"[圖片偵測] trait (嘗試 {trait_attempt+1}/10): {trait_result}")
                                if trait_result:
                                    break
                                Sleep(0.5)
                            if trait_result:
                                story_result = CheckIf(scn,'story', [[676,800,220,108]])
                                logger.debug(f"[圖片偵測] story: {story_result}")
                                if story_result:
                                    Press([725,850])
                                else:
                                    Press([830,850])
                                Sleep(1)
                                FindCoordsOrElseExecuteFallbackAndWait(
                                    ['recover','combatActive','combatActive_2'],
                                    [833,843],
                                    1
                                    )
                                recover_result = CheckIf(ScreenShot(),'recover')
                                logger.debug(f"[圖片偵測] recover: {recover_result}")
                                if recover_result:
                                    Press([600,1200])
                                    Sleep(1)
                                    for _ in range(5):
                                        t = time.time()
                                        PressReturn()
                                        if time.time()-t<0.3:
                                            Sleep(0.3-(time.time()-t))
                                    shouldRecover = False
                                    # 麻痺/封技恢復後重置戰鬥計數器
                                    if runtimeContext._RESET_BATTLE_COUNT_AFTER_RECOVER:
                                        logger.info("[恢復] 麻痺/封技恢復完成，重置戰鬥計數器以重新執行技能施放")
                                        runtimeContext._COMBAT_BATTLE_COUNT = 0
                                        runtimeContext._AOE_TRIGGERED_THIS_DUNGEON = False
                                        runtimeContext._RESET_BATTLE_COUNT_AFTER_RECOVER = False
                                    break
                    ########### OPEN MAP
                    ########### 防止轉圈 (from upstream 1.9.27)
                    ########### OPEN MAP / RESUME LOGIC (Refactored)
                    # 這一大塊現在只負責環境初始化和轉態，具體移動逻辑交給 DungeonMover
                    
                    has_chest_auto = any(t.target == 'chest_auto' for t in targetInfoList) if targetInfoList else False
                    
                    if not runtimeContext._STEPAFTERRESTART:
                        # 防止轉圈：前後左右平移一次（僅重啟後執行）
                        logger.info("防止轉圈: 前後左右平移一次")

                        # 前平移 (改為上滑，前進)
                        Swipe([450,700], [450, 500])
                        Sleep(1)

                        # 後平移 (改為下滑，後退)
                        Swipe([450,700], [450, 900])
                        Sleep(1)

                        # 左平移
                        Press([27,950])
                        Sleep(1)

                        # 右平移
                        Press([853,950])
                        Sleep(1)

                        runtimeContext._STEPAFTERRESTART = True

                    # 重置一次性標記
                    if runtimeContext._FIRST_DUNGEON_ENTRY:
                        runtimeContext._FIRST_DUNGEON_ENTRY = False
                    
                    if runtimeContext._MID_DUNGEON_START:
                        runtimeContext._MID_DUNGEON_START = False
                    
                    # [註: _RESTART_OPEN_MAP_PENDING 的重置已移至 DungeonMover 內部處理]
                    # 確保只有在成功於地圖點選新目標後才允許 Resume 優化

                    # 無論是 Resume 還是 Open Map，都統一轉交給 Map 狀態
                    # DungeonMover.initiate_move -> resume_navigation 會處理 Resume 和開地圖
                    dungState = DungeonState.Map
                case DungeonState.Map:
                    # [關鍵修復] 檢查是否需要重新載入目標列表（跳過回城後由 IdentifyState 設置）
                    if runtimeContext._RESET_TARGETS_PENDING:
                        logger.info("[StateDungeon] 偵測到目標重置標誌，退出以重新載入目標列表")
                        break  # 退出 StateDungeon，讓 DungeonFarm 重新初始化 targetInfoList
                    
                    # ==================== 使用 DungeonMover 統一處理移動 ====================
                    logger.info("[StateDungeon] 使用 DungeonMover 處理移動")
                    dungState = dungeon_mover.initiate_move(targetInfoList, runtimeContext)

                    # 檢查目標是否完成
                    if (targetInfoList is None) or (targetInfoList == []):
                        logger.info("地下城目標完成. 地下城狀態結束.(僅限任務模式.)")
                        elapsed_ms = (time.time() - state_handle_start) * 1000
                        logger.debug(f"[耗時] 地城狀態處理 {state_handle_name} (耗時 {elapsed_ms:.0f} ms)")
                        break


                case DungeonState.Chest:
                    needRecoverBecauseChest = True
                    dungState = StateChest()
                case DungeonState.Combat:
                    needRecoverBecauseCombat =True
                    combat_start = time.time()
                    StateCombat()
                    combat_elapsed_ms = (time.time() - combat_start) * 1000
                    logger.debug(f"[耗時] 戰鬥狀態處理 (耗時 {combat_elapsed_ms:.0f} ms)")
                    dungState = None
            elapsed_ms = (time.time() - state_handle_start) * 1000
            logger.debug(f"[耗時] 地城狀態處理 {state_handle_name} (耗時 {elapsed_ms:.0f} ms)")
    def StateAcceptRequest(request: str, pressbias:list = [0,0]):
        FindCoordsOrElseExecuteFallbackAndWait('Inn',[1,1],1)
        StateInn()
        Press(FindCoordsOrElseExecuteFallbackAndWait('guildRequest',['guild',[1,1]],1))
        Press(FindCoordsOrElseExecuteFallbackAndWait('guildFeatured',['guildRequest',[1,1]],1))
        for _ in range(3):
            Sleep(1)
            DeviceShell(f"input swipe 150 1000 150 200")
        Sleep(2)
        pos = FindCoordsOrElseExecuteFallbackAndWait(request,['input swipe 150 200 150 250',[1,1]],1)
        if not CheckIf(ScreenShot(),'request_accepted',[[0,pos[1]-200,900,pos[1]+200]]):
            FindCoordsOrElseExecuteFallbackAndWait(['Inn','guildRequest'],[[pos[0]+pressbias[0],pos[1]+pressbias[1]],'return',[1,1]],1)
            FindCoordsOrElseExecuteFallbackAndWait('Inn',['return',[1,1]],1)
        else:
            logger.info("奇怪, 任務怎麼已經接了.")
            FindCoordsOrElseExecuteFallbackAndWait('Inn',['return',[1,1]],1)

    def DungeonFarm():
        nonlocal runtimeContext
        # [Fix] 初始化戰鬥計數器，確保定點戰鬥邏輯正常運作
        runtimeContext._COMBAT_ACTION_COUNT = 0
        runtimeContext._COMBAT_BATTLE_COUNT = 0
        runtimeContext._FORCE_LOWHP_RECOVER = False  # 初始化低血量強制恢復標誌

        # 初始化監控狀態
        MonitorState.reset()
        MonitorState.karma_adjust = str(setting._KARMAADJUST)
        if runtimeContext._LAPTIME == 0:
            runtimeContext._LAPTIME = time.time()

        state = None
        initial_dungState = None  # 用於傳遞給 StateDungeon 的初始狀態
        targetInfoList = None     # 地城目標列表，應在單次地城運作中保持狀態
        while 1:
            try:
                check_stop_signal()  # 每次迭代開始時檢查停止信號
            except StopSignalException:
                logger.info("DungeonFarm 收到停止信號，優雅退出")
                break
            logger.info("======================")
            Sleep(1)
            
            # 更新監控狀態
            MonitorState.current_state = str(state.value) if state else "識別中"
            MonitorState.dungeon_count = runtimeContext._COUNTERDUNG
            MonitorState.combat_count = runtimeContext._COUNTERCOMBAT
            MonitorState.chest_count = runtimeContext._COUNTERCHEST
            if runtimeContext._LAPTIME > 0:
                MonitorState.total_time = runtimeContext._TOTALTIME + (time.time() - runtimeContext._LAPTIME)
            else:
                MonitorState.total_time = runtimeContext._TOTALTIME
            MonitorState.adb_retry_count = runtimeContext._COUNTERADBRETRY
            MonitorState.crash_counter = runtimeContext._CRASHCOUNTER
            MonitorState.battle_count = runtimeContext._COMBAT_BATTLE_COUNT
            MonitorState.action_count = runtimeContext._COMBAT_ACTION_COUNT
            MonitorState.aoe_triggered = runtimeContext._AOE_TRIGGERED_THIS_DUNGEON
            MonitorState.update_warnings()

            logger.info(f"當前狀態: {state}")
            match state:
                case None:
                    def _identifyState():
                        nonlocal state, initial_dungState
                        state, initial_dungState, _ = IdentifyState()
                    RestartableSequenceExecution(
                        lambda: _identifyState()
                        )
                    logger.info(f"下一狀態: {state}")
                    
                    # 地城內啟動偵測：如果首次識別就是 Dungeon 狀態，說明在地城內啟動
                    if state == State.Dungeon and runtimeContext._COUNTERDUNG == 0:
                        logger.info("[地城內啟動] 偵測到在地城內啟動腳本，初始化參數...")
                        runtimeContext._FIRST_DUNGEON_ENTRY = False  # 已經在地城內，不是第一次進入
                        runtimeContext._STEPAFTERRESTART = True      # 不需要防轉圈
                        # 重置戰鬥計數，讓黑屏偵測立即生效（視為新地城第一戰）
                        runtimeContext._AOE_TRIGGERED_THIS_DUNGEON = False
                        runtimeContext._COMBAT_ACTION_COUNT = 0
                        runtimeContext._COMBAT_BATTLE_COUNT = 0
                        runtimeContext._DUNGEON_CONFIRMED = True     # 直接確認在地城
                        # 不設置 _MID_DUNGEON_START = True，讓黑屏偵測正常觸發
                        logger.info("[地城內啟動] 參數初始化完成，黑屏偵測已啟用")
                    
                    if state ==State.Quit:
                        logger.info("即將停止腳本...")
                        break
                case State.Inn:
                    if runtimeContext._LAPTIME!= 0:
                        runtimeContext._TOTALTIME = runtimeContext._TOTALTIME + time.time() - runtimeContext._LAPTIME
                        summary_text = f"已完成{runtimeContext._COUNTERDUNG}次\"{setting._FARMTARGET_TEXT}\"地下城.\n總計{round(runtimeContext._TOTALTIME,2)}秒.上次用時:{round(time.time()-runtimeContext._LAPTIME,2)}秒.\n"
                        if runtimeContext._COUNTERCHEST > 0:
                            summary_text += f"箱子效率{round(runtimeContext._TOTALTIME/runtimeContext._COUNTERCHEST,2)}秒/箱.\n累計開箱{runtimeContext._COUNTERCHEST}次,開箱平均耗時{round(runtimeContext._TIME_CHEST_TOTAL/runtimeContext._COUNTERCHEST,2)}秒.\n"
                        if runtimeContext._COUNTERCOMBAT > 0:
                            summary_text += f"累計戰鬥{runtimeContext._COUNTERCOMBAT}次.戰鬥平均用時{round(runtimeContext._TIME_COMBAT_TOTAL/runtimeContext._COUNTERCOMBAT,2)}秒.\n"
                        if runtimeContext._COUNTERADBRETRY > 0 or runtimeContext._COUNTEREMULATORCRASH > 0:
                            summary_text += f"ADB重啓{runtimeContext._COUNTERADBRETRY}次,模擬器崩潰{runtimeContext._COUNTEREMULATORCRASH}次."
                        logger.info(f"{runtimeContext._IMPORTANTINFO}{summary_text}",extra={"summary": True})
                    runtimeContext._LAPTIME = time.time()
                    runtimeContext._COUNTERDUNG+=1
                    if not runtimeContext._MEET_CHEST_OR_COMBAT:
                        logger.info("因爲沒有遇到戰鬥或寶箱, 跳過恢復")
                    else:
                        # 回城後一定執行 StateInn（旅店休息間隔已整合到 should_skip_return_to_town）
                        logger.info("休息時間到!")
                        runtimeContext._MEET_CHEST_OR_COMBAT = False
                        # 重置連續刷地城計數器（在執行完 StateInn 之後）
                        runtimeContext._DUNGEON_REPEAT_COUNT = 0
                        targetInfoList = None  # 進入村莊時清除目標列表，確保下回合重新加載
                        RestartableSequenceExecution(
                        lambda:StateInn()
                        )
                    state = State.EoT
                case State.EoT:
                    RestartableSequenceExecution(
                        lambda:StateEoT()
                        )
                    state = State.Dungeon
                case State.Dungeon:
                    # 只有在正常進入地城時才重置，地城內啟動不重置（已在 case None 設定好）
                    is_mid_dungeon_start = initial_dungState in [DungeonState.Combat, DungeonState.Chest, DungeonState.Dungeon, DungeonState.Map]
                    if not is_mid_dungeon_start:
                        runtimeContext._FIRST_DUNGEON_ENTRY = True  # 重置第一次進入標誌
                        runtimeContext._DUNGEON_CONFIRMED = False  # 重置地城確認標記（新地城循環開始）
                        runtimeContext._MEET_CHEST_OR_COMBAT = False # [關鍵修復] 重置事件標誌，確保每場地城重新統計
                        reset_ae_caster_flags()  # 重置 AE 手相關旗標
                    else:
                        logger.debug("[地城內啟動] 跳過 flag 重置")

                    # 只有在列表為空或正式進入地城時才初始化
                    if targetInfoList is None or runtimeContext._RESET_TARGETS_PENDING:
                        logger.info(f"[DungeonFarm] 初始化地城目標列表 (原因: targetInfoList={targetInfoList is None}, RESET_TARGETS_PENDING={runtimeContext._RESET_TARGETS_PENDING})")
                        logger.info(f"[DEBUG] quest._TARGETINFOLIST 長度: {len(quest._TARGETINFOLIST) if quest._TARGETINFOLIST else 0}")
                        targetInfoList = quest._TARGETINFOLIST.copy()
                        logger.info(f"[DEBUG] 新 targetInfoList 長度: {len(targetInfoList) if targetInfoList else 0}, 首目標: {targetInfoList[0].target if targetInfoList else 'None'}")
                        runtimeContext._RESET_TARGETS_PENDING = False # 重置標誌

                    # 傳遞 initial_dungState 避免重複檢測（如 Chest 狀態）
                    _initial = initial_dungState
                    RestartableSequenceExecution(
                        lambda: StateDungeon(targetInfoList, _initial)
                        )
                    initial_dungState = None  # 使用後清除
                    state = None
        # 停止時重置監控狀態，避免 GUI 超時進度條繼續計算
        MonitorState.reset()
        # 通過消息隊列通知主線程，避免從工作線程直接調用 Tkinter 方法
        if setting._MSGQUEUE:
            setting._MSGQUEUE.put(('task_finished', None))
        elif setting._FINISHINGCALLBACK:
            setting._FINISHINGCALLBACK()
    def QuestFarm():
        nonlocal setting # 強制自動戰鬥 等等.
        nonlocal runtimeContext
        match setting._FARMTARGET:
            case '7000G':
                while 1:
                    if setting._FORCESTOPING.is_set():
                        break

                    starttime = time.time()
                    runtimeContext._COUNTERDUNG += 1
                    def stepMain():
                        logger.info("第一步: 開始詛咒之旅...")
                        Press(FindCoordsOrElseExecuteFallbackAndWait('cursedWheel_timeLeap',['ruins','cursedWheel',[1,1]],1))
                        Press(FindCoordsOrElseExecuteFallbackAndWait('cursedwheel_impregnableFortress',['cursedWheelTapRight',[1,1]],1))

                        if not Press(CheckIf(ScreenShot(),'FortressArrival')):
                            DeviceShell(f"input swipe 450 1200 450 200")
                            Press(FindCoordsOrElseExecuteFallbackAndWait('FortressArrival','input swipe 50 1200 50 1300',1))

                        while pos:= CheckIf(ScreenShot(), 'leap'):
                            if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                                return
                            Press(pos)
                            Sleep(2)
                            Press(CheckIf(ScreenShot(),'FortressArrival'))
                    RestartableSequenceExecution(
                        lambda: stepMain()
                        )

                    Sleep(10)
                    logger.info("第二步: 返回要塞...")
                    RestartableSequenceExecution(
                        lambda: FindCoordsOrElseExecuteFallbackAndWait('Inn',['returntotown','returnText','leaveDung','blessing',[1,1]],2)
                        )

                    logger.info("第三步: 前往王城...")
                    RestartableSequenceExecution(
                        lambda:TeleportFromCityToWorldLocation('RoyalCityLuknalia', 'input swipe 450 150 500 150'),
                        lambda:FindCoordsOrElseExecuteFallbackAndWait('guild',['RoyalCityLuknalia',[1,1]],1),
                        )

                    logger.info("第四步: 給我!(伸手)")
                    stepMark = -1
                    def stepMain():
                        nonlocal stepMark
                        if stepMark == -1:
                            Press(FindCoordsOrElseExecuteFallbackAndWait('guild',[1,1],1))
                            Press(FindCoordsOrElseExecuteFallbackAndWait('7000G/illgonow',[1,1],1))
                            Sleep(15)
                            FindCoordsOrElseExecuteFallbackAndWait(['7000G/olddist','7000G/iminhungry'],[1,1],2)
                            if pos:=CheckIf(scn:=ScreenShot(),'7000G/olddist'):
                                Press(pos)
                            else:
                                Press(CheckIf(scn,'7000G/iminhungry'))
                                Press(FindCoordsOrElseExecuteFallbackAndWait('7000G/olddist',[1,1],2))
                            stepMark = 0
                        if stepMark == 0:
                            Sleep(4)
                            Press([1,1])
                            Press([1,1])
                            Sleep(8)
                            Press(FindCoordsOrElseExecuteFallbackAndWait('7000G/royalcapital',[1,1],2))
                            FindCoordsOrElseExecuteFallbackAndWait('intoWorldMap',[1,1],2)
                            stepMark = 1
                        if stepMark == 1:
                            FindCoordsOrElseExecuteFallbackAndWait('fastforward',[450,1111],0)
                            FindCoordsOrElseExecuteFallbackAndWait('intoWorldMap',['7000G/why',[1,1]],2)
                            stepMark = 2
                        if stepMark == 2:
                            FindCoordsOrElseExecuteFallbackAndWait('fastforward',[200,1180],0)
                            FindCoordsOrElseExecuteFallbackAndWait('intoWorldMap',['7000G/why',[1,1]],2)
                            stepMark = 3
                        if stepMark == 3:
                            FindCoordsOrElseExecuteFallbackAndWait('fastforward',[680,1200],0)
                            Press(FindCoordsOrElseExecuteFallbackAndWait('7000G/leavethechild',['7000G/why',[1,1]],2))
                            stepMark = 4
                        if stepMark == 4:
                            Press(FindCoordsOrElseExecuteFallbackAndWait('7000G/icantagreewithU',[1,1],1))
                            stepMark = 5
                        if stepMark == 5:
                            Press(FindCoordsOrElseExecuteFallbackAndWait('7000G/illgo',[[1,1],'7000G/olddist'],1))
                            Press(FindCoordsOrElseExecuteFallbackAndWait('7000G/noeasytask',[1,1],1))
                            FindCoordsOrElseExecuteFallbackAndWait('ruins',[1,1],1)
                    RestartableSequenceExecution(
                        lambda: stepMain()
                        )
                    costtime = time.time()-starttime
                    logger.info(f"第{runtimeContext._COUNTERDUNG}次\"7000G\"完成. 該次花費時間{costtime:.2f}, 每秒收益:{7000/costtime:.2f}Gps.",
                                extra={"summary": True})
            case 'fordraig':
                quest._SPECIALDIALOGOPTION = ['fordraig/thedagger','fordraig/InsertTheDagger']
                while 1:
                    if setting._FORCESTOPING.is_set():
                        break
                    runtimeContext._COUNTERDUNG += 1
                    setting._SYSTEMAUTOCOMBAT = True
                    starttime = time.time()
                    logger.info('第一步: 詛咒之旅...')
                    RestartableSequenceExecution(
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait('cursedWheel',['ruins',[1,1]],1)),
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait('Fordraig/Leap',['specialRequest',[1,1]],1)),
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait('OK','leap',1)),
                        )
                    Sleep(15)

                    RestartableSequenceExecution(
                        lambda: logger.info('第二步: 領取任務.'),
                        lambda: StateAcceptRequest('fordraig/RequestAccept',[350,180])
                        )

                    logger.info('第三步: 進入地下城.')
                    TeleportFromCityToWorldLocation('fordraig/labyrinthOfFordraig','input swipe 450 150 500 150')
                    Press(FindCoordsOrElseExecuteFallbackAndWait('fordraig/Entrance',['fordraig/labyrinthOfFordraig',[1,1]],1))
                    FindCoordsOrElseExecuteFallbackAndWait('dungFlag',['fordraig/Entrance','GotoDung',[1,1]],1)

                    logger.info('第四步: 陷阱.')
                    RestartableSequenceExecution(
                        lambda:StateDungeon([
                            TargetInfo('position',"左上",[721,448]),
                            TargetInfo('position',"左上",[720,608])]), # 前往第一個陷阱
                        lambda:FindCoordsOrElseExecuteFallbackAndWait("dungFlag","return",1), # 關閉地圖
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait("fordraig/TryPushingIt",["input swipe 100 250 800 250",[400,800],[400,800],[400,800]],1)), # 轉向來開啓機關
                        )
                    logger.info('已完成第一個陷阱.')

                    RestartableSequenceExecution(
                        lambda:StateDungeon([
                            TargetInfo('stair_down',"左上",[721,236]),
                            TargetInfo('position',"左下", [240,921])]), #前往第二個陷阱
                        lambda:FindCoordsOrElseExecuteFallbackAndWait("dungFlag","return",1), # 關閉地圖
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait("fordraig/TryPushingIt",["input swipe 100 250 800 250",[400,800],[400,800],[400,800]],1)), # 轉向來開啓機關
                        )
                    logger.info('已完成第二個陷阱.')

                    RestartableSequenceExecution(
                        lambda:StateDungeon([
                            TargetInfo("position","左下",[33,1238]),
                            TargetInfo("stair_down","左下",[453,1027]),
                            TargetInfo("position","左下",[187,1027]),
                            TargetInfo("stair_teleport","左下",[80,1026])
                            ]), #前往第三個陷阱
                        )
                    logger.info('已完成第三個陷阱.')

                    StateDungeon([TargetInfo('position','左下',[508,1025])]) # 前往boss戰門前
                    setting._SYSTEMAUTOCOMBAT = False
                    StateDungeon([TargetInfo('position','左下',[720,1025])]) # 前往boss戰鬥
                    setting._SYSTEMAUTOCOMBAT = True
                    StateDungeon([TargetInfo('stair_teleport','左上',[665,395])]) # 第四層出口
                    FindCoordsOrElseExecuteFallbackAndWait("dungFlag","return",1)
                    Press(FindCoordsOrElseExecuteFallbackAndWait("ReturnText",["leaveDung",[455,1200]],3.75)) # 回城
                    # 3.75什麼意思 正常循環是3秒 有4次嘗試機會 因此3.75秒按一次剛剛好.
                    Press(FindCoordsOrElseExecuteFallbackAndWait("RoyalCityLuknalia",['return',[1,1]],1)) # 回城
                    FindCoordsOrElseExecuteFallbackAndWait("Inn",[1,1],1)

                    costtime = time.time()-starttime
                    logger.info(f"第{runtimeContext._COUNTERDUNG}次\"鳥劍\"完成. 該次花費時間{costtime:.2f}.",
                            extra={"summary": True})
            case 'repelEnemyForces':
                # 使用連續刷地城次數控制每回合戰鬥次數
                if setting._DUNGEON_REPEAT_LIMIT <= 0:
                    logger.info("注意, \"連續刷地城\"控制連續戰鬥多少次後回城. 當前值<=0, 強制設置爲1.")
                    setting._DUNGEON_REPEAT_LIMIT = 1
                logger.info("注意, 該流程不包括時間跳躍和接取任務, 請確保接取任務後再開啓!")
                counter = 0
                while 1:
                    if setting._FORCESTOPING.is_set():
                        break
                    t = time.time()
                    RestartableSequenceExecution(
                        lambda : StateInn()
                    )
                    RestartableSequenceExecution(
                        lambda : Press(FindCoordsOrElseExecuteFallbackAndWait('TradeWaterway','EdgeOfTown',1)),
                        lambda : FindCoordsOrElseExecuteFallbackAndWait('7thDist',[1,1],1),
                        lambda : FindCoordsOrElseExecuteFallbackAndWait('dungFlag',['7thDist','GotoDung',[1,1]],1),
                    )
                    RestartableSequenceExecution(
                        lambda : StateDungeon([TargetInfo('position','左下',[559,599]),
                                               TargetInfo('position','左下',[186,813])])
                    )
                    logger.info('已抵達目標地點, 開始戰鬥.')
                    FindCoordsOrElseExecuteFallbackAndWait('dungFlag',['return',[1,1]],1)
                    for i in range(setting._DUNGEON_REPEAT_LIMIT):
                        logger.info(f"第{i+1}輪開始.")
                        secondcombat = False
                        combat_loop_start = time.time()
                        MAX_COMBAT_LOOP_TIME = 300  # 單輪最多 5 分鐘
                        while time.time() - combat_loop_start < MAX_COMBAT_LOOP_TIME:
                            if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                                return
                            Press(FindCoordsOrElseExecuteFallbackAndWait(['icanstillgo','combatActive','combatActive_2'],['input swipe 400 400 400 100',[1,1]],1))
                            Sleep(1)
                            inner_loop_count = 0
                            MAX_INNER_LOOP = 200  # 內層循環最多 200 次
                            while inner_loop_count < MAX_INNER_LOOP:
                                if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                                    return
                                scn=ScreenShot()
                                if TryPressRetry(scn):
                                    inner_loop_count += 1
                                    continue
                                if CheckIf(scn,'icanstillgo'):
                                    break
                                if CheckIf(scn,'combatActive') or CheckIf(scn,'combatActive_2'):
                                    StateCombat()
                                else:
                                    Press([1,1])
                                inner_loop_count += 1
                            if inner_loop_count >= MAX_INNER_LOOP:
                                logger.warning(f"戰鬥內層循環超過 {MAX_INNER_LOOP} 次，強制退出")
                                break
                            if not secondcombat:
                                logger.info(f"第1場戰鬥結束.")
                                secondcombat = True
                                Press(CheckIf(ScreenShot(),'icanstillgo'))
                            else:
                                logger.info(f"第2場戰鬥結束.")
                                Press(CheckIf(ScreenShot(),'letswithdraw'))
                                Sleep(1)
                                break
                        if time.time() - combat_loop_start >= MAX_COMBAT_LOOP_TIME:
                            logger.warning(f"戰鬥循環超時 {MAX_COMBAT_LOOP_TIME} 秒，強制退出本輪")
                        logger.info(f"第{i+1}輪結束.")
                    RestartableSequenceExecution(
                        lambda:StateDungeon([TargetInfo('position','左上',[612,448])])
                    )
                    RestartableSequenceExecution(
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait('returnText',[[1,1],'leaveDung','return'],3))
                    )
                    RestartableSequenceExecution(
                        lambda:FindCoordsOrElseExecuteFallbackAndWait('Inn',['return',[1,1]],1)
                    )
                    counter+=1
                    logger.info(f"第{counter}x{setting._DUNGEON_REPEAT_LIMIT}輪\"擊退敵勢力\"完成, 共計{counter*setting._DUNGEON_REPEAT_LIMIT*2}場戰鬥. 該次花費時間{(time.time()-t):.2f}秒.",
                                    extra={"summary": True})
            case 'darkLight':
                gameFrozen_none = []
                dungState = None
                shouldRecover = False
                needRecoverBecauseCombat = False
                needRecoverBecauseChest = False
                while 1:
                    if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                        break
                    _, dungState,_ = IdentifyState()
                    logger.info(dungState)
                    match dungState:
                        case None:
                            s, dungState,scn = IdentifyState()
                            if (s == State.Inn) or (dungState == DungeonState.Quit):
                                break
                            gameFrozen_none, result = GameFrozenCheck(gameFrozen_none,scn)
                            if result:
                                logger.info("由於畫面卡死, 在state:None中重啓.")
                                restartGame()
                            MAXTIMEOUT = 400
                            if (runtimeContext._TIME_CHEST != 0 ) and (time.time()-runtimeContext._TIME_CHEST > MAXTIMEOUT):
                                logger.info("由於寶箱用時過久, 在state:None中重啓.")
                                restartGame()
                            if (runtimeContext._TIME_COMBAT != 0) and (time.time()-runtimeContext._TIME_COMBAT > MAXTIMEOUT):
                                logger.info("由於戰鬥用時過久, 在state:None中重啓.")
                                restartGame()
                        case DungeonState.Dungeon:
                            Press([1,1])
                            ########### COMBAT RESET
                            # 戰鬥結束了, 我們將一些設置復位
                            ########### TIMER
                            if (runtimeContext._TIME_CHEST !=0) or (runtimeContext._TIME_COMBAT!=0):
                                spend_on_chest = 0
                                if runtimeContext._TIME_CHEST !=0:
                                    spend_on_chest = time.time()-runtimeContext._TIME_CHEST
                                    runtimeContext._TIME_CHEST = 0
                                spend_on_combat = 0
                                if runtimeContext._TIME_COMBAT !=0:
                                    spend_on_combat = time.time()-runtimeContext._TIME_COMBAT
                                    runtimeContext._TIME_COMBAT = 0
                                logger.info(f"粗略統計: 寶箱{spend_on_chest:.2f}秒, 戰鬥{spend_on_combat:.2f}秒.")
                                if (spend_on_chest!=0) and (spend_on_combat!=0):
                                    if spend_on_combat>spend_on_chest:
                                        runtimeContext._TIME_COMBAT_TOTAL = runtimeContext._TIME_COMBAT_TOTAL + spend_on_combat-spend_on_chest
                                        runtimeContext._TIME_CHEST_TOTAL = runtimeContext._TIME_CHEST_TOTAL + spend_on_chest
                                    else:
                                        runtimeContext._TIME_CHEST_TOTAL = runtimeContext._TIME_CHEST_TOTAL + spend_on_chest-spend_on_combat
                                        runtimeContext._TIME_COMBAT_TOTAL = runtimeContext._TIME_COMBAT_TOTAL + spend_on_combat
                                else:
                                    runtimeContext._TIME_COMBAT_TOTAL = runtimeContext._TIME_COMBAT_TOTAL + spend_on_combat
                                    runtimeContext._TIME_CHEST_TOTAL = runtimeContext._TIME_CHEST_TOTAL + spend_on_chest
                            ########### RECOVER
                            if needRecoverBecauseChest:
                                logger.info("進行開啓寶箱後的恢復.")
                                runtimeContext._COUNTERCHEST+=1
                                needRecoverBecauseChest = False
                                runtimeContext._MEET_CHEST_OR_COMBAT = True
                                if not setting._SKIPCHESTRECOVER:
                                    logger.info("由於面板配置, 進行開啓寶箱後恢復.")
                                    shouldRecover = True
                                else:
                                    logger.info("由於面板配置, 跳過了開啓寶箱後恢復.")
                            if needRecoverBecauseCombat:
                                runtimeContext._COUNTERCOMBAT+=1
                                needRecoverBecauseCombat = False
                                runtimeContext._MEET_CHEST_OR_COMBAT = True
                                if (not setting._SKIPCOMBATRECOVER):
                                    logger.info("由於面板配置, 進行戰後恢復.")
                                    shouldRecover = True
                                else:
                                    logger.info("由於面板配置, 跳過了戰後後恢復.")
                            if shouldRecover:
                                Press([1,1])
                                FindCoordsOrElseExecuteFallbackAndWait( # 點擊打開人物面板有可能會被戰鬥打斷
                                    ['trait','combatActive','combatActive_2','chestFlag','combatClose'],
                                    [[36,1425],[322,1425],[606,1425]],
                                    1
                                    )
                                if CheckIf(ScreenShot(),'trait'):
                                    Press([833,843])
                                    Sleep(1)
                                    FindCoordsOrElseExecuteFallbackAndWait(
                                        ['recover','combatActive','combatActive_2'],
                                        [833,843],
                                        1
                                        )
                                    if CheckIf(ScreenShot(),'recover'):
                                        Sleep(1)
                                        Press([600,1200])
                                        for _ in range(5):
                                            t = time.time()
                                            PressReturn()
                                            if time.time()-t<0.3:
                                                Sleep(0.3-(time.time()-t))
                                        shouldRecover = False
                            ########### light the dark light
                            Press(FindCoordsOrElseExecuteFallbackAndWait('darklight_lightIt','darkLight',1))
                        case DungeonState.Chest:
                            needRecoverBecauseChest = True
                            dungState = StateChest()
                        case DungeonState.Combat:
                            needRecoverBecauseCombat =True
                            StateCombat()
                            dungState = None
            case 'LBC-oneGorgon':
                while 1:
                    if setting._FORCESTOPING.is_set():
                        break
                    if runtimeContext._LAPTIME!= 0:
                        runtimeContext._TOTALTIME = runtimeContext._TOTALTIME + time.time() - runtimeContext._LAPTIME
                        logger.info(f"第{runtimeContext._COUNTERDUNG}次三牛完成. 本次用時:{round(time.time()-runtimeContext._LAPTIME,2)}秒. 累計開箱子{runtimeContext._COUNTERCHEST}, 累計戰鬥{runtimeContext._COUNTERCOMBAT}, 累計用時{round(runtimeContext._TOTALTIME,2)}秒.",
                                    extra={"summary": True})
                    runtimeContext._LAPTIME = time.time()
                    runtimeContext._COUNTERDUNG+=1

                    RestartableSequenceExecution(
                        lambda: logger.info('第一步: 重置因果'),
                        lambda: CursedWheelTimeLeap(None,'LBC/symbolofalliance',[['LBC/EnaWasSaved',2,1,0]])
                        )
                    Sleep(10)
                    RestartableSequenceExecution(
                        lambda: logger.info("第二步: 返回要塞"),
                        lambda: FindCoordsOrElseExecuteFallbackAndWait('Inn',['returntotown','returnText','leaveDung','blessing',[1,1]],2)
                        )
                    RestartableSequenceExecution(
                        lambda: logger.info("第三步: 前往王城"),
                        lambda: TeleportFromCityToWorldLocation('RoyalCityLuknalia','input swipe 450 150 500 150'),
                        lambda: FindCoordsOrElseExecuteFallbackAndWait('guild',['RoyalCityLuknalia',[1,1]],1),
                        )
               
                    RestartableSequenceExecution(
                        lambda: logger.info('第四步: 領取任務'),
                        lambda: StateAcceptRequest('LBC/Request',[266,257]),
                    )
                    RestartableSequenceExecution(
                        lambda: logger.info('第五步: 進入牛洞'),
                        lambda: TeleportFromCityToWorldLocation('LBC/LBC','input swipe 400 400 400 500')
                        )

                    Gorgon1 = TargetInfo('position','左上',[134,342])
                    Gorgon2 = TargetInfo('position','右上',[500,395])
                    Gorgon3 = TargetInfo('position','右下',[340,1027])
                    LBC_quit = TargetInfo('LBC/LBC_quit')
                    # 使用連續刷地城設定判斷是否中途休息
                    if setting._DUNGEON_REPEAT_LIMIT > 0:
                        RestartableSequenceExecution(
                            lambda: logger.info('第六步: 擊殺一牛'),
                            lambda: StateDungeon([Gorgon1,LBC_quit])
                            )
                        RestartableSequenceExecution(
                            lambda: logger.info('第七步: 回去睡覺'),
                            lambda: StateInn()
                            )
                        RestartableSequenceExecution(
                            lambda: logger.info('第八步: 再入牛洞'),
                            lambda: TeleportFromCityToWorldLocation('LBC/LBC','input swipe 400 400 400 500')
                            )
                        RestartableSequenceExecution(
                            lambda: logger.info('第九步: 擊殺二牛'),
                            lambda: StateDungeon([Gorgon2,Gorgon3,LBC_quit])
                            )
                    else:
                        logger.info('跳過回城休息.')
                        RestartableSequenceExecution(
                            lambda: logger.info('第六步: 連殺三牛'),
                            lambda: StateDungeon([Gorgon1,Gorgon2,Gorgon3,LBC_quit])
                            )
            case 'SSC-goldenchest':
                while 1:
                    quest._SPECIALDIALOGOPTION = ['SSC/dotdotdot','SSC/shadow']
                    if setting._FORCESTOPING.is_set():
                        break
                    if runtimeContext._LAPTIME!= 0:
                        runtimeContext._TOTALTIME = runtimeContext._TOTALTIME + time.time() - runtimeContext._LAPTIME
                        logger.info(f"第{runtimeContext._COUNTERDUNG}次忍洞完成. 本次用時:{round(time.time()-runtimeContext._LAPTIME,2)}秒. 累計開箱子{runtimeContext._COUNTERCHEST}, 累計戰鬥{runtimeContext._COUNTERCOMBAT}, 累計用時{round(runtimeContext._TOTALTIME,2)}秒.",
                                    extra={"summary": True})
                    runtimeContext._LAPTIME = time.time()
                    runtimeContext._COUNTERDUNG+=1
                    RestartableSequenceExecution(
                        lambda: logger.info('第一步: 重置因果'),
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait('cursedWheel',['ruins',[1,1]],1)),
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait('SSC/Leap',['specialRequest',[1,1]],1)),
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait('OK','leap',1)),
                        )
                    Sleep(10)
                    RestartableSequenceExecution(
                        lambda: logger.info("第二步: 前往王城"),
                        lambda: TeleportFromCityToWorldLocation('RoyalCityLuknalia','input swipe 450 150 500 150'),
                        lambda: FindCoordsOrElseExecuteFallbackAndWait('guild',['RoyalCityLuknalia',[1,1]],1),
                        )
                    def stepThree():
                        FindCoordsOrElseExecuteFallbackAndWait('Inn',[1,1],1)
                        StateInn()
                        Press(FindCoordsOrElseExecuteFallbackAndWait('guildRequest',['guild',[1,1]],1))
                        Press(FindCoordsOrElseExecuteFallbackAndWait('guildFeatured',['guildRequest',[1,1]],1))
                        Sleep(1)
                        DeviceShell(f"input swipe 150 1300 150 200")
                        Sleep(2)
                        MAX_SSC_SWIPES = 20  # 最大滑動次數
                        ssc_swipe_count = 0
                        while ssc_swipe_count < MAX_SSC_SWIPES:
                            if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                                return
                            pos = CheckIf(ScreenShot(),'SSC/Request')
                            if not pos:
                                DeviceShell(f"input swipe 150 200 150 250")
                                ssc_swipe_count += 1
                                Sleep(1)
                            else:
                                Press(pos)
                                break
                        if ssc_swipe_count >= MAX_SSC_SWIPES:
                            logger.warning(f"SSC 任務搜索超過 {MAX_SSC_SWIPES} 次，未找到任務")
                        FindCoordsOrElseExecuteFallbackAndWait('guildRequest',[1,1],1)
                        PressReturn()
                    RestartableSequenceExecution(
                        lambda: logger.info('第三步: 領取任務'),
                        lambda: stepThree()
                        )

                    RestartableSequenceExecution(
                        lambda: logger.info('第四步: 進入忍洞'),
                        lambda: TeleportFromCityToWorldLocation('SSC/SSC','input swipe 700 500 600 600')
                        )
                    RestartableSequenceExecution(
                        lambda: logger.info('第五步: 關閉陷阱'),
                        lambda:FindCoordsOrElseExecuteFallbackAndWait('SSC/trapdeactived',['input swipe 450 1050 450 850',[445,721]],4),
                        lambda:FindCoordsOrElseExecuteFallbackAndWait('dungFlag',[1,1],1)
                    )
                    quest._SPECIALDIALOGOPTION = ['SSC/dotdotdot','SSC/shadow']
                    RestartableSequenceExecution(
                        lambda: logger.info('第六步: 第一個箱子'),
                        lambda: StateDungeon([
                                TargetInfo('position',     '左上', [719,1088]),
                                TargetInfo('position',     '左上', [346,874]),
                                TargetInfo('chest',        '左上', [[0,0,900,1600],[640,0,260,1600],[506,0,200,700]]),
                                TargetInfo('chest',        '右上', [[0,0,900,1600],[0,0,407,1600]]),
                                TargetInfo('chest',        '右下', [[0,0,900,1600],[0,0,900,800]]),
                                TargetInfo('chest',        '左下', [[0,0,900,1600],[650,0,250,811],[507,166,179,165]]),
                                TargetInfo('SSC/SSC_quit', '右下', None)
                            ])
                        )
            case 'CaveOfSeperation':
                while 1:
                    if setting._FORCESTOPING.is_set():
                        break
                    if runtimeContext._LAPTIME!= 0:
                        runtimeContext._TOTALTIME = runtimeContext._TOTALTIME + time.time() - runtimeContext._LAPTIME
                        logger.info(f"第{runtimeContext._COUNTERDUNG}次約定之劍完成. 本次用時:{round(time.time()-runtimeContext._LAPTIME,2)}秒. 累計開箱子{runtimeContext._COUNTERCHEST}, 累計戰鬥{runtimeContext._COUNTERCOMBAT}, 累計用時{round(runtimeContext._TOTALTIME,2)}秒.",
                                    extra={"summary": True})
                    runtimeContext._LAPTIME = time.time()
                    runtimeContext._COUNTERDUNG+=1
                    RestartableSequenceExecution(
                        lambda: logger.info('第一步: 重置因果'),
                        lambda: CursedWheelTimeLeap(None,'COS/ArnasPast')
                        )
                    Sleep(10)
                    RestartableSequenceExecution(
                        lambda: logger.info("第二步: 返回要塞"),
                        lambda: FindCoordsOrElseExecuteFallbackAndWait('Inn',['returntotown','returnText','leaveDung','blessing',[1,1]],2)
                        )
                    RestartableSequenceExecution(
                        lambda: logger.info("第三步: 前往王城"),
                        lambda: TeleportFromCityToWorldLocation('RoyalCityLuknalia','input swipe 450 150 500 150'),
                        lambda: FindCoordsOrElseExecuteFallbackAndWait('guild',['RoyalCityLuknalia',[1,1]],1),
                        )
                    
                    RestartableSequenceExecution(
                        lambda: logger.info('第四步: 領取任務'),
                        lambda: FindCoordsOrElseExecuteFallbackAndWait(['COS/Okay','guildRequest'],['guild',[1,1]],1),
                        lambda: FindCoordsOrElseExecuteFallbackAndWait('Inn',['COS/Okay','return',[1,1]],1),
                        lambda: StateInn(),
                        )
                    
                    RestartableSequenceExecution(
                        lambda: logger.info('第五步: 進入洞窟'),
                        lambda: Press(FindCoordsOrElseExecuteFallbackAndWait('COS/COS',['EdgeOfTown',[1,1]],1)),
                        lambda: Press(FindCoordsOrElseExecuteFallbackAndWait('COS/COSENT',[1,1],1))
                        )
                    quest._SPECIALDIALOGOPTION = ['COS/takehimwithyou']
                    cosb1f = [TargetInfo('position',"右下",[286-54,440]),
                              TargetInfo('position',"右下",[819,653+54]),
                              TargetInfo('position',"右上",[659-54,501]),
                              TargetInfo('stair_2',"右上",[126-54,342]),
                        ]
                    RestartableSequenceExecution(
                        lambda: logger.info('第六步: 1層找人'),
                        lambda: StateDungeon(cosb1f)
                        )

                    quest._SPECIALFORCESTOPINGSYMBOL = ['COS/EnaTheAdventurer']
                    cosb2f = [TargetInfo('position',"右上",[340+54,448]),
                              TargetInfo('position',"右上",[500-54,1088]),
                              TargetInfo('position',"左上",[398+54,766]),
                        ]
                    RestartableSequenceExecution(
                        lambda: logger.info('第七步: 2層找人'),
                        lambda: StateDungeon(cosb2f)
                        )

                    quest._SPECIALFORCESTOPINGSYMBOL = ['COS/requestwasfor'] 
                    cosb3f = [TargetInfo('stair_3',"左上",[720,822]),
                              TargetInfo('position',"左下",[239,600]),
                              TargetInfo('position',"左下",[185,1185]),
                              TargetInfo('position',"左下",[560,652]),
                              ]
                    RestartableSequenceExecution(
                        lambda: logger.info('第八步: 3層找人'),
                        lambda: StateDungeon(cosb3f)
                        )

                    quest._SPECIALFORCESTOPINGSYMBOL = None
                    quest._SPECIALDIALOGOPTION = ['COS/requestwasfor'] 
                    cosback2f = [
                                 TargetInfo('stair_2',"左下",[827,547]),
                                 TargetInfo('position',"右上",[340+54,448]),
                                 TargetInfo('position',"右上",[500-54,1088]),
                                 TargetInfo('position',"左上",[398+54,766]),
                                 TargetInfo('position',"左上",[559,1087]),
                                 TargetInfo('stair_1',"左上",[666,448]),
                                 TargetInfo('position', "右下",[660,919])
                        ]
                    RestartableSequenceExecution(
                        lambda: logger.info('第九步: 離開洞穴'),
                        lambda: StateDungeon(cosback2f)
                        )
                    Press(FindCoordsOrElseExecuteFallbackAndWait("guild",['return',[1,1]],1)) # 回城
                    FindCoordsOrElseExecuteFallbackAndWait("Inn",['return',[1,1]],1)
                    
                pass
            case 'gaintKiller':
                while 1:
                    if setting._FORCESTOPING.is_set():
                        break
                    if runtimeContext._LAPTIME!= 0:
                        runtimeContext._TOTALTIME = runtimeContext._TOTALTIME + time.time() - runtimeContext._LAPTIME
                        logger.info(f"第{runtimeContext._COUNTERDUNG}次巨人完成. 本次用時:{round(time.time()-runtimeContext._LAPTIME,2)}秒. 累計開箱子{runtimeContext._COUNTERCHEST}, 累計戰鬥{runtimeContext._COUNTERCOMBAT}, 累計用時{round(runtimeContext._TOTALTIME,2)}秒.",
                                    extra={"summary": True})
                    runtimeContext._LAPTIME = time.time()
                    runtimeContext._COUNTERDUNG+=1

                    quest._EOT = [
                        ["press","impregnableFortress",["EdgeOfTown",[1,1]],1],
                        ["press","fortressb7f",[1,1],1]]
                    RestartableSequenceExecution(
                        lambda: StateEoT()
                        )
                    RestartableSequenceExecution(
                        lambda: StateDungeon([TargetInfo('position','左上',[560,928])]),
                        lambda: FindCoordsOrElseExecuteFallbackAndWait('dungFlag','return',1)
                    )

                    counter_candelabra = 0
                    for _ in range(3):
                        scn = ScreenShot()
                        if CheckIf(scn,"gaint_candelabra_1") or CheckIf(scn,"gaint_candelabra_2"):
                            counter_candelabra+=1
                        Sleep(1)
                    if counter_candelabra != 0:
                        logger.info("沒發現巨人.")
                        RestartableSequenceExecution(
                        lambda: StateDungeon([TargetInfo('harken2','左上')]),
                        lambda: FindCoordsOrElseExecuteFallbackAndWait('Inn',['returntotown','returnText','leaveDung','blessing',[1,1]],2)
                    )
                        continue
                    
                    logger.info("發現了巨人.")
                    RestartableSequenceExecution(
                        lambda: StateDungeon([TargetInfo('position','左上',[560,928+54],True),
                                              TargetInfo('harken2','左上')]),
                        lambda: FindCoordsOrElseExecuteFallbackAndWait('Inn',['returntotown','returnText','leaveDung','blessing',[1,1]],2)
                    )

                    # 每 N 次地城後回旅店休息
                    if (runtimeContext._COUNTERDUNG % max(setting._DUNGEON_REPEAT_LIMIT, 1) == 0):
                        RestartableSequenceExecution(
                            lambda: StateInn()
                        )
            case 'Scorpionesses':
                total_time = 0
                while 1:
                    if setting._FORCESTOPING.is_set():
                        break

                    starttime = time.time()
                    runtimeContext._COUNTERDUNG += 1

                    RestartableSequenceExecution(
                        lambda: CursedWheelTimeLeap()
                        )

                    Sleep(10)
                    logger.info("第二步: 返回要塞...")
                    RestartableSequenceExecution(
                        lambda: FindCoordsOrElseExecuteFallbackAndWait('Inn',['returntotown','returnText','leaveDung','blessing',[1,1]],2)
                        )

                    logger.info("第三步: 前往王城...")
                    RestartableSequenceExecution(
                        lambda:TeleportFromCityToWorldLocation('RoyalCityLuknalia','input swipe 450 150 500 150'),
                        )

                    logger.info("第四步: 懸賞揭榜")
                    RestartableSequenceExecution(
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait('guildRequest',['guild',[1,1]],1)),
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait('Bounties',['guild','guildRequest','input swipe 600 1400 300 1400',[1,1]],1)),
                        lambda:FindCoordsOrElseExecuteFallbackAndWait('EdgeOfTown',['return',[1,1]],1)
                        )

                    logger.info("第五步: 擊殺蠍女")
                    RestartableSequenceExecution(
                        lambda:FindCoordsOrElseExecuteFallbackAndWait('dungFlag',['EdgeOfTown','beginningAbyss','B2FTemple','GotoDung',[1,1]],1),
                    )
                    RestartableSequenceExecution(
                        lambda:StateDungeon([TargetInfo('position','左下',[505,760]),
                                             TargetInfo('position','左上',[506,821])]),
                        )
                    
                    logger.info("第六步: 提交懸賞")
                    RestartableSequenceExecution(
                        lambda:FindCoordsOrElseExecuteFallbackAndWait("guild",['return',[1,1]],1),
                    )
                    RestartableSequenceExecution(
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait('CompletionReported',['guild','guildRequest','input swipe 600 1400 300 1400','Bounties',[1,1]],1))
                        )
                    RestartableSequenceExecution(
                        lambda:FindCoordsOrElseExecuteFallbackAndWait('EdgeOfTown',['return',[1,1]],1)
                        )
                    
                    logger.info("第七步: 休息")
                    # 每 N 次地城後回旅店休息
                    if (runtimeContext._COUNTERDUNG % max(setting._DUNGEON_REPEAT_LIMIT, 1) == 0):
                        RestartableSequenceExecution(
                            lambda:StateInn()
                            )
                        
                    costtime = time.time()-starttime
                    total_time = total_time + costtime
                    logger.info(f"第{runtimeContext._COUNTERDUNG}次\"懸賞:蠍女\"完成. \n該次花費時間{costtime:.2f}s.\n總計用時{total_time:.2f}s.\n平均用時{total_time/runtimeContext._COUNTERDUNG:.2f}",
                            extra={"summary": True})
            case 'steeltrail':
                total_time = 0
                while 1:
                    if setting._FORCESTOPING.is_set():
                        break

                    starttime = time.time()
                    runtimeContext._COUNTERDUNG += 1

                    RestartableSequenceExecution(
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait('guildRequest',['guild',[1,1]],1)),
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait('gradeexam',['guild','guildRequest','input swipe 600 1400 300 1400',[1,1]],1)),
                        lambda:FindCoordsOrElseExecuteFallbackAndWait("Steel",'gradeexam',1)
                    )

                    pos = CheckIf(ScreenShot(),'Steel')
                    Press([pos[0]+306,pos[1]+258])
                    
                    quest._SPECIALDIALOGOPTION = ['ready','noneed', 'quit']
                    RestartableSequenceExecution(
                        StateDungeon([TargetInfo('position','左上',[131,769]),
                                    TargetInfo('position','左上',[827,447]),
                                    TargetInfo('position','左上',[131,769]),
                                    TargetInfo('position','左下',[719,1080]),
                                    ])
                                  )
                    
                    # 每 N 次地城後回旅店休息
                    if (runtimeContext._COUNTERDUNG % max(setting._DUNGEON_REPEAT_LIMIT, 1) == 0):
                        RestartableSequenceExecution(
                            lambda:StateInn()
                            )
                    costtime = time.time()-starttime
                    total_time = total_time + costtime
                    logger.info(f"第{runtimeContext._COUNTERDUNG}次\"鋼試煉\"完成. \n該次花費時間{costtime:.2f}s.\n總計用時{total_time:.2f}s.\n平均用時{total_time/runtimeContext._COUNTERDUNG:.2f}",
                            extra={"summary": True})

            case 'jier':
                total_time = 0
                while 1:
                    quest._SPECIALDIALOGOPTION = ['bounty/cuthimdown']

                    if setting._FORCESTOPING.is_set():
                        break

                    starttime = time.time()
                    runtimeContext._COUNTERDUNG += 1

                    RestartableSequenceExecution(
                        lambda: CursedWheelTimeLeap("requestToRescueTheDuke")
                        )

                    Sleep(10)
                    logger.info("第二步: 返回要塞...")
                    RestartableSequenceExecution(
                        lambda: FindCoordsOrElseExecuteFallbackAndWait('Inn',['returntotown','returnText','leaveDung','blessing',[1,1]],2)
                        )

                    logger.info("第三步: 前往王城...")
                    RestartableSequenceExecution(
                        lambda:TeleportFromCityToWorldLocation('RoyalCityLuknalia','input swipe 450 150 500 150'),
                        )

                    logger.info("第四步: 懸賞揭榜")
                    RestartableSequenceExecution(
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait('guildRequest',['guild',[1,1]],1)),
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait('Bounties',['guild','guildRequest','input swipe 600 1400 300 1400',[1,1]],1)),
                        lambda:FindCoordsOrElseExecuteFallbackAndWait('EdgeOfTown',['return',[1,1]],1)
                        )

                    logger.info("第五步: 和吉爾說再見吧")
                    RestartableSequenceExecution(
                        lambda:FindCoordsOrElseExecuteFallbackAndWait('dungFlag',['EdgeOfTown','beginningAbyss','B4FLabyrinth','GotoDung',[1,1]],1)
                        )
                    RestartableSequenceExecution( 
                        lambda:StateDungeon([TargetInfo('position','左下',[452,1026]),
                                             TargetInfo('harken','左上',None)]),
                        )
                    
                    logger.info("第六步: 提交懸賞")
                    RestartableSequenceExecution(
                        lambda:FindCoordsOrElseExecuteFallbackAndWait("guild",['return',[1,1]],1),
                    )
                    RestartableSequenceExecution(
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait('CompletionReported',['guild','guildRequest','input swipe 600 1400 300 1400','Bounties',[1,1]],1))
                        )
                    RestartableSequenceExecution(
                        lambda:FindCoordsOrElseExecuteFallbackAndWait('EdgeOfTown',['return',[1,1]],1)
                        )
                    
                    logger.info("第七步: 休息")
                    # 每 N 次地城後回旅店休息
                    if (runtimeContext._COUNTERDUNG % max(setting._DUNGEON_REPEAT_LIMIT, 1) == 0):
                        RestartableSequenceExecution(
                            lambda:StateInn()
                            )
                        
                    costtime = time.time()-starttime
                    total_time = total_time + costtime
                    logger.info(f"第{runtimeContext._COUNTERDUNG}次\"懸賞:吉爾\"完成. \n該次花費時間{costtime:.2f}s.\n總計用時{total_time:.2f}s.\n平均用時{total_time/runtimeContext._COUNTERDUNG:.2f}",
                            extra={"summary": True})
            # case 'test':
            #     while 1:
            #         quest._SPECIALDIALOGOPTION = ["bounty/Slayhim"]
            #         # StateDungeon([TargetInfo('position','左下',[612,1132])])
            #         StateDungeon([TargetInfo('position','右上',[553,821])])
        MonitorState.reset()
        # 通過消息隊列通知主線程，避免從工作線程直接調用 Tkinter 方法
        if setting._MSGQUEUE:
            setting._MSGQUEUE.put(('task_finished', None))
        elif setting._FINISHINGCALLBACK:
            setting._FINISHINGCALLBACK()
        return
    def Farm(set:FarmConfig):
        nonlocal quest
        nonlocal setting # 初始化
        nonlocal runtimeContext
        
        # 保存統計計數器（避免重啟時清零）
        saved_counters = None
        if runtimeContext is not None:
            saved_counters = {
                '_COUNTERDUNG': runtimeContext._COUNTERDUNG,
                '_COUNTERCOMBAT': runtimeContext._COUNTERCOMBAT,
                '_COUNTERCHEST': runtimeContext._COUNTERCHEST,
                '_COUNTERADBRETRY': runtimeContext._COUNTERADBRETRY,
                '_COUNTEREMULATORCRASH': runtimeContext._COUNTEREMULATORCRASH,
                '_TIME_COMBAT_TOTAL': runtimeContext._TIME_COMBAT_TOTAL,
                '_TIME_CHEST_TOTAL': runtimeContext._TIME_CHEST_TOTAL,
                '_TOTALTIME': runtimeContext._TOTALTIME,
                '_LAPTIME': runtimeContext._LAPTIME,
                '_CRASHCOUNTER': runtimeContext._CRASHCOUNTER,
                '_IMPORTANTINFO': runtimeContext._IMPORTANTINFO,
            }
        
        runtimeContext = RuntimeContext()
        
        # 恢復計數器
        if saved_counters:
            for key, value in saved_counters.items():
                setattr(runtimeContext, key, value)

        setting = set

        try:
            Sleep(1) # 沒有等utils初始化完成

            # 檢查停止信號
            if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                logger.info("Farm 初始化時檢測到停止信號")
                MonitorState.reset()
                # 通過消息隊列通知主線程
                if setting._MSGQUEUE:
                    setting._MSGQUEUE.put(('task_finished', None))
                elif setting._FINISHINGCALLBACK:
                    setting._FINISHINGCALLBACK()
                return

            ResetADBDevice()

            # 檢查 ADB 連接是否成功
            if not setting._ADBDEVICE:
                logger.error("ADB 連接失敗或被中斷，無法啟動任務")
                MonitorState.reset()
                # 通過消息隊列通知主線程
                if setting._MSGQUEUE:
                    setting._MSGQUEUE.put(('task_finished', None))
                elif setting._FINISHINGCALLBACK:
                    setting._FINISHINGCALLBACK()
                return

            # 啟動 pyscrcpy 串流（如果可用）
            stream = get_scrcpy_stream()
            if stream:
                if stream.start():
                    logger.info("pyscrcpy 串流已啟動，截圖將使用快速模式")
                else:
                    logger.info("pyscrcpy 串流啟動失敗，將使用傳統 ADB 截圖")

            # 檢查並啟動遊戲
            package_name = "jp.co.drecom.wizardry.daphne"
            try:
                # 檢查遊戲是否在前台運行
                current_focus = DeviceShell("dumpsys window | grep mCurrentFocus")
                logger.debug(f"當前前台應用: {current_focus.strip()}")
                
                if package_name not in current_focus:
                    logger.info("遊戲未在前台運行，正在啟動遊戲...")
                    # 獲取主 Activity
                    mainAct = DeviceShell(f"cmd package resolve-activity --brief {package_name}").strip().split('\n')[-1]
                    # 啟動遊戲
                    Sleep(5)
                    logger.info("巫術, 啓動!")
                    logger.debug(DeviceShell(f"am start -n {mainAct}"))
                    # 等待遊戲載入
                    logger.info("等待遊戲載入...")
                    Sleep(15)  # 給遊戲足夠的啟動時間
                else:
                    logger.info("遊戲已在前台運行")
            except Exception as e:
                logger.warning(f"檢查/啟動遊戲時發生錯誤: {e}，繼續執行...")

            # 再次檢查停止信號
            if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                logger.info("Farm ADB 初始化後檢測到停止信號")
                if stream:
                    stream.stop()
                MonitorState.reset()
                # 通過消息隊列通知主線程
                if setting._MSGQUEUE:
                    setting._MSGQUEUE.put(('task_finished', None))
                elif setting._FINISHINGCALLBACK:
                    setting._FINISHINGCALLBACK()
                return

            quest = LoadQuest(setting._FARMTARGET)
            if quest:
                if quest._TYPE =="dungeon":
                    DungeonFarm()
                else:
                    QuestFarm()
            else:
                MonitorState.reset()
                # 通過消息隊列通知主線程
                if setting._MSGQUEUE:
                    setting._MSGQUEUE.put(('task_finished', None))
                elif setting._FINISHINGCALLBACK:
                    setting._FINISHINGCALLBACK()
        except StopSignalException:
            logger.info("Farm 收到停止信號，正在清理...")
            MonitorState.reset()
            # 通過消息隊列通知主線程
            if setting._MSGQUEUE:
                setting._MSGQUEUE.put(('task_finished', None))
            elif setting._FINISHINGCALLBACK:
                setting._FINISHINGCALLBACK()
        except Exception as e:
            logger.error(f"Farm 執行時發生錯誤: {e}")
            MonitorState.reset()
            # 通過消息隊列通知主線程
            if setting._MSGQUEUE:
                setting._MSGQUEUE.put(('task_finished', None))
            elif setting._FINISHINGCALLBACK:
                setting._FINISHINGCALLBACK()
        finally:
            # 清理：停止 pyscrcpy 串流
            stream = get_scrcpy_stream()
            if stream:
                stream.stop()
    return Farm

def TestFactory():
    """獨立的測試工廠，用於快速測試特定功能而不執行完整任務循環"""
    setting = None
    
    def ResetADBDevice():
        nonlocal setting # 修改device
        MonitorState.current_state = "Connecting"
        if device := CheckRestartConnectADB(setting):
            setting._ADBDEVICE = device
            logger.info("ADB服務成功啓動，設備已連接.")
    
    def DeviceShell(cmdStr):
        logger.debug(f"DeviceShell {cmdStr}")
        while True:
            if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                return ""
            try:
                result = setting._ADBDEVICE.shell(cmdStr, timeout=5)
                return result
            except Exception as e:
                logger.error(f"ADB命令失敗: {e}")
                ResetADBDevice()
                continue
    
    def Sleep(waitTime=1):
        if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
            return
        time.sleep(waitTime)
    
    def ScreenShot():
        screenshot = setting._ADBDEVICE.screencap()
        screenshot_np = np.frombuffer(screenshot, dtype=np.uint8)
        image = cv2.imdecode(screenshot_np, cv2.IMREAD_COLOR)
        return image
    
    def Press(pos):
        if pos:
            DeviceShell(f"input tap {pos[0]} {pos[1]}")
            return True
        return False
    
    def PressReturn():
        DeviceShell("input keyevent KEYCODE_BACK")
    
    def CheckIf(screenImage, shortPathOfTarget, roi=None, outputMatchResult=False, threshold=0.80):
        template = LoadTemplateImage(shortPathOfTarget)
        if template is None:
            return None
        screenshot = screenImage.copy()
        search_area = CutRoI(screenshot, roi)
        try:
            result = cv2.matchTemplate(search_area, template, cv2.TM_CCOEFF_NORMED)
        except Exception as e:
            logger.error(f"{e}")
            return None
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        logger.debug(f"搜索到疑似{shortPathOfTarget}, 匹配程度:{max_val*100:.2f}%")
        if max_val < threshold:
            logger.debug("匹配程度不足閾值.")
            return None
        pos = [max_loc[0] + template.shape[1]//2, max_loc[1] + template.shape[0]//2]
        return pos
    
    def get_organize_items():
        """動態讀取 Organize 資料夾中的物品圖片"""
        import glob
        organize_path = ResourcePath(os.path.join(IMAGE_FOLDER, 'Organize'))
        items = []
        for ext in ['*.png', '*.jpg']:
            items.extend(glob.glob(os.path.join(organize_path, ext)))
        return [os.path.splitext(os.path.basename(f))[0] for f in items]

    def FindCoordsOrElseExecuteFallbackAndWait(targetPattern, fallback, waitTime):
        """簡化版的 FindCoordsOrElseExecuteFallbackAndWait（模擬原版邏輯）"""
        max_attempts = 60

        for attempt in range(max_attempts):
            if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                return None

            scn = ScreenShot()

            # 檢查是否找到目標
            if isinstance(targetPattern, (list, tuple)):
                for pattern in targetPattern:
                    pos = CheckIf(scn, pattern)
                    if pos:
                        logger.info(f"找到目標: {pattern}")
                        return pos
            else:
                pos = CheckIf(scn, targetPattern)
                if pos:
                    logger.info(f"找到目標: {targetPattern}")
                    return pos

            # 執行整個 fallback 列表
            if fallback:
                if isinstance(fallback, (list, tuple)):
                    # 檢查是否為單一座標 [x, y]
                    if len(fallback) == 2 and all(isinstance(x, (int, float)) for x in fallback):
                        Press(fallback)
                    else:
                        # 遍歷 fallback 列表
                        for fb in fallback:
                            if isinstance(fb, str):
                                if fb.lower() == 'return':
                                    PressReturn()
                                elif fb.startswith('input '):
                                    DeviceShell(fb)
                                else:
                                    Press(CheckIf(scn, fb))
                            elif isinstance(fb, (list, tuple)) and len(fb) == 2:
                                Press(fb)
                                Sleep(0.1)
                elif isinstance(fallback, str):
                    if fallback.lower() == 'return':
                        PressReturn()
                    elif fallback.startswith('input '):
                        DeviceShell(fallback)
                    else:
                        Press(CheckIf(scn, fallback))

            Sleep(waitTime)

        logger.warning(f"超過最大嘗試次數，未找到: {targetPattern}")
        return None

    def TestOrganizeBackpack(num_characters):
        """測試整理背包功能"""
        if num_characters <= 0:
            return
        
        items_to_organize = get_organize_items()
        if not items_to_organize:
            logger.info("Organize 資料夾為空，跳過整理")
            return
        
        logger.info(f"開始整理 {num_characters} 人的背包，物品: {items_to_organize}")
        
        for char_index in range(num_characters):
            # 檢查停止信號
            if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                logger.info("收到停止信號，終止整理背包")
                return
            
            logger.info(f"整理第 {char_index} 號角色背包")
            
            # 角色座標（固定值）
            char_positions = [
                [162, 1333],   # 角色 0
                [465, 1333],   # 角色 1
                [750, 1333],   # 角色 2
                [162, 1515],   # 角色 3
                [465, 1515],   # 角色 4
                [750, 1515],   # 角色 5
            ]
            char_pos = char_positions[char_index]
            
            # 步驟1: 點選角色
            logger.info(f"步驟1: 點選角色 {char_index} 位置 {char_pos}")
            Press(char_pos)
            Sleep(5)  # 等待角色詳情載入
            
            if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                return
            
            # 步驟2: 點選 inventory 打開背包
            logger.info("步驟2: 點選 inventory 打開背包")
            scn = ScreenShot()
            inv_pos = CheckIf(scn, 'inventory')
            if inv_pos:
                Press(inv_pos)
                Sleep(5)
            else:
                logger.warning("找不到 inventory 按鈕，跳過此角色")
                PressReturn()
                Sleep(5)
                continue
            
            if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                return
            
            # 步驟3: 對每個物品執行整理
            logger.info("步驟3: 開始整理物品")
            for item in items_to_organize:
                if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                    return
                
                item_path = f'Organize/{item}'
                Sleep(5)
                
                while True:
                    if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                        return
                    
                    scn = ScreenShot()
                    item_pos = CheckIf(scn, item_path)
                    
                    if not item_pos:
                        logger.info(f"沒有找到物品: {item}")
                        break
                    
                    logger.info(f"找到物品: {item}，位置: {item_pos}")
                    Press(item_pos)
                    Sleep(5)
                    
                    scn = ScreenShot()
                    put_pos = CheckIf(scn, 'putinstorage')
                    if put_pos:
                        Press(put_pos)
                        Sleep(5)
                        logger.info(f"已將 {item} 放入倉庫")
                    else:
                        logger.warning("找不到 putinstorage 按鈕")
                        PressReturn()
                        Sleep(5)
                        break
            
            if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                return

            # 步驟4: 關閉 inventory 視窗
            logger.info("步驟4: 關閉 inventory")
            scn = ScreenShot()
            close_pos = CheckIf(scn, 'closeInventory')
            if close_pos:
                Press(close_pos)
            else:
                PressReturn()
            Sleep(5)

        logger.info("背包整理完成")

    def TestStateInn(num_characters, use_royal_suite=False):
        """測試完整的 StateInn 流程：住宿 → 補給 → 整理背包"""
        logger.info("=== 開始測試 StateInn 流程 ===")

        # 1. 住宿
        logger.info("步驟1: 住宿")
        if not use_royal_suite:
            FindCoordsOrElseExecuteFallbackAndWait('OK', ['Inn', 'Stay', 'Economy', [1, 1]], 2)

        else:
            FindCoordsOrElseExecuteFallbackAndWait('OK', ['Inn', 'Stay', 'royalsuite', [1, 1]], 2)

        FindCoordsOrElseExecuteFallbackAndWait('Stay', ['OK', [299, 1464]], 2)
        Sleep(2)

        if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
            return

        # 2. 自動補給
        logger.info("步驟2: 自動補給")
        FindCoordsOrElseExecuteFallbackAndWait('refilled', ['box', 'refill', 'OK', [1, 1]], 2)


        if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
            return

        # 3. 整理背包
        if num_characters > 0:
            logger.info("步驟3: 整理背包")
            try:
                TestOrganizeBackpack(num_characters)
            except Exception as e:
                logger.error(f"整理背包失敗: {e}")
                for _ in range(3):
                    PressReturn()
                    Sleep(1)
        else:
            logger.info("步驟3: 跳過整理背包（未設定角色數量）")

        logger.info("=== StateInn 流程測試完成 ===")

    # 小地圖區域 ROI (右上角): 左上角(651,24) 右下角(870,244)
    MINIMAP_ROI = [651, 24, 870, 244]  # [x1, y1, x2, y2]
    
    def CheckIf_minimapFloor(screenImage, floorImage):
        """偵測主畫面小地圖中的樓層標識
        
        Args:
            screenImage: 主畫面截圖（非地圖畫面）
            floorImage: 樓層標識圖片名稱
        
        Returns:
            dict: 包含是否找到、匹配度、位置等資訊
        """
        template = LoadTemplateImage(floorImage)
        if template is None:
            logger.error(f"無法載入圖片: {floorImage}")
            return {"found": False, "match_val": 0, "pos": None, "error": "圖片不存在"}
        
        # 使用固定的小地圖 ROI 區域 [x1, y1, x2, y2]
        x1, y1, x2, y2 = MINIMAP_ROI
        search_area = screenImage[y1:y2, x1:x2].copy()
        
        try:
            result = cv2.matchTemplate(search_area, template, cv2.TM_CCOEFF_NORMED)
        except Exception as e:
            logger.error(f"匹配失敗: {e}")
            return {"found": False, "match_val": 0, "pos": None, "error": str(e)}
        
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        threshold = 0.80
        
        logger.info(f"小地圖樓層偵測 {floorImage}: 匹配度 {max_val*100:.2f}%")
        
        pos = None
        if max_val >= threshold:
            pos = [max_loc[0] + template.shape[1]//2, max_loc[1] + template.shape[0]//2]
        
        return {
            "found": max_val >= threshold,
            "match_val": max_val,
            "pos": pos,
            "threshold": threshold
        }
    
    def TestMinimapStairDetection(floor_image, stair_coords, swipe_dir):
        """測試小地圖樓梯偵測完整流程
        
        流程：開地圖 → 滑動找樓梯 → 點擊移動 → 持續監控小地圖
        
        Args:
            floor_image: 要偵測的樓層圖片名稱（如 "DH-R5-minimap"）
            stair_coords: 樓梯在大地圖上的座標 [x, y]
            swipe_dir: 滑動方向字符串（如 "右下"）
        """
        logger.info("=== 開始小地圖樓梯完整流程測試 ===")
        logger.info(f"目標樓層圖片: {floor_image}")
        logger.info(f"樓梯座標: {stair_coords}")
        logger.info(f"滑動方向: {swipe_dir}")
        logger.info(f"小地圖 ROI 區域: {MINIMAP_ROI}")
        
        # 滑動方向對照表
        SWIPE_DIRECTIONS = {
            "左上": [200, 400, 700, 1100],
            "右上": [700, 400, 200, 1100],
            "左下": [200, 1100, 700, 400],
            "右下": [700, 1100, 200, 400],
        }
        
        # 步驟 1：打開地圖
        logger.info("步驟 1: 打開地圖...")
        Press([777, 150])  # 地圖按鈕位置
        Sleep(1.5)
        
        # 檢查地圖是否打開
        screen = ScreenShot()
        map_flag = CheckIf(screen, 'mapFlag')
        if not map_flag:
            logger.error("地圖未打開，嘗試再次打開...")
            Press([777, 150])
            Sleep(1.5)
            screen = ScreenShot()
            if not CheckIf(screen, 'mapFlag'):
                logger.error("無法打開地圖，測試終止")
                return
        
        logger.info("地圖已打開 ✓")
        
        # 步驟 2：滑動地圖找樓梯
        if swipe_dir and swipe_dir in SWIPE_DIRECTIONS:
            logger.info(f"步驟 2: 滑動地圖（{swipe_dir}）...")
            swipe = SWIPE_DIRECTIONS[swipe_dir]
            DeviceShell(f"input swipe {swipe[0]} {swipe[1]} {swipe[2]} {swipe[3]}")
            Sleep(1)
        else:
            logger.info("步驟 2: 無需滑動地圖")
        
        # 步驟 3：點擊樓梯座標開始移動
        logger.info(f"步驟 3: 點擊樓梯座標 {stair_coords}...")
        Press(stair_coords)
        Sleep(0.3)
        Press([280, 1433])  # automove 按鈕
        Sleep(1)
        
        # 步驟 4：持續監控小地圖
        logger.info("步驟 4: 開始監控小地圖，尋找樓層標識...")
        max_checks = 60  # 最多檢查 60 次（約 60 秒）
        found = False
        
        for i in range(max_checks):
            if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                logger.info("偵測到停止訊號，結束測試")
                break
            
            screen = ScreenShot()
            result = CheckIf_minimapFloor(screen, floor_image)
            
            if result["found"]:
                logger.info(f"✓ 偵測到樓層標識！匹配度: {result['match_val']*100:.2f}%")
                logger.info(f"已到達目標樓層！")
                found = True
                break
            else:
                # 每 5 次輸出一次狀態
                if i % 5 == 0:
                    logger.info(f"監控中... ({i}/{max_checks}) 匹配度: {result['match_val']*100:.2f}%")
            
            Sleep(1)
        
        if not found:
            logger.warning(f"超過 {max_checks} 秒未偵測到樓層標識")
        
        # 步驟 5：完成
        logger.info("步驟 5: 打開地圖確認狀態...")
        Press([777, 150])
        Sleep(1)
        
        logger.info("=== 小地圖樓梯完整流程測試完成 ===")
        return found

    def run(set, test_type, **kwargs):
        nonlocal setting
        setting = set
        setting._FORCESTOPING = Event()
        
        try:
            ResetADBDevice()
            
            if not setting._ADBDEVICE:
                logger.error("ADB 連接失敗")
                return
            
            if test_type == "organize_backpack":
                count = kwargs.get('count', 1)
                TestOrganizeBackpack(count)
            elif test_type == "state_inn":
                count = kwargs.get('count', 0)
                use_royal_suite = kwargs.get('use_royal_suite', False)
                TestStateInn(count, use_royal_suite)
            elif test_type == "minimap_stair":
                floor_image = kwargs.get('floor_image', 'DH-R5-minimap')
                stair_coords = kwargs.get('stair_coords', [294, 239])
                swipe_dir = kwargs.get('swipe_dir', '右上')
                TestMinimapStairDetection(floor_image, stair_coords, swipe_dir)
            elif test_type == "screenshot_adb":
                # 強制使用 ADB 方式截圖
                logger.info("強制使用 ADB 方式截圖 (高畫質)")
                return ScreenShot()
            elif test_type == "screenshot":
                # 嘗試使用串流截圖
                global _scrcpy_stream
                if _scrcpy_stream and _scrcpy_stream.is_available():
                    logger.info("使用串流方式截圖")
                    frame = _scrcpy_stream.get_frame()
                    if frame is not None:
                        return frame
                    else:
                        logger.warning("串流截圖失敗，改用 ADB 截圖")
                # 退回到 ADB 截圖
                logger.info("使用 ADB 方式截圖")
                return ScreenShot()

            logger.info("測試完成")
        except Exception as e:
            logger.error(f"測試失敗: {e}")
    
    
    return run

