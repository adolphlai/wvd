from ppadb.client import Client as AdbClient
from win10toast import ToastNotifier
from scipy.optimize import curve_fit
from scipy.signal import find_peaks
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


CC_SKILLS = ["KANTIOS"]
SECRET_AOE_SKILLS = ["SAoLABADIOS","SAoLAERLIK","SAoLAFOROS"]
FULL_AOE_SKILLS = ["LAERLIK", "LAMIGAL","LAZELOS", "LACONES", "LAFOROS","LAHALITO", "LAFERU", "千恋万花"]
ROW_AOE_SKILLS = ["maerlik", "mahalito", "mamigal","mazelos","maferu", "macones","maforos","终焉之刻"]
PHYSICAL_SKILLS = ["unendingdeaths","動靜斬","地裂斬","全力一击","tzalik","居合","精密攻击","锁腹刺","破甲","星光裂","迟钝连携击","强袭","重装一击","眩晕打击","幻影狩猎"]
ALL_AOE_SKILLS = SECRET_AOE_SKILLS + FULL_AOE_SKILLS + ROW_AOE_SKILLS

ALL_SKILLS = CC_SKILLS + SECRET_AOE_SKILLS + FULL_AOE_SKILLS + ROW_AOE_SKILLS +  PHYSICAL_SKILLS
ALL_SKILLS = [s for s in ALL_SKILLS if s in list(set(ALL_SKILLS))]

SPELLSEKILL_TABLE = [
            ["btn_enable_all","所有技能",ALL_SKILLS,0,0],
            ["btn_enable_horizontal_aoe","橫排AOE",ROW_AOE_SKILLS,0,1],
            ["btn_enable_full_aoe","全體AOE",FULL_AOE_SKILLS,1,0],
            ["btn_enable_secret_aoe","秘術AOE",SECRET_AOE_SKILLS,1,1],
            ["btn_enable_physical","強力單體",PHYSICAL_SKILLS,2,0],
            ["btn_enable_cc","群體控制",CC_SKILLS,2,1]
            ]

DUNGEON_TARGETS = BuildQuestReflection()

####################################
CONFIG_VAR_LIST = [
            #var_name,                      type,          config_name,                  default_value
            ["farm_target_text_var",        tk.StringVar,  "_FARMTARGET_TEXT",           list(DUNGEON_TARGETS.keys())[0] if DUNGEON_TARGETS else ""],
            ["farm_target_var",             tk.StringVar,  "_FARMTARGET",                ""],
            ["randomly_open_chest_var",     tk.BooleanVar, "_SMARTDISARMCHEST",          False],
            ["who_will_open_it_var",        tk.IntVar,     "_WHOWILLOPENIT",             0],
            ["skip_recover_var",            tk.BooleanVar, "_SKIPCOMBATRECOVER",         False],
            ["skip_chest_recover_var",      tk.BooleanVar, "_SKIPCHESTRECOVER",          False],
            ["enable_resume_optimization_var", tk.BooleanVar, "_ENABLE_RESUME_OPTIMIZATION", True],
            ["force_physical_first_combat_var", tk.BooleanVar, "_FORCE_PHYSICAL_FIRST_COMBAT", True],
            ["force_physical_after_inn_var", tk.BooleanVar, "_FORCE_PHYSICAL_AFTER_INN", True],
            ["force_aoe_first_combat_var", tk.BooleanVar, "_FORCE_AOE_FIRST_COMBAT", False],
            ["force_aoe_after_inn_var", tk.BooleanVar, "_FORCE_AOE_AFTER_INN", False],
            ["auto_upgrade_skill_level_var", tk.StringVar, "_AUTO_UPGRADE_SKILL_LEVEL", "LV5"],  # 選項: 關閉, LV2, LV3, LV4, LV5
            # AE 手設定
            ["ae_caster_1_order_var", tk.StringVar, "_AE_CASTER_1_ORDER", "關閉"],  # AE 手 1 順序：關閉/1~6
            ["ae_caster_1_skill_var", tk.StringVar, "_AE_CASTER_1_SKILL", ""],      # AE 手 1 技能
            ["ae_caster_1_level_var", tk.StringVar, "_AE_CASTER_1_LEVEL", "關閉"],  # AE 手 1 技能等級：關閉/LV2~LV5
            ["ae_caster_2_order_var", tk.StringVar, "_AE_CASTER_2_ORDER", "關閉"],  # AE 手 2 順序：關閉/1~6
            ["ae_caster_2_skill_var", tk.StringVar, "_AE_CASTER_2_SKILL", ""],      # AE 手 2 技能
            ["ae_caster_2_level_var", tk.StringVar, "_AE_CASTER_2_LEVEL", "關閉"],  # AE 手 2 技能等級：關閉/LV2~LV5
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
            ]

class FarmConfig:
    for attr_name, var_type, var_config_name, var_default_value in CONFIG_VAR_LIST:
        locals()[var_config_name] = var_default_value
    def __init__(self):
        #### 面板配置其他
        self._FORCESTOPING = None
        self._FINISHINGCALLBACK = None
        self._MSGQUEUE = None
        #### 底层接口
        self._ADBDEVICE = None
    def __getattr__(self, name):
        # 当访问不存在的属性时，抛出AttributeError
        raise AttributeError(f"FarmConfig对象没有属性'{name}'")
class RuntimeContext:
    #### 统计信息
    _LAPTIME = 0
    _TOTALTIME = 0
    _COUNTERDUNG = 0
    _COUNTERCOMBAT = 0
    _COUNTERCHEST = 0
    _COUNTERADBRETRY = 0      # ADB 重启次数（闪退/连接失败）
    _COUNTEREMULATORCRASH = 0 # 模拟器崩溃次数（需完全重启模拟器）
    _TIME_COMBAT= 0
    _TIME_COMBAT_TOTAL = 0
    _TIME_CHEST = 0
    _TIME_CHEST_TOTAL = 0
    #### 其他临时参数
    _MEET_CHEST_OR_COMBAT = False
    _ENOUGH_AOE = False
    _AOE_CAST_TIME = 0  # AOE 釋放次數計數器
    _COMBATSPD = False
    _SUICIDE = False # 当有两个人死亡的时候(multipeopledead), 在战斗中尝试自杀.
    _MAXRETRYLIMIT = 20
    _ACTIVESPELLSEQUENCE = None
    _SHOULDAPPLYSPELLSEQUENCE = True
    _RECOVERAFTERREZ = False
    _ZOOMWORLDMAP = False
    _CRASHCOUNTER = 0
    _IMPORTANTINFO = ""
    _FIRST_DUNGEON_ENTRY = True  # 第一次进入地城标志，进入后打开地图时重置
    _DUNGEON_CONFIRMED = False  # 已確認進入地城（偵測到地城狀態後設為 True）
    _GOHOME_IN_PROGRESS = False  # 正在回城标志，战斗/宝箱后继续回城
    _STEPAFTERRESTART = False  # 重启后左右平移标志，防止原地转圈
    _FIRST_COMBAT_AFTER_RESTART = 0  # 重启后前N次战斗标志（计数器），只在restartGame中设为2
    _FIRST_COMBAT_AFTER_INN = 0  # 从村庄返回地城后前N次战斗标志（计数器）
    _FORCE_PHYSICAL_CURRENT_COMBAT = False  # 当前战斗是否持续使用强力单体技能
    _FORCE_AOE_CURRENT_COMBAT = False  # 当前战斗是否持续使用全体技能
    _COMBAT_ACTION_COUNT = 0  # 每場戰鬥的行動次數（進入 StateCombat +1，戰鬥結束重置）
    _AOE_TRIGGERED_THIS_DUNGEON = False  # 本次地城是否已觸發 AOE 開自動
    _HARKEN_FLOOR_TARGET = None  # harken 樓層選擇目標（字符串圖片名），None 表示返回村莊
    _HARKEN_TELEPORT_JUST_COMPLETED = False  # harken 樓層傳送剛剛完成標記
    _MINIMAP_STAIR_FLOOR_TARGET = None  # minimap_stair 目標樓層圖片名稱
    _MINIMAP_STAIR_IN_PROGRESS = False  # minimap_stair 移動中標記
    _RESTART_OPEN_MAP_PENDING = False  # 重启后待打开地图标志，跳过Resume优化
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
        # 当访问不存在的属性时，抛出AttributeError
        raise AttributeError(f"FarmQuest对象没有属性'{name}'")
class TargetInfo:
    def __init__(self, target: str, swipeDir: list = None, roi=None, floorImage=None, activeSpellSequenceOverride = False):
        self.target = target
        self.swipeDir = swipeDir
        # 注意 roi校验需要target的值. 请严格保证roi在最后.
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
        logger.info(f"正在检查并关闭adb...")
        # Windows 系统使用 taskkill 命令
        if os.name == 'nt':
            subprocess.run(
                f"taskkill /f /im adb.exe", 
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False  # 不检查命令是否成功（进程可能不存在）
            )
            time.sleep(1)
            subprocess.run(
                f"taskkill /f /im HD-Adb.exe", 
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False  # 不检查命令是否成功（进程可能不存在）
            )
        else:
            subprocess.run(
                f"pkill -f {adb_path}", 
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False
            )
        logger.info(f"已尝试终止adb")
    except Exception as e:
        logger.error(f"终止模拟器进程时出错: {str(e)}")
    
def KillEmulator(setting : FarmConfig):
    emulator_name = os.path.basename(setting._EMUPATH)
    emulator_SVC = "MuMuVMMSVC.exe"
    try:
        logger.info(f"正在检查并关闭已运行的模拟器实例{emulator_name}...")
        # Windows 系统使用 taskkill 命令
        if os.name == 'nt':
            subprocess.run(
                f"taskkill /f /im {emulator_name}", 
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False  # 不检查命令是否成功（进程可能不存在）
            )
            time.sleep(1)
            subprocess.run(
                f"taskkill /f /im {emulator_SVC}", 
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False  # 不检查命令是否成功（进程可能不存在）
            )
            time.sleep(1)

        # Unix/Linux 系统使用 pkill 命令
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
        logger.info(f"已尝试终止模拟器进程: {emulator_name}")
    except Exception as e:
        logger.error(f"终止模拟器进程时出错: {str(e)}")
def StartEmulator(setting):
    hd_player_path = setting._EMUPATH
    if not os.path.exists(hd_player_path):
        logger.error(f"模拟器启动程序不存在: {hd_player_path}")
        return False

    try:
        logger.info(f"启动模拟器: {hd_player_path}")
        subprocess.Popen(
            hd_player_path, 
            shell=True,
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL,
            cwd=os.path.dirname(hd_player_path))
    except Exception as e:
        logger.error(f"启动模拟器失败: {str(e)}")
        return False
    
    logger.info("等待模拟器启动...")
    time.sleep(15)
def GetADBPath(setting):
    adb_path = setting._EMUPATH
    adb_path = adb_path.replace("HD-Player.exe", "HD-Adb.exe") # 蓝叠
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

        logger.info(f"-----------------------\n开始尝试连接adb. 次数:{attempt + 1}/{MAXRETRIES}...")

        if attempt == 3:
            logger.info(f"失败次数过多, 尝试关闭adb.")
            KillAdb(setting)

            # 我们不起手就关, 但是如果2次链接还是尝试失败, 那就触发一次强制重启.

        try:
            logger.info("检查adb服务...")
            result = CMDLine(f"\"{adb_path}\" devices")
            logger.debug(f"adb链接返回(输出信息):{result.stdout}")
            logger.debug(f"adb链接返回(错误信息):{result.stderr}")

            if ("daemon not running" in result.stderr) or ("offline" in result.stdout):
                logger.info("adb服务未启动!\n启动adb服务...")
                CMDLine(f"\"{adb_path}\" kill-server")
                CMDLine(f"\"{adb_path}\" start-server")

                # 檢查停止信號的 sleep
                for _ in range(4):  # 2秒拆成4次0.5秒
                    if hasattr(setting, '_FORCESTOPING') and setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                        logger.info("啟動 ADB 服務時檢測到停止信號")
                        return None
                    time.sleep(0.5)

            logger.debug(f"尝试连接到adb...")
            result = CMDLine(f"\"{adb_path}\" connect 127.0.0.1:{setting._ADBPORT}")
            logger.debug(f"adb链接返回(输出信息):{result.stdout}")
            logger.debug(f"adb链接返回(错误信息):{result.stderr}")

            if result.returncode == 0 and ("connected" in result.stdout or "already" in result.stdout):
                logger.info("成功连接到模拟器")
                break
            if ("refused" in result.stderr) or ("cannot connect" in result.stdout):
                logger.info("模拟器未运行，尝试启动...")
                StartEmulator(setting)
                logger.info("模拟器(应该)启动完毕.")
                logger.info("尝试连接到模拟器...")
                result = CMDLine(f"\"{adb_path}\" connect 127.0.0.1:{setting._ADBPORT}")
                if result.returncode == 0 and ("connected" in result.stdout or "already" in result.stdout):
                    logger.info("成功连接到模拟器")
                    break
                logger.info("无法连接. 检查adb端口.")

            logger.info(f"连接失败: {result.stderr.strip()}")

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
            logger.error(f"重启ADB服务时出错: {e}")

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
        logger.info("达到最大重试次数，连接失败")
        return None

    try:
        client = AdbClient(host="127.0.0.1", port=5037)
        devices = client.devices()

        # 查找匹配的设备
        target_device = f"127.0.0.1:{setting._ADBPORT}"
        for device in devices:
            if device.serial == target_device:
                logger.info(f"成功获取设备对象: {device.serial}")
                return device
    except Exception as e:
        logger.error(f"获取ADB设备时出错: {e}")

    return None
##################################################################
def CutRoI(screenshot,roi):
    if roi is None:
        return screenshot

    img_height, img_width = screenshot.shape[:2]
    roi_copy = roi.copy()
    roi1_rect = roi_copy.pop(0)  # 第一个矩形 (x, y, width, height)

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

                # 将位于 roi2 中的像素设置为0
                # (如果这些像素之前因为不在roi1中已经被设为0，则此操作无额外效果)
                screenshot[pixels_in_roi2_mask_for_current_op] = 0

    # cv2.imwrite(f'CutRoI_{time.time()}.png', screenshot)
    return screenshot
##################################################################

