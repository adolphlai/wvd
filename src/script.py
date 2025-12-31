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


# ==================== 技能分類與載入 ====================

# 技能類別與施放方式對應
SKILL_CATEGORIES = {
    "普攻": {"cast_type": "target", "folder": "普攻"},
    "單體": {"cast_type": "target", "folder": "單體"},
    "橫排": {"cast_type": "target", "folder": "橫排"},
    "全體": {"cast_type": "ok", "folder": "全體"},
    "秘術": {"cast_type": "ok", "folder": "秘術"},
    "群控": {"cast_type": "target", "folder": "群控"},
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
        str: "target" (需選目標) 或 "ok" (OK 確認)
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

# 相容性：維持舊常數供現有程式碼使用（之後會移除）
CC_SKILLS = SKILLS_BY_CATEGORY.get("群控", ["KANTIOS"])
SECRET_AOE_SKILLS = SKILLS_BY_CATEGORY.get("秘術", ["SAoLABADIOS", "SAoLAERLIK", "SAoLAFOROS"])
FULL_AOE_SKILLS = SKILLS_BY_CATEGORY.get("全體", ["LAERLIK", "LAMIGAL", "LAZELOS", "LACONES", "LAFOROS", "LAHALITO", "LAFERU"])
ROW_AOE_SKILLS = SKILLS_BY_CATEGORY.get("橫排", ["maerlik", "mahalito", "mamigal", "mazelos", "maferu", "macones", "maforos"])
PHYSICAL_SKILLS = SKILLS_BY_CATEGORY.get("單體", ["unendingdeaths", "動靜斬", "地裂斬", "全力一擊", "tzalik", "居合"])
ALL_AOE_SKILLS = SECRET_AOE_SKILLS + FULL_AOE_SKILLS + ROW_AOE_SKILLS
ALL_SKILLS = CC_SKILLS + SECRET_AOE_SKILLS + FULL_AOE_SKILLS + ROW_AOE_SKILLS + PHYSICAL_SKILLS

SPELLSEKILL_TABLE = [
            ["btn_enable_all","所有技能",ALL_SKILLS,0,0],
            ["btn_enable_horizontal_aoe","橫排AOE",ROW_AOE_SKILLS,0,1],
            ["btn_enable_full_aoe","全體AOE",FULL_AOE_SKILLS,1,0],
            ["btn_enable_secret_aoe","祕術AOE",SECRET_AOE_SKILLS,1,1],
            ["btn_enable_physical","強力單體",PHYSICAL_SKILLS,2,0],
            ["btn_enable_cc","羣體控制",CC_SKILLS,2,1]
            ]

DUNGEON_TARGETS = BuildQuestReflection()

####################################
CONFIG_VAR_LIST = [
            #var_name,                      type,          config_name,                  default_value
            ["farm_target_text_var",        tk.StringVar,  "_FARMTARGET_TEXT",           list(DUNGEON_TARGETS.keys())[0] if DUNGEON_TARGETS else ""],
            ["farm_target_var",             tk.StringVar,  "_FARMTARGET",                ""],
            ["who_will_open_it_var",        tk.IntVar,     "_WHOWILLOPENIT",             0],
            ["skip_recover_var",            tk.BooleanVar, "_SKIPCOMBATRECOVER",         False],
            ["skip_chest_recover_var",      tk.BooleanVar, "_SKIPCHESTRECOVER",          False],
            # AE 手設定
            ["ae_caster_count_var", tk.IntVar, "_AE_CASTER_COUNT", 1],  # 單位數量：1~6
            ["ae_caster_interval_var", tk.IntVar, "_AE_CASTER_INTERVAL", 0],  # AE 手觸發間隔：0=每場觸發
            ["ae_caster_1_skill_var", tk.StringVar, "_AE_CASTER_1_SKILL", ""],      # 順序 1 技能
            ["ae_caster_1_level_var", tk.StringVar, "_AE_CASTER_1_LEVEL", "關閉"],  # 順序 1 技能等級：關閉/LV2~LV5
            ["ae_caster_2_skill_var", tk.StringVar, "_AE_CASTER_2_SKILL", ""],      # 順序 2 技能
            ["ae_caster_2_level_var", tk.StringVar, "_AE_CASTER_2_LEVEL", "關閉"],  # 順序 2 技能等級：關閉/LV2~LV5
            ["ae_caster_3_skill_var", tk.StringVar, "_AE_CASTER_3_SKILL", ""],      # 順序 3 技能
            ["ae_caster_3_level_var", tk.StringVar, "_AE_CASTER_3_LEVEL", "關閉"],  # 順序 3 技能等級
            ["ae_caster_4_skill_var", tk.StringVar, "_AE_CASTER_4_SKILL", ""],      # 順序 4 技能
            ["ae_caster_4_level_var", tk.StringVar, "_AE_CASTER_4_LEVEL", "關閉"],  # 順序 4 技能等級
            ["ae_caster_5_skill_var", tk.StringVar, "_AE_CASTER_5_SKILL", ""],      # 順序 5 技能
            ["ae_caster_5_level_var", tk.StringVar, "_AE_CASTER_5_LEVEL", "關閉"],  # 順序 5 技能等級
            ["ae_caster_6_skill_var", tk.StringVar, "_AE_CASTER_6_SKILL", ""],      # 順序 6 技能
            ["ae_caster_6_level_var", tk.StringVar, "_AE_CASTER_6_LEVEL", "關閉"],  # 順序 6 技能等級
            ["system_auto_combat_var",      tk.BooleanVar, "_SYSTEMAUTOCOMBAT",          False],
            ["aoe_once_var",                tk.BooleanVar, "_AOE_ONCE",                  False],
            ["custom_aoe_time_var",         tk.IntVar,     "_AOE_TIME",                  1],
            ["auto_after_aoe_var",          tk.BooleanVar, "_AUTO_AFTER_AOE",            False],
            ["active_rest_var",             tk.BooleanVar, "_ACTIVE_REST",               True],
            ["active_royalsuite_rest_var",  tk.BooleanVar, "_ACTIVE_ROYALSUITE_REST",    False],
            ["active_triumph_var",          tk.BooleanVar, "_ACTIVE_TRIUMPH",            False],
            ["rest_intervel_var",           tk.IntVar,     "_RESTINTERVEL",              0],
            ["karma_adjust_var",            tk.StringVar,  "_KARMAADJUST",               "+0"],
            ["emu_path_var",                tk.StringVar,  "_EMUPATH",                   ""],
            ["adb_port_var",                tk.StringVar,  "_ADBPORT",                   5555],
            ["last_version",                tk.StringVar,  "LAST_VERSION",               ""],
            ["latest_version",              tk.StringVar,  "LATEST_VERSION",             None],
            ["_spell_skill_config_internal",list,          "_SPELLSKILLCONFIG",          []],
            ["active_csc_var",              tk.BooleanVar, "ACTIVE_CSC",                 True],
            ["organize_backpack_enabled_var", tk.BooleanVar, "_ORGANIZE_BACKPACK_ENABLED", False],
            ["organize_backpack_count_var",  tk.IntVar,     "_ORGANIZE_BACKPACK_COUNT",   0],
            ["auto_refill_var",              tk.BooleanVar, "_AUTO_REFILL",               True],  # 自動補給
            ]

class FarmConfig:
    for attr_name, var_type, var_config_name, var_default_value in CONFIG_VAR_LIST:
        locals()[var_config_name] = var_default_value
    def __init__(self):
        #### 面板配置其他
        self._FORCESTOPING = None
        self._FINISHINGCALLBACK = None
        self._MSGQUEUE = None
        #### 底層接口
        self._ADBDEVICE = None
    def __getattr__(self, name):
        # 當訪問不存在的屬性時，拋出AttributeError
        raise AttributeError(f"FarmConfig對象沒有屬性'{name}'")
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
    #### 其他臨時參數
    _MEET_CHEST_OR_COMBAT = False
    _ENOUGH_AOE = False
    _AOE_CAST_TIME = 0  # AOE 釋放次數計數器
    _COMBATSPD = False
    _SUICIDE = False # 當有兩個人死亡的時候(multipeopledead), 在戰鬥中嘗試自殺.
    _MAXRETRYLIMIT = 20
    _ACTIVESPELLSEQUENCE = None
    _SHOULDAPPLYSPELLSEQUENCE = True
    _RECOVERAFTERREZ = False
    _ZOOMWORLDMAP = False
    _CRASHCOUNTER = 0
    _IMPORTANTINFO = ""
    _FIRST_DUNGEON_ENTRY = True  # 第一次進入地城標誌，進入後打開地圖時重置
    _DUNGEON_CONFIRMED = False  # 已確認進入地城（偵測到地城狀態後設為 True）
    _STEPAFTERRESTART = True  # 重啓後左右平移標誌，False=需要執行防轉圈，True=已執行或無需執行
    _COMBAT_ACTION_COUNT = 0  # 每場戰鬥的行動次數（進入 StateCombat +1，戰鬥結束重置）
    _COMBAT_BATTLE_COUNT = 0  # 當前第幾戰 (1=第一戰, 2=第二戰...)
    _AOE_TRIGGERED_THIS_DUNGEON = False  # 本次地城是否已觸發 AOE 開自動
    _AE_CASTER_FIRST_ATTACK_DONE = False  # AE 手是否已完成首次普攻
    _HARKEN_FLOOR_TARGET = None  # harken 樓層選擇目標（字符串圖片名），None 表示返回村莊
    _HARKEN_TELEPORT_JUST_COMPLETED = False  # harken 樓層傳送剛剛完成標記
    _MINIMAP_STAIR_FLOOR_TARGET = None  # minimap_stair 目標樓層圖片名稱
    _MINIMAP_STAIR_IN_PROGRESS = False  # minimap_stair 移動中標記
    _RESTART_OPEN_MAP_PENDING = False  # 重啓後待打開地圖標誌，跳過Resume優化
    _MID_DUNGEON_START = False  # 地城內啟動標記，用於跳過黑屏打斷（因為不知道已打幾戰）
class FarmQuest:
    _DUNGWAITTIMEOUT = 0
    _TARGETINFOLIST = None
    _EOT = None
    _preEOTcheck = None
    _SPECIALDIALOGOPTION = None
    _SPECIALFORCESTOPINGSYMBOL = None
    _SPELLSEQUENCE = None
    _TYPE = None
    def __getattr__(self, name):
        # 當訪問不存在的屬性時，拋出AttributeError
        raise AttributeError(f"FarmQuest對象沒有屬性'{name}'")
class TargetInfo:
    def __init__(self, target: str, swipeDir: list = None, roi=None, floorImage=None, activeSpellSequenceOverride = False):
        self.target = target
        self.swipeDir = swipeDir
        # 注意 roi校驗需要target的值. 請嚴格保證roi在最後.
        self.roi = roi
        self.floorImage = floorImage  # 用於 harken 樓層選擇
        self.activeSpellSequenceOverride = activeSpellSequenceOverride
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
        if value == 'default':
            value = [[0,0,900,1600],[0,0,900,208],[0,1265,900,335],[0,636,137,222],[763,636,137,222], [336,208,228,77],[336,1168,228,97]]
        if self.target == 'chest':
            if value == None:
                value = [[0,0,900,1600]]
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
            time.sleep(1)
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
            time.sleep(1)
            subprocess.run(
                f"taskkill /f /im {emulator_SVC}", 
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False  # 不檢查命令是否成功（進程可能不存在）
            )
            time.sleep(1)

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
    time.sleep(15)
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
    def DeviceShell(cmdStr):
        logger.trace(f"[DeviceShell] {cmdStr}")

        while True:
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
                logger.warning(f"ADB操作失敗 ({type(e).__name__}): {e}")
                logger.info("嘗試重啓ADB服務...")
                
                ResetADBDevice()
                time.sleep(1)

                continue
            except Exception as e:
                # 非預期異常直接拋出
                logger.error(f"非預期的ADB異常: {type(e).__name__}: {e}")
                raise
    
    def Sleep(t=1):
        """可響應停止信號的 sleep 函數"""
        # 將長時間 sleep 分割成小段，每段檢查停止標誌
        interval = 0.5  # 每 0.5 秒檢查一次
        elapsed = 0
        while elapsed < t:
            if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                logger.debug(f"Sleep 中檢測到停止信號，提前退出")
                return
            sleep_time = min(interval, t - elapsed)
            time.sleep(sleep_time)
            elapsed += sleep_time

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

        # [功能] 定期截圖記錄 (每 60 秒)
        try:
            # 使用函數屬性來存儲上次記錄時間，避免使用全域變量
            if not hasattr(ScreenShot, "last_record_time"):
                ScreenShot.last_record_time = 0
            
            # 使用函數屬性來存儲記錄目錄路徑 (初始化一次)
            if not hasattr(ScreenShot, "record_dir"):
                ScreenShot.record_dir = os.path.join(LOGS_FOLDER_NAME, "record")
                if not os.path.exists(ScreenShot.record_dir):
                    os.makedirs(ScreenShot.record_dir, exist_ok=True)

        except Exception as e:
            logger.error(f"[自動截圖] 保存失敗: {e}")

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
        
        # 預設只返回原始目標
        return [target_name]

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
        if is_black:
            logger.debug(f"[黑屏偵測] 平均亮度: {mean_brightness:.2f} < {threshold}，判定為黑屏")
        return is_black

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
    def FindCoordsOrElseExecuteFallbackAndWait(targetPattern, fallback,waitTime):
        # fallback可以是座標[x,y]或者字符串. 當爲字符串的時候, 視爲圖片地址
        while True:
            for _ in range(runtimeContext._MAXRETRYLIMIT):
                if setting._FORCESTOPING.is_set():
                    return None
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
    def restartGame(skipScreenShot = False):
        nonlocal runtimeContext
        runtimeContext._COMBATSPD = False # 重啓會重置2倍速, 所以重置標識符以便重新打開.
        runtimeContext._MAXRETRYLIMIT = min(50, runtimeContext._MAXRETRYLIMIT + 5) # 每次重啓後都會增加5次嘗試次數, 以避免不同電腦導致的反覆重啓問題.
        runtimeContext._TIME_CHEST = 0
        runtimeContext._TIME_COMBAT = 0 # 因爲重啓了, 所以清空戰鬥和寶箱計時器.
        runtimeContext._ZOOMWORLDMAP = False
        runtimeContext._STEPAFTERRESTART = False  # 重啓後重置防止轉圈標誌，確保會執行左右平移
        runtimeContext._RESTART_OPEN_MAP_PENDING = True  # 重啓後待打開地圖，跳過Resume優化
        runtimeContext._DUNGEON_CONFIRMED = False  # 重啓後重置地城確認標記
        reset_ae_caster_flags()  # 重啓後重置 AE 手旗標

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
        mainAct = DeviceShell(f"cmd package resolve-activity --brief {package_name}").strip().split('\n')[-1]
        DeviceShell(f"am force-stop {package_name}")
        Sleep(2)
        logger.info("巫術, 啓動!")
        logger.debug(DeviceShell(f"am start -n {mainAct}"))
        Sleep(10)
        raise RestartSignal()
    class RestartSignal(Exception):
        pass
    def RestartableSequenceExecution(*operations):
        while True:
            try:
                for op in operations:
                    # 在每個操作之前檢查停止信號
                    if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                        logger.info("RestartableSequenceExecution 檢測到停止信號")
                        return
                    op()
                return
            except RestartSignal:
                logger.info("任務進度重置中...")
                # 重置前也檢查停止信號
                if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                    logger.info("重置過程中檢測到停止信號")
                    return
                continue
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
        while CheckIf(ScreenShot(), 'leap'):
            if CSC_symbol != None:
                FindCoordsOrElseExecuteFallbackAndWait(CSC_symbol,'CSC',1)
                last_scn = CutRoI(ScreenShot(), [[77,349,757,1068]])
                # 先關閉所有因果
                while 1:
                    Press(CheckIf(WrapImage(ScreenShot(),2,0,0),'didnottakethequest'))
                    DeviceShell(f"input swipe 150 500 150 400")
                    Sleep(1)
                    scn = CutRoI(ScreenShot(), [[77,349,757,1068]])
                    logger.debug(f"因果: 滑動後的截圖誤差={cv2.absdiff(scn, last_scn).mean()/255:.6f}")
                    if cv2.absdiff(scn, last_scn).mean()/255 < 0.006:
                        break
                    else:
                        last_scn = scn
                # 然後調整每個因果
                if CSC_setting!=None:
                    last_scn = CutRoI(ScreenShot(), [[77,349,757,1068]])
                    while 1:
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
                PressReturn()
                Sleep(0.5)
            Press(CheckIf(ScreenShot(),'leap'))
            Sleep(2)
            Press(CheckIf(ScreenShot(),target))

    def RiseAgainReset(reason):
        nonlocal runtimeContext
        runtimeContext._SUICIDE = False # 死了 自殺成功 設置爲false
        runtimeContext._SHOULDAPPLYSPELLSEQUENCE = True # 死了 序列失效, 應當重置序列.
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
    def IdentifyState():
        nonlocal setting # 修改因果
        counter = 0
        while 1:
            # [串流優化] 節流延遲，避免檢測太快導致遊戲來不及響應
            if PYSCRCPY_AVAILABLE:
                Sleep(0.5)  # 串流模式下每次檢測間隔 500ms
            
            state_check_start = time.time()
            screen = ScreenShot()
            logger.debug(f'狀態機檢查中...(第{counter+1}次)')

            if setting._FORCESTOPING.is_set():
                return State.Quit, DungeonState.Quit, screen

            # [黑屏偵測] 首戰/二戰打斷自動戰鬥
            # 當偵測到黑屏且 AE 手尚未觸發 AOE 時，提前開始點擊打斷
            # 條件：已確認進入地城 + AOE 尚未觸發 + 行動計數為 0 + 戰鬥次數 < 2（僅限前兩戰）+ 非地城內啟動
            is_black = IsScreenBlack(screen)
            if runtimeContext._DUNGEON_CONFIRMED and not runtimeContext._AOE_TRIGGERED_THIS_DUNGEON and runtimeContext._COMBAT_ACTION_COUNT == 0 and runtimeContext._COMBAT_BATTLE_COUNT < 2 and not runtimeContext._MID_DUNGEON_START and is_black:
                # 檢查是否需要首戰打斷（AE 手機制）
                need_first_combat_interrupt = bool(setting._AE_CASTER_1_SKILL)

                if need_first_combat_interrupt:
                    logger.info("[黑屏偵測] 偵測到戰鬥過場黑屏，開始提前打斷自動戰鬥...")
                    click_count = 0
                    # 在黑屏期間持續點擊打斷
                    while IsScreenBlack(ScreenShot()):
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
                    Sleep(2)
                    return IdentifyState()
                
                # 如果沒找到樓層按鈕，檢查 returnText（可能選擇界面還沒出現）
                returntext_pos = CheckIf(screen, "returnText")
                if returntext_pos:
                    # returnText 出現但樓層按鈕還沒出現，先點擊等待
                    logger.info(f"哈肯樓層選擇: 發現 returnText，等待樓層 {floor_target} 出現...")
                    Press(returntext_pos)
                    Sleep(2)
                    return IdentifyState()
                
                # 如果都沒找到，看看是否在移動中（不應該立即返回 Dungeon 狀態）
                logger.debug(f"哈肯樓層選擇: 未找到 {floor_target} 或 returnText，繼續等待...")

            # 動態掃描 combatActive 系列圖片
            combat_active_config = [(t, DungeonState.Combat) for t in get_combat_active_templates()]
            # 優先級順序：戰鬥 > 寶箱 > 地城 > 地圖
            # 寶箱優先級高於地城，避免戰鬥結束時先偵測到 dungFlag 而走冗餘流程
            identifyConfig = combat_active_config + [
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
                    return State.Dungeon, state, screen

            if CheckIf(screen,'someonedead'):
                AddImportantInfo("他們活了,活了!")
                for _ in range(5):
                    Press([400+random.randint(0,100),750+random.randint(0,100)])
                    Sleep(1)

            # 正常的 returnText 和 returntoTown 處理（當沒有設置樓層選擇時）
            if runtimeContext._HARKEN_FLOOR_TARGET is None:
                if Press(CheckIf(screen, "returnText")):
                    Sleep(2)
                    return IdentifyState()

                if CheckIf(screen,"returntoTown"):
                    if runtimeContext._MEET_CHEST_OR_COMBAT:
                        FindCoordsOrElseExecuteFallbackAndWait('Inn',['return',[1,1]],1)
                        return State.Inn,DungeonState.Quit, screen
                    else:
                        logger.info("由於沒有遇到任何寶箱或發生任何戰鬥, 跳過回城.")
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
                        return State.Dungeon, None, ScreenShot()

            if pos:=CheckIf(screen,"openworldmap"):
                if runtimeContext._MEET_CHEST_OR_COMBAT:
                    Press(pos)
                    return IdentifyState()
                else:
                    logger.info("由於沒有遇到任何寶箱或發生任何戰鬥, 跳過回城.")
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
                    return State.Dungeon, None, ScreenShot()

            if CheckIf(screen,"RoyalCityLuknalia"):
                FindCoordsOrElseExecuteFallbackAndWait(['Inn','dungFlag'],['RoyalCityLuknalia',[1,1]],1)
                if CheckIf(scn:=ScreenShot(),'Inn'):
                    return State.Inn,DungeonState.Quit, screen
                elif CheckIf(scn,'dungFlag'):
                    return State.Dungeon,None, screen

            if CheckIf(screen,"fortressworldmap"):
                FindCoordsOrElseExecuteFallbackAndWait(['Inn','dungFlag'],['fortressworldmap',[1,1]],1)
                if CheckIf(scn:=ScreenShot(),'Inn'):
                    return State.Inn,DungeonState.Quit, screen
                elif CheckIf(scn,'dungFlag'):
                    return State.Dungeon,None, screen

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
                        if not os.path.exists(ScreenShot.record_dir):
                            os.makedirs(ScreenShot.record_dir, exist_ok=True)
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filename = os.path.join(ScreenShot.record_dir, f"unusual_{timestamp}.png")
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
        """整理揹包功能：將 Organize 資料夾中的物品放入倉庫

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

        logger.info(f"開始整理 {num_characters} 人的揹包，物品: {items_to_organize}")

        for char_index in range(num_characters):
            logger.info(f"整理第 {char_index} 號角色揹包")
            
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
            
            # 步驟2: 點選 inventory 打開揹包
            logger.info("步驟2: 點選 inventory 打開揹包")
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
                
                # 可能需要多次嘗試（如果有多個相同物品）
                while True:
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
                    else:
                        logger.warning("找不到 putinstorage 按鈕")
                        PressReturn()
                        Sleep(5)
                        break
            
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

        logger.info("揹包整理完成")

    def StateInn():
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

        # 3. 整理揹包（可選）
        if setting._ORGANIZE_BACKPACK_ENABLED and setting._ORGANIZE_BACKPACK_COUNT > 0:
            try:
                StateOrganizeBackpack(setting._ORGANIZE_BACKPACK_COUNT)
                # StateOrganizeBackpack 內部已有 PressReturn 離開旅館
            except Exception as e:
                logger.error(f"整理揹包失敗: {e}")
                for _ in range(3):
                    PressReturn()
                    Sleep(1)
        else:
            # 沒有整理揹包時，在這裡離開旅館
            logger.info("離開旅館")
            PressReturn()
            Sleep(2)
    def StateEoT():
        if quest._preEOTcheck:
            if Press(CheckIf(ScreenShot(),quest._preEOTcheck)):
                pass
        for info in quest._EOT:
            if info[1]=="intoWorldMap":
                TeleportFromCityToWorldLocation(info[2][0],info[2][1])
            else:
                pos = FindCoordsOrElseExecuteFallbackAndWait(info[1],info[2],info[3])
                if info[0]=="press":
                    Press(pos)
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
            skill_pos = CheckIf(scn, 'spellskill/'+skillspell, threshold=0.70)
            if skill_pos:
                found_skills.append(skillspell)
                logger.info(f"[強制單體] 使用技能: {skillspell}")
                Press(skill_pos)
                doubleConfirmCastSpell_func()
                return True
            else:
                not_found_skills.append(skillspell)
        
        # 保存偵錯截圖
        import os
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
            if Press(CheckIf(scn, 'spellskill/'+skillspell, threshold=0.70)):
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
        """使用普攻"""
        scn = ScreenShot()
        if Press(CheckIf(scn, 'spellskill/attack')):
            logger.info("[順序] 使用普攻")
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
        skill_path = 'spellskill/' + skill
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
                    Sleep(1)
                    scn = ScreenShot()

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
                    target_y1 = next_pos[1] + 100
                    target_y2 = next_pos[1] + 170
                    logger.info(f"[順序 {caster_type}] 點擊 4 個目標位置")
                    Press([target_x1, target_y1])
                    Sleep(0.1)
                    Press([target_x1, target_y2])
                    Sleep(0.1)
                    Press([target_x2, target_y1])
                    Sleep(0.1)
                    Press([target_x2, target_y2])
                else:
                    # 如果找不到 next，使用固定座標
                    logger.info(f"[順序 {caster_type}] 找不到 next 按鈕，使用固定座標點擊敵人")
                    Press([450, 750])
                    Sleep(0.2)
                    Press([450, 800])
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
        """重置 AE 手相關旗標，用於新地城開始時"""
        nonlocal runtimeContext
        runtimeContext._AOE_TRIGGERED_THIS_DUNGEON = False
        runtimeContext._AE_CASTER_FIRST_ATTACK_DONE = False
        runtimeContext._COMBAT_ACTION_COUNT = 0
        runtimeContext._COMBAT_BATTLE_COUNT = 0
        runtimeContext._DUNGEON_CONFIRMED = False  # 重置地城確認標誌，避免返回時誤觸黑屏檢測
        logger.info("[技能施放] 重置旗標")

    def StateCombat():
        def doubleConfirmCastSpell(skill_name=None):
            is_success_aoe = False
            Sleep(1)
            scn = ScreenShot()
            ok_pos = CheckIf(scn,'OK')
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
                    Press(CheckIf(scn, 'spellskill/attack'))
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
                Press([pos[0]-15+random.randint(0,30),pos[1]+150+random.randint(0,30)])
                Sleep(1)
                scn = ScreenShot()
                if CheckIf(scn,'notenoughsp') or CheckIf(scn,'notenoughmp'):
                    # SP/MP 不足，關閉提示後點擊 attack 普攻
                    logger.info("[戰鬥] SP/MP 不足，改用普攻")
                    Press(CheckIf(scn,'notenough_close'))
                    Sleep(0.5)
                    scn = ScreenShot()
                    Press(CheckIf(scn, 'spellskill/attack'))
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

        nonlocal runtimeContext

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
            
            # 偵測黑屏：如果已有行動且偵測到黑屏，表示戰鬥結束，準備進入下一戰
            if runtimeContext._COMBAT_ACTION_COUNT > 0 and IsScreenBlack(screen):
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
                    
                    # 如果還在黑屏，繼續點擊
                    if IsScreenBlack(scn):
                        continue
                        
                    # 3. 檢查下一狀態標誌 (優先級: 戰鬥 > 寶箱 > 地城 > 其它)
                    # 這些標誌出現意味著過場結束，應立即交回主循環處理
                    next_state_markers = ['chestFlag', 'dungFlag', 'combatActive', 'mapFlag']
                    if any(CheckIf(scn, marker) for marker in next_state_markers):
                        logger.info(f"[戰後加速] 偵測到下一狀態標誌 (點擊 {spam_click_count} 次)，結束等待")
                        break
                
                logger.info(f"[戰後加速] 完成，共點擊 {spam_click_count} 次")
                # 黑屏結束後，回到 StateCombat 開頭重新計數
                return
            
            if CheckIf(screen, 'flee'):
                logger.info(f"[戰鬥] flee 出現，等待 {wait_count + 1} 次")
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

        # === AE 手機制 ===
        # 檢查是否啟用 AE 手功能，並判斷觸發間隔
        ae_enabled = bool(setting._AE_CASTER_1_SKILL)
        # Fix: Handle _COUNTERDUNG=0 on first run and ensure interval=0 always matches
        eff_counter = runtimeContext._COUNTERDUNG if runtimeContext._COUNTERDUNG > 0 else 1
        ae_interval_match = ((eff_counter-1) % (setting._AE_CASTER_INTERVAL+1) == 0)
        if setting._AE_CASTER_INTERVAL == 0:
            ae_interval_match = True

        # 調試 log：確認 AE 手條件
        logger.debug(f"[AE手調試] ae_enabled={ae_enabled}, ae_interval_match={ae_interval_match}, "
                     f"_COUNTERDUNG={runtimeContext._COUNTERDUNG}, _AE_CASTER_INTERVAL={setting._AE_CASTER_INTERVAL}, "
                     f"_AE_CASTER_1_SKILL='{setting._AE_CASTER_1_SKILL}'")

        # === 間隔不匹配時的處理 ===
        # 當 AE 手啟用但間隔不匹配時，直接開啟自動戰鬥（而不是進入 Fallback）
        if ae_enabled and not ae_interval_match:
            logger.info(f"[技能施放] AE 手啟用但間隔不匹配（第 {runtimeContext._COUNTERDUNG} 次地城，間隔設定 {setting._AE_CASTER_INTERVAL}），開啟自動戰鬥")
            runtimeContext._AOE_TRIGGERED_THIS_DUNGEON = True  # 標記已觸發，跳過黑屏檢測
            enable_auto_combat()
            Sleep(3)
            return

        if ae_enabled and ae_interval_match:
            battle_num = runtimeContext._COMBAT_BATTLE_COUNT
            action_count = runtimeContext._COMBAT_ACTION_COUNT
            position = ((action_count - 1) % 6) + 1  # 當前角色順序 (1~6)
            
            # 取得該順序的設定
            skill = ""
            level = "關閉"
            if position <= setting._AE_CASTER_COUNT:
                skill = getattr(setting, f"_AE_CASTER_{position}_SKILL", "")
                level = getattr(setting, f"_AE_CASTER_{position}_LEVEL", "關閉")
            
            is_aoe = skill in ALL_AOE_SKILLS
            is_single = skill and skill not in ALL_AOE_SKILLS and skill != "attack"
            is_attack = skill == "attack"
            is_unconfigured = not skill
            
            logger.info(f"[技能施放] 第{battle_num}戰, action={action_count}, position={position}, skill={skill or '未設定'}, is_aoe={is_aoe}")
            
            if battle_num > 2:
                # === 第 3 戰以後：開自動戰鬥 ===
                # 即使之前觸發過，如果流程再次進入此處（表示 flee 仍存在），則再次嘗試開啟
                logger.info(f"[技能施放] 第 {battle_num} 戰，嘗試開啟自動戰鬥")
                runtimeContext._AOE_TRIGGERED_THIS_DUNGEON = True
                enable_auto_combat()
                Sleep(3)  # 等待遊戲反應，避免快速循環
                return
            elif battle_num == 1:
                # === 第一戰 ===
                if is_aoe:
                    # AOE 技能單位：使用普攻
                    logger.info(f"[順序 {position}] 第一戰，AOE 單位使用普攻")
                    use_normal_attack()
                    return
                elif is_single or is_attack:
                    # 單體技能/普攻 單位：使用設定的技能
                    logger.info(f"[順序 {position}] 第一戰，使用技能: {skill}")
                    use_ae_caster_skill(position, setting)
                    return
                else:
                    # 未設定：使用優先順序單體技能
                    logger.info(f"[順序 {position}] 第一戰，未設定，使用優先順序單體技能")
                    screen = ScreenShot()
                    useForcedPhysicalSkill(screen, doubleConfirmCastSpell, f"順序{position}")
                    return
            elif battle_num == 2:
                # === 第二戰 ===
                if is_aoe:
                    # AOE 技能單位：使用 AOE 技能
                    logger.info(f"[順序 {position}] 第二戰，使用 AOE: {skill}")
                    use_ae_caster_skill(position, setting)
                    return
                elif is_single or is_attack:
                    # 單體技能/普攻 單位：使用設定的技能
                    logger.info(f"[順序 {position}] 第二戰，使用技能: {skill}")
                    use_ae_caster_skill(position, setting)
                    return
                else:
                    # 未設定：使用優先順序單體技能
                    logger.info(f"[順序 {position}] 第二戰，未設定，使用優先順序單體技能")
                    screen = ScreenShot()
                    useForcedPhysicalSkill(screen, doubleConfirmCastSpell, f"順序{position}")
                    return


        screen = ScreenShot()
        # combatSpd 檢查已移至 StateCombat 開頭

        spellsequence = runtimeContext._ACTIVESPELLSEQUENCE
        if spellsequence != None:
            logger.info(f"當前施法序列:{spellsequence}")
            for k in spellsequence.keys():
                if CheckIf(screen,'spellskill/'+ k):
                    targetSpell = 'spellskill/'+ spellsequence[k][0]
                    if not CheckIf(screen, targetSpell):
                        logger.error("錯誤:施法序列包含不可用的技能")
                        Press([850,1100])
                        Sleep(0.5)
                        Press([850,1100])
                        Sleep(3)
                        return
                    
                    logger.info(f"使用技能{targetSpell}, 施法序列特徵: {k}:{spellsequence[k]}")
                    if len(spellsequence[k])!=1:
                        spellsequence[k].pop(0)
                    Press(CheckIf(screen,targetSpell))
                    if targetSpell != 'spellskill/' + 'defend':
                        doubleConfirmCastSpell()

                    return

        # AE 手啟用時，必須等 AOE 觸發後才能開啟系統自動戰鬥
        ae_caster_enabled = bool(setting._AE_CASTER_1_SKILL) or bool(setting._AE_CASTER_2_SKILL)
        ae_logic_complete = not ae_caster_enabled or runtimeContext._AOE_TRIGGERED_THIS_DUNGEON

        if ae_logic_complete and ((setting._SYSTEMAUTOCOMBAT) or (runtimeContext._ENOUGH_AOE and setting._AUTO_AFTER_AOE)):
            # 只點擊一次，避免兩個都匹配時連續點擊導致開啟後又關閉
            if not Press(CheckIf(WrapImage(screen,0.1,0.3,1),'combatAuto',[[700,1000,200,200]])):
                Press(CheckIf(screen,'combatAuto_2',[[700,1000,200,200]]))
            Sleep(5) # Increased sleep duration
            return

        if not CheckIf(screen,'flee'):
            return
        if runtimeContext._SUICIDE:
            Press(CheckIf(screen,'spellskill/'+'defend'))
        else:
            # 正常戰鬥邏輯
            castSpellSkill = False
            castAndPressOK = False
            for skillspell in setting._SPELLSKILLCONFIG:
                if runtimeContext._ENOUGH_AOE and ((skillspell in SECRET_AOE_SKILLS) or (skillspell in FULL_AOE_SKILLS)):
                    #logger.info(f"本次戰鬥已經釋放全體aoe, 由於面板配置, 不進行更多的技能釋放.")
                    continue
                elif Press((CheckIf(screen, 'spellskill/'+skillspell))):
                    logger.info(f"使用技能 {skillspell}")
                    castAndPressOK = doubleConfirmCastSpell(skill_name=skillspell)
                    castSpellSkill = True
                    if castAndPressOK and setting._AOE_ONCE and ((skillspell in SECRET_AOE_SKILLS) or (skillspell in FULL_AOE_SKILLS)):
                        runtimeContext._AOE_CAST_TIME += 1
                        if runtimeContext._AOE_CAST_TIME >= setting._AOE_TIME:
                            runtimeContext._ENOUGH_AOE = True
                            runtimeContext._AOE_CAST_TIME = 0
                        logger.info(f"已釋放全體AOE ({runtimeContext._AOE_CAST_TIME}/{setting._AOE_TIME})")
                    break
            if not castSpellSkill:
                # 使用 use_normal_attack 取代原本的 combatClose 判斷與點擊
                # User request: "你不要弄那個普攻 他會卡住"
                # 改回只點擊空白處，或者乾脆不做事 (防止卡住戰鬥流程)
                logger.warning("[戰鬥] 無可用技能且 Fallback 被呼叫，嘗試點擊空白處取消選單")
                Press(CheckIf(ScreenShot(),'combatClose'))
                Press([850,1100])
                Sleep(0.5)
                Press([850,1100])
                Sleep(3) # Increased sleep duration

    # ==================== DungeonMover 類別 ====================
    # 統一的地城移動管理器，整合 chest_auto, position, harken, gohome 邏輯
    class DungeonMover:
        """
        統一的地城移動管理器
        - 整合 chest_auto, position, harken, gohome 的處理邏輯
        - 實現分層超時機制 (Soft 30s -> GoHome, Hard 60s -> Restart)
        - 統一 Resume 和 Chest_Resume 處理
        """
        
        # 超時設定
        SOFT_TIMEOUT = 30  # 軟超時：觸發 GoHome
        HARD_TIMEOUT = 60  # 硬超時：觸發重啟
        
        # 輪詢設定
        POLL_INTERVAL = 0.5
        STILL_REQUIRED = 10  # 約 5 秒靜止判定
        
        # Resume 設定
        MAX_RESUME_RETRIES = 5
        RESUME_CLICK_INTERVAL = 5  # 每 5 秒主動檢查
        CHEST_AUTO_CLICK_INTERVAL = 5  # chest_auto 每 5 秒檢查
        
        # 轉向解卡設定
        MAX_TURN_ATTEMPTS = 3
        
        def __init__(self):
            self.reset()
        
        def reset(self):
            """重置所有狀態"""
            self.move_start_time = time.time()
            self.last_screen = None
            self.still_count = 0
            self.turn_attempt_count = 0
            self.resume_consecutive_count = 0
            self.last_resume_click_time = time.time()
            self.last_chest_auto_click_time = time.time()
            self.is_gohome_mode = False
            self.current_target = None
        
        def initiate_move(self, targetInfoList: list, ctx):
            """
            啟動移動流程
            Args:
                targetInfoList: 目標列表
                ctx: RuntimeContext
            Returns:
                DungeonState: 下一個狀態
            """
            if not targetInfoList:
                logger.info("[DungeonMover] 無目標，返回 Map 狀態")
                return DungeonState.Map
            
            self.reset()
            target_info = targetInfoList[0]
            self.current_target = target_info.target
            
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
                    return self._start_chest_auto(targetInfoList, ctx)
                elif self.current_target == 'gohome':
                    self.is_gohome_mode = True
                    return self._start_gohome(targetInfoList, ctx)
                else:
                    # position, harken, stair 等
                    return self._start_normal_move(targetInfoList, ctx)
            except Exception as e:
                logger.error(f"[DungeonMover] 啟動移動發生例外: {e}")
                return DungeonState.Dungeon
        
        def _start_chest_auto(self, targetInfoList, ctx):
            """啟動 chest_auto 移動"""
            screen = ScreenShot()
            pos = CheckIf(screen, "chest_auto", [[710,250,180,180]])
            
            if pos:
                logger.info(f"[DungeonMover] 找到 chest_auto 按鈕: {pos}")
                Press(pos)
            else:
                # 嘗試打開地圖面板尋找
                logger.info("[DungeonMover] 主畫面找不到 chest_auto，嘗試打開地圖")
                Press([777, 150])
                Sleep(1)
                screen = ScreenShot()
                pos = CheckIf(screen, "chest_auto", [[710,250,180,180]])
                if pos:
                    Press(pos)
                else:
                    # 檢查是否無寶箱
                    if CheckIf(screen, 'notresure'):
                        logger.info("[DungeonMover] 偵測到 notresure，無寶箱")
                        targetInfoList.pop(0)
                        return DungeonState.Map
                    logger.warning("[DungeonMover] 無法找到 chest_auto 按鈕")
                    targetInfoList.pop(0)
                    return DungeonState.Map
            
            return self._monitor_move(targetInfoList, ctx)
        
        def _start_gohome(self, targetInfoList, ctx):
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
                    Press([800, 360])  # 常見的 gohome 位置
            
            return self._monitor_move(targetInfoList, ctx)
        
        def _start_normal_move(self, targetInfoList, ctx):
            """啟動一般移動 (position, harken, stair)"""
            target_info = targetInfoList[0]
            
            # 確保地圖開啟
            screen = ScreenShot()
            if not CheckIf(screen, 'mapFlag'):
                logger.info("[DungeonMover] 打開地圖")
                Press([777, 150])
                Sleep(1)
                screen = ScreenShot()
                
                # 檢查暴風雪（無法開地圖）
                if CheckIf(screen, 'visibliityistoopoor'):
                    logger.warning("[DungeonMover] 能見度過低，直接觸發 GoHome")
                    self.is_gohome_mode = True
                    return self._start_gohome(targetInfoList, ctx)
                
                if not CheckIf(screen, 'mapFlag'):
                    logger.warning("[DungeonMover] 無法打開地圖")
                    return DungeonState.Dungeon
            
            # 搜索並點擊目標
            try:
                search_result = StateMap_FindSwipeClick(target_info)
                if search_result:
                    # 設定特殊 Flag
                    if target_info.target == 'harken' and target_info.floorImage:
                        ctx._HARKEN_FLOOR_TARGET = target_info.floorImage
                    if target_info.target == 'minimap_stair' and target_info.floorImage:
                        ctx._MINIMAP_STAIR_FLOOR_TARGET = target_info.floorImage
                        ctx._MINIMAP_STAIR_IN_PROGRESS = True
                    
                    Press(search_result)
                    Press([138, 1432])  # automove
                    logger.info(f"[DungeonMover] 點擊目標並開始移動")
                else:
                    logger.info(f"[DungeonMover] 找不到目標 {target_info.target}")
                    if target_info.target in ['position', 'minimap_stair'] or target_info.target.startswith('stair'):
                        targetInfoList.pop(0)
                    return DungeonState.Map
            except KeyError as e:
                logger.error(f"[DungeonMover] 地圖操作錯誤: {e}")
                return DungeonState.Dungeon
            
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
            
            while True:
                # 檢查停止信號
                if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                    return DungeonState.Quit
                
                Sleep(self.POLL_INTERVAL)
                
                # ========== A. 硬超時檢查 (60s) ==========
                elapsed = time.time() - self.move_start_time
                if elapsed > self.HARD_TIMEOUT:
                    logger.error(f"[DungeonMover] 硬超時 ({self.HARD_TIMEOUT}s)，觸發重啟")
                    restartGame()
                
                # ========== B. 軟超時檢查 (30s) ==========
                if elapsed > self.SOFT_TIMEOUT and not self.is_gohome_mode:
                    logger.warning(f"[DungeonMover] 軟超時 ({self.SOFT_TIMEOUT}s)，切換至 GoHome 模式")
                    self.is_gohome_mode = True
                    # 不重置計時器，讓硬超時繼續計時
                    return self._start_gohome(targetInfoList, ctx)
                
                # ========== C. 狀態檢查 ==========
                # ========== C. 異常狀況預先檢查 (防止 IdentifyState 卡死) ==========
                screen_pre = ScreenShot()
                
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
                _, state, screen = IdentifyState()
                
                # Harken 傳送完成檢測
                if ctx._HARKEN_FLOOR_TARGET is None and state == DungeonState.Dungeon:
                    if hasattr(ctx, '_HARKEN_TELEPORT_JUST_COMPLETED') and ctx._HARKEN_TELEPORT_JUST_COMPLETED:
                        logger.info("[DungeonMover] Harken 傳送完成")
                        ctx._HARKEN_TELEPORT_JUST_COMPLETED = False
                        if target == 'harken':
                            targetInfoList.pop(0)
                        return DungeonState.Map
                
                # 狀態轉換
                if state == DungeonState.Combat:
                    logger.info("[DungeonMover] 進入戰鬥")
                    return DungeonState.Combat
                if state == DungeonState.Chest:
                    logger.info("[DungeonMover] 進入寶箱")
                    return DungeonState.Chest
                if state == DungeonState.Quit:
                    return DungeonState.Quit
                
                # ========== D. chest_resume (chest_auto 專用) ==========
                if is_chest_auto:
                    if time.time() - self.last_chest_auto_click_time > self.CHEST_AUTO_CLICK_INTERVAL:
                        pos = CheckIf(screen, "chest_auto", [[710,250,180,180]])
                        if pos:
                            logger.info(f"[DungeonMover] chest_resume: 點擊 {pos}")
                            Press(pos)
                        self.last_chest_auto_click_time = time.time()
                    
                    # 檢查無寶箱
                    if CheckIf(screen, 'notresure'):
                        logger.info("[DungeonMover] chest_auto: 無寶箱 (notresure)")
                        Press([1, 1])
                        targetInfoList.pop(0)
                        return DungeonState.Map
                
                # ========== E. gohome Keep-Alive ==========
                if self.is_gohome_mode:
                    # E1. 離開地城檢測（世界地圖或 Inn）
                    if CheckIf(screen, 'worldmapflag'):
                        logger.info("[DungeonMover] gohome: 偵測到世界地圖，已離開地城")
                        return DungeonState.Quit
                    if CheckIf(screen, 'Inn'):
                        logger.info("[DungeonMover] gohome: 偵測到 Inn，已回城")
                        return DungeonState.Quit
                    
                    # E2. Keep-Alive 點擊
                    if time.time() - self.last_resume_click_time > self.RESUME_CLICK_INTERVAL:
                        pos = CheckIf(screen, "gohome")
                        if pos:
                            logger.info(f"[DungeonMover] gohome Keep-Alive: 點擊 {pos}")
                            Press(pos)
                        self.last_resume_click_time = time.time()
                
                # ========== F. 靜止與 Resume 偵測 ==========
                if self.last_screen is not None:
                    gray1 = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                    gray2 = cv2.cvtColor(self.last_screen, cv2.COLOR_BGR2GRAY)
                    diff = cv2.absdiff(gray1, gray2).mean() / 255
                    
                    if diff < 0.1:
                        self.still_count += 1
                        logger.debug(f"[DungeonMover] 靜止 {self.still_count}/{self.STILL_REQUIRED}")
                        
                        if self.still_count >= self.STILL_REQUIRED:
                            logger.info(f"[DungeonMover] 連續靜止 {self.STILL_REQUIRED} 次")
                            
                            # 檢查是否已在地圖
                            if CheckIf(screen, 'mapFlag'):
                                logger.info("[DungeonMover] 已在地圖狀態")
                                return DungeonState.Map
                            
                            # Resume 檢查 (非 chest_auto)
                            if not is_chest_auto:
                                resume_pos = CheckIf(screen, 'resume')
                                if resume_pos:
                                    if self.resume_consecutive_count < self.MAX_RESUME_RETRIES:
                                        self.resume_consecutive_count += 1
                                        logger.info(f"[DungeonMover] 點擊 Resume ({self.resume_consecutive_count}/{self.MAX_RESUME_RETRIES})")
                                        Press(resume_pos)
                                        Sleep(1)
                                        
                                        # 檢查 RouteNotFound
                                        if CheckIf(ScreenShot(), 'routenotfound'):
                                            logger.info("[DungeonMover] RouteNotFound，到達目的地")
                                            if target in ['position', 'minimap_stair'] or (target and target.startswith('stair')):
                                                targetInfoList.pop(0)
                                            return DungeonState.Map
                                        
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
                            
                            # Minimap Stair 檢測
                            if ctx._MINIMAP_STAIR_IN_PROGRESS and ctx._MINIMAP_STAIR_FLOOR_TARGET:
                                result = CheckIf_minimapFloor(screen, ctx._MINIMAP_STAIR_FLOOR_TARGET)
                                if result["found"]:
                                    logger.info("[DungeonMover] 到達目標樓層 (MiniMap)")
                                    ctx._MINIMAP_STAIR_IN_PROGRESS = False
                                    targetInfoList.pop(0)
                                    return DungeonState.Map
                            
                            # 判定停止（無 Resume 且靜止）
                            if not is_chest_auto and not CheckIf(screen, 'resume'):
                                logger.info("[DungeonMover] 靜止且無 Resume，判定到達")
                                if target in ['position', 'harken'] or (target and target.startswith('stair')):
                                    targetInfoList.pop(0)
                                return DungeonState.Map
                    else:
                        # 畫面有變化
                        if self.still_count > 0:
                            self.still_count = max(0, self.still_count - 1)
                        if self.resume_consecutive_count > 0:
                            self.resume_consecutive_count = 0
                        if self.turn_attempt_count > 0:
                            self.turn_attempt_count = 0
                
                self.last_screen = screen
    
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
    def StateMoving_CheckFrozen():
        lastscreen = None
        dungState = None
        resume_consecutive_count = 0  # Resume連續點擊計數（畫面持續靜止）
        MAX_RESUME_RETRIES = 5  # Resume最大連續點擊次數

        # 移動超時檢測（防止原地旋轉BUG）
        moving_start_time = time.time()
        MOVING_TIMEOUT = 60  # 60秒超時
        
        # 輪詢參數
        POLL_INTERVAL = 0.3  # 每 0.3 秒檢查一次
        
        # 連續靜止參數（唯一檢查點）
        # 3 秒 ÷ 0.3 秒 ≈ 10 次
        STILL_REQUIRED = 10  # 連續 10 次靜止（約 3 秒）才判定停止
        still_count = 0
        
        
        # 轉向嘗試參數（靜止後嘗試轉向解決動態背景問題）
        turn_attempt_count = 0
        MAX_TURN_ATTEMPTS = 3  # 最多轉向 3 次

        # 定期點擊 Resume 參數（防止雖然判定為移動但實際已停止顯示Resume的情況）
        last_resume_click_time = time.time()
        RESUME_CLICK_INTERVAL = 5  # 每 5 秒檢查一次

        logger.info("面具男, 移動.")
        while 1:
            # 等待一個輪詢週期
            if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                return None
            time.sleep(POLL_INTERVAL)
            poll_screen = ScreenShot()

            # 檢查移動是否超時
            elapsed = time.time() - moving_start_time
            if elapsed > MOVING_TIMEOUT:
                logger.error(f"移動超時（{elapsed:.1f}秒），疑似原地旋轉BUG，準備重啓遊戲")
                restartGame()
            
            # 定期檢查並點擊 Resume 按鈕（不管是否判斷為移動中）
            # 這能處理動態背景導致誤判為移動，但實際已出現 Resume 的情況
            if time.time() - last_resume_click_time > RESUME_CLICK_INTERVAL:
                resume_pos_periodic = CheckIf(screen, 'resume')
                if resume_pos_periodic:
                    logger.info(f"【定期檢查】偵測到 Resume 按鈕，主動點擊: {resume_pos_periodic}")
                    Press(resume_pos_periodic)
                last_resume_click_time = time.time()

            _, dungState, screen = IdentifyState()
            
            # harken 樓層傳送完成檢測：如果 _HARKEN_FLOOR_TARGET 被清除，說明傳送已完成
            if runtimeContext._HARKEN_FLOOR_TARGET is None and dungState == DungeonState.Dungeon:
                # 檢查是否剛剛完成了樓層傳送（此時應該在新樓層的地城中）
                if hasattr(runtimeContext, '_HARKEN_TELEPORT_JUST_COMPLETED') and runtimeContext._HARKEN_TELEPORT_JUST_COMPLETED:
                    logger.info("哈肯樓層傳送完成，打開地圖搜索下一個目標")
                    runtimeContext._HARKEN_TELEPORT_JUST_COMPLETED = False
                    Press([777,150])  # 打開地圖
                    Sleep(1)
                    dungState = DungeonState.Map  # 直接返回 Map 狀態，跳過 Resume 優化
                    break
            
            # minimap_stair 小地圖偵測：持續監控小地圖直到找到樓層標識
            if runtimeContext._MINIMAP_STAIR_IN_PROGRESS and runtimeContext._MINIMAP_STAIR_FLOOR_TARGET:
                floor_target = runtimeContext._MINIMAP_STAIR_FLOOR_TARGET
                result = CheckIf_minimapFloor(screen, floor_target)
                
                if result["found"]:
                    logger.info(f"✓ 小地圖偵測到樓層標識 {floor_target}！匹配度: {result['match_val']*100:.2f}%")
                    logger.info("已到達目標樓層，清除 minimap_stair flag")
                    runtimeContext._MINIMAP_STAIR_FLOOR_TARGET = None
                    runtimeContext._MINIMAP_STAIR_IN_PROGRESS = False
                    # 打開地圖繼續下一個目標
                    Press([777,150])
                    Sleep(1)
                    dungState = DungeonState.Map
                    break
                else:
                    logger.debug(f"小地圖監控中... 匹配度: {result['match_val']*100:.2f}%")
            
            if dungState == DungeonState.Map:
                logger.info(f"開始移動失敗. 不要停下來啊面具男!")
                FindCoordsOrElseExecuteFallbackAndWait("dungFlag", [[280, 1433], [1, 1]], 1)
                dungState = dungState.Dungeon
                break
            if dungState != DungeonState.Dungeon:
                logger.info(f"已退出移動狀態. 當前狀態: {dungState}.")
                break
            if lastscreen is not None:
                gray1 = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                gray2 = cv2.cvtColor(lastscreen, cv2.COLOR_BGR2GRAY)
                mean_diff = cv2.absdiff(gray1, gray2).mean() / 255
                logger.debug(f"移動停止檢查:{mean_diff:.2f}")
                if mean_diff < 0.1:
                    still_count += 1
                    logger.debug(f"畫面靜止，連續靜止 {still_count}/{STILL_REQUIRED}")
                    
                    if still_count < STILL_REQUIRED:
                        # 還沒達到連續靜止次數，繼續等待
                        lastscreen = screen
                        continue
                    
                    # 達到連續靜止次數（約 10 秒），進入 Resume/退出判斷
                    logger.info(f"連續 {STILL_REQUIRED} 次靜止（約 {STILL_REQUIRED * POLL_INTERVAL:.1f} 秒），判定停止")
                    
                    # 轉向嘗試機制：如果靜止，先嘗試轉向確認是否真的停止（或卡住）
                    if turn_attempt_count < MAX_TURN_ATTEMPTS:
                        turn_attempt_count += 1
                        logger.info(f"靜止判定觸發轉向機制 (第 {turn_attempt_count}/{MAX_TURN_ATTEMPTS} 次)，向左轉並等待 6 秒...")
                        # 向左轉 (改用 Swipe 以確保生效)
                        Swipe([450, 700], [250, 700])
                        # 等待 6 秒（用戶指定）
                        Sleep(6)
                        
                        # 重置狀態以重新判斷靜止
                        still_count = 0
                        lastscreen = None
                        logger.info("轉向完成，重新開始靜止判定...")
                        continue

                    # 畫面靜止，檢查Resume按鈕
                    # 先檢查是否已在地圖狀態（避免不必要的 Resume 檢測）
                    if CheckIf(screen, 'mapFlag'):
                        logger.info("StateMoving: 已在地圖狀態，跳過 Resume 檢測")
                        dungState = DungeonState.Map
                        break
                    
                    resume_pos = CheckIf(screen, 'resume')
                    
                    if resume_pos:
                        # Resume按鈕存在 = 移動被打斷但未到達
                        resume_consecutive_count += 1
                        
                        if resume_consecutive_count <= MAX_RESUME_RETRIES:
                            # 繼續點擊Resume
                            logger.info(f"檢測到Resume按鈕（畫面靜止），點擊繼續移動（第 {resume_consecutive_count} 次）位置:{resume_pos}")
                            Press(resume_pos)
                            Sleep(1)
                            
                            # 檢查 routenotfound 是否出現
                            screen_after_resume = ScreenShot()
                            if CheckIf(screen_after_resume, 'routenotfound'):
                                logger.info("StateMoving: 檢測到routenotfound，已到達目的地，打開地圖")
                                Sleep(1)  # routenotfound 會自動消失，稍等一下
                                Press([777,150])  # 打開地圖
                                dungState = DungeonState.Map
                                break
                            else:
                                logger.info("StateMoving: 未檢測到routenotfound")
                            
                            lastscreen = None  # 重置lastscreen以重新開始檢測
                            still_count = 0  # 重置靜止計數
                            continue  # 繼續循環，不退出
                        else:
                            # Resume點擊多次仍然靜止 = 可能卡住，打開地圖重新導航
                            logger.warning(f"Resume按鈕點擊{MAX_RESUME_RETRIES}次後畫面仍靜止，打開地圖重新導航")
                            Press([777,150])  # 打開地圖
                            Sleep(1)
                            dungState = DungeonState.Map
                            break
                    else:
                        # Resume按鈕不存在 = 已到達目標
                        logger.info("已退出移動狀態（畫面靜止且Resume按鈕消失）.進行狀態檢查...")
                        dungState = None
                        break
                else:
                    # 畫面在移動，重置連續計數器
                    # 使用 Soft Reset：不直接歸零，而是減少計數，以容忍偶爾的畫面閃爍（如暴風雪）
                    if still_count > 0:
                        decay = 1  # 衰減值
                        old_count = still_count
                        still_count = max(0, still_count - decay)
                        if still_count == 0:
                            logger.debug(f"畫面恢復變化，靜止計數歸零（之前: {old_count}）")
                        else:
                            logger.debug(f"畫面有變化，靜止計數衰減（{old_count} -> {still_count}）")
                    if resume_consecutive_count > 0:
                        logger.debug(f"畫面恢復移動，重置Resume計數器（之前: {resume_consecutive_count}）")
                        resume_consecutive_count = 0
                    if turn_attempt_count > 0:
                        logger.debug(f"畫面恢復變化，重置轉向計數（之前: {turn_attempt_count}）")
                        turn_attempt_count = 0
            lastscreen = screen
        return dungState
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
                result_state = StateMoving_CheckFrozen()
                
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
                    return StateMoving_CheckFrozen(),targetInfoList
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
    def StateChest():
        nonlocal runtimeContext
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
            
            # [新增] 黑幕檢測：如果畫面太暗，可能正在進入戰鬥，停止點擊
            screen_brightness = scn.mean()
            if screen_brightness < 30:
                logger.info(f"[StateChest] 偵測到黑幕 (亮度={screen_brightness:.1f})，可能正在進入戰鬥，停止點擊")
                return DungeonState.Combat
            
            logger.debug(f"[StateChest] 執行 Burst Click (3次) - has_interaction={has_interaction}, dungFlag計數={dungflag_consecutive_count}")
            for _ in range(3):
                Press(disarm)
                Sleep(0.05)
    def StateDungeon(targetInfoList : list[TargetInfo], initial_dungState = None):
        gameFrozen_none = []
        gameFrozen_map = 0
        dungState = initial_dungState
        shouldRecover = False
        waitTimer = time.time()
        needRecoverBecauseCombat = False
        needRecoverBecauseChest = False
        
        nonlocal runtimeContext
        runtimeContext._SHOULDAPPLYSPELLSEQUENCE = True
        while 1:
            state_handle_start = time.time()
            state_handle_name = dungState
            logger.info("----------------------")
            if setting._FORCESTOPING.is_set():
                logger.info("即將停止腳本...")
                dungState = DungeonState.Quit
            logger.info(f"當前狀態(地下城): {dungState}")

            match dungState:
                case None:
                    s, dungState,scn = IdentifyState()
                    if (s == State.Inn) or (dungState == DungeonState.Quit):
                        elapsed_ms = (time.time() - state_handle_start) * 1000
                        logger.debug(f"[耗時] 地城狀態處理 {state_handle_name} (耗時 {elapsed_ms:.0f} ms)")
                        break
                    # 只有在 IdentifyState 沒有識別到狀態時才執行卡死檢測
                    if dungState is None:
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
                case DungeonState.Quit:
                    elapsed_ms = (time.time() - state_handle_start) * 1000
                    logger.debug(f"[耗時] 地城狀態處理 {state_handle_name} (耗時 {elapsed_ms:.0f} ms)")
                    break
                case DungeonState.Dungeon:
                    Press([1,1])
                    ########### COMBAT RESET
                    # 戰鬥結束了, 我們將一些設置復位
                    if setting._AOE_ONCE:
                        runtimeContext._ENOUGH_AOE = False
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
                            counter_trychar += 1
                            dunflag_result = CheckIf(ScreenShot(),'dungflag')
                            logger.debug(f"[圖片偵測] dungflag: {dunflag_result}")
                            if dunflag_result and (counter_trychar <=20):
                                Press([36+(counter_trychar%3)*286,1425])
                                Sleep(1)
                            else:
                                logger.info("自動回覆失敗, 暫不進行回覆.")
                                break
                            trait_result = CheckIf(scn:=ScreenShot(),'trait')
                            logger.debug(f"[圖片偵測] trait: {trait_result}")
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
                                    break
                    ########### OPEN MAP
                    ########### 防止轉圈 (from upstream 1.9.27)
                    has_chest_auto = any(t.target == 'chest_auto' for t in targetInfoList)
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
                    # 第一次進入地城時，無條件打開地圖（不檢查能見度）
                    # 例外：chest_auto 跳過此機制
                    if runtimeContext._FIRST_DUNGEON_ENTRY and not has_chest_auto:
                        logger.info("第一次進入地城，打開地圖")
                        Sleep(1)
                        Press([777,150])
                        dungState = DungeonState.Map
                        runtimeContext._FIRST_DUNGEON_ENTRY = False  # 標記爲已進入過
                    elif runtimeContext._FIRST_DUNGEON_ENTRY and has_chest_auto:
                        logger.debug("chest_auto 模式：跳過第一次進入地城打開地圖，直接進入 Map 狀態")
                        runtimeContext._FIRST_DUNGEON_ENTRY = False
                        dungState = DungeonState.Map  # 仍需進入 Map 狀態以處理 chest_auto 邏輯
                    # 重啓後：跳過Resume優化，直接嘗試打開地圖
                    elif runtimeContext._RESTART_OPEN_MAP_PENDING:
                        logger.info("重啓後：跳過Resume優化，嘗試打開地圖")
                        Sleep(1)
                        Press([777,150])
                        Sleep(1)
                        screen = ScreenShot()
                        mapFlag_result = CheckIf(screen, 'mapFlag')
                        logger.debug(f"[圖片偵測] mapFlag: {mapFlag_result}")
                        if mapFlag_result:
                            logger.info("重啓後：成功打開地圖")
                            dungState = DungeonState.Map
                            runtimeContext._RESTART_OPEN_MAP_PENDING = False
                        else:
                            visib_result = CheckIf(screen, 'visibliityistoopoor')
                            logger.debug(f"[圖片偵測] visibliityistoopoor: {visib_result}")
                            if visib_result:
                                # 能見度太低，無法打開地圖，等待後重新檢測
                                logger.warning("重啓後：能見度太低無法打開地圖，等待後重新檢測狀態")
                                runtimeContext._RESTART_OPEN_MAP_PENDING = False
                                Sleep(3)
                                dungState = None
                            else:
                                # 其他情況（可能在戰鬥/寶箱），重新檢測狀態
                                logger.info("重啓後：地圖未打開，重新檢測狀態")
                                dungState = None
                    # minimap_stair 恢復監控：如果標誌仍在（戰鬥/寶箱打斷後），繼續移動並監控小地圖
                    elif runtimeContext._MINIMAP_STAIR_IN_PROGRESS and runtimeContext._MINIMAP_STAIR_FLOOR_TARGET:
                        logger.info(f"minimap_stair 恢復監控: 繼續尋找樓層標識 {runtimeContext._MINIMAP_STAIR_FLOOR_TARGET}")
                        Sleep(1)
                        # 檢測 Resume 按鈕並繼續移動
                        screen = ScreenShot()
                        resume_pos = CheckIf(screen, 'resume')
                        logger.debug(f"[圖片偵測] resume (minimap_stair): {resume_pos}")
                        if resume_pos:
                            logger.info(f"minimap_stair: 檢測到 Resume 按鈕，繼續移動 {resume_pos}")
                            Press(resume_pos)
                            Sleep(1)
                            result_state = StateMoving_CheckFrozen()
                            if not runtimeContext._MINIMAP_STAIR_IN_PROGRESS:
                                # minimap_stair 完成（在 StateMoving_CheckFrozen 中清除 flag）
                                logger.info("minimap_stair: 目標完成，彈出目標並返回 Map 狀態")
                                # 彈出當前目標
                                if targetInfoList and len(targetInfoList) > 0:
                                    targetInfoList.pop(0)
                                dungState = DungeonState.Map
                            elif result_state == DungeonState.Map:
                                dungState = DungeonState.Map
                            else:
                                dungState = result_state
                        else:
                            # 沒有 Resume 按鈕，可能角色已停止，嘗試打開地圖
                            logger.info("minimap_stair: 未檢測到 Resume 按鈕，打開地圖繼續")
                            Press([777,150])
                            dungState = DungeonState.Map
                    # Resume: 非第一次進入，檢查Resume按鈕決定下一步動作
                    # 注意: 重啓後跳過Resume優化，因爲之前的路徑可能已失效
                    # 注意: chest_auto 跳過 Resume，使用自己的移動等待邏輯
                    elif runtimeContext._STEPAFTERRESTART and not has_chest_auto:
                        # 檢測Resume按鈕，最多重試3次（等待畫面過渡）
                        # 同時檢測寶箱和戰鬥狀態，避免錯過剛出現的寶箱
                        MAX_RESUME_DETECT_RETRIES = 3
                        resume_pos = None
                        detected_other_state = False
                        for detect_retry in range(MAX_RESUME_DETECT_RETRIES):
                            screen = ScreenShot()
                            
                            # 先檢查是否已在地圖狀態（避免不必要的 Resume 檢測）
                            if CheckIf(screen, 'mapFlag'):
                                logger.info("Resume優化: 已在地圖狀態，跳過 Resume 檢測")
                                dungState = DungeonState.Map
                                detected_other_state = True
                                break
                            
                            # 先檢查是否有寶箱或戰鬥
                            if CheckIf(screen, 'chestFlag') or CheckIf(screen, 'whowillopenit'):
                                logger.info(f"Resume優化: 檢測到寶箱狀態（第 {detect_retry + 1} 次嘗試）")
                                dungState = DungeonState.Chest
                                detected_other_state = True
                                break
                            if CheckIf(screen, 'combatActive') or CheckIf(screen, 'combatActive_2'):
                                logger.info(f"Resume優化: 檢測到戰鬥狀態（第 {detect_retry + 1} 次嘗試）")
                                dungState = DungeonState.Combat
                                detected_other_state = True
                                break
                            
                            # 檢查Resume按鈕
                            resume_pos = CheckIf(screen, 'resume')
                            if resume_pos:
                                logger.info(f"Resume優化: 檢測到Resume按鈕（第 {detect_retry + 1} 次嘗試）")
                                break
                            else:
                                if detect_retry < MAX_RESUME_DETECT_RETRIES - 1:
                                    logger.info(f"Resume優化: 未檢測到Resume按鈕，等待重試（{detect_retry + 1}/{MAX_RESUME_DETECT_RETRIES}）")
                                    Sleep(0.5)  # 縮短等待時間
                        
                        # 如果檢測到其他狀態，跳過Resume優化
                        if detected_other_state:
                            pass  # dungState已設置，直接進入下一輪循環
                        elif resume_pos:
                            # Resume存在，點擊Resume，最多重試3次
                            MAX_RESUME_RETRIES = 3
                            resume_success = False
                            
                            for retry in range(MAX_RESUME_RETRIES):
                                logger.info(f"Resume優化: 點擊Resume按鈕（第 {retry + 1}/{MAX_RESUME_RETRIES} 次）位置:{resume_pos}")
                                Press(resume_pos)
                                Sleep(1)  # 等待 routenotfound 可能出現
                                
                                # 檢查 routenotfound 是否出現
                                screen_after = ScreenShot()
                                if CheckIf(screen_after, 'routenotfound'):
                                    # routenotfound 出現 = 已到達目的地
                                    logger.info("Resume優化: 檢測到routenotfound，已到達目的地，打開地圖")
                                    Sleep(1)  # routenotfound 會自動消失，稍等一下
                                    Press([777,150])  # 打開地圖
                                    Sleep(1)
                                    # 檢查能見度（僅記錄日誌，不再觸發回城）
                                    if CheckIf(ScreenShot(), 'visibliityistoopoor'):
                                        logger.warning("visibliityistoopoor，但繼續嘗試導航")
                                    dungState = DungeonState.Map
                                    resume_success = True
                                    break
                                else:
                                    logger.info("Resume優化: 未檢測到routenotfound")
                                
                                # 檢查畫面是否有變化（表示正在移動）
                                gray1 = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                                gray2 = cv2.cvtColor(screen_after, cv2.COLOR_BGR2GRAY)
                                mean_diff = cv2.absdiff(gray1, gray2).mean() / 255
                                logger.info(f"Resume優化: 畫面變化檢測 mean_diff={mean_diff:.4f}")
                                
                                if mean_diff >= 0.02:  # 閾值降低到 2%
                                    # 畫面有變化 = 還在路上，繼續移動監控
                                    logger.info("Resume優化: 畫面有變化，繼續移動監控")
                                    dungState = StateMoving_CheckFrozen()
                                    resume_success = True
                                    break
                                
                                # 畫面沒變化，準備重試
                                logger.warning(f"Resume優化: 畫面無變化，準備重試 ({retry + 1}/{MAX_RESUME_RETRIES})")
                                screen = screen_after  # 更新參考畫面
                                resume_pos = CheckIf(screen, 'resume')
                                if not resume_pos:
                                    # Resume按鈕消失了，可能已經開始移動
                                    logger.info("Resume優化: Resume按鈕消失，進入移動監控")
                                    dungState = StateMoving_CheckFrozen()
                                    resume_success = True
                                    break
                            
                            if not resume_success:
                                # 5次Resume失敗
                                # 檢查當前目標是否是樓梯：如果是樓梯，Resume失效代表換樓成功
                                current_target = targetInfoList[0].target if targetInfoList else None
                                if current_target and current_target.startswith('stair'):
                                    logger.info(f"Resume優化: {MAX_RESUME_RETRIES}次Resume失敗，但目標是樓梯({current_target})，判定爲換樓成功")
                                    targetInfoList.pop(0)  # 彈出當前樓梯目標
                                    logger.info("Resume優化: 打開地圖繼續下一個目標")
                                    Press([777,150])  # 打開地圖
                                    Sleep(1)
                                    dungState = DungeonState.Map
                                else:
                                    # 非樓梯目標，打開地圖重新導航
                                    logger.warning(f"Resume優化: {MAX_RESUME_RETRIES}次Resume失敗，打開地圖重新導航")
                                    Press([777,150])  # 打開地圖
                                    Sleep(1)
                                    
                                    # [Fix] 黑暗區域緊急撤離 (Panic Mode)
                                    if CheckIf(ScreenShot(), 'visibliityistoopoor'):
                                        logger.warning("Resume失敗且能見度過低(visibliityistoopoor)，進入緊急撤離邏輯")
                                        if gohome_pos := CheckIf(ScreenShot(), 'gohome'):
                                            logger.info(f"找到 gohome {gohome_pos}，持續點擊直到撤離")
                                            _panic_start = time.time()
                                            while time.time() - _panic_start < 60:
                                                if setting._FORCESTOPING.is_set(): break
                                                Press(gohome_pos)
                                                Sleep(0.5)
                                                if not CheckIf(ScreenShot(), 'gohome'):
                                                    break
                                            dungState = None
                                        else:
                                            logger.warning("未找到 gohome，嘗試隨機移動脫困")
                                            Press([1100, 360])
                                            Sleep(2)
                                            dungState = None
                                    else:
                                        dungState = DungeonState.Map
                        else:
                            # 3次都沒檢測到Resume，打開地圖
                            logger.info("Resume優化: 3次均未檢測到Resume按鈕，打開地圖")
                            Press([777,150])
                            Sleep(1)
                            # 檢查能見度 - 如果太黑，嘗試緊急撤離
                            if CheckIf(ScreenShot(), 'visibliityistoopoor'):
                                logger.warning("能見度過低(visibliityistoopoor)，進入緊急撤離邏輯")
                                if gohome_pos := CheckIf(ScreenShot(), 'gohome'):
                                    logger.info(f"找到 gohome {gohome_pos}，持續點擊直到撤離")
                                    _panic_start = time.time()
                                    while time.time() - _panic_start < 60:
                                        if setting._FORCESTOPING.is_set(): break
                                        Press(gohome_pos)
                                        Sleep(0.5)
                                        if not CheckIf(ScreenShot(), 'gohome'):
                                            break
                                    dungState = None
                                else:
                                    logger.warning("未找到 gohome，嘗試隨機移動脫困")
                                    Press([1100, 360])
                                    Sleep(2)
                                    dungState = None
                            else:
                                dungState = DungeonState.Map
                    else:
                        # chest_auto 不需要打開地圖，直接回到 Map 狀態讓其專屬邏輯處理
                        if has_chest_auto:
                            logger.debug("chest_auto: 跳過打開地圖，直接進入 Map 狀態")
                            dungState = DungeonState.Map
                        else:
                            Sleep(1)
                            Press([777,150])
                            Sleep(1)
                            # 檢查能見度（僅記錄日誌，不再觸發回城）
                            if CheckIf(ScreenShot(), 'visibliityistoopoor'):
                                logger.warning("visibliityistoopoor，但繼續嘗試導航")
                            dungState = DungeonState.Map
                case DungeonState.Map:
                    if runtimeContext._SHOULDAPPLYSPELLSEQUENCE: # 默認值(第一次)和重啓後應當直接應用序列
                        runtimeContext._SHOULDAPPLYSPELLSEQUENCE = False
                        if targetInfoList[0].activeSpellSequenceOverride:
                            logger.info("因爲初始化, 複製了施法序列.")
                            runtimeContext._ACTIVESPELLSEQUENCE = copy.deepcopy(quest._SPELLSEQUENCE)

                    # ==================== 使用 DungeonMover 統一處理移動 ====================
                    logger.info("[StateDungeon] 使用 DungeonMover 處理移動")
                    dungState = dungeon_mover.initiate_move(targetInfoList, runtimeContext)
                    
                    # 檢查目標是否完成
                    if (targetInfoList is None) or (targetInfoList == []):
                        logger.info("地下城目標完成. 地下城狀態結束.(僅限任務模式.)")
                        elapsed_ms = (time.time() - state_handle_start) * 1000
                        logger.debug(f"[耗時] 地城狀態處理 {state_handle_name} (耗時 {elapsed_ms:.0f} ms)")
                        break
                    
                    # 更新施法序列（如果目標變更）
                    if targetInfoList and targetInfoList[0].activeSpellSequenceOverride:
                        if runtimeContext._ACTIVESPELLSEQUENCE is None:
                            logger.info("因爲目標信息變動, 重新複製了施法序列.")
                            runtimeContext._ACTIVESPELLSEQUENCE = copy.deepcopy(quest._SPELLSEQUENCE)


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
        state = None
        initial_dungState = None  # 用於傳遞給 StateDungeon 的初始狀態
        while 1:
            logger.info("======================")
            Sleep(1)
            if setting._FORCESTOPING.is_set():
                logger.info("即將停止腳本...")
                break
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
                        runtimeContext._DUNGEON_CONFIRMED = True     # 直接確認在地城
                        runtimeContext._STEPAFTERRESTART = True      # 不需要防轉圈
                        runtimeContext._MID_DUNGEON_START = True     # 標記地城內啟動（跳過黑屏打斷）
                        logger.info("[地城內啟動] 參數初始化完成")
                    
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
                    elif not setting._ACTIVE_REST:
                        logger.info("因爲面板設置, 跳過恢復")
                    elif ((runtimeContext._COUNTERDUNG-1) % (setting._RESTINTERVEL+1) != 0):
                        logger.info("還有許多地下城要刷. 面具男, 現在還不能休息哦.")
                    else:
                        logger.info("休息時間到!")
                        runtimeContext._MEET_CHEST_OR_COMBAT = False
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
                        reset_ae_caster_flags()  # 重置 AE 手相關旗標
                    else:
                        logger.debug("[地城內啟動] 跳過 flag 重置")
                    # 注意：不重置 _STEPAFTERRESTART，只有 restartGame 才會設為 False
                    targetInfoList = quest._TARGETINFOLIST.copy()
                    # 傳遞 initial_dungState 避免重複檢測（如 Chest 狀態）
                    _initial = initial_dungState
                    RestartableSequenceExecution(
                        lambda: StateDungeon(targetInfoList, _initial)
                        )
                    initial_dungState = None  # 使用後清除
                    state = None
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
                if not setting._ACTIVE_REST:
                    logger.info("注意, \"休息間隔\"控制連續戰鬥多少次後回城. 當前未啓用休息, 強制設置爲1.")
                    setting._RESTINTERVEL = 1
                if setting._RESTINTERVEL == 0:
                    logger.info("注意, \"休息間隔\"控制連續戰鬥多少次後回城. 當前值0爲無效值, 最低爲1.")
                    setting._RESTINTERVEL = 1
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
                    for i in range(setting._RESTINTERVEL):
                        logger.info(f"第{i+1}輪開始.")
                        secondcombat = False
                        while 1:
                            Press(FindCoordsOrElseExecuteFallbackAndWait(['icanstillgo','combatActive','combatActive_2'],['input swipe 400 400 400 100',[1,1]],1))
                            Sleep(1)
                            if setting._AOE_ONCE:
                                runtimeContext._ENOUGH_AOE = False
                            while 1:
                                scn=ScreenShot()
                                if TryPressRetry(scn):
                                    continue
                                if CheckIf(scn,'icanstillgo'):
                                    break
                                if CheckIf(scn,'combatActive') or CheckIf(scn,'combatActive_2'):
                                    StateCombat()
                                else:
                                    Press([1,1])
                            if not secondcombat:
                                logger.info(f"第1場戰鬥結束.")
                                secondcombat = True
                                Press(CheckIf(ScreenShot(),'icanstillgo'))
                            else:
                                logger.info(f"第2場戰鬥結束.")
                                Press(CheckIf(ScreenShot(),'letswithdraw'))
                                Sleep(1)
                                break
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
                    logger.info(f"第{counter}x{setting._RESTINTERVEL}輪\"擊退敵勢力\"完成, 共計{counter*setting._RESTINTERVEL*2}場戰鬥. 該次花費時間{(time.time()-t):.2f}秒.",
                                    extra={"summary": True})
            case 'darkLight':
                gameFrozen_none = []
                dungState = None
                shouldRecover = False
                needRecoverBecauseCombat = False
                needRecoverBecauseChest = False
                while 1:
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
                            if setting._AOE_ONCE:
                                runtimeContext._ENOUGH_AOE = False
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
                    if setting._ACTIVE_REST:
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
                        while 1:
                            pos = CheckIf(ScreenShot(),'SSC/Request')
                            if not pos:
                                DeviceShell(f"input swipe 150 200 150 250")
                                Sleep(1)
                            else:
                                Press([pos[0]+300,pos[1]+150])
                                break
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

                    if ((runtimeContext._COUNTERDUNG-1) % (setting._RESTINTERVEL+1) == 0):
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
                    if ((runtimeContext._COUNTERDUNG-1) % (setting._RESTINTERVEL+1) == 0):
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
                    
                    if ((runtimeContext._COUNTERDUNG-1) % (setting._RESTINTERVEL+1) == 0):
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
                    if ((runtimeContext._COUNTERDUNG-1) % (setting._RESTINTERVEL+1) == 0):
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
                setting._FINISHINGCALLBACK()
                return

            ResetADBDevice()

            # 檢查 ADB 連接是否成功
            if not setting._ADBDEVICE:
                logger.error("ADB 連接失敗或被中斷，無法啟動任務")
                setting._FINISHINGCALLBACK()
                return

            # 啟動 pyscrcpy 串流（如果可用）
            stream = get_scrcpy_stream()
            if stream:
                if stream.start():
                    logger.info("pyscrcpy 串流已啟動，截圖將使用快速模式")
                else:
                    logger.info("pyscrcpy 串流啟動失敗，將使用傳統 ADB 截圖")

            # 再次檢查停止信號
            if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                logger.info("Farm ADB 初始化後檢測到停止信號")
                if stream:
                    stream.stop()
                setting._FINISHINGCALLBACK()
                return

            quest = LoadQuest(setting._FARMTARGET)
            if quest:
                if quest._TYPE =="dungeon":
                    DungeonFarm()
                else:
                    QuestFarm()
            else:
                setting._FINISHINGCALLBACK()
        except Exception as e:
            logger.error(f"Farm 執行時發生錯誤: {e}")
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
        nonlocal setting
        if device := CheckRestartConnectADB(setting):
            setting._ADBDEVICE = device
            logger.info("ADB服務成功啓動，設備已連接.")
    
    def DeviceShell(cmdStr):
        logger.debug(f"DeviceShell {cmdStr}")
        while True:
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
        """測試整理揹包功能"""
        if num_characters <= 0:
            return
        
        items_to_organize = get_organize_items()
        if not items_to_organize:
            logger.info("Organize 資料夾為空，跳過整理")
            return
        
        logger.info(f"開始整理 {num_characters} 人的揹包，物品: {items_to_organize}")
        
        for char_index in range(num_characters):
            # 檢查停止信號
            if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                logger.info("收到停止信號，終止整理揹包")
                return
            
            logger.info(f"整理第 {char_index} 號角色揹包")
            
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
            
            # 步驟2: 點選 inventory 打開揹包
            logger.info("步驟2: 點選 inventory 打開揹包")
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

        logger.info("揹包整理完成")

    def TestStateInn(num_characters, use_royal_suite=False):
        """測試完整的 StateInn 流程：住宿 → 補給 → 整理揹包"""
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

        # 3. 整理揹包
        if num_characters > 0:
            logger.info("步驟3: 整理揹包")
            try:
                TestOrganizeBackpack(num_characters)
            except Exception as e:
                logger.error(f"整理揹包失敗: {e}")
                for _ in range(3):
                    PressReturn()
                    Sleep(1)
        else:
            logger.info("步驟3: 跳過整理揹包（未設定角色數量）")

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