def Factory():
    toaster = ToastNotifier()
    setting =  None
    quest = None
    runtimeContext = None
    def LoadQuest(farmtarget):
        # 构建文件路径
        jsondict = LoadJson(ResourcePath(QUEST_FILE))
        if setting._FARMTARGET in jsondict:
            data = jsondict[setting._FARMTARGET]
        else:
            logger.error("任务列表已更新.请重新手动选择地下城任务.")
            return
        
        
        # 创建 Quest 实例并填充属性
        quest = FarmQuest()
        for key, value in data.items():
            if key == '_TARGETINFOLIST':
                setattr(quest, key, [TargetInfo(*args) for args in value])
            elif hasattr(FarmQuest, key):
                setattr(quest, key, value)
            elif key in ["type","questName","questId",'extraConfig']:
                pass
            else:
                logger.info(f"'{key}'并不存在于FarmQuest中.")
        
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
            logger.info("ADB服务成功启动，设备已连接.")

            # ADB 重連後，嘗試重啟 pyscrcpy 串流
            stream = get_scrcpy_stream()
            if stream:
                if stream.restart():
                    logger.info("pyscrcpy 串流重啟成功")
                else:
                    logger.warning("pyscrcpy 串流重啟失敗，將使用傳統 ADB 截圖")
    def DeviceShell(cmdStr):
        logger.debug(f"DeviceShell {cmdStr}")

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
                    # 线程超时未完成
                    logger.warning(f"ADB命令执行超时: {cmdStr}")
                    raise TimeoutError(f"ADB命令在{7}秒内未完成")
                
                if exception is not None:
                    raise exception
                    
                return result
            except (TimeoutError, RuntimeError, ConnectionResetError, cv2.error) as e:
                logger.warning(f"ADB操作失败 ({type(e).__name__}): {e}")
                logger.info("尝试重启ADB服务...")
                
                ResetADBDevice()
                time.sleep(1)

                continue
            except Exception as e:
                # 非预期异常直接抛出
                logger.error(f"非预期的ADB异常: {type(e).__name__}: {e}")
                raise
    
    def Sleep(t=1):
        """可响应停止信号的 sleep 函数"""
        # 将长时间 sleep 分割成小段，每段检查停止标志
        interval = 0.5  # 每 0.5 秒检查一次
        elapsed = 0
        while elapsed < t:
            if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                logger.debug(f"Sleep 中检测到停止信号，提前退出")
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
                            return frame
                        # 否則用補黑邊方式調整
                        pad_bottom = max(0, 1600 - h)
                        pad_right = max(0, 900 - w)
                        if pad_bottom > 0 or pad_right > 0:
                            frame = cv2.copyMakeBorder(frame, 0, pad_bottom, 0, pad_right, cv2.BORDER_CONSTANT, value=[0,0,0])
                        return frame[:1600, :900]
                    elif abs(h - 900) <= 10 and abs(w - 1600) <= 10:
                        # 橫屏，旋轉後處理
                        frame = cv2.transpose(frame)
                        h, w = frame.shape[:2]
                        if h == 1600 and w == 900:
                            return frame
                        pad_bottom = max(0, 1600 - h)
                        pad_right = max(0, 900 - w)
                        if pad_bottom > 0 or pad_right > 0:
                            frame = cv2.copyMakeBorder(frame, 0, pad_bottom, 0, pad_right, cv2.BORDER_CONSTANT, value=[0,0,0])
                        return frame[:1600, :900]
                    else:
                        logger.warning(f"串流幀尺寸異常: {frame.shape}，使用 ADB 截圖")
        
        # 退回 ADB 截圖（較慢：~150-570ms）
        return _ScreenShot_ADB()
    
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
                logger.debug(f'ScreenShot 開始截圖 (嘗試 {retry_count + 1}/{max_retries})')

                # 關鍵點：ADB screencap 調用，使用超時機制防止無限阻塞
                logger.debug('正在調用 ADB screencap...')
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

                logger.debug(f'ADB screencap 完成，數據大小: {len(screenshot)} bytes')

                screenshot_np = np.frombuffer(screenshot, dtype=np.uint8)
                logger.debug(f'轉換為 numpy 陣列，大小: {screenshot_np.size}')

                if screenshot_np.size == 0:
                    logger.error("截图数据为空！")
                    raise RuntimeError("截图数据为空")

                logger.debug('正在解碼圖像...')
                image = cv2.imdecode(screenshot_np, cv2.IMREAD_COLOR)

                if image is None:
                    logger.error("OpenCV解码失败：图像数据损坏")
                    raise RuntimeError("图像解码失败")

                logger.debug(f'圖像解碼完成，尺寸: {image.shape}')

                if image.shape != (1600, 900, 3):  # OpenCV格式为(高, 宽, 通道)
                    if image.shape == (900, 1600, 3):
                        logger.error(f"截图尺寸错误: 当前{image.shape}, 为横屏.")
                        image = cv2.transpose(image)
                        restartGame(skipScreenShot = True) # 这里直接重启, 会被外部接收到重启的exception
                    else:
                        logger.error(f"截图尺寸错误: 期望(1600,900,3), 实际{image.shape}.")
                        raise RuntimeError("截图尺寸异常")

                #cv2.imwrite('screen.png', image)
                logger.debug('截圖成功')
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
                        logger.info(f"adb重启中... (重試 {retry_count}/{max_retries})")
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
        
        for template_name in templates_to_try:
            template = LoadTemplateImage(template_name)
            screenshot = screenImage.copy()
            search_area = CutRoI(screenshot, roi)
            try:
                result = cv2.matchTemplate(search_area, template, cv2.TM_CCOEFF_NORMED)
            except Exception as e:
                logger.error(f"{e}")
                logger.info(f"{e}")
                if isinstance(e, (cv2.error)):
                    logger.info(f"cv2异常.")
                    continue  # 嘗試下一個模板

            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            
            logger.debug(f"搜索到疑似{template_name}, 匹配程度:{max_val*100:.2f}%")
            
            # 記錄最佳匹配
            if max_val > best_val:
                best_val = max_val
                best_pos = [max_loc[0] + template.shape[1]//2, max_loc[1] + template.shape[0]//2]
                best_template_name = template_name

        if outputMatchResult and best_pos:
            cv2.imwrite("origin.png", screenImage)
            screenshot_copy = screenImage.copy()
            template = LoadTemplateImage(best_template_name)
            cv2.rectangle(screenshot_copy, 
                         (best_pos[0] - template.shape[1]//2, best_pos[1] - template.shape[0]//2),
                         (best_pos[0] + template.shape[1]//2, best_pos[1] + template.shape[0]//2), 
                         (0, 255, 0), 2)
            cv2.imwrite("matched.png", screenshot_copy)

        if best_val < threshold:
            logger.debug("匹配程度不足阈值.")
            return None
        if best_val <= 0.9:
            logger.debug(f"警告: {shortPathOfTarget}的匹配程度超过了{threshold*100:.0f}%但不足90%")
        
        if len(templates_to_try) > 1:
            logger.debug(f"多模板匹配: 選擇 {best_template_name} (匹配度 {best_val*100:.2f}%)")

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
            rectangles.append([x, y, w, h]) # 复制两次, 这样groupRectangles可以保留那些单独的矩形.
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
        logger.debug(f"搜索到疑似{shortPathOfTarget}, 匹配程度:{max_val*100:.2f}%")
        if max_val >= threshold:
            if max_val<=0.9:
                logger.debug(f"警告: {shortPathOfTarget}的匹配程度超过了80%但不足90%")

            cropped = screenshot[max_loc[1]:max_loc[1]+template.shape[0], max_loc[0]:max_loc[0]+template.shape[1]]
            SIZE = 15 # size of cursor 光标就是这么大
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
            logger.debug(f"中心匹配检查:{mean_diff:.2f}")

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

            logger.debug(f"目标格搜素{position}, 匹配程度:{max_val*100:.2f}%")
            if max_val > threshold:
                logger.debug("已达到检测阈值.")
                return None 
        return position
    def CheckIf_throughStair(screenImage,targetInfo : TargetInfo):
        stair_img = ["stair_up","stair_down","stair_teleport"]
        screenshot = screenImage
        position = targetInfo.roi
        cropped = screenshot[position[1]-33:position[1]+33, position[0]-33:position[0]+33]
        
        if (targetInfo.target not in stair_img):
            # 验证楼层
            template = LoadTemplateImage(targetInfo.target)
            result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
            threshold = 0.80
            _, max_val, _, _ = cv2.minMaxLoc(result)

            logger.debug(f"搜索楼层标识{targetInfo.target}, 匹配程度:{max_val*100:.2f}%")
            if max_val > threshold:
                logger.info("楼层正确, 判定为已通过")
                return None
            return position
            
        else: #equal: targetInfo.target IN stair_img
            template = LoadTemplateImage(targetInfo.target)
            result = cv2.matchTemplate(cropped, template, cv2.TM_CCOEFF_NORMED)
            threshold = 0.80
            _, max_val, _, _ = cv2.minMaxLoc(result)

            logger.debug(f"搜索楼梯{targetInfo.target}, 匹配程度:{max_val*100:.2f}%")
            if max_val > threshold:
                logger.info("判定为楼梯存在, 尚未通过.")
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
            logger.info(f"快进未开启, 即将开启.{pos}")
            return pos
        return None
    def Press(pos):
        if pos!=None:
            DeviceShell(f"input tap {pos[0]} {pos[1]}")
            return True
        return False
    def PressReturn():
        DeviceShell('input keyevent KEYCODE_BACK')
    def WrapImage(image,r,g,b):
        scn_b = image * np.array([b, g, r])
        return np.clip(scn_b, 0, 255).astype(np.uint8)
    def TryPressRetry(scn):
        if Press(CheckIf(scn,'retry')):
            logger.info("发现并点击了\"重试\". 你遇到了网络波动.")
            return True
        if pos:=(CheckIf(scn,'retry_blank')):
            Press([pos[0], pos[1]+103])
            logger.info("发现并点击了\"重试\". 你遇到了网络波动.")
            return True
        return False
    def AddImportantInfo(str):
        nonlocal runtimeContext
        if runtimeContext._IMPORTANTINFO == "":
            runtimeContext._IMPORTANTINFO = "👆向上滑动查看重要信息👆\n"
        time_str = datetime.now().strftime("%Y%m%d-%H%M%S") 
        runtimeContext._IMPORTANTINFO = f"{time_str} {str}\n{runtimeContext._IMPORTANTINFO}"
    ##################################################################
    def FindCoordsOrElseExecuteFallbackAndWait(targetPattern, fallback,waitTime):
        # fallback可以是坐标[x,y]或者字符串. 当为字符串的时候, 视为图片地址
        while True:
            for _ in range(runtimeContext._MAXRETRYLIMIT):
                if setting._FORCESTOPING.is_set():
                    return None
                scn = ScreenShot()
                if isinstance(targetPattern, (list, tuple)):
                    for pattern in targetPattern:
                        p = CheckIf(scn,pattern)
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
                                    logger.debug(f"错误: 非法的目标{p}.")
                                    setting._FORCESTOPING.set()
                                    return None
                    else:
                        if isinstance(fallback, str):
                            pressTarget(fallback)
                        else:
                            logger.debug("错误: 非法的目标.")
                            setting._FORCESTOPING.set()
                            return None
                Sleep(waitTime) # and wait

            logger.info(f"{runtimeContext._MAXRETRYLIMIT}次截图依旧没有找到目标{targetPattern}, 疑似卡死. 重启游戏.")
            Sleep()
            restartGame()
            return None # restartGame会抛出异常 所以直接返回none就行了
    def restartGame(skipScreenShot = False):
        nonlocal runtimeContext
        runtimeContext._COMBATSPD = False # 重启会重置2倍速, 所以重置标识符以便重新打开.
        runtimeContext._MAXRETRYLIMIT = min(50, runtimeContext._MAXRETRYLIMIT + 5) # 每次重启后都会增加5次尝试次数, 以避免不同电脑导致的反复重启问题.
        runtimeContext._TIME_CHEST = 0
        runtimeContext._TIME_COMBAT = 0 # 因为重启了, 所以清空战斗和宝箱计时器.
        runtimeContext._FIRST_COMBAT_AFTER_RESTART = 1  # 重启后重置战斗计数器
        runtimeContext._ZOOMWORLDMAP = False
        runtimeContext._STEPAFTERRESTART = False  # 重启后重置防止转圈标志，确保会执行左右平移
        runtimeContext._RESTART_OPEN_MAP_PENDING = True  # 重启后待打开地图，跳过Resume优化
        runtimeContext._DUNGEON_CONFIRMED = False  # 重启后重置地城確認標記

        if not skipScreenShot:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")  # 格式：20230825_153045
            file_path = os.path.join(LOGS_FOLDER_NAME, f"{timestamp}.png")
            cv2.imwrite(file_path, ScreenShot())
            logger.info(f"重启前截图已保存在{file_path}中.")
        else:
            runtimeContext._CRASHCOUNTER +=1
            logger.info(f"跳过了重启前截图.\n崩溃计数器: {runtimeContext._CRASHCOUNTER}\n崩溃计数器超过5次后会重启模拟器.")
            if runtimeContext._CRASHCOUNTER > 5:
                runtimeContext._CRASHCOUNTER = 0
                runtimeContext._COUNTEREMULATORCRASH += 1
                KillEmulator(setting)
                CheckRestartConnectADB(setting)

        package_name = "jp.co.drecom.wizardry.daphne"
        mainAct = DeviceShell(f"cmd package resolve-activity --brief {package_name}").strip().split('\n')[-1]
        DeviceShell(f"am force-stop {package_name}")
        Sleep(2)
        logger.info("巫术, 启动!")
        logger.debug(DeviceShell(f"am start -n {mainAct}"))
        Sleep(10)
        raise RestartSignal()
    class RestartSignal(Exception):
        pass
    def RestartableSequenceExecution(*operations):
        while True:
            try:
                for op in operations:
                    # 在每个操作之前检查停止信号
                    if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                        logger.info("RestartableSequenceExecution 检测到停止信号")
                        return
                    op()
                return
            except RestartSignal:
                logger.info("任务进度重置中...")
                # 重置前也检查停止信号
                if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                    logger.info("重置过程中检测到停止信号")
                    return
                continue
    ##################################################################
    def getCursorCoordinates(input, threshold=0.8):
        """在本地图片中查找模板位置"""
        template = LoadTemplateImage('cursor')
        if template is None:
            raise ValueError("无法加载模板图片！")

        h, w = template.shape[:2]  # 获取模板尺寸
        coordinates = []

        # 按指定顺序读取截图文件
        img = input

        # 执行模板匹配
        result = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val > threshold:
            # 返回中心坐标（相对于截图左上角）
            center_x = max_loc[0] + w // 2
            coordinates = center_x
        else:
            coordinates = None
        return coordinates
    def findWidestRectMid(input):
        crop_area = (30,62),(880,115)
        # 转换为灰度图
        gray = cv2.cvtColor(input, cv2.COLOR_BGR2GRAY)

        # 裁剪图像 (y1:y2, x1:x2)
        (x1, y1), (x2, y2) = crop_area
        cropped = gray[y1:y2, x1:x2]

        # cv2.imwrite("Matched Result.png",cropped)

        # 返回结果
        column_means = np.mean(cropped, axis=0)
        aver = np.average(column_means)
        binary = column_means > aver

        # 离散化
        rect_range = []
        startIndex = None
        for i, val in enumerate(binary):
            if val and startIndex is None:
                startIndex = i
            elif not val and startIndex is not None:
                rect_range.append([startIndex,i-1])
                startIndex = None
        if startIndex is not None:
            rect_range.append([startIndex,i-1])

        logger.debug(rect_range)

        widest = 0
        widest_rect = []
        for rect in rect_range:
            if rect[1]-rect[0]>widest:
                widest = rect[1]-rect[0]
                widest_rect = rect


        return int((widest_rect[1]+widest_rect[0])/2)+x1
    def triangularWave(t, p, c):
        t_mod = np.mod(t-c, p)
        return np.where(t_mod < p/2, (2/p)*t_mod, 2 - (2/p)*t_mod)
    def calculSpd(t,x):
        t_data = np.array(t)
        x_data = np.array(x)
        peaks, _ = find_peaks(x_data)
        if len(peaks) >= 2:
            t_peaks = t_data[peaks]
            p0 = np.mean(np.diff(t_peaks))
        else:
            # 备选方法：傅里叶变换或手动设置初值
            p0 = 1.0  # 根据数据调整

        # 非线性最小二乘拟合
        p_opt, _ = curve_fit(
            triangularWave,
            t_data,
            x_data,
            p0=[p0,0],
            bounds=(0, np.inf)  # 确保周期为正
        )
        estimated_p = p_opt[0]
        logger.debug(f"周期 p = {estimated_p:.4f}")
        estimated_c = p_opt[1]
        logger.debug(f"初始偏移 c = {estimated_c:.4f}")

        return p_opt[0], p_opt[1]
    def ChestOpen():
        logger.info("开始智能开箱(?)...")
        ts = []
        xs = []
        t0 = float(DeviceShell("date +%s.%N").strip())
        while 1:
            while 1:
                Sleep(0.2)
                t = float(DeviceShell("date +%s.%N").strip())
                s = ScreenShot()
                x = getCursorCoordinates(s)
                if x != None:
                    ts.append(t-t0)
                    xs.append(x/900)
                    logger.debug(f"t={t-t0}, x={x}")
                else:
                    # cv2.imwrite("Matched Result.png",s)
                    None
                if len(ts)>=20:
                    break
            p, c = calculSpd(ts,xs)
            spd = 2/p*900
            logger.debug(f"s = {2/p*900}")

            t = float(DeviceShell("date +%s.%N").strip())
            s = ScreenShot()
            x = getCursorCoordinates(s)
            target = findWidestRectMid(s)
            logger.debug(f"理论点: {triangularWave(t-t0,p,c)*900}")
            logger.debug(f"起始点: {x}")
            logger.debug(f"目标点: {target}")

            if x!=None:
                waittime = 0
                t_mod = np.mod(t-c, p)
                if t_mod<p/2:
                    # 正向移动, 向右
                    waittime = ((900-x)+(900-target))/spd
                    logger.debug("先向右再向左")
                else:
                    waittime = (x+target)/spd
                    logger.debug("先向左再向右")

                if waittime > 0.270 :
                    logger.debug(f"预计等待 {waittime}")
                    Sleep(waittime-0.270)
                    DeviceShell(f"input tap 527 920") # 这里和retry重合, 也和to_title+retry重合.
                    Sleep(3)
                else:
                    logger.debug(f"等待时间过短: {waittime}")

            if not CheckIf(ScreenShot(), 'chestOpening'):
                break
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
            # 如果已经在副本里了 直接结束.
            # 因为该函数预设了是从城市开始的.
            return
        elif Press(CheckIf(scn,'intoWorldMap')):
            # 如果在城市, 尝试进入世界地图
            Sleep(0.5)
            FindCoordsOrElseExecuteFallbackAndWait('worldmapflag','intoWorldMap',1)
        elif CheckIf(scn,'worldmapflag'):
            # 如果在世界地图, 下一步.
            pass

        # 往下都是确保了现在能看见'worldmapflag', 并尝试看见'target'
        Sleep(0.5)
        if not runtimeContext._ZOOMWORLDMAP:
            for _ in range(3):
                Press([100,1500])
                Sleep(0.5)
            Press([250,1500])
            runtimeContext._ZOOMWORLDMAP = True
        pos = FindCoordsOrElseExecuteFallbackAndWait(target,[swipe,[550,1]],1)

        # 现在已经确保了可以看见target, 那么确保可以点击成功
        Sleep(1)
        Press(pos)
        Sleep(1)
        FindCoordsOrElseExecuteFallbackAndWait(['Inn','openworldmap','dungFlag'],[target,[550,1]],1)
        
    def CursedWheelTimeLeap(tar=None, CSC_symbol=None,CSC_setting = None):
        # CSC_symbol: 是否开启因果? 如果开启因果, 将用这个作为是否点开ui的检查标识
        # CSC_setting: 默认会先选择不接所有任务. 这个列表中储存的是想要打开的因果.
        # 其中的RGB用于缩放颜色维度, 以增加识别的可靠性.
        if setting.ACTIVE_CSC == False:
            logger.info(f"因为面板设置, 跳过了调整因果.")
            CSC_symbol = None

        target = "GhostsOfYore"
        if tar != None:
            target = tar
        if setting._ACTIVE_TRIUMPH:
            target = "Triumph"

        logger.info(f"开始时间跳跃, 本次跳跃目标:{target}")

        # 调整条目以找到跳跃目标
        Press(FindCoordsOrElseExecuteFallbackAndWait('cursedWheel',['ruins',[1,1]],1))
        Press(FindCoordsOrElseExecuteFallbackAndWait('cursedwheel_impregnableFortress',['cursedWheelTapRight','cursedWheel',[1,1]],1))
        if not Press(CheckIf(ScreenShot(),target)):
            DeviceShell(f"input swipe 450 1200 450 200")
            Sleep(2)
            Press(FindCoordsOrElseExecuteFallbackAndWait(target,'input swipe 50 1200 50 1300',1))
        Sleep(1)

        # 跳跃前尝试调整因果
        while CheckIf(ScreenShot(), 'leap'):
            if CSC_symbol != None:
                FindCoordsOrElseExecuteFallbackAndWait(CSC_symbol,'CSC',1)
                last_scn = CutRoI(ScreenShot(), [[77,349,757,1068]])
                # 先关闭所有因果
                while 1:
                    Press(CheckIf(WrapImage(ScreenShot(),2,0,0),'didnottakethequest'))
                    DeviceShell(f"input swipe 150 500 150 400")
                    Sleep(1)
                    scn = CutRoI(ScreenShot(), [[77,349,757,1068]])
                    logger.debug(f"因果: 滑动后的截图误差={cv2.absdiff(scn, last_scn).mean()/255:.6f}")
                    if cv2.absdiff(scn, last_scn).mean()/255 < 0.006:
                        break
                    else:
                        last_scn = scn
                # 然后调整每个因果
                if CSC_setting!=None:
                    last_scn = CutRoI(ScreenShot(), [[77,349,757,1068]])
                    while 1:
                        for option, r, g, b in CSC_setting:
                            Press(CheckIf(WrapImage(ScreenShot(),r,g,b),option))
                            Sleep(1)
                        DeviceShell(f"input swipe 150 400 150 500")
                        Sleep(1)
                        scn = CutRoI(ScreenShot(), [[77,349,757,1068]])
                        logger.debug(f"因果: 滑动后的截图误差={cv2.absdiff(scn, last_scn).mean()/255:.6f}")
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
        runtimeContext._SUICIDE = False # 死了 自杀成功 设置为false
        runtimeContext._SHOULDAPPLYSPELLSEQUENCE = True # 死了 序列失效, 应当重置序列.
        runtimeContext._RECOVERAFTERREZ = True
        if reason == 'chest':
            runtimeContext._COUNTERCHEST -=1
        else:
            runtimeContext._COUNTERCOMBAT -=1
        logger.info("快快请起.")
        AddImportantInfo("面具死了但没死.")
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
            
            screen = ScreenShot()
            logger.info(f'状态机检查中...(第{counter+1}次)')

            if setting._FORCESTOPING.is_set():
                return State.Quit, DungeonState.Quit, screen

            # [黑屏偵測] 首戰打斷自動戰鬥
            # 當偵測到黑屏且需要首戰強制技能時，提前開始點擊打斷
            # 條件：已確認進入地城 + 還沒遇到過戰鬥或寶箱（避免 chest_auto 返回地城時誤判）
            if runtimeContext._DUNGEON_CONFIRMED and not runtimeContext._MEET_CHEST_OR_COMBAT and IsScreenBlack(screen):
                # 檢查是否需要首戰打斷
                need_first_combat_interrupt = (
                    (runtimeContext._FIRST_COMBAT_AFTER_INN > 0 and
                     (setting._FORCE_PHYSICAL_AFTER_INN or setting._FORCE_AOE_AFTER_INN)) or
                    (runtimeContext._FIRST_COMBAT_AFTER_RESTART > 0 and
                     (setting._FORCE_PHYSICAL_FIRST_COMBAT or setting._FORCE_AOE_FIRST_COMBAT))
                )

                if need_first_combat_interrupt:
                    logger.info("[黑屏偵測] 偵測到戰鬥過場黑屏，開始提前打斷自動戰鬥...")
                    click_count = 0
                    # 在黑屏期間持續點擊打斷
                    while IsScreenBlack(ScreenShot()):
                        Press([1, 1])
                        click_count += 1
                        logger.info(f"[黑屏偵測] 點擊打斷 #{click_count}")
                        Sleep(0.1)  # 快速點擊
                        if click_count > 100:  # 防止無限迴圈（最多 10 秒）
                            logger.warning("[黑屏偵測] 黑屏持續過久，中斷點擊")
                            break
                    # 黑屏結束後額外點擊，確保打斷過渡期的自動戰鬥
                    logger.info(f"[黑屏偵測] 黑屏結束，額外點擊確保打斷...")
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

            identifyConfig = [
                ('combatActive',  DungeonState.Combat),
                ('combatActive_2',DungeonState.Combat),
                ('combatActive_3',DungeonState.Combat),
                ('combatActive_4',DungeonState.Combat),
                ('dungFlag',      DungeonState.Dungeon),
                ('chestFlag',     DungeonState.Chest),
                ('whowillopenit', DungeonState.Chest),
                ('mapFlag',       DungeonState.Map),
                ]

            for pattern, state in identifyConfig:
                # combatActive 系列使用較低閾值（串流品質問題）
                if pattern.startswith('combatActive'):
                    result = CheckIf(screen, pattern, threshold=0.70)
                else:
                    result = CheckIf(screen, pattern)
                if result:
                    logger.info(f"[狀態識別] 匹配成功: {pattern} -> {state}")
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
                AddImportantInfo("他们活了,活了!")
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
                        logger.info("由于没有遇到任何宝箱或发生任何战斗, 跳过回城.")
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

            if pos:=CheckIf(screen,"openworldmap"):
                if runtimeContext._MEET_CHEST_OR_COMBAT:
                    Press(pos)
                    return IdentifyState()
                else:
                    logger.info("由于没有遇到任何宝箱或发生任何战斗, 跳过回城.")
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
                logger.info("看起来遇到了一些不太寻常的情况...")
                if (CheckIf(screen,'RiseAgain')):
                    RiseAgainReset(reason = 'combat')
                    return IdentifyState()
                if CheckIf(screen, 'worldmapflag'):
                    logger.info("检测到世界地图, 尝试缩放并返回城市...")
                    for _ in range(3):
                        Press([100,1500])
                        Sleep(0.5)
                    Press([250,1500])
                    Sleep(1)
                    # [關鍵操作] 強制使用 ADB 截圖，避免串流幀延遲
                    scn = _ScreenShot_ADB()
                    if pos:=CheckIf(scn, 'Deepsnow'):
                        logger.info(f"点击 Deepsnow 返回城市 (位置: {pos})")
                        Press(pos)
                        Sleep(2)
                        return IdentifyState()
                    else:
                        logger.info("找不到 Deepsnow, 尝试关闭世界地图")
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
                        logger.info(f"即将进行善恶值调整. 剩余次数:{new_str}")
                        AddImportantInfo(f"新的善恶:{new_str}")
                        setting._KARMAADJUST = new_str
                        SetOneVarInConfig("_KARMAADJUST",setting._KARMAADJUST)
                        Press(pos)
                        logger.info("伏击起手!")
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
                        logger.info(f"即将进行善恶值调整. 剩余次数:{new_str}")
                        AddImportantInfo(f"新的善恶:{new_str}")
                        setting._KARMAADJUST = new_str
                        SetOneVarInConfig("_KARMAADJUST",setting._KARMAADJUST)
                        Press(pos)
                        logger.info("积善行德!")
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
                            AddImportantInfo("购买了骨头.")
                        if op == 'halfBone':
                            AddImportantInfo("购买了尸油.")
                        return IdentifyState()
                
                if (CheckIf(screen,'multipeopledead')):
                    runtimeContext._SUICIDE = True # 准备尝试自杀
                    logger.info("死了好几个, 惨哦")
                    # logger.info("Corpses strew the screen")
                    Press(CheckIf(screen,'skull'))
                    Sleep(2)
                if Press(CheckIf(screen,'startdownload')):
                    logger.info("确认, 下载, 确认.")
                    # logger.info("")
                    Sleep(2)
                if Press(CheckIf(screen,'totitle')):
                    logger.info("网络故障警报! 网络故障警报! 返回标题, 重复, 返回标题!")
                    return IdentifyState()
                PressReturn()
                Sleep(0.5)
                PressReturn()
            if counter>15:
                black = LoadTemplateImage("blackScreen")
                mean_diff = cv2.absdiff(black, screen).mean()/255
                if mean_diff<0.02:
                    logger.info(f"警告: 游戏画面长时间处于黑屏中, 即将重启({25-counter})")
            if counter>= 25:
                logger.info("看起来遇到了一些非同寻常的情况...重启游戏.")
                restartGame()
                counter = 0
            if counter>=4:
                Press([1,1])
                Sleep(0.25)
                Press([1,1])
                Sleep(0.25)
                Press([1,1])

            Sleep(1)
            counter += 1
        return None, None, screen
    def GameFrozenCheck(queue, scn):
        if scn is None:
            raise ValueError("GameFrozenCheck被传入了一个空值.")
        logger.info("卡死检测截图")
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
            logger.info(f"卡死检测耗时: {time.time()-t:.5f}秒")
            logger.info(f"卡死检测结果: {totalDiff:.5f}")
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

        logger.info("背包整理完成")

    def StateInn():
        # 1. 住宿
        if not setting._ACTIVE_ROYALSUITE_REST:
            FindCoordsOrElseExecuteFallbackAndWait('OK',['Inn','Stay','Economy',[1,1]],2)
        else:
            FindCoordsOrElseExecuteFallbackAndWait('OK',['Inn','Stay','royalsuite',[1,1]],2)
        FindCoordsOrElseExecuteFallbackAndWait('Stay',['OK',[299,1464]],2)

        # 2. 自動補給
        FindCoordsOrElseExecuteFallbackAndWait('refilled', ['box', 'refill', 'OK', [1, 1]], 2)
        Press([1, 1])
        Sleep(2)  # 等待補給動畫結束

        # 3. 整理背包（如果啟用）- 補給結束後在角色選擇畫面
        if setting._ORGANIZE_BACKPACK_ENABLED and setting._ORGANIZE_BACKPACK_COUNT > 0:
            try:
                StateOrganizeBackpack(setting._ORGANIZE_BACKPACK_COUNT)
            except Exception as e:
                logger.error(f"整理背包失敗: {e}")
                for _ in range(3):
                    PressReturn()
                    Sleep(1)
        else:
            # 不啟用整理背包時，退出角色選擇畫面
            logger.info("退出角色選擇畫面")
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
        强制使用强力单体技能
        注意：此函数由调用者决定何时调用（通过 _FORCE_PHYSICAL_CURRENT_COMBAT 标志）
              函数本身不再检查开关设定，信任调用者的判断
        Args:
            screen: 当前截图
            doubleConfirmCastSpell_func: 确认施法的函数
            reason: 触发原因（用于日志）
        Returns:
            bool: 是否成功使用了技能
        """
        logger.info(f"{reason}，强制使用强力单体技能")
        
        # 先打断自动战斗（点击画面空白处）
        # 因为自动战斗进行中画面会变动，无法可靠检测，所以直接盲点
        logger.info("点击打断自动战斗...")
        for _ in range(3):
            Press([1, 1])
            Sleep(0.5)
        scn = ScreenShot()
        
        for skillspell in PHYSICAL_SKILLS:
            if Press(CheckIf(scn, 'spellskill/'+skillspell)):
                logger.info(f"强制使用技能: {skillspell}")
                doubleConfirmCastSpell_func()
                return True
        logger.info("未找到可用的强力单体技能")
        return False
    def useForcedAOESkill(screen, doubleConfirmCastSpell_func, reason=""):
        """
        强制使用全体技能
        Args:
            screen: 当前截图
            doubleConfirmCastSpell_func: 确认施法的函数
            reason: 触发原因（用于日志）
        Returns:
            bool: 是否成功使用了技能
        """
        logger.info(f"{reason}，强制使用全体技能")

        # 先打断自动战斗（点击画面空白处）
        logger.info("点击打断自动战斗...")
        for _ in range(3):
            Press([1, 1])
            Sleep(0.5)
        scn = ScreenShot()

        for skillspell in ALL_AOE_SKILLS:
            if Press(CheckIf(scn, 'spellskill/'+skillspell)):
                logger.info(f"强制使用全体技能: {skillspell}")
                doubleConfirmCastSpell_func()
                return True
        logger.info("未找到可用的全体技能")
        return False
    def StateCombat():
        def doubleConfirmCastSpell(skill_name=None):
            is_success_aoe = False
            Sleep(1)
            scn = ScreenShot()
            # 檢測是否選中 LV1，如果是則自動點擊目標等級升級
            # 等級座標對照表（X 座標固定，Y 座標從 lv1_selected 偵測位置取得）
            SKILL_LEVEL_X = {"LV2": 251, "LV3": 378, "LV4": 500, "LV5": 625}
            target_level = setting._AUTO_UPGRADE_SKILL_LEVEL
            if target_level != "關閉" and target_level in SKILL_LEVEL_X:
                lv1_pos = CheckIf(scn, 'lv1_selected', roi=[[0, 1188, 900, 112]])
                if lv1_pos:
                    logger.info(f"[戰鬥] 檢測到 LV1 技能，自動點擊 {target_level} 升級")
                    Press([SKILL_LEVEL_X[target_level], lv1_pos[1]])  # X 固定，Y 動態
                    Sleep(1)  # 等待介面更新
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

        def get_ae_caster_type(action_count):
            """判斷當前行動是否為 AE 手
            Returns:
                0: 非 AE 手
                1: AE 手 1
                2: AE 手 2
            """
            order1 = setting._AE_CASTER_1_ORDER
            order2 = setting._AE_CASTER_2_ORDER
            # 計算當前是第幾個角色（1~6）
            position = ((action_count - 1) % 6) + 1
            if order1 != "關閉" and position == int(order1):
                return 1
            if order2 != "關閉" and position == int(order2):
                return 2
            return 0

        def use_ae_caster_skill(caster_type):
            """AE 手使用指定 AOE 技能
            Args:
                caster_type: 1 或 2，對應 AE 手 1 或 AE 手 2
            Returns:
                bool: 是否成功使用技能
            """
            if caster_type == 1:
                skill = setting._AE_CASTER_1_SKILL
                level = setting._AE_CASTER_1_LEVEL
            else:
                skill = setting._AE_CASTER_2_SKILL
                level = setting._AE_CASTER_2_LEVEL

            if not skill:
                logger.info(f"[AE 手 {caster_type}] 未設定技能")
                return False

            # 打斷自動戰鬥
            logger.info(f"[AE 手 {caster_type}] 打斷自動戰鬥...")
            for _ in range(3):
                Press([1, 1])
                Sleep(0.5)

            scn = ScreenShot()
            skill_path = 'spellskill/' + skill
            if Press(CheckIf(scn, skill_path)):
                logger.info(f"[AE 手 {caster_type}] 使用技能: {skill}")
                Sleep(1)
                scn = ScreenShot()

                # 如果設定了技能等級，自動升級
                SKILL_LEVEL_X = {"LV2": 251, "LV3": 378, "LV4": 500, "LV5": 625}
                if level != "關閉" and level in SKILL_LEVEL_X:
                    lv1_pos = CheckIf(scn, 'lv1_selected', roi=[[0, 1188, 900, 112]])
                    if lv1_pos:
                        logger.info(f"[AE 手 {caster_type}] 升級技能到 {level}")
                        Press([SKILL_LEVEL_X[level], lv1_pos[1]])
                        Sleep(1)
                        scn = ScreenShot()

                # 點擊 OK 確認
                ok_pos = CheckIf(scn, 'OK')
                if ok_pos:
                    logger.info(f"[AE 手 {caster_type}] 點擊 OK 確認")
                    Press(ok_pos)
                    Sleep(2)
                return True

            logger.info(f"[AE 手 {caster_type}] 找不到技能: {skill}")
            return False

        def use_normal_attack():
            """使用普攻"""
            scn = ScreenShot()
            if Press(CheckIf(scn, 'spellskill/attack')):
                logger.info("[AE 手] 使用普攻")
                Sleep(0.5)
                # 點擊敵人位置
                Press([450, 750])
                Sleep(0.5)
                return True
            return False

        def enable_auto_combat():
            """開啟自動戰鬥"""
            logger.info("[AE 手] 開啟自動戰鬥")
            scn = ScreenShot()
            if not Press(CheckIf(WrapImage(scn, 0.1, 0.3, 1), 'combatAuto', [[700, 1000, 200, 200]])):
                Press(CheckIf(scn, 'combatAuto_2', [[700, 1000, 200, 200]]))
            Sleep(2)

        nonlocal runtimeContext

        # 每次進入 StateCombat 增加行動計數器
        runtimeContext._COMBAT_ACTION_COUNT += 1
        logger.info(f"[戰鬥] 行動次數: {runtimeContext._COMBAT_ACTION_COUNT}")

        # === AE 手機制 ===
        # 檢查是否啟用 AE 手功能
        ae_enabled = setting._AE_CASTER_1_ORDER != "關閉"
        is_first_combat = (runtimeContext._FIRST_COMBAT_AFTER_RESTART > 0 or
                          runtimeContext._FIRST_COMBAT_AFTER_INN > 0)

        if ae_enabled and not runtimeContext._AOE_TRIGGERED_THIS_DUNGEON:
            action_count = runtimeContext._COMBAT_ACTION_COUNT
            caster_type = get_ae_caster_type(action_count)

            if is_first_combat:
                # 第一戰
                if action_count <= 6:
                    # 第一輪
                    if caster_type > 0:
                        # AE 手第一輪使用普攻（為了讓遊戲記住「重複上一次動作」）
                        logger.info(f"[AE 手 {caster_type}] 第一戰第一輪，使用普攻")
                        use_normal_attack()
                        return
                    else:
                        # 非 AE 手使用單體技能
                        logger.info("[非 AE 手] 第一戰第一輪，使用單體技能")
                        screen = ScreenShot()
                        if useForcedPhysicalSkill(screen, doubleConfirmCastSpell, "非 AE 手"):
                            return
                else:
                    # 第二輪以後
                    if caster_type > 0:
                        # AE 手第二輪使用 AOE → 開自動
                        logger.info(f"[AE 手 {caster_type}] 第一戰第二輪，使用 AOE")
                        if use_ae_caster_skill(caster_type):
                            runtimeContext._AOE_TRIGGERED_THIS_DUNGEON = True
                            enable_auto_combat()
                            return
            else:
                # 第二戰及以後（如果第一戰沒觸發 AOE）
                if caster_type > 0:
                    logger.info(f"[AE 手 {caster_type}] 後續戰鬥，使用 AOE")
                    if use_ae_caster_skill(caster_type):
                        runtimeContext._AOE_TRIGGERED_THIS_DUNGEON = True
                        enable_auto_combat()
                        return

        if runtimeContext._TIME_COMBAT==0:
            runtimeContext._TIME_COMBAT = time.time()

        screen = ScreenShot()
        if not runtimeContext._COMBATSPD:
            if Press(CheckIf(screen,'combatSpd')):
                runtimeContext._COMBATSPD = True
                Sleep(1)

        spellsequence = runtimeContext._ACTIVESPELLSEQUENCE
        if spellsequence != None:
            logger.info(f"当前施法序列:{spellsequence}")
            for k in spellsequence.keys():
                if CheckIf(screen,'spellskill/'+ k):
                    targetSpell = 'spellskill/'+ spellsequence[k][0]
                    if not CheckIf(screen, targetSpell):
                        logger.error("错误:施法序列包含不可用的技能")
                        Press([850,1100])
                        Sleep(0.5)
                        Press([850,1100])
                        Sleep(3)
                        return
                    
                    logger.info(f"使用技能{targetSpell}, 施法序列特征: {k}:{spellsequence[k]}")
                    if len(spellsequence[k])!=1:
                        spellsequence[k].pop(0)
                    Press(CheckIf(screen,targetSpell))
                    if targetSpell != 'spellskill/' + 'defend':
                        doubleConfirmCastSpell()

                    return

        # 重启后前N次战斗，开启整场战斗强制使用强力单体技能或全体技能模式
        # 只有在新战斗开始时才倒数
        if runtimeContext._FIRST_COMBAT_AFTER_RESTART > 0 and not runtimeContext._FORCE_PHYSICAL_CURRENT_COMBAT and not runtimeContext._FORCE_AOE_CURRENT_COMBAT:
            combat_number = 3 - runtimeContext._FIRST_COMBAT_AFTER_RESTART  # 2->第1次, 1->第2次
            runtimeContext._FIRST_COMBAT_AFTER_RESTART -= 1
            if setting._FORCE_AOE_FIRST_COMBAT:
                logger.info(f"重启后第 {combat_number} 次战斗，开启全体技能模式（整场战斗）")
                runtimeContext._FORCE_AOE_CURRENT_COMBAT = True
            elif setting._FORCE_PHYSICAL_FIRST_COMBAT:
                logger.info(f"重启后第 {combat_number} 次战斗，开启强力单体技能模式（整场战斗）")
                runtimeContext._FORCE_PHYSICAL_CURRENT_COMBAT = True

        # 从村庄返回后前N次战斗，开启整场战斗强制使用强力单体技能或全体技能模式
        # 同样只在新战斗开始时才倒数
        if runtimeContext._FIRST_COMBAT_AFTER_INN > 0 and not runtimeContext._FORCE_PHYSICAL_CURRENT_COMBAT and not runtimeContext._FORCE_AOE_CURRENT_COMBAT:
            combat_number = 3 - runtimeContext._FIRST_COMBAT_AFTER_INN  # 2->第1次, 1->第2次
            runtimeContext._FIRST_COMBAT_AFTER_INN -= 1
            if setting._FORCE_AOE_AFTER_INN:
                logger.info(f"返回后第 {combat_number} 次战斗，开启全体技能模式（整场战斗）")
                runtimeContext._FORCE_AOE_CURRENT_COMBAT = True
            elif setting._FORCE_PHYSICAL_AFTER_INN:
                logger.info(f"返回后第 {combat_number} 次战斗，开启强力单体技能模式（整场战斗）")
                runtimeContext._FORCE_PHYSICAL_CURRENT_COMBAT = True

        # 如果当前战斗需要强制使用全体技能
        if runtimeContext._FORCE_AOE_CURRENT_COMBAT:
            if useForcedAOESkill(screen, doubleConfirmCastSpell, "全体技能模式"):
                return
            # AOE 找不到，嘗試單體技能
            if useForcedPhysicalSkill(screen, doubleConfirmCastSpell, "全体技能找不到，改用强力单体"):
                return
            # 都找不到，跳過自動戰鬥，讓下個角色繼續嘗試
            logger.info("当前角色无可用技能，等待下个角色")
            return

        # 如果当前战斗需要强制使用强力单体技能
        elif runtimeContext._FORCE_PHYSICAL_CURRENT_COMBAT:
            if useForcedPhysicalSkill(screen, doubleConfirmCastSpell, "强力单体技能模式"):
                return
            # 找不到，跳過自動戰鬥，讓下個角色繼續嘗試
            logger.info("当前角色无可用技能，等待下个角色")
            return

        if (setting._SYSTEMAUTOCOMBAT) or (runtimeContext._ENOUGH_AOE and setting._AUTO_AFTER_AOE):
            # 只點擊一次，避免兩個都匹配時連續點擊導致開啟後又關閉
            if not Press(CheckIf(WrapImage(screen,0.1,0.3,1),'combatAuto',[[700,1000,200,200]])):
                Press(CheckIf(screen,'combatAuto_2',[[700,1000,200,200]]))
            Sleep(5)
            return

        if not CheckIf(screen,'flee'):
            return
        if runtimeContext._SUICIDE:
            Press(CheckIf(screen,'spellskill/'+'defend'))
        else:
            # 正常战斗逻辑
            castSpellSkill = False
            castAndPressOK = False
            for skillspell in setting._SPELLSKILLCONFIG:
                if runtimeContext._ENOUGH_AOE and ((skillspell in SECRET_AOE_SKILLS) or (skillspell in FULL_AOE_SKILLS)):
                    #logger.info(f"本次战斗已经释放全体aoe, 由于面板配置, 不进行更多的技能释放.")
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
                        logger.info(f"已释放全体AOE ({runtimeContext._AOE_CAST_TIME}/{setting._AOE_TIME})")
                    break
            if not castSpellSkill:
                Press(CheckIf(ScreenShot(),'combatClose'))
                Press([850,1100])
                Sleep(0.5)
                Press([850,1100])
                Sleep(3)
    def StateMap_FindSwipeClick(targetInfo : TargetInfo):
        ### return = None: 视为没找到, 大约等于目标点结束.
        ### return = [x,y]: 视为找到, [x,y]是坐标.
        target = targetInfo.target
        roi = targetInfo.roi
        for i in range(len(targetInfo.swipeDir)):
            scn = ScreenShot()
            if not CheckIf(scn,'mapFlag'):
                raise KeyError("地图不可用.")

            swipeDir = targetInfo.swipeDir[i]
            if swipeDir!=None:
                logger.debug(f"拖动地图:{swipeDir[0]} {swipeDir[1]} {swipeDir[2]} {swipeDir[3]}")
                DeviceShell(f"input swipe {swipeDir[0]} {swipeDir[1]} {swipeDir[2]} {swipeDir[3]}")
                Sleep(2)
                scn = ScreenShot()
            
            targetPos = None
            if target == 'position':
                logger.info(f"当前目标: 地点{roi}")
                targetPos = CheckIf_ReachPosition(scn,targetInfo)
            elif target == 'minimap_stair':
                # minimap_stair: 直接使用座標，不搜索圖片（偵測在 StateMoving_CheckFrozen 中進行）
                logger.info(f"当前目标: 小地圖樓梯 座標{roi} 目標圖片{targetInfo.floorImage}")
                targetPos = roi  # 直接返回座標
                break
            elif target.startswith("stair"):
                logger.info(f"当前目标: 楼梯{target}")
                targetPos = CheckIf_throughStair(scn,targetInfo)
            else:
                logger.info(f"搜索{target}...")
                # harken: roi 正常用於搜索區域限制，floorImage 用於樓層選擇
                if targetPos:=CheckIf(scn,target,roi):
                    logger.info(f'找到了 {target}! {targetPos}')
                    if (target == 'chest') and (swipeDir!= None):
                        logger.debug(f"宝箱热力图: 地图:{setting._FARMTARGET} 方向:{swipeDir} 位置:{targetPos}")
                    if not roi:
                        # 如果没有指定roi 我们使用二次确认
                        # logger.debug(f"拖动: {targetPos[0]},{targetPos[1]} -> 450,800")
                        # DeviceShell(f"input swipe {targetPos[0]} {targetPos[1]} {(targetPos[0]+450)//2} {(targetPos[1]+800)//2}")
                        # 二次确认也不拖动了 太容易触发bug
                        Sleep(2)
                        Press([1,1255])
                        targetPos = CheckIf(ScreenShot(),target,roi)
                    break
        return targetPos
    def StateMoving_CheckFrozen():
        lastscreen = None
        dungState = None
        resume_consecutive_count = 0  # Resume连续点击计数（画面持续静止）
        MAX_RESUME_RETRIES = 5  # Resume最大连续点击次数

        # 移动超时检测（防止原地旋转BUG）
        moving_start_time = time.time()
        MOVING_TIMEOUT = 60  # 60秒超时
        
        # 輪詢參數（替代固定 Sleep(3)）
        POLL_INTERVAL = 0.3  # 每 0.3 秒檢查一次
        MAX_POLL_COUNT = 10  # 最多檢查 10 次 = 3 秒

        logger.info("面具男, 移动.")
        while 1:
            # 輪詢式等待：檢查畫面變化，發現靜止就提前進入下一步
            poll_screen = None
            for poll_i in range(MAX_POLL_COUNT):
                if setting._FORCESTOPING and setting._FORCESTOPING.is_set():
                    return None
                time.sleep(POLL_INTERVAL)
                poll_screen = ScreenShot()
                
                # 如果有上一幀，比較畫面變化
                if lastscreen is not None:
                    gray_poll = cv2.cvtColor(poll_screen, cv2.COLOR_BGR2GRAY)
                    gray_last = cv2.cvtColor(lastscreen, cv2.COLOR_BGR2GRAY)
                    diff = cv2.absdiff(gray_poll, gray_last).mean() / 255
                    
                    if diff < 0.05:  # 畫面幾乎靜止，可能已停止移動
                        logger.debug(f"輪詢 {poll_i+1}/{MAX_POLL_COUNT}: 畫面靜止 (diff={diff:.3f})，提前進入狀態檢查")
                        break
                    else:
                        logger.debug(f"輪詢 {poll_i+1}/{MAX_POLL_COUNT}: 畫面變化中 (diff={diff:.3f})")
                        lastscreen = poll_screen  # 更新參考幀

            # 检查移动是否超时
            elapsed = time.time() - moving_start_time
            if elapsed > MOVING_TIMEOUT:
                logger.error(f"移动超时（{elapsed:.1f}秒），疑似原地旋转BUG，准备重启游戏")
                restartGame()

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
                logger.info(f"开始移动失败. 不要停下来啊面具男!")
                FindCoordsOrElseExecuteFallbackAndWait("dungFlag", [[280, 1433], [1, 1]], 1)
                dungState = dungState.Dungeon
                break
            if dungState != DungeonState.Dungeon:
                logger.info(f"已退出移动状态. 当前状态: {dungState}.")
                break
            if lastscreen is not None:
                gray1 = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                gray2 = cv2.cvtColor(lastscreen, cv2.COLOR_BGR2GRAY)
                mean_diff = cv2.absdiff(gray1, gray2).mean() / 255
                logger.debug(f"移动停止检查:{mean_diff:.2f}")
                if mean_diff < 0.1:
                    # 画面静止，检查Resume按钮（如果启用了Resume优化）
                    if setting._ENABLE_RESUME_OPTIMIZATION:
                        # 先檢查是否已在地圖狀態（避免不必要的 Resume 檢測）
                        if CheckIf(screen, 'mapFlag'):
                            logger.info("StateMoving: 已在地圖狀態，跳過 Resume 檢測")
                            dungState = DungeonState.Map
                            break
                        
                        resume_pos = CheckIf(screen, 'resume')
                        
                        if resume_pos:
                            # Resume按钮存在 = 移动被打断但未到达
                            resume_consecutive_count += 1
                            
                            if resume_consecutive_count <= MAX_RESUME_RETRIES:
                                # 继续点击Resume
                                logger.info(f"检测到Resume按钮（画面静止），点击继续移动（第 {resume_consecutive_count} 次）位置:{resume_pos}")
                                Press(resume_pos)
                                Sleep(1)
                                
                                # 检查 routenotfound 是否出现
                                screen_after_resume = ScreenShot()
                                if CheckIf(screen_after_resume, 'routenotfound'):
                                    logger.info("StateMoving: 检测到routenotfound，已到达目的地，打开地图")
                                    Sleep(1)  # routenotfound 会自动消失，稍等一下
                                    Press([777,150])  # 打开地图
                                    dungState = DungeonState.Map
                                    break
                                else:
                                    logger.info("StateMoving: 未检测到routenotfound")
                                
                                lastscreen = None  # 重置lastscreen以重新开始检测
                                continue  # 继续循环，不退出
                            else:
                                # Resume点击多次仍然静止 = 可能卡住，执行回城
                                logger.warning(f"Resume按钮点击{MAX_RESUME_RETRIES}次后画面仍静止，执行回城")
                                runtimeContext._GOHOME_IN_PROGRESS = True
                                dungState = DungeonState.Dungeon
                                break
                        else:
                            # Resume按钮不存在 = 已到达目标
                            logger.info("已退出移动状态（画面静止且Resume按钮消失）.进行状态检查...")
                            dungState = None
                            break
                    else:
                        # 未启用Resume优化，使用原始逻辑
                        dungState = None
                        logger.info("已退出移动状态.进行状态检查...")
                        break
                else:
                    # 画面在移动，重置连续计数器
                    if resume_consecutive_count > 0:
                        logger.debug(f"画面恢复移动，重置Resume计数器（之前: {resume_consecutive_count}）")
                        resume_consecutive_count = 0
            lastscreen = screen
        return dungState
    def StateSearch(waitTimer, targetInfoList : list[TargetInfo]):
        normalPlace = ['harken','chest','leaveDung','position']
        targetInfo = targetInfoList[0]
        target = targetInfo.target
        # 地图已经打开.
        map = ScreenShot()
        if not CheckIf(map,'mapFlag'):
                return None,targetInfoList # 发生了错误

        try:
            searchResult = StateMap_FindSwipeClick(targetInfo)
        except KeyError as e:
            logger.info(f"错误: {e}") # 一般来说这里只会返回"地图不可用"
            return None,  targetInfoList
    
        if not CheckIf(map,'mapFlag'):
                return None,targetInfoList # 发生了错误, 应该是进战斗了

        if searchResult == None:
            if target == 'chest':
                # 结束, 弹出.
                targetInfoList.pop(0)
                logger.info(f"没有找到宝箱.\n停止检索宝箱.")
            elif (target == 'position' or target.startswith('stair')):
                # 结束, 弹出.
                targetInfoList.pop(0)
                logger.info(f"已经抵达目标地点或目标楼层.")
            else:
                # 这种时候我们认为真正失败了. 所以不弹出.
                # 当然, 更好的做法时传递finish标识()
                logger.info(f"未找到目标{target}.")

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
                
                # 如果启用了Resume优化且成功到达(返回None)，返回Dungeon状态避免重新打开地图
                if setting._ENABLE_RESUME_OPTIMIZATION and result_state is None:
                    logger.debug("Resume优化: 移动完成，跳过重新打开地图")
                    return DungeonState.Dungeon, targetInfoList
                else:
                    return result_state, targetInfoList
            else:
                if (CheckIf_FocusCursor(ScreenShot(),target)): #注意 这里通过二次确认 我们可以看到目标地点 而且是未选中的状态
                    logger.info("经过对比中心区域, 确认没有抵达.")
                    Press(searchResult)
                    Press([138,1432]) # automove
                    return StateMoving_CheckFrozen(),targetInfoList
                else:
                    if setting._DUNGWAITTIMEOUT == 0:
                        logger.info("经过对比中心区域, 判断为抵达目标地点.")
                        logger.info("无需等待, 当前目标已完成.")
                        targetInfoList.pop(0)
                        return DungeonState.Map,  targetInfoList
                    else:
                        logger.info("经过对比中心区域, 判断为抵达目标地点.")
                        logger.info('开始等待...等待...')
                        PressReturn()
                        Sleep(0.5)
                        PressReturn()
                        while 1:
                            if setting._DUNGWAITTIMEOUT-time.time()+waitTimer<0:
                                logger.info("等得够久了. 目标地点完成.")
                                targetInfoList.pop(0)
                                Sleep(1)
                                Press([777,150])
                                return None,  targetInfoList
                            logger.info(f'还需要等待{setting._DUNGWAITTIMEOUT-time.time()+waitTimer}秒.')
                            if CheckIf(ScreenShot(),'combatActive') or CheckIf(ScreenShot(),'combatActive_2'):
                                return DungeonState.Combat,targetInfoList
        return DungeonState.Map,  targetInfoList
    def StateChest():
        nonlocal runtimeContext
        availableChar = [0, 1, 2, 3, 4, 5]
        disarm = [515,934]  # 527,920会按到接受死亡 450 1000会按到技能 445,1050还是会按到技能
        haveBeenTried = False

        if runtimeContext._TIME_CHEST==0:
            runtimeContext._TIME_CHEST = time.time()

        while 1:
            FindCoordsOrElseExecuteFallbackAndWait(
                ['dungFlag','combatActive', 'combatActive_2','chestOpening','whowillopenit','RiseAgain'],
                [[1,1],[1,1],'chestFlag'],
                1)
            scn = ScreenShot()

            if CheckIf(scn,'whowillopenit'):
                while 1:
                    pointSomeone = setting._WHOWILLOPENIT - 1
                    if (pointSomeone != -1) and (pointSomeone in availableChar) and (not haveBeenTried):
                        whowillopenit = pointSomeone # 如果指定了一个角色并且该角色可用并且没尝试过, 使用它
                    else:
                        whowillopenit = random.choice(availableChar) # 否则从列表里随机选一个
                    pos = [258+(whowillopenit%3)*258, 1161+((whowillopenit)//3)%2*184]
                    # logger.info(f"{availableChar},{pos}")
                    if CheckIf(scn,'chestfear',[[pos[0]-125,pos[1]-82,250,164]]):
                        if whowillopenit in availableChar:
                            availableChar.remove(whowillopenit) # 如果发现了恐惧, 删除这个角色.
                    else:
                        Press(pos)
                        Sleep(1.5)
                        if not setting._SMARTDISARMCHEST:
                            for _ in range(8):
                                t = time.time()
                                Press(disarm)
                                if time.time()-t<0.3:
                                    Sleep(0.3-(time.time()-t))
                                
                        break
                if not haveBeenTried:
                    haveBeenTried = True

            if CheckIf(scn,'chestOpening'):
                Sleep(1)
                if setting._SMARTDISARMCHEST:
                    ChestOpen()
                FindCoordsOrElseExecuteFallbackAndWait(
                    ['dungFlag','combatActive','combatActive_2','chestFlag','RiseAgain'], # 如果这个fallback重启了, 战斗箱子会直接消失, 固有箱子会是chestFlag
                    [disarm,disarm,disarm,disarm,disarm,disarm,disarm,disarm],
                    1)
            
            if CheckIf(scn,'RiseAgain'):
                RiseAgainReset(reason = 'chest')
                return None
            if CheckIf(scn,'dungFlag'):
                return DungeonState.Dungeon
            if CheckIf(scn,'combatActive') or CheckIf(scn,'combatActive_2'):
                return DungeonState.Combat
            
            TryPressRetry(scn)
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
            logger.info("----------------------")
            if setting._FORCESTOPING.is_set():
                logger.info("即将停止脚本...")
                dungState = DungeonState.Quit
            logger.info(f"当前状态(地下城): {dungState}")

            match dungState:
                case None:
                    s, dungState,scn = IdentifyState()
                    if (s == State.Inn) or (dungState == DungeonState.Quit):
                        break
                    gameFrozen_none, result = GameFrozenCheck(gameFrozen_none,scn)
                    if result:
                        logger.info("由于画面卡死, 在state:None中重启.")
                        restartGame()
                    MAXTIMEOUT = 400
                    if (runtimeContext._TIME_CHEST != 0 ) and (time.time()-runtimeContext._TIME_CHEST > MAXTIMEOUT):
                        logger.info("由于宝箱用时过久, 在state:None中重启.")
                        restartGame()
                    if (runtimeContext._TIME_COMBAT != 0) and (time.time()-runtimeContext._TIME_COMBAT > MAXTIMEOUT):
                        logger.info("由于战斗用时过久, 在state:None中重启.")
                        restartGame()
                case DungeonState.Quit:
                    break
                case DungeonState.Dungeon:
                    Press([1,1])
                    ########### COMBAT RESET
                    # 战斗结束了, 我们将一些设置复位
                    if setting._AOE_ONCE:
                        runtimeContext._ENOUGH_AOE = False
                    runtimeContext._FORCE_PHYSICAL_CURRENT_COMBAT = False  # 重置强力单体技能模式
                    runtimeContext._FORCE_AOE_CURRENT_COMBAT = False  # 重置全体技能模式
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
                        logger.info(f"粗略统计: 宝箱{spend_on_chest:.2f}秒, 战斗{spend_on_combat:.2f}秒.")
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
                        logger.info("进行开启宝箱后的恢复.")
                        runtimeContext._COUNTERCHEST+=1
                        needRecoverBecauseChest = False
                        runtimeContext._MEET_CHEST_OR_COMBAT = True
                        if not setting._SKIPCHESTRECOVER:
                            logger.info("由于面板配置, 进行开启宝箱后恢复.")
                            shouldRecover = True
                        else:
                            logger.info("由于面板配置, 跳过了开启宝箱后恢复.")
                    if needRecoverBecauseCombat:
                        runtimeContext._COUNTERCOMBAT+=1
                        needRecoverBecauseCombat = False
                        runtimeContext._MEET_CHEST_OR_COMBAT = True
                        if (not setting._SKIPCOMBATRECOVER):
                            logger.info("由于面板配置, 进行战后恢复.")
                            shouldRecover = True
                        else:
                            logger.info("由于面板配置, 跳过了战后后恢复.")
                    if runtimeContext._RECOVERAFTERREZ == True:
                        shouldRecover = True
                        runtimeContext._RECOVERAFTERREZ = False
                    if shouldRecover:
                        Press([1,1])
                        counter_trychar = -1
                        while 1:
                            counter_trychar += 1
                            if CheckIf(ScreenShot(),'dungflag') and (counter_trychar <=20):
                                Press([36+(counter_trychar%3)*286,1425])
                                Sleep(1)
                            else:
                                logger.info("自动回复失败, 暂不进行回复.")
                                break
                            if CheckIf(scn:=ScreenShot(),'trait'):
                                if CheckIf(scn,'story', [[676,800,220,108]]):
                                    Press([725,850])
                                else:
                                    Press([830,850])
                                Sleep(1)
                                FindCoordsOrElseExecuteFallbackAndWait(
                                    ['recover','combatActive','combatActive_2'],
                                    [833,843],
                                    1
                                    )
                                if CheckIf(ScreenShot(),'recover'):
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
                    # 如果正在回城中（被战斗/宝箱打断后），继续回城
                    if runtimeContext._GOHOME_IN_PROGRESS:
                        logger.info("继续回城（之前被战斗/宝箱打断）")
                        gohome_click_count = 0
                        MAX_GOHOME_CLICKS = 10
                        while True:
                            main_state, current_state, _ = IdentifyState()
                            # 检查是否已回到城内（Inn）
                            if main_state == State.Inn:
                                logger.info("已回到城内")
                                dungState = DungeonState.Quit
                                runtimeContext._GOHOME_IN_PROGRESS = False
                                break
                            elif current_state == DungeonState.Combat:
                                logger.info("回城途中遇到战斗")
                                dungState = DungeonState.Combat
                                break
                            elif current_state == DungeonState.Chest:
                                logger.info("回城途中遇到宝箱")
                                dungState = DungeonState.Chest
                                break
                            gohome_pos = CheckIf(ScreenShot(), 'gohome')
                            if gohome_pos:
                                logger.info(f"点击gohome: {gohome_pos}")
                                Press(gohome_pos)
                                gohome_click_count += 1
                                if gohome_click_count >= MAX_GOHOME_CLICKS:
                                    logger.warning(f"gohome点击{MAX_GOHOME_CLICKS}次仍未回到城内，放弃回城")
                                    runtimeContext._GOHOME_IN_PROGRESS = False
                                    break
                            else:
                                # 如果找不到gohome，尝试打开地图
                                logger.info("未找到gohome按钮，尝试打开地图")
                                Press([777,150])
                                gohome_click_count += 1
                                if gohome_click_count >= MAX_GOHOME_CLICKS:
                                    logger.warning(f"尝试{MAX_GOHOME_CLICKS}次仍未找到gohome，放弃回城")
                                    runtimeContext._GOHOME_IN_PROGRESS = False
                                    break
                            Sleep(2)
                    ########### 防止转圈 (from upstream 1.9.27)
                    # 例外：當目標包含 chest_auto 時，跳過防止轉圈機制
                    has_chest_auto = any(t.target == 'chest_auto' for t in targetInfoList)
                    if has_chest_auto:
                        logger.debug("目標包含 chest_auto，跳過防止轉圈機制")
                        runtimeContext._STEPAFTERRESTART = True  # 標記為已處理，避免後續執行
                    if not runtimeContext._STEPAFTERRESTART:
                        # 重啟後：前後左右移動
                        if runtimeContext._FIRST_COMBAT_AFTER_RESTART > 0:
                            logger.info("防止转圈（重啟後）: 前後左右移動測試")

                            # 前進（向上）
                            DeviceShell("input swipe 440 950 440 750")
                            Sleep(1)

                            # 後退（向下）
                            DeviceShell("input swipe 440 950 440 1150")
                            Sleep(1)

                            # 左平移
                            Press([27,950])
                            Sleep(1)

                            # 右平移
                            Press([853,950])
                            Sleep(1)
                        else:
                            # 第一次進入：只左右移動
                            logger.info("防止转圈: 左右平移一次")

                            # 左平移
                            Press([27,950])
                            Sleep(1)

                            # 右平移
                            Press([853,950])
                            Sleep(1)

                        runtimeContext._STEPAFTERRESTART = True
                    # 第一次进入地城时，无条件打开地图（不检查能见度）
                    # 例外：chest_auto 跳過此機制
                    if runtimeContext._FIRST_DUNGEON_ENTRY and not has_chest_auto:
                        logger.info("第一次进入地城，打开地图")
                        Sleep(1)
                        Press([777,150])
                        dungState = DungeonState.Map
                        runtimeContext._FIRST_DUNGEON_ENTRY = False  # 标记为已进入过
                    elif runtimeContext._FIRST_DUNGEON_ENTRY and has_chest_auto:
                        logger.debug("chest_auto 模式：跳過第一次進入地城打開地圖，直接進入 Map 狀態")
                        runtimeContext._FIRST_DUNGEON_ENTRY = False
                        dungState = DungeonState.Map  # 仍需進入 Map 狀態以處理 chest_auto 邏輯
                    # 重启后：跳过Resume优化，直接尝试打开地图
                    elif runtimeContext._RESTART_OPEN_MAP_PENDING:
                        logger.info("重启后：跳过Resume优化，尝试打开地图")
                        Sleep(1)
                        Press([777,150])
                        Sleep(1)
                        screen = ScreenShot()
                        if CheckIf(screen, 'mapFlag'):
                            logger.info("重启后：成功打开地图")
                            dungState = DungeonState.Map
                            runtimeContext._RESTART_OPEN_MAP_PENDING = False
                        elif CheckIf(screen, 'visibliityistoopoor'):
                            # 能见度太低，无法打开地图，执行gohome
                            logger.warning("重启后：能见度太低无法打开地图，执行gohome")
                            runtimeContext._GOHOME_IN_PROGRESS = True
                            runtimeContext._RESTART_OPEN_MAP_PENDING = False
                        else:
                            # 其他情况（可能在战斗/宝箱），重新检测状态
                            logger.info("重启后：地图未打开，重新检测状态")
                            dungState = None
                    # minimap_stair 恢復監控：如果標誌仍在（戰鬥/寶箱打斷後），繼續移動並監控小地圖
                    elif runtimeContext._MINIMAP_STAIR_IN_PROGRESS and runtimeContext._MINIMAP_STAIR_FLOOR_TARGET:
                        logger.info(f"minimap_stair 恢復監控: 繼續尋找樓層標識 {runtimeContext._MINIMAP_STAIR_FLOOR_TARGET}")
                        Sleep(1)
                        # 檢測 Resume 按鈕並繼續移動
                        screen = ScreenShot()
                        resume_pos = CheckIf(screen, 'resume')
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
                    # Resume优化: 非第一次进入，检查Resume按钮决定下一步动作
                    # 注意: 重启后跳过Resume优化，因为之前的路径可能已失效
                    elif setting._ENABLE_RESUME_OPTIMIZATION and runtimeContext._STEPAFTERRESTART:
                        Sleep(1)
                        
                        # 检测Resume按钮，最多重试3次（等待画面过渡）
                        # 同时检测宝箱和战斗状态，避免错过刚出现的宝箱
                        MAX_RESUME_DETECT_RETRIES = 3
                        resume_pos = None
                        detected_other_state = False
                        for detect_retry in range(MAX_RESUME_DETECT_RETRIES):
                            screen = ScreenShot()
                            
                            # 先檢查是否已在地圖狀態（避免不必要的 Resume 檢測）
                            if CheckIf(screen, 'mapFlag'):
                                logger.info("Resume优化: 已在地圖狀態，跳過 Resume 檢測")
                                dungState = DungeonState.Map
                                detected_other_state = True
                                break
                            
                            # 先检查是否有宝箱或战斗
                            if CheckIf(screen, 'chestFlag') or CheckIf(screen, 'whowillopenit'):
                                logger.info(f"Resume优化: 检测到宝箱状态（第 {detect_retry + 1} 次尝试）")
                                dungState = DungeonState.Chest
                                detected_other_state = True
                                break
                            if CheckIf(screen, 'combatActive') or CheckIf(screen, 'combatActive_2'):
                                logger.info(f"Resume优化: 检测到战斗状态（第 {detect_retry + 1} 次尝试）")
                                dungState = DungeonState.Combat
                                detected_other_state = True
                                break
                            
                            # 检查Resume按钮
                            resume_pos = CheckIf(screen, 'resume')
                            if resume_pos:
                                logger.info(f"Resume优化: 检测到Resume按钮（第 {detect_retry + 1} 次尝试）")
                                break
                            else:
                                if detect_retry < MAX_RESUME_DETECT_RETRIES - 1:
                                    logger.info(f"Resume优化: 未检测到Resume按钮，等待重试（{detect_retry + 1}/{MAX_RESUME_DETECT_RETRIES}）")
                                    Sleep(1)
                        
                        # 如果检测到其他状态，跳过Resume优化
                        if detected_other_state:
                            pass  # dungState已设置，直接进入下一轮循环
                        elif resume_pos:
                            # Resume存在，点击Resume，最多重试3次
                            MAX_RESUME_RETRIES = 3
                            resume_success = False
                            
                            for retry in range(MAX_RESUME_RETRIES):
                                logger.info(f"Resume优化: 点击Resume按钮（第 {retry + 1}/{MAX_RESUME_RETRIES} 次）位置:{resume_pos}")
                                Press(resume_pos)
                                Sleep(1)  # 等待 routenotfound 可能出现
                                
                                # 检查 routenotfound 是否出现
                                screen_after = ScreenShot()
                                if CheckIf(screen_after, 'routenotfound'):
                                    # routenotfound 出现 = 已到达目的地
                                    logger.info("Resume优化: 检测到routenotfound，已到达目的地，打开地图")
                                    Sleep(1)  # routenotfound 会自动消失，稍等一下
                                    Press([777,150])  # 打开地图
                                    Sleep(1)
                                    # 检查能见度
                                    if CheckIf(ScreenShot(), 'visibliityistoopoor'):
                                        logger.warning("visibliityistoopoor，开始持续点击gohome回城")
                                        runtimeContext._GOHOME_IN_PROGRESS = True
                                        while True:
                                            main_state, current_state, _ = IdentifyState()
                                            if main_state == State.Inn:
                                                logger.info("已回到城内")
                                                dungState = DungeonState.Quit
                                                runtimeContext._GOHOME_IN_PROGRESS = False
                                                break
                                            elif current_state == DungeonState.Combat:
                                                logger.info("回城途中遇到战斗")
                                                dungState = DungeonState.Combat
                                                break
                                            elif current_state == DungeonState.Chest:
                                                logger.info("回城途中遇到宝箱")
                                                dungState = DungeonState.Chest
                                                break
                                            gohome_pos = CheckIf(ScreenShot(), 'gohome')
                                            if gohome_pos:
                                                logger.info(f"点击gohome: {gohome_pos}")
                                                Press(gohome_pos)
                                            Sleep(2)
                                    else:
                                        dungState = DungeonState.Map
                                    resume_success = True
                                    break
                                else:
                                    logger.info("Resume优化: 未检测到routenotfound")
                                
                                # 检查画面是否有变化（表示正在移动）
                                gray1 = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                                gray2 = cv2.cvtColor(screen_after, cv2.COLOR_BGR2GRAY)
                                mean_diff = cv2.absdiff(gray1, gray2).mean() / 255
                                logger.info(f"Resume优化: 画面变化检测 mean_diff={mean_diff:.4f}")
                                
                                if mean_diff >= 0.02:  # 阈值降低到 2%
                                    # 画面有变化 = 还在路上，继续移动监控
                                    logger.info("Resume优化: 画面有变化，继续移动监控")
                                    dungState = StateMoving_CheckFrozen()
                                    resume_success = True
                                    break
                                
                                # 画面没变化，准备重试
                                logger.warning(f"Resume优化: 画面无变化，准备重试 ({retry + 1}/{MAX_RESUME_RETRIES})")
                                screen = screen_after  # 更新参考画面
                                resume_pos = CheckIf(screen, 'resume')
                                if not resume_pos:
                                    # Resume按钮消失了，可能已经开始移动
                                    logger.info("Resume优化: Resume按钮消失，进入移动监控")
                                    dungState = StateMoving_CheckFrozen()
                                    resume_success = True
                                    break
                            
                            if not resume_success:
                                # 5次Resume失败
                                # 检查当前目标是否是楼梯：如果是楼梯，Resume失效代表换楼成功
                                current_target = targetInfoList[0].target if targetInfoList else None
                                if current_target and current_target.startswith('stair'):
                                    logger.info(f"Resume优化: {MAX_RESUME_RETRIES}次Resume失败，但目标是楼梯({current_target})，判定为换楼成功")
                                    targetInfoList.pop(0)  # 弹出当前楼梯目标
                                    logger.info("Resume优化: 打开地图继续下一个目标")
                                    Press([777,150])  # 打开地图
                                    Sleep(1)
                                    dungState = DungeonState.Map
                                else:
                                    # 非楼梯目标，执行gohome
                                    logger.warning(f"Resume优化: {MAX_RESUME_RETRIES}次Resume失败，执行gohome回城")
                                    runtimeContext._GOHOME_IN_PROGRESS = True
                                    while True:
                                        main_state, current_state, _ = IdentifyState()
                                        if main_state == State.Inn:
                                            logger.info("已回到城内")
                                            dungState = DungeonState.Quit
                                            runtimeContext._GOHOME_IN_PROGRESS = False
                                            break
                                        elif current_state == DungeonState.Combat:
                                            logger.info("回城途中遇到战斗")
                                            dungState = DungeonState.Combat
                                            break
                                        elif current_state == DungeonState.Chest:
                                            logger.info("回城途中遇到宝箱")
                                            dungState = DungeonState.Chest
                                            break
                                        gohome_pos = CheckIf(ScreenShot(), 'gohome')
                                        if gohome_pos:
                                            logger.info(f"点击gohome: {gohome_pos}")
                                            Press(gohome_pos)
                                        else:
                                            # 如果找不到gohome，尝试打开地图
                                            logger.info("未找到gohome按钮，尝试打开地图")
                                            Press([777,150])
                                        Sleep(2)
                        else:
                            # 3次都没检测到Resume，打开地图
                            logger.info("Resume优化: 3次均未检测到Resume按钮，打开地图")
                            Press([777,150])
                            Sleep(1)
                            # 检查能见度
                            if CheckIf(ScreenShot(), 'visibliityistoopoor'):
                                logger.warning("visibliityistoopoor，开始持续点击gohome回城")
                                runtimeContext._GOHOME_IN_PROGRESS = True
                                while True:
                                    main_state, current_state, _ = IdentifyState()
                                    if main_state == State.Inn:
                                        logger.info("已回到城内")
                                        dungState = DungeonState.Quit
                                        runtimeContext._GOHOME_IN_PROGRESS = False
                                        break
                                    elif current_state == DungeonState.Combat:
                                        logger.info("回城途中遇到战斗")
                                        dungState = DungeonState.Combat
                                        break
                                    elif current_state == DungeonState.Chest:
                                        logger.info("回城途中遇到宝箱")
                                        dungState = DungeonState.Chest
                                        break
                                    gohome_pos = CheckIf(ScreenShot(), 'gohome')
                                    if gohome_pos:
                                        logger.info(f"点击gohome: {gohome_pos}")
                                        Press(gohome_pos)
                                    Sleep(2)
                            else:
                                dungState = DungeonState.Map
                    else:
                        Sleep(1)
                        Press([777,150])
                        Sleep(1)
                        # 检查能见度
                        if CheckIf(ScreenShot(), 'visibliityistoopoor'):
                            logger.warning("visibliityistoopoor，开始持续点击gohome回城")
                            runtimeContext._GOHOME_IN_PROGRESS = True
                            while True:
                                main_state, current_state, _ = IdentifyState()
                                if main_state == State.Inn:
                                    logger.info("已回到城内")
                                    dungState = DungeonState.Quit
                                    runtimeContext._GOHOME_IN_PROGRESS = False
                                    break
                                elif current_state == DungeonState.Combat:
                                    logger.info("回城途中遇到战斗")
                                    dungState = DungeonState.Combat
                                    break
                                elif current_state == DungeonState.Chest:
                                    logger.info("回城途中遇到宝箱")
                                    dungState = DungeonState.Chest
                                    break
                                gohome_pos = CheckIf(ScreenShot(), 'gohome')
                                if gohome_pos:
                                    logger.info(f"点击gohome: {gohome_pos}")
                                    Press(gohome_pos)
                                Sleep(2)
                        else:
                            dungState = DungeonState.Map
                case DungeonState.Map:
                    if runtimeContext._SHOULDAPPLYSPELLSEQUENCE: # 默认值(第一次)和重启后应当直接应用序列
                        runtimeContext._SHOULDAPPLYSPELLSEQUENCE = False
                        if targetInfoList[0].activeSpellSequenceOverride:
                            logger.info("因为初始化, 复制了施法序列.")
                            runtimeContext._ACTIVESPELLSEQUENCE = copy.deepcopy(quest._SPELLSEQUENCE)

                    # chest_auto 特殊處理：不打開地圖，直接使用遊戲內建自動寶箱
                    if targetInfoList and targetInfoList[0] and (targetInfoList[0].target == "chest_auto"):
                        logger.info("使用遊戲內建自動寶箱功能")
                        lastscreen = ScreenShot()
                        chest_auto_pos = CheckIf(lastscreen, "chest_auto", [[710,250,180,180]])
                        if not Press(chest_auto_pos):
                            # 找不到就打開地圖面板再找
                            Press(CheckIf(lastscreen, "mapFlag"))
                            Press([664,329])
                            Sleep(1)
                            lastscreen = ScreenShot()
                            if not Press(CheckIf(lastscreen, "chest_auto", [[710,250,180,180]])):
                                logger.warning("無法找到自動寶箱按鈕，跳過此目標")
                                dungState = None
                                continue
                        Sleep(0.5)
                        # 等待移動完成
                        while True:
                            Sleep(3)
                            _, dungState, screen = IdentifyState()
                            if dungState != DungeonState.Dungeon:
                                logger.info(f"已退出移動狀態. 當前狀態為{dungState}.")
                                break
                            elif lastscreen is not None:
                                gray1 = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                                gray2 = cv2.cvtColor(lastscreen, cv2.COLOR_BGR2GRAY)
                                mean_diff = cv2.absdiff(gray1, gray2).mean()/255
                                logger.debug(f"移動停止檢查:{mean_diff:.2f}")
                                if mean_diff < 0.05:
                                    logger.info(f"停止移動. 誤差:{mean_diff}. 當前狀態為{dungState}.")
                                    if dungState == DungeonState.Dungeon:
                                        targetInfoList.pop(0)
                                    break
                                lastscreen = screen
                        continue

                    dungState, newTargetInfoList = StateSearch(waitTimer,targetInfoList)
                    
                    if newTargetInfoList == targetInfoList:
                        gameFrozen_map +=1
                        logger.info(f"地图卡死检测:{gameFrozen_map}")
                    else:
                        gameFrozen_map = 0
                    if gameFrozen_map > 50:
                        gameFrozen_map = 0
                        restartGame()

                    if (targetInfoList==None) or (targetInfoList == []):
                        logger.info("地下城目标完成. 地下城状态结束.(仅限任务模式.)")
                        break

                    if (newTargetInfoList != targetInfoList):
                        if newTargetInfoList[0].activeSpellSequenceOverride:
                            logger.info("因为目标信息变动, 重新复制了施法序列.")
                            runtimeContext._ACTIVESPELLSEQUENCE = copy.deepcopy(quest._SPELLSEQUENCE)
                        else:
                            logger.info("因为目标信息变动, 清空了施法序列.")
                            runtimeContext._ACTIVESPELLSEQUENCE = None

                case DungeonState.Chest:
                    needRecoverBecauseChest = True
                    dungState = StateChest()
                case DungeonState.Combat:
                    needRecoverBecauseCombat =True
                    StateCombat()
                    dungState = None
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
            logger.info("奇怪, 任务怎么已经接了.")
            FindCoordsOrElseExecuteFallbackAndWait('Inn',['return',[1,1]],1)

    def DungeonFarm():
        nonlocal runtimeContext
        state = None
        initial_dungState = None  # 用於傳遞給 StateDungeon 的初始狀態
        while 1:
            logger.info("======================")
            Sleep(1)
            if setting._FORCESTOPING.is_set():
                logger.info("即将停止脚本...")
                break
            logger.info(f"当前状态: {state}")
            match state:
                case None:
                    def _identifyState():
                        nonlocal state, initial_dungState
                        state, initial_dungState, _ = IdentifyState()
                    RestartableSequenceExecution(
                        lambda: _identifyState()
                        )
                    logger.info(f"下一状态: {state}")
                    if state ==State.Quit:
                        logger.info("即将停止脚本...")
                        break
                case State.Inn:
                    if runtimeContext._LAPTIME!= 0:
                        runtimeContext._TOTALTIME = runtimeContext._TOTALTIME + time.time() - runtimeContext._LAPTIME
                        summary_text = f"已完成{runtimeContext._COUNTERDUNG}次\"{setting._FARMTARGET_TEXT}\"地下城.\n总计{round(runtimeContext._TOTALTIME,2)}秒.上次用时:{round(time.time()-runtimeContext._LAPTIME,2)}秒.\n"
                        if runtimeContext._COUNTERCHEST > 0:
                            summary_text += f"箱子效率{round(runtimeContext._TOTALTIME/runtimeContext._COUNTERCHEST,2)}秒/箱.\n累计开箱{runtimeContext._COUNTERCHEST}次,开箱平均耗时{round(runtimeContext._TIME_CHEST_TOTAL/runtimeContext._COUNTERCHEST,2)}秒.\n"
                        if runtimeContext._COUNTERCOMBAT > 0:
                            summary_text += f"累计战斗{runtimeContext._COUNTERCOMBAT}次.战斗平均用时{round(runtimeContext._TIME_COMBAT_TOTAL/runtimeContext._COUNTERCOMBAT,2)}秒.\n"
                        if runtimeContext._COUNTERADBRETRY > 0 or runtimeContext._COUNTEREMULATORCRASH > 0:
                            summary_text += f"ADB重启{runtimeContext._COUNTERADBRETRY}次,模拟器崩溃{runtimeContext._COUNTEREMULATORCRASH}次."
                        logger.info(f"{runtimeContext._IMPORTANTINFO}{summary_text}",extra={"summary": True})
                    runtimeContext._LAPTIME = time.time()
                    runtimeContext._COUNTERDUNG+=1
                    if not runtimeContext._MEET_CHEST_OR_COMBAT:
                        logger.info("因为没有遇到战斗或宝箱, 跳过恢复")
                    elif not setting._ACTIVE_REST:
                        logger.info("因为面板设置, 跳过恢复")
                    elif ((runtimeContext._COUNTERDUNG-1) % (setting._RESTINTERVEL+1) != 0):
                        logger.info("还有许多地下城要刷. 面具男, 现在还不能休息哦.")
                    else:
                        logger.info("休息时间到!")
                        runtimeContext._MEET_CHEST_OR_COMBAT = False
                        RestartableSequenceExecution(
                        lambda:StateInn()
                        )
                    # 无论是否休息，只要从村庄进入地城，都设置返回后首次战斗标志
                    runtimeContext._FIRST_COMBAT_AFTER_INN = 1
                    state = State.EoT
                case State.EoT:
                    RestartableSequenceExecution(
                        lambda:StateEoT()
                        )
                    state = State.Dungeon
                case State.Dungeon:
                    runtimeContext._FIRST_DUNGEON_ENTRY = True  # 重置第一次进入标志
                    runtimeContext._DUNGEON_CONFIRMED = False  # 重置地城確認標記（新地城循環開始）
                    runtimeContext._GOHOME_IN_PROGRESS = False  # 重置回城标志
                    runtimeContext._AOE_TRIGGERED_THIS_DUNGEON = False  # 重置 AE 手觸發標記
                    runtimeContext._COMBAT_ACTION_COUNT = 0  # 重置行動計數器
                    runtimeContext._STEPAFTERRESTART = False  # 重置防止转圈标志
                    # 注意: _FIRST_COMBAT_AFTER_RESTART 只在 restartGame 中重置
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
        nonlocal setting # 强制自动战斗 等等.
        nonlocal runtimeContext
        match setting._FARMTARGET:
            case '7000G':
                while 1:
                    if setting._FORCESTOPING.is_set():
                        break

                    starttime = time.time()
                    runtimeContext._COUNTERDUNG += 1
                    def stepMain():
                        logger.info("第一步: 开始诅咒之旅...")
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

                    logger.info("第四步: 给我!(伸手)")
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
                    logger.info(f"第{runtimeContext._COUNTERDUNG}次\"7000G\"完成. 该次花费时间{costtime:.2f}, 每秒收益:{7000/costtime:.2f}Gps.",
                                extra={"summary": True})
            case 'fordraig':
                quest._SPECIALDIALOGOPTION = ['fordraig/thedagger','fordraig/InsertTheDagger']
                while 1:
                    if setting._FORCESTOPING.is_set():
                        break
                    runtimeContext._COUNTERDUNG += 1
                    setting._SYSTEMAUTOCOMBAT = True
                    starttime = time.time()
                    logger.info('第一步: 诅咒之旅...')
                    RestartableSequenceExecution(
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait('cursedWheel',['ruins',[1,1]],1)),
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait('Fordraig/Leap',['specialRequest',[1,1]],1)),
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait('OK','leap',1)),
                        )
                    Sleep(15)

                    RestartableSequenceExecution(
                        lambda: logger.info('第二步: 领取任务.'),
                        lambda: StateAcceptRequest('fordraig/RequestAccept',[350,180])
                        )

                    logger.info('第三步: 进入地下城.')
                    TeleportFromCityToWorldLocation('fordraig/labyrinthOfFordraig','input swipe 450 150 500 150')
                    Press(FindCoordsOrElseExecuteFallbackAndWait('fordraig/Entrance',['fordraig/labyrinthOfFordraig',[1,1]],1))
                    FindCoordsOrElseExecuteFallbackAndWait('dungFlag',['fordraig/Entrance','GotoDung',[1,1]],1)

                    logger.info('第四步: 陷阱.')
                    RestartableSequenceExecution(
                        lambda:StateDungeon([
                            TargetInfo('position',"左上",[721,448]),
                            TargetInfo('position',"左上",[720,608])]), # 前往第一个陷阱
                        lambda:FindCoordsOrElseExecuteFallbackAndWait("dungFlag","return",1), # 关闭地图
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait("fordraig/TryPushingIt",["input swipe 100 250 800 250",[400,800],[400,800],[400,800]],1)), # 转向来开启机关
                        )
                    logger.info('已完成第一个陷阱.')

                    RestartableSequenceExecution(
                        lambda:StateDungeon([
                            TargetInfo('stair_down',"左上",[721,236]),
                            TargetInfo('position',"左下", [240,921])]), #前往第二个陷阱
                        lambda:FindCoordsOrElseExecuteFallbackAndWait("dungFlag","return",1), # 关闭地图
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait("fordraig/TryPushingIt",["input swipe 100 250 800 250",[400,800],[400,800],[400,800]],1)), # 转向来开启机关
                        )
                    logger.info('已完成第二个陷阱.')

                    RestartableSequenceExecution(
                        lambda:StateDungeon([
                            TargetInfo("position","左下",[33,1238]),
                            TargetInfo("stair_down","左下",[453,1027]),
                            TargetInfo("position","左下",[187,1027]),
                            TargetInfo("stair_teleport","左下",[80,1026])
                            ]), #前往第三个陷阱
                        )
                    logger.info('已完成第三个陷阱.')

                    StateDungeon([TargetInfo('position','左下',[508,1025])]) # 前往boss战门前
                    setting._SYSTEMAUTOCOMBAT = False
                    StateDungeon([TargetInfo('position','左下',[720,1025])]) # 前往boss战斗
                    setting._SYSTEMAUTOCOMBAT = True
                    StateDungeon([TargetInfo('stair_teleport','左上',[665,395])]) # 第四层出口
                    FindCoordsOrElseExecuteFallbackAndWait("dungFlag","return",1)
                    Press(FindCoordsOrElseExecuteFallbackAndWait("ReturnText",["leaveDung",[455,1200]],3.75)) # 回城
                    # 3.75什么意思 正常循环是3秒 有4次尝试机会 因此3.75秒按一次刚刚好.
                    Press(FindCoordsOrElseExecuteFallbackAndWait("RoyalCityLuknalia",['return',[1,1]],1)) # 回城
                    FindCoordsOrElseExecuteFallbackAndWait("Inn",[1,1],1)

                    costtime = time.time()-starttime
                    logger.info(f"第{runtimeContext._COUNTERDUNG}次\"鸟剑\"完成. 该次花费时间{costtime:.2f}.",
                            extra={"summary": True})
            case 'repelEnemyForces':
                if not setting._ACTIVE_REST:
                    logger.info("注意, \"休息间隔\"控制连续战斗多少次后回城. 当前未启用休息, 强制设置为1.")
                    setting._RESTINTERVEL = 1
                if setting._RESTINTERVEL == 0:
                    logger.info("注意, \"休息间隔\"控制连续战斗多少次后回城. 当前值0为无效值, 最低为1.")
                    setting._RESTINTERVEL = 1
                logger.info("注意, 该流程不包括时间跳跃和接取任务, 请确保接取任务后再开启!")
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
                    logger.info('已抵达目标地点, 开始战斗.')
                    FindCoordsOrElseExecuteFallbackAndWait('dungFlag',['return',[1,1]],1)
                    for i in range(setting._RESTINTERVEL):
                        logger.info(f"第{i+1}轮开始.")
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
                                logger.info(f"第1场战斗结束.")
                                secondcombat = True
                                Press(CheckIf(ScreenShot(),'icanstillgo'))
                            else:
                                logger.info(f"第2场战斗结束.")
                                Press(CheckIf(ScreenShot(),'letswithdraw'))
                                Sleep(1)
                                break
                        logger.info(f"第{i+1}轮结束.")
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
                    logger.info(f"第{counter}x{setting._RESTINTERVEL}轮\"击退敌势力\"完成, 共计{counter*setting._RESTINTERVEL*2}场战斗. 该次花费时间{(time.time()-t):.2f}秒.",
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
                                logger.info("由于画面卡死, 在state:None中重启.")
                                restartGame()
                            MAXTIMEOUT = 400
                            if (runtimeContext._TIME_CHEST != 0 ) and (time.time()-runtimeContext._TIME_CHEST > MAXTIMEOUT):
                                logger.info("由于宝箱用时过久, 在state:None中重启.")
                                restartGame()
                            if (runtimeContext._TIME_COMBAT != 0) and (time.time()-runtimeContext._TIME_COMBAT > MAXTIMEOUT):
                                logger.info("由于战斗用时过久, 在state:None中重启.")
                                restartGame()
                        case DungeonState.Dungeon:
                            Press([1,1])
                            ########### COMBAT RESET
                            # 战斗结束了, 我们将一些设置复位
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
                                logger.info(f"粗略统计: 宝箱{spend_on_chest:.2f}秒, 战斗{spend_on_combat:.2f}秒.")
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
                                logger.info("进行开启宝箱后的恢复.")
                                runtimeContext._COUNTERCHEST+=1
                                needRecoverBecauseChest = False
                                runtimeContext._MEET_CHEST_OR_COMBAT = True
                                if not setting._SKIPCHESTRECOVER:
                                    logger.info("由于面板配置, 进行开启宝箱后恢复.")
                                    shouldRecover = True
                                else:
                                    logger.info("由于面板配置, 跳过了开启宝箱后恢复.")
                            if needRecoverBecauseCombat:
                                runtimeContext._COUNTERCOMBAT+=1
                                needRecoverBecauseCombat = False
                                runtimeContext._MEET_CHEST_OR_COMBAT = True
                                if (not setting._SKIPCOMBATRECOVER):
                                    logger.info("由于面板配置, 进行战后恢复.")
                                    shouldRecover = True
                                else:
                                    logger.info("由于面板配置, 跳过了战后后恢复.")
                            if shouldRecover:
                                Press([1,1])
                                FindCoordsOrElseExecuteFallbackAndWait( # 点击打开人物面板有可能会被战斗打断
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
                        logger.info(f"第{runtimeContext._COUNTERDUNG}次三牛完成. 本次用时:{round(time.time()-runtimeContext._LAPTIME,2)}秒. 累计开箱子{runtimeContext._COUNTERCHEST}, 累计战斗{runtimeContext._COUNTERCOMBAT}, 累计用时{round(runtimeContext._TOTALTIME,2)}秒.",
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
                        lambda: logger.info('第四步: 领取任务'),
                        lambda: StateAcceptRequest('LBC/Request',[266,257]),
                    )
                    RestartableSequenceExecution(
                        lambda: logger.info('第五步: 进入牛洞'),
                        lambda: TeleportFromCityToWorldLocation('LBC/LBC','input swipe 400 400 400 500')
                        )

                    Gorgon1 = TargetInfo('position','左上',[134,342])
                    Gorgon2 = TargetInfo('position','右上',[500,395])
                    Gorgon3 = TargetInfo('position','右下',[340,1027])
                    LBC_quit = TargetInfo('LBC/LBC_quit')
                    if setting._ACTIVE_REST:
                        RestartableSequenceExecution(
                            lambda: logger.info('第六步: 击杀一牛'),
                            lambda: StateDungeon([Gorgon1,LBC_quit])
                            )
                        RestartableSequenceExecution(
                            lambda: logger.info('第七步: 回去睡觉'),
                            lambda: StateInn()
                            )
                        RestartableSequenceExecution(
                            lambda: logger.info('第八步: 再入牛洞'),
                            lambda: TeleportFromCityToWorldLocation('LBC/LBC','input swipe 400 400 400 500')
                            )
                        RestartableSequenceExecution(
                            lambda: logger.info('第九步: 击杀二牛'),
                            lambda: StateDungeon([Gorgon2,Gorgon3,LBC_quit])
                            )
                    else:
                        logger.info('跳过回城休息.')
                        RestartableSequenceExecution(
                            lambda: logger.info('第六步: 连杀三牛'),
                            lambda: StateDungeon([Gorgon1,Gorgon2,Gorgon3,LBC_quit])
                            )
            case 'SSC-goldenchest':
                while 1:
                    quest._SPECIALDIALOGOPTION = ['SSC/dotdotdot','SSC/shadow']
                    if setting._FORCESTOPING.is_set():
                        break
                    if runtimeContext._LAPTIME!= 0:
                        runtimeContext._TOTALTIME = runtimeContext._TOTALTIME + time.time() - runtimeContext._LAPTIME
                        logger.info(f"第{runtimeContext._COUNTERDUNG}次忍洞完成. 本次用时:{round(time.time()-runtimeContext._LAPTIME,2)}秒. 累计开箱子{runtimeContext._COUNTERCHEST}, 累计战斗{runtimeContext._COUNTERCOMBAT}, 累计用时{round(runtimeContext._TOTALTIME,2)}秒.",
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
                        lambda: logger.info('第三步: 领取任务'),
                        lambda: stepThree()
                        )

                    RestartableSequenceExecution(
                        lambda: logger.info('第四步: 进入忍洞'),
                        lambda: TeleportFromCityToWorldLocation('SSC/SSC','input swipe 700 500 600 600')
                        )
                    RestartableSequenceExecution(
                        lambda: logger.info('第五步: 关闭陷阱'),
                        lambda:FindCoordsOrElseExecuteFallbackAndWait('SSC/trapdeactived',['input swipe 450 1050 450 850',[445,721]],4),
                        lambda:FindCoordsOrElseExecuteFallbackAndWait('dungFlag',[1,1],1)
                    )
                    quest._SPECIALDIALOGOPTION = ['SSC/dotdotdot','SSC/shadow']
                    RestartableSequenceExecution(
                        lambda: logger.info('第六步: 第一个箱子'),
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
                        logger.info(f"第{runtimeContext._COUNTERDUNG}次约定之剑完成. 本次用时:{round(time.time()-runtimeContext._LAPTIME,2)}秒. 累计开箱子{runtimeContext._COUNTERCHEST}, 累计战斗{runtimeContext._COUNTERCOMBAT}, 累计用时{round(runtimeContext._TOTALTIME,2)}秒.",
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
                        lambda: logger.info('第四步: 领取任务'),
                        lambda: FindCoordsOrElseExecuteFallbackAndWait(['COS/Okay','guildRequest'],['guild',[1,1]],1),
                        lambda: FindCoordsOrElseExecuteFallbackAndWait('Inn',['COS/Okay','return',[1,1]],1),
                        lambda: StateInn(),
                        )
                    
                    RestartableSequenceExecution(
                        lambda: logger.info('第五步: 进入洞窟'),
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
                        lambda: logger.info('第六步: 1层找人'),
                        lambda: StateDungeon(cosb1f)
                        )

                    quest._SPECIALFORCESTOPINGSYMBOL = ['COS/EnaTheAdventurer']
                    cosb2f = [TargetInfo('position',"右上",[340+54,448]),
                              TargetInfo('position',"右上",[500-54,1088]),
                              TargetInfo('position',"左上",[398+54,766]),
                        ]
                    RestartableSequenceExecution(
                        lambda: logger.info('第七步: 2层找人'),
                        lambda: StateDungeon(cosb2f)
                        )

                    quest._SPECIALFORCESTOPINGSYMBOL = ['COS/requestwasfor'] 
                    cosb3f = [TargetInfo('stair_3',"左上",[720,822]),
                              TargetInfo('position',"左下",[239,600]),
                              TargetInfo('position',"左下",[185,1185]),
                              TargetInfo('position',"左下",[560,652]),
                              ]
                    RestartableSequenceExecution(
                        lambda: logger.info('第八步: 3层找人'),
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
                        lambda: logger.info('第九步: 离开洞穴'),
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
                        logger.info(f"第{runtimeContext._COUNTERDUNG}次巨人完成. 本次用时:{round(time.time()-runtimeContext._LAPTIME,2)}秒. 累计开箱子{runtimeContext._COUNTERCHEST}, 累计战斗{runtimeContext._COUNTERCOMBAT}, 累计用时{round(runtimeContext._TOTALTIME,2)}秒.",
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
                        logger.info("没发现巨人.")
                        RestartableSequenceExecution(
                        lambda: StateDungeon([TargetInfo('harken2','左上')]),
                        lambda: FindCoordsOrElseExecuteFallbackAndWait('Inn',['returntotown','returnText','leaveDung','blessing',[1,1]],2)
                    )
                        continue
                    
                    logger.info("发现了巨人.")
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

                    logger.info("第四步: 悬赏揭榜")
                    RestartableSequenceExecution(
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait('guildRequest',['guild',[1,1]],1)),
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait('Bounties',['guild','guildRequest','input swipe 600 1400 300 1400',[1,1]],1)),
                        lambda:FindCoordsOrElseExecuteFallbackAndWait('EdgeOfTown',['return',[1,1]],1)
                        )

                    logger.info("第五步: 击杀蝎女")
                    RestartableSequenceExecution(
                        lambda:FindCoordsOrElseExecuteFallbackAndWait('dungFlag',['EdgeOfTown','beginningAbyss','B2FTemple','GotoDung',[1,1]],1),
                    )
                    RestartableSequenceExecution(
                        lambda:StateDungeon([TargetInfo('position','左下',[505,760]),
                                             TargetInfo('position','左上',[506,821])]),
                        )
                    
                    logger.info("第六步: 提交悬赏")
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
                    logger.info(f"第{runtimeContext._COUNTERDUNG}次\"悬赏:蝎女\"完成. \n该次花费时间{costtime:.2f}s.\n总计用时{total_time:.2f}s.\n平均用时{total_time/runtimeContext._COUNTERDUNG:.2f}",
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
                    logger.info(f"第{runtimeContext._COUNTERDUNG}次\"钢试炼\"完成. \n该次花费时间{costtime:.2f}s.\n总计用时{total_time:.2f}s.\n平均用时{total_time/runtimeContext._COUNTERDUNG:.2f}",
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

                    logger.info("第四步: 悬赏揭榜")
                    RestartableSequenceExecution(
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait('guildRequest',['guild',[1,1]],1)),
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait('Bounties',['guild','guildRequest','input swipe 600 1400 300 1400',[1,1]],1)),
                        lambda:FindCoordsOrElseExecuteFallbackAndWait('EdgeOfTown',['return',[1,1]],1)
                        )

                    logger.info("第五步: 和吉尔说再见吧")
                    RestartableSequenceExecution(
                        lambda:FindCoordsOrElseExecuteFallbackAndWait('dungFlag',['EdgeOfTown','beginningAbyss','B4FLabyrinth','GotoDung',[1,1]],1)
                        )
                    RestartableSequenceExecution( 
                        lambda:StateDungeon([TargetInfo('position','左下',[452,1026]),
                                             TargetInfo('harken','左上',None)]),
                        )
                    
                    logger.info("第六步: 提交悬赏")
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
                    logger.info(f"第{runtimeContext._COUNTERDUNG}次\"悬赏:吉尔\"完成. \n该次花费时间{costtime:.2f}s.\n总计用时{total_time:.2f}s.\n平均用时{total_time/runtimeContext._COUNTERDUNG:.2f}",
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
            Sleep(1) # 没有等utils初始化完成

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
            logger.info("ADB服务成功启动，设备已连接.")
    
    def DeviceShell(cmdStr):
        logger.debug(f"DeviceShell {cmdStr}")
        while True:
            try:
                result = setting._ADBDEVICE.shell(cmdStr, timeout=5)
                return result
            except Exception as e:
                logger.error(f"ADB命令失败: {e}")
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
            logger.debug("匹配程度不足阈值.")
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

            logger.info("測試完成")
        except Exception as e:
            logger.error(f"測試失敗: {e}")
    
    
    return run