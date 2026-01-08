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

CC_SKILLS = ["KANTIOS"]
SECRET_AOE_SKILLS = ["SAoLABADIOS","SAoLAERLIK","SAoLAFOROS"]
FULL_AOE_SKILLS = ["LAERLIK", "LAMIGAL","LAZELOS", "LACONES", "LAFOROS","LAHALITO", "LAFERU", "??銝"]
ROW_AOE_SKILLS = ["maerlik", "mahalito", "mamigal","mazelos","maferu", "macones","maforos","蝏?銋"]
PHYSICAL_SKILLS = ["?券?銝??,"鋆銝??,"?典?銝??,"甇餅香餈","tzalik","撅?","蝎曉??餃","???,"?渡","??鋆?,"餈?餈??,"撘箄╲","??銝??,"?拇??","撟餃蔣?拍?"]

ALL_SKILLS = CC_SKILLS + SECRET_AOE_SKILLS + FULL_AOE_SKILLS + ROW_AOE_SKILLS +  PHYSICAL_SKILLS
ALL_SKILLS = [s for s in ALL_SKILLS if s in list(set(ALL_SKILLS))]

SPELLSEKILL_TABLE = [
            ["btn_enable_all","?????,ALL_SKILLS,0,0],
            ["btn_enable_horizontal_aoe","璅芣?AOE",ROW_AOE_SKILLS,0,1],
            ["btn_enable_full_aoe","?其?AOE",FULL_AOE_SKILLS,1,0],
            ["btn_enable_secret_aoe","蝘AOE",SECRET_AOE_SKILLS,1,1],
            ["btn_enable_physical","撘箏???",PHYSICAL_SKILLS,2,0],
            ["btn_enable_cc","蝢支??批",CC_SKILLS,2,1]
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
            ["active_csc_var",              tk.BooleanVar, "ACTIVE_CSC",                 True]
            ]

class FarmConfig:
    for attr_name, var_type, var_config_name, var_default_value in CONFIG_VAR_LIST:
        locals()[var_config_name] = var_default_value
    def __init__(self):
        #### ?Ｘ?蔭?嗡?
        self._FORCESTOPING = None
        self._FINISHINGCALLBACK = None
        self._MSGQUEUE = None
        #### 摨??亙
        self._ADBDEVICE = None
    def __getattr__(self, name):
        # 敶挪?桐?摮???扳嚗??態ttributeError
        raise AttributeError(f"FarmConfig撖寡情瘝⊥?撅?{name}'")
class RuntimeContext:
    #### 蝏恣靽⊥
    _LAPTIME = 0
    _TOTALTIME = 0
    _COUNTERDUNG = 0
    _COUNTERCOMBAT = 0
    _COUNTERCHEST = 0
    _TIME_COMBAT= 0
    _TIME_COMBAT_TOTAL = 0
    _TIME_CHEST = 0
    _TIME_CHEST_TOTAL = 0
    #### ?嗡?銝湔?
    _MEET_CHEST_OR_COMBAT = False
    _ENOUGH_AOE = False
    _AOE_CAST_TIME = 0
    _COMBATSPD = False
    _SUICIDE = False # 敶?銝支葵鈭箸香鈭∠??嗅?multipeopledead), ?冽??葉撠??芣?.
    _MAXRETRYLIMIT = 20
    _ACTIVESPELLSEQUENCE = None
    _SHOULDAPPLYSPELLSEQUENCE = True
    _RECOVERAFTERREZ = False
    _ZOOMWORLDMAP = False
    _CRASHCOUNTER = 0
    _IMPORTANTINFO = ""
    _STEPAFTERRESTART = True
    _RESUMEAVAILABLE = False
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
        # 敶挪?桐?摮???扳嚗??態ttributeError
        raise AttributeError(f"FarmQuest撖寡情瘝⊥?撅?{name}'")
class TargetInfo:
    def __init__(self, target: str, swipeDir: list = None, roi=None, activeSpellSequenceOverride = False):
        self.target = target
        self.swipeDir = swipeDir
        # 瘜冽? roi?⊿??閬arget?? 霂瑚艇?潔?霂oi?冽???
        self.roi = roi
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
            case "撌虫?":
                value = [[100,250,700,1200]]
            case "?喃?":
                value = [[700,250,100,1200]]
            case "?喃?":
                value = [[700,1200,100,250]]
            case "撌虫?":
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
        logger.info(f"甇?璉?亙僎?喲adb...")
        # Windows 蝟餌?雿輻 taskkill ?賭誘
        if os.name == 'nt':
            subprocess.run(
                f"taskkill /f /im adb.exe", 
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False  # 銝??亙隞斗?行???餈??航銝??剁?
            )
            time.sleep(1)
            subprocess.run(
                f"taskkill /f /im HD-Adb.exe", 
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False  # 銝??亙隞斗?行???餈??航銝??剁?
            )
        else:
            subprocess.run(
                f"pkill -f {adb_path}", 
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False
            )
        logger.info(f"撌脣?霂?甇糎db")
    except Exception as e:
        logger.error(f"蝏迫璅⊥??刻?蝔?粹?: {str(e)}")
    
def KillEmulator(setting : FarmConfig):
    emulator_name = os.path.basename(setting._EMUPATH)
    emulator_SVC = "MuMuVMMSVC.exe"
    try:
        logger.info(f"甇?璉?亙僎?喲撌脰?銵?璅⊥??典?靘emulator_name}...")
        # Windows 蝟餌?雿輻 taskkill ?賭誘
        if os.name == 'nt':
            subprocess.run(
                f"taskkill /f /im {emulator_name}", 
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False  # 銝??亙隞斗?行???餈??航銝??剁?
            )
            time.sleep(1)
            subprocess.run(
                f"taskkill /f /im {emulator_SVC}", 
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False  # 銝??亙隞斗?行???餈??航銝??剁?
            )
            time.sleep(1)

        # Unix/Linux 蝟餌?雿輻 pkill ?賭誘
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
        logger.info(f"撌脣?霂?甇Ｘ芋?餈?: {emulator_name}")
    except Exception as e:
        logger.error(f"蝏迫璅⊥??刻?蝔?粹?: {str(e)}")
def StartEmulator(setting):
    hd_player_path = setting._EMUPATH
    if not os.path.exists(hd_player_path):
        logger.error(f"璅⊥??典?函?摨?摮: {hd_player_path}")
        return False

    try:
        logger.info(f"?臬璅⊥??? {hd_player_path}")
        subprocess.Popen(
            hd_player_path, 
            shell=True,
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL,
            cwd=os.path.dirname(hd_player_path))
    except Exception as e:
        logger.error(f"?臬璅⊥??典仃韐? {str(e)}")
        return False
    
    logger.info("蝑?璅⊥??典??..")
    time.sleep(15)
def GetADBPath(setting):
    adb_path = setting._EMUPATH
    adb_path = adb_path.replace("HD-Player.exe", "HD-Adb.exe") # ??
    adb_path = adb_path.replace("MuMuPlayer.exe", "adb.exe") # mumu
    adb_path = adb_path.replace("MuMuNxDevice.exe", "adb.exe") # mumu
    if not os.path.exists(adb_path):
        logger.error(f"adb蝔?摨?摮: {adb_path}")
        return None
    
    return adb_path

def CMDLine(cmd):
    logger.debug(f"cmd line: {cmd}")
    return subprocess.run(cmd,shell=True, capture_output=True, text=True, timeout=10,encoding='utf-8')

def CheckRestartConnectADB(setting: FarmConfig):
    MAXRETRIES = 20

    adb_path = GetADBPath(setting)

    for attempt in range(MAXRETRIES):
        logger.info(f"-----------------------\n撘憪?霂??仟db. 甈⊥:{attempt + 1}/{MAXRETRIES}...")

        if attempt == 3:
            logger.info(f"憭梯揖甈⊥餈?, 撠??喲adb.")
            KillAdb(setting)

            # ?賑銝絲?停?? 雿憒?2甈⊿?亥??臬?霂仃韐? ??停閫血?銝甈∪撩?園???
        
        try:
            logger.info("璉?仟db?...")
            result = CMDLine(f"\"{adb_path}\" devices")
            logger.debug(f"adb?暹餈?(颲靽⊥):{result.stdout}")
            logger.debug(f"adb?暹餈?(?秤靽⊥):{result.stderr}")
            
            if ("daemon not running" in result.stderr) or ("offline" in result.stdout):
                logger.info("adb??芸??\n?臬adb?...")
                CMDLine(f"\"{adb_path}\" kill-server")
                CMDLine(f"\"{adb_path}\" start-server")
                time.sleep(2)

            logger.debug(f"撠?餈?軒db...")
            result = CMDLine(f"\"{adb_path}\" connect 127.0.0.1:{setting._ADBPORT}")
            logger.debug(f"adb?暹餈?(颲靽⊥):{result.stdout}")
            logger.debug(f"adb?暹餈?(?秤靽⊥):{result.stderr}")
            
            if result.returncode == 0 and ("connected" in result.stdout or "already" in result.stdout):
                logger.info("??餈?唳芋?")
                break
            if ("refused" in result.stderr) or ("cannot connect" in result.stdout):
                logger.info("璅⊥??冽餈?嚗?霂??..")
                StartEmulator(setting)
                logger.info("璅⊥???摨砲)?臬摰?.")
                logger.info("撠?餈?唳芋?...")
                result = CMDLine(f"\"{adb_path}\" connect 127.0.0.1:{setting._ADBPORT}")
                if result.returncode == 0 and ("connected" in result.stdout or "already" in result.stdout):
                    logger.info("??餈?唳芋?")
                    break
                logger.info("??餈. 璉?仟db蝡臬.")

            logger.info(f"餈憭梯揖: {result.stderr.strip()}")
            time.sleep(2)
            KillEmulator(setting)
            KillAdb(setting)
            time.sleep(2)
        except Exception as e:
            logger.error(f"?ADB??嗅?? {e}")
            time.sleep(2)
            KillEmulator(setting)
            KillAdb(setting)
            time.sleep(2)
            return None
    else:
        logger.info("颲曉?憭折?霂活?堆?餈憭梯揖")
        return None

    try:
        client = AdbClient(host="127.0.0.1", port=5037)
        devices = client.devices()
        
        # ?交?寥??挽憭?        target_device = f"127.0.0.1:{setting._ADBPORT}"
        for device in devices:
            if device.serial == target_device:
                logger.info(f"???瑕?霈曉?撖寡情: {device.serial}")
                return device
    except Exception as e:
        logger.error(f"?瑕?ADB霈曉??嗅?? {e}")
    
    return None
##################################################################
def CutRoI(screenshot,roi):
    if roi is None:
        return screenshot

    img_height, img_width = screenshot.shape[:2]
    roi_copy = roi.copy()
    roi1_rect = roi_copy.pop(0)  # 蝚砌?銝芰敶?(x, y, width, height)

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

                # 撠?鈭?roi2 銝剔???霈曄蔭銝?
                # (憒?餈???銋??蛹銝roi1銝剖歇蝏◤霈曆蛹0嚗?甇斗?雿?憸???)
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
        # ?遣?辣頝臬?
        jsondict = LoadJson(ResourcePath(QUEST_FILE))
        if setting._FARMTARGET in jsondict:
            data = jsondict[setting._FARMTARGET]
        else:
            logger.error("隞餃?”撌脫??霂琿??唳??券?唬??遙??")
            return
        
        
        # ?遣 Quest 摰?撟嗅‵????        quest = FarmQuest()
        for key, value in data.items():
            if key == '_TARGETINFOLIST':
                setattr(quest, key, [TargetInfo(*args) for args in value])
            elif hasattr(FarmQuest, key):
                setattr(quest, key, value)
            elif key in ["type","questName","questId",'extraConfig']:
                pass
            else:
                logger.info(f"'{key}'撟嗡?摮鈭armQuest銝?")
        
        if 'extraConfig' in data and isinstance(data['extraConfig'], dict):
            for key, value in data['extraConfig'].items():
                if hasattr(setting, key):
                    setattr(setting, key, value)
                else:
                    logger.info(f"Warning: Config has no attribute '{key}' to override")
        return quest
    ##################################################################
    def ResetADBDevice():
        nonlocal setting # 靽格device
        if device := CheckRestartConnectADB(setting):
            setting._ADBDEVICE = device
            logger.info("ADB????臬嚗挽憭歇餈.")
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
                    # 蝥輻?頞?芸???                    logger.warning(f"ADB?賭誘?扯?頞: {cmdStr}")
                    raise TimeoutError(f"ADB?賭誘?肚7}蝘??芸???)
                
                if exception is not None:
                    raise exception
                    
                return result
            except (TimeoutError, RuntimeError, ConnectionResetError, cv2.error) as e:
                logger.warning(f"ADB??憭梯揖 ({type(e).__name__}): {e}")
                logger.info("撠??ADB?...")
                
                ResetADBDevice()
                time.sleep(1)

                continue
            except Exception as e:
                # ????撣貊?交???                logger.error(f"????ADB撘虜: {type(e).__name__}: {e}")
                raise
    
    def Sleep(t=1):
        time.sleep(t)
    def ScreenShot():
        while True:
            exception = None
            result = None
            completed = Event()

            def adb_screencap_thread():
                nonlocal exception, result
                try:
                    result = setting._ADBDEVICE.screencap()
                except Exception as e:
                    exception = e
                finally:
                    completed.set()
            
            thread = Thread(target= adb_screencap_thread)
            thread.daemon = True
            thread.start()

            try:
                if not completed.wait(timeout=5):
                    logger.warning(f"?芸頞")
                    raise TimeoutError(f"?芸頞")
                if exception is not None:
                    raise exception
                
                screenshot = result
                screenshot_np = np.frombuffer(screenshot, dtype=np.uint8)

                if screenshot_np.size == 0:
                    logger.error("?芸?唳銝箇征嚗?)
                    raise RuntimeError("?芸?唳銝箇征")

                image = cv2.imdecode(screenshot_np, cv2.IMREAD_COLOR)

                if image is None:
                    logger.error("OpenCV閫??憭梯揖嚗??格???)
                    raise RuntimeError("?曉?閫??憭梯揖")

                if image.shape != (1600, 900, 3):  # OpenCV?澆?銝?擃? 摰? ??)
                    if image.shape == (900, 1600, 3):
                        logger.error(f"?芸撠箏站?秤: 敶?{image.shape}, 銝箸赤撅?")
                        image = cv2.transpose(image)
                        restartGame(skipScreenShot = True) # 餈??湔?, 隡◤憭?交?圈??舐?exception
                    else:
                        logger.error(f"?芸撠箏站?秤: ??(1600,900,3), 摰?{image.shape}.")
                        raise RuntimeError("?芸撠箏站撘虜")

                #cv2.imwrite('screen.png', image)
                return image
            except Exception as e:
                logger.debug(f"{e}")
                if isinstance(e, (AttributeError,RuntimeError, ConnectionResetError, cv2.error)):
                    logger.info("adb?銝?..")
                    ResetADBDevice()
    def CheckIf(screenImage, shortPathOfTarget, roi = None, outputMatchResult = False):
        template = LoadTemplateImage(shortPathOfTarget)
        screenshot = screenImage.copy()
        threshold = 0.80
        pos = None
        search_area = CutRoI(screenshot, roi)
        try:
            result = cv2.matchTemplate(search_area, template, cv2.TM_CCOEFF_NORMED)
        except Exception as e:
                logger.error(f"{e}")
                logger.info(f"{e}")
                if isinstance(e, (cv2.error)):
                    logger.info(f"cv2撘虜.")
                    # timestamp = datetime.now().strftime("cv2_%Y%m%d_%H%M%S")  # ?澆?嚗?0230825_153045
                    # file_path = os.path.join(LOGS_FOLDER_NAME, f"{timestamp}.png")
                    # cv2.imwrite(file_path, ScreenShot())
                    return None

        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if outputMatchResult:
            cv2.imwrite("origin.png", screenshot)
            cv2.rectangle(screenshot, max_loc, (max_loc[0] + template.shape[1], max_loc[1] + template.shape[0]), (0, 255, 0), 2)
            cv2.imwrite("matched.png", screenshot)

        logger.debug(f"?揣?啁?隡慮shortPathOfTarget}, ?寥?蝔漲:{max_val*100:.2f}%")
        if max_val < threshold:
            logger.debug("?寥?蝔漲銝雲??")
            return None
        if max_val<=0.9:
            logger.debug(f"霅血?: {shortPathOfTarget}???摨西?餈?{threshold*100:.0f}%雿?頞?0%")

        pos=[max_loc[0] + template.shape[1]//2, max_loc[1] + template.shape[0]//2]
        return pos
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
            rectangles.append([x, y, w, h]) # 憭銝斗活, 餈groupRectangles?臭誑靽??????敶?
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
        logger.debug(f"?揣?啁?隡慮shortPathOfTarget}, ?寥?蝔漲:{max_val*100:.2f}%")
        if max_val >= threshold:
            if max_val<=0.9:
                logger.debug(f"霅血?: {shortPathOfTarget}???摨西?餈?80%雿?頞?0%")

            cropped = screenshot[max_loc[1]:max_loc[1]+template.shape[0], max_loc[0]:max_loc[0]+template.shape[1]]
            SIZE = 15 # size of cursor ??撠望餈?憭?            left = (template.shape[1] - SIZE) // 2
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
            logger.debug(f"銝剖??寥?璉??{mean_diff:.2f}")

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

            logger.debug(f"?格??潭?蝝position}, ?寥?蝔漲:{max_val*100:.2f}%")
            if max_val > threshold:
                logger.debug("撌脰噢?唳?瘚???")
                return None 
        return position
    def CheckIf_throughStair(screenImage,targetInfo : TargetInfo):
        stair_img = ["stair_up","stair_down","stair_teleport"]
        screenshot = screenImage
        position = targetInfo.roi
        cropped = screenshot[position[1]-33:position[1]+33, position[0]-33:position[0]+33]
        
        if (targetInfo.target not in stair_img):
            # 撉?璆澆?
            template = LoadTemplateImage(targetInfo.target)
            result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
            threshold = 0.80
            _, max_val, _, _ = cv2.minMaxLoc(result)

            logger.debug(f"?揣璆澆???{targetInfo.target}, ?寥?蝔漲:{max_val*100:.2f}%")
            if max_val > threshold:
                logger.info("璆澆?甇?＆, ?文?銝箏歇??")
                return None
            return position
            
        else: #equal: targetInfo.target IN stair_img
            template = LoadTemplateImage(targetInfo.target)
            result = cv2.matchTemplate(cropped, template, cv2.TM_CCOEFF_NORMED)
            threshold = 0.80
            _, max_val, _, _ = cv2.minMaxLoc(result)

            logger.debug(f"?揣璆潭０{targetInfo.target}, ?寥?蝔漲:{max_val*100:.2f}%")
            if max_val > threshold:
                logger.info("?文?銝箸未璇臬??? 撠??.")
                return position
            return None
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
            logger.info(f"敹怨??芸??? ?喳?撘??{pos}")
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
            logger.info("?撟嗥?颱?\"??\". 雿??唬?蝵?瘜Ｗ.")
            return True
        if pos:=(CheckIf(scn,'retry_blank')):
            Press([pos[0], pos[1]+103])
            logger.info("?撟嗥?颱?\"??\". 雿??唬?蝵?瘜Ｗ.")
            return True
        return False
    def AddImportantInfo(str):
        nonlocal runtimeContext
        if runtimeContext._IMPORTANTINFO == "":
            runtimeContext._IMPORTANTINFO = "????皛?亦???靽⊥??\n"
        time_str = datetime.now().strftime("%Y%m%d-%H%M%S") 
        runtimeContext._IMPORTANTINFO = f"{time_str} {str}\n{runtimeContext._IMPORTANTINFO}"
    ##################################################################
    def FindCoordsOrElseExecuteFallbackAndWait(targetPattern, fallback,waitTime):
        # fallback?臭誑?臬??x,y]??蝚虫葡. 敶蛹摮泵銝脩??嗅? 閫蛹?曄??啣?
        def pressTarget(target):
            if target.lower() == 'return':
                PressReturn()
            elif target.startswith("input swipe"):
                DeviceShell(target)
            else:
                Press(CheckIf(scn, target))
        def checkPattern(scn, pattern):
            if pattern.startswith('combatActive'):
                return StateCombatCheck(scn)
            else:
                return CheckIf(scn,pattern)

        while True:
            for _ in range(runtimeContext._MAXRETRYLIMIT):
                if setting._FORCESTOPING.is_set():
                    return None
                scn = ScreenShot()
                if isinstance(targetPattern, (list, tuple)):
                    for pattern in targetPattern:
                        if p:=checkPattern(scn, pattern):
                            return p
                else:
                    if p:=checkPattern(scn,targetPattern):
                        return p # FindCoords
                # OrElse
                if TryPressRetry(scn):
                    Sleep(1)
                    continue
                if Press(CheckIf_fastForwardOff(scn)):
                    Sleep(1)
                    continue
                
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
                                    logger.debug(f"?秤: ????p}.")
                                    setting._FORCESTOPING.set()
                                    return None
                    else:
                        if isinstance(fallback, str):
                            pressTarget(fallback)
                        else:
                            logger.debug("?秤: ?????")
                            setting._FORCESTOPING.set()
                            return None
                Sleep(waitTime) # and wait

            logger.info(f"{runtimeContext._MAXRETRYLIMIT}甈⊥?曆??扳瓷??啁?targetPattern}, ?撮?⊥香. ?皜豢?.")
            Sleep()
            restartGame()
            return None # restartGame隡??箏?撣??隞亦?亥??one撠梯?鈭?    def restartGame(skipScreenShot = False):
        nonlocal runtimeContext
        runtimeContext._COMBATSPD = False # ?隡?蝵??? ?隞仿?蝵格?霂泵隞乩噶???.
        runtimeContext._MAXRETRYLIMIT = min(50, runtimeContext._MAXRETRYLIMIT + 5) # 瘥活??隡???甈∪?霂活?? 隞仿????紡?渡?????桅?.
        runtimeContext._TIME_CHEST = 0
        runtimeContext._TIME_COMBAT = 0 # ?蛹?鈭? ?隞交?蝛箸???摰拳霈⊥??
        runtimeContext._ZOOMWORLDMAP = False
        runtimeContext._STEPAFTERRESTART = False

        if not skipScreenShot:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")  # ?澆?嚗?0230825_153045
            file_path = os.path.join(LOGS_FOLDER_NAME, f"{timestamp}.png")
            cv2.imwrite(file_path, ScreenShot())
            logger.info(f"???曉歇靽??肚file_path}銝?")
        else:
            runtimeContext._CRASHCOUNTER +=1
            logger.info(f"頝唾?鈭??臬??芸.\n撏拇?霈⊥?? {runtimeContext._CRASHCOUNTER}\n撏拇?霈⊥?刻?餈?甈∪?隡??舀芋?.")
            if runtimeContext._CRASHCOUNTER > 5:
                runtimeContext._CRASHCOUNTER = 0
                KillEmulator(setting)
                CheckRestartConnectADB(setting)

        package_name = "jp.co.drecom.wizardry.daphne"
        mainAct = DeviceShell(f"cmd package resolve-activity --brief {package_name}").strip().split('\n')[-1]
        DeviceShell(f"am force-stop {package_name}")
        Sleep(2)
        logger.info("撌急, ?臬!")
        logger.debug(DeviceShell(f"am start -n {mainAct}"))
        Sleep(10)
        raise RestartSignal()
    class RestartSignal(Exception):
        pass
    def RestartableSequenceExecution(*operations):
        while True:
            try:
                for op in operations:
                    op()
                return
            except RestartSignal:
                logger.info("隞餃餈漲?蔭銝?..")
                continue
    ##################################################################
    def getCursorCoordinates(input, threshold=0.8):
        """?冽?啣?葉?交璅⊥雿蔭"""
        template = LoadTemplateImage('cursor')
        if template is None:
            raise ValueError("???蝸璅⊥?曄?嚗?)

        h, w = template.shape[:2]  # ?瑕?璅⊥撠箏站
        coordinates = []

        # ??摰◇摨粉??暹?隞?        img = input

        # ?扯?璅⊥?寥?
        result = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val > threshold:
            # 餈?銝剖???嚗撖嫣??芸撌虫?閫?
            center_x = max_loc[0] + w // 2
            coordinates = center_x
        else:
            coordinates = None
        return coordinates
    def findWidestRectMid(input):
        crop_area = (30,62),(880,115)
        # 頧祆銝箇摨血
        gray = cv2.cvtColor(input, cv2.COLOR_BGR2GRAY)

        # 鋆?曉? (y1:y2, x1:x2)
        (x1, y1), (x2, y2) = crop_area
        cropped = gray[y1:y2, x1:x2]

        # cv2.imwrite("Matched Result.png",cropped)

        # 餈?蝏?
        column_means = np.mean(cropped, axis=0)
        aver = np.average(column_means)
        binary = column_means > aver

        # 蝳餅??        rect_range = []
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
            # 憭瘜????嗅??Ｘ??霈曄蔭??            p0 = 1.0  # ?寞?唳靚

        # ?瑪?扳?撠?銋???        p_opt, _ = curve_fit(
            triangularWave,
            t_data,
            x_data,
            p0=[p0,0],
            bounds=(0, np.inf)  # 蝖桐??冽?銝箸迤
        )
        estimated_p = p_opt[0]
        logger.debug(f"?冽? p = {estimated_p:.4f}")
        estimated_c = p_opt[1]
        logger.debug(f"???宏 c = {estimated_c:.4f}")

        return p_opt[0], p_opt[1]
    def ChestOpen():
        logger.info("撘憪?賢?蝞??)...")
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
            logger.debug(f"?捏?? {triangularWave(t-t0,p,c)*900}")
            logger.debug(f"韏瑕??? {x}")
            logger.debug(f"?格??? {target}")

            if x!=None:
                waittime = 0
                t_mod = np.mod(t-c, p)
                if t_mod<p/2:
                    # 甇??蝘餃, ?
                    waittime = ((900-x)+(900-target))/spd
                    logger.debug("???喳??椰")
                else:
                    waittime = (x+target)/spd
                    logger.debug("??撌血??")

                if waittime > 0.270 :
                    logger.debug(f"憸恣蝑? {waittime}")
                    Sleep(waittime-0.270)
                    DeviceShell(f"input tap 527 920") # 餈??etry??, 銋?to_title+retry??.
                    Sleep(3)
                else:
                    logger.debug(f"蝑??園餈: {waittime}")

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

    def DungeonCompletionCounter():
        nonlocal runtimeContext
        if runtimeContext._LAPTIME!= 0:
            runtimeContext._TOTALTIME = runtimeContext._TOTALTIME + time.time() - runtimeContext._LAPTIME
            summary_text = f"撌脣??runtimeContext._COUNTERDUNG}甈﹏"{setting._FARMTARGET_TEXT}\"?唬???\n?餉恣{round(runtimeContext._TOTALTIME,2)}蝘?銝活?冽:{round(time.time()-runtimeContext._LAPTIME,2)}蝘?\n"
            if runtimeContext._COUNTERCHEST > 0:
                summary_text += f"蝞勗???{round(runtimeContext._TOTALTIME/runtimeContext._COUNTERCHEST,2)}蝘?蝞?\n蝝航恣撘蝞惋runtimeContext._COUNTERCHEST}甈?撘蝞勗像?{round(runtimeContext._TIME_CHEST_TOTAL/runtimeContext._COUNTERCHEST,2)}蝘?\n"
            if runtimeContext._COUNTERCOMBAT > 0:
                summary_text += f"蝝航恣??{runtimeContext._COUNTERCOMBAT}甈???撟喳??冽{round(runtimeContext._TIME_COMBAT_TOTAL/runtimeContext._COUNTERCOMBAT,2)}蝘?"
            logger.info(f"{runtimeContext._IMPORTANTINFO}{summary_text}",extra={"summary": True})
        runtimeContext._LAPTIME = time.time()
        runtimeContext._COUNTERDUNG+=1

    def TeleportFromCityToWorldLocation(target, swipe):
        nonlocal runtimeContext
        FindCoordsOrElseExecuteFallbackAndWait(['intoWorldMap','dungFlag','worldmapflag','openworldmap'],['closePartyInfo','closePartyInfo_fortress',[550,1]],1)
        
        if CheckIf(scn:=ScreenShot(), 'dungflag'):
            # 憒?撌脩??典?祇?鈭??湔蝏?.
            # ?蛹霂亙?圈?霈曆??臭???撘憪?.
            return
        
        if CheckIf(scn, 'openworldmap'):
            # 憒?撌脩?餈鈭?蝒? ?湔蝏?.
            # ?蛹餈????摰拳?嗅??撠?????
            return
        
        if Press(CheckIf(scn,'intoWorldMap')):
            # 憒??典?撣? 撠?餈銝??啣
            Sleep(0.5)
            FindCoordsOrElseExecuteFallbackAndWait('worldmapflag','intoWorldMap',1)
        elif CheckIf(scn,'worldmapflag'):
            # 憒??其???? 銝?甇?
            pass

        # 敺銝?舐＆靽??啣?賜?閫?worldmapflag', 撟嗅?霂?閫?target'
        Sleep(0.5)
        if not runtimeContext._ZOOMWORLDMAP:
            for _ in range(3):
                Press([100,1500])
                Sleep(0.5)
            Press([250,1500])
            runtimeContext._ZOOMWORLDMAP = True
        pos = FindCoordsOrElseExecuteFallbackAndWait(target,[swipe,[550,1]],1)

        # ?啣撌脩?蝖桐?鈭隞亦?閫arget, ???蝖桐??臭誑?孵??
        Sleep(1)
        Press(pos)
        Sleep(1)
        FindCoordsOrElseExecuteFallbackAndWait(['Inn','openworldmap','dungFlag'],[target,[550,1]],1)
        
    def CursedWheelTimeLeap(tar=None, CSC_symbol=None,CSC_setting = None):
        # CSC_symbol: ?臬撘?臬??? 憒?撘?臬??? 撠餈葵雿蛹?臬?孵?ui???交?霂?        # CSC_setting: 暺恕隡??銝??遙?? 餈葵?”銝剖摮??舀閬?撘????
        # ?嗡葉?GB?其?蝻拇憸蝏游漲, 隞亙????怎??舫???
        if setting.ACTIVE_CSC == False:
            logger.info(f"?蛹?Ｘ霈曄蔭, 頝唾?鈭??游???")
            CSC_symbol = None

        target = "GhostsOfYore"
        if tar != None:
            target = tar
        if setting._ACTIVE_TRIUMPH:
            target = "Triumph"

        logger.info(f"撘憪?渲歲頝? ?祆活頝唾??格?:{target}")

        # 靚?∠隞交?啗歲頝??        Press(FindCoordsOrElseExecuteFallbackAndWait('cursedWheel',['ruins',[1,1]],1))
        Press(FindCoordsOrElseExecuteFallbackAndWait('cursedwheel_impregnableFortress',['cursedWheelTapRight','cursedWheel',[1,1]],1))
        if not Press(CheckIf(ScreenShot(),target)):
            DeviceShell(f"input swipe 450 1200 450 200")
            Sleep(2)
            Press(FindCoordsOrElseExecuteFallbackAndWait(target,'input swipe 50 1200 50 1300',1))
        Sleep(1)

        # 頝唾???霂??游???        while CheckIf(ScreenShot(), 'leap'):
            if CSC_symbol != None:
                FindCoordsOrElseExecuteFallbackAndWait(CSC_symbol,'CSC',1)
                last_scn = CutRoI(ScreenShot(), [[77,349,757,1068]])
                # ??剜?????                while 1:
                    Press(CheckIf(WrapImage(ScreenShot(),2,0,0),'didnottakethequest'))
                    DeviceShell(f"input swipe 150 500 150 400")
                    Sleep(1)
                    scn = CutRoI(ScreenShot(), [[77,349,757,1068]])
                    logger.debug(f"??: 皛???芸霂臬榆={cv2.absdiff(scn, last_scn).mean()/255:.6f}")
                    if cv2.absdiff(scn, last_scn).mean()/255 < 0.006:
                        break
                    else:
                        last_scn = scn
                # ?嗅?靚瘥葵??
                if CSC_setting!=None:
                    last_scn = CutRoI(ScreenShot(), [[77,349,757,1068]])
                    while 1:
                        for option, r, g, b in CSC_setting:
                            Press(CheckIf(WrapImage(ScreenShot(),r,g,b),option))
                            Sleep(1)
                        DeviceShell(f"input swipe 150 400 150 500")
                        Sleep(1)
                        scn = CutRoI(ScreenShot(), [[77,349,757,1068]])
                        logger.debug(f"??: 皛???芸霂臬榆={cv2.absdiff(scn, last_scn).mean()/255:.6f}")
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
        runtimeContext._SUICIDE = False # 甇颱? ?芣??? 霈曄蔭銝榻alse
        runtimeContext._SHOULDAPPLYSPELLSEQUENCE = True # 甇颱? 摨?憭望?, 摨??蔭摨?.
        runtimeContext._RECOVERAFTERREZ = True
        if reason == 'chest':
            runtimeContext._COUNTERCHEST -=1
        else:
            runtimeContext._COUNTERCOMBAT -=1
        logger.info("敹怠翰霂瑁絲.")
        AddImportantInfo("?Ｗ甇颱?雿瓷甇?")
        # logger.info("REZ.")
        Press([450,750])
        Sleep(10)
    def IdentifyState():
        nonlocal setting # 靽格??
        counter = 0
        while 1:
            screen = ScreenShot()
            logger.info(f'?嗆璉?乩葉...(蝚洌counter+1}甈?')

            if setting._FORCESTOPING.is_set():
                return State.Quit, DungeonState.Quit, screen

            if TryPressRetry(screen):
                    Sleep(2)

            identifyConfig = [
                ('dungFlag',      DungeonState.Dungeon),
                ('chestFlag',     DungeonState.Chest),
                ('whowillopenit', DungeonState.Chest),
                ('mapFlag',       DungeonState.Map),
                ]
            for pattern, state in identifyConfig:
                if CheckIf(screen, pattern):
                    return State.Dungeon, state, screen
                
            if StateCombatCheck(screen):
                return State.Dungeon, DungeonState.Combat, screen

            if CheckIf(screen,'someonedead'):
                AddImportantInfo("隞賑瘣颱?,瘣颱?!")
                for _ in range(5):
                    Press([400+random.randint(0,100),750+random.randint(0,100)])
                    Sleep(1)

            if Press(CheckIf(screen, "returnText")):
                Sleep(2)
                return IdentifyState()

            if CheckIf(screen,"returntoTown"):
                if setting._ACTIVE_REST and runtimeContext._MEET_CHEST_OR_COMBAT:
                    FindCoordsOrElseExecuteFallbackAndWait('Inn',['return',[1,1]],1)
                    return State.Inn,DungeonState.Quit, screen
                else:
                    logger.info("?曹?瘝⊥??隞颱?摰拳???遙雿??? 頝唾???.")
                    DungeonCompletionCounter()
                    return State.EoT,DungeonState.Quit,screen

            if pos:=(CheckIf(screen,"openworldmap")):
                if setting._ACTIVE_REST and runtimeContext._MEET_CHEST_OR_COMBAT:
                    Press(pos)
                    return IdentifyState()
                else:
                    logger.info("?曹?瘝⊥??隞颱?摰拳???遙雿??? 頝唾???.")
                    DungeonCompletionCounter()
                    return State.EoT,DungeonState.Quit,screen

            if CheckIf(screen,"RoyalCityLuknalia") or CheckIf(screen,"DHI"):
                FindCoordsOrElseExecuteFallbackAndWait(['Inn','dungFlag'],['RoyalCityLuknalia','DHI',[1,1]],1)
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
                logger.info("?絲?仿??唬?銝鈭?憭芸粉撣貊??...")
                if (CheckIf(screen,'RiseAgain')):
                    RiseAgainReset(reason = 'combat')
                    return IdentifyState()
                if CheckIf(screen, 'worldmapflag'):
                    for _ in range(3):
                        Press([100,1500])
                        Sleep(0.5)
                    Press([250,1500])
                    # 餈?銝?閬ontinue?? ?湔蝏抒賒餈?撠梯?
                if Press(CheckIf(screen, 'sandman_recover')):
                    return IdentifyState()
                if (CheckIf(screen,'cursedWheel_timeLeap')):
                    setting._MSGQUEUE.put(('turn_to_7000G',""))
                    raise SystemExit
                if CheckIf(screen,'ambush') or CheckIf(screen,'ignore'):
                    if int(setting._KARMAADJUST) == 0:
                        Press(CheckIf(screen,'ambush'))
                        new_str = "+2"
                    elif setting._KARMAADJUST.startswith('-'):
                        Press(CheckIf(screen,'ambush'))
                        num = int(setting._KARMAADJUST)
                        num = num + 2
                        new_str = f"{num}"
                    else:
                        Press(CheckIf(screen,'ignore'))
                        num = int(setting._KARMAADJUST)
                        num = num - 1
                        new_str = f"+{num}"

                    logger.info(f"?喳?餈???潸??? ?拐?甈⊥:{new_str}")
                    AddImportantInfo(f"?啁??:{new_str}")
                    setting._KARMAADJUST = new_str
                    SetOneVarInConfig("_KARMAADJUST",setting._KARMAADJUST)
                    Sleep(2)

                for op in DIALOG_OPTION_IMAGE_LIST:
                    if Press(CheckIf(screen, 'dialogueChoices/'+op)):
                        Sleep(2)
                        if op == 'adventurersbones':
                            AddImportantInfo("韐凋僭鈭爸憭?")
                        if op == 'halfBone':
                            AddImportantInfo("韐凋僭鈭偶瘝?")
                        return IdentifyState()
                
                if (CheckIf(screen,'multipeopledead')):
                    runtimeContext._SUICIDE = True # ??撠??芣?
                    logger.info("甇颱?憟賢?銝? ?典")
                    # logger.info("Corpses strew the screen")
                    Press(CheckIf(screen,'skull'))
                    Sleep(2)
                if Press(CheckIf(screen,'startdownload')):
                    logger.info("蝖株恕, 銝蝸, 蝖株恕.")
                    # logger.info("")
                    Sleep(2)
                if Press(CheckIf(screen,'totitle')):
                    logger.info("蝵???霅行! 蝵???霅行! 餈???, ??, 餈???!")
                    return IdentifyState()
                PressReturn()
                Sleep(0.5)
                PressReturn()
            if counter>15:
                black = LoadTemplateImage("blackScreen")
                mean_diff = cv2.absdiff(black, screen).mean()/255
                if mean_diff<0.02:
                    logger.info(f"霅血?: 皜豢??駁?踵?游?鈭?撅葉, ?喳??({25-counter})")
            if counter>= 25:
                logger.info("?絲?仿??唬?銝鈭??粉撣貊??...?皜豢?.")
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
            raise ValueError("GameFrozenCheck鋡思??乩?銝銝芰征??")
        logger.info("?⊥香璉瘚??)
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
            logger.info(f"?⊥香璉瘚: {time.time()-t:.5f}蝘?)
            logger.info(f"?⊥香璉瘚??? {totalDiff:.5f}")
            if totalDiff<=0.15:
                return queue, True
        return queue, False
    def StateCombatCheck(screen):
        combatActiveFlag = [
            'combatActive',
            'combatActive_2',
            'combatActive_3',
            'combatActive_4',
            ]
        for combat in combatActiveFlag:
            if pos:=CheckIf(screen,combat, [[0,0,150,80]]):
                return pos
        return None
    def StateInn():
        if not setting._ACTIVE_ROYALSUITE_REST:
            FindCoordsOrElseExecuteFallbackAndWait('OK',['Inn','Stay','Economy',[1,1]],2)
        else:
            FindCoordsOrElseExecuteFallbackAndWait('OK',['Inn','Stay','royalsuite',[1,1]],2)
        FindCoordsOrElseExecuteFallbackAndWait('Stay',['OK',[299,1464]],2)
        PressReturn()
    def StateEoT():
        runtimeContext._RESUMEAVAILABLE = False
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
    def StateCombat():
        def doubleConfirmCastSpell():
            is_success_aoe = False
            Sleep(1)
            scn = ScreenShot()
            if Press(CheckIf(scn,'OK')):
                is_success_aoe = True
                Sleep(2)
                scn = ScreenShot()
                if CheckIf(scn,'notenoughsp') or CheckIf(scn,'notenoughmp'):
                    Press(CheckIf(scn,'notenough_close'))
                    Press(CheckIf(ScreenShot(),'spellskill/lv1'))
                    Press(CheckIf(scn,'OK'))
                    Sleep(1)
            elif pos:=(CheckIf(scn,'next')):
                Press([pos[0]-15+random.randint(0,30),pos[1]+150+random.randint(0,30)])
                Sleep(1)
                scn = ScreenShot()
                if CheckIf(scn,'notenoughsp') or CheckIf(scn,'notenoughmp'):
                    Press(CheckIf(scn,'notenough_close'))
                    Press(CheckIf(ScreenShot(),'spellskill/lv1'))
                    Press([pos[0]-15+random.randint(0,30),pos[1]+150+random.randint(0,30)])
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
        if runtimeContext._TIME_COMBAT==0:
            runtimeContext._TIME_COMBAT = time.time()

        screen = ScreenShot()
        if not runtimeContext._COMBATSPD:
            if Press(CheckIf(screen,'combatSpd')):
                runtimeContext._COMBATSPD = True
                Sleep(1)

        spellsequence = runtimeContext._ACTIVESPELLSEQUENCE
        if spellsequence != None:
            logger.info(f"敶??賣?摨?:{spellsequence}")
            for k in spellsequence.keys():
                if CheckIf(screen,'spellskill/'+ k):
                    targetSpell = 'spellskill/'+ spellsequence[k][0]
                    if not CheckIf(screen, targetSpell):
                        logger.error("?秤:?賣?摨??銝?函????)
                        Press([850,1100])
                        Sleep(0.5)
                        Press([850,1100])
                        Sleep(3)
                        return
                    
                    logger.info(f"雿輻??緹targetSpell}, ?賣?摨??孵?: {k}:{spellsequence[k]}")
                    if len(spellsequence[k])!=1:
                        spellsequence[k].pop(0)
                    Press(CheckIf(screen,targetSpell))
                    if targetSpell != 'spellskill/' + 'defend':
                        doubleConfirmCastSpell()

                    return

        if (setting._SYSTEMAUTOCOMBAT) or (runtimeContext._ENOUGH_AOE and setting._AUTO_AFTER_AOE):
            Press(CheckIf(WrapImage(screen,0.1,0.3,1),'combatAuto',[[700,1000,200,200]]))
            Press(CheckIf(screen,'combatAuto_2',[[700,1000,200,200]]))
            Sleep(5)
            return

        if not CheckIf(screen,'flee'):
            return
        if runtimeContext._SUICIDE:
            Press(CheckIf(screen,'spellskill/'+'defend'))
        else:
            castSpellSkill = False
            castAndPressOK = False
            for skillspell in setting._SPELLSKILLCONFIG:
                if runtimeContext._ENOUGH_AOE and ((skillspell in SECRET_AOE_SKILLS) or (skillspell in FULL_AOE_SKILLS)):
                    #logger.info(f"?祆活??撌脩???其?aoe, ?曹??Ｘ?蔭, 銝?銵憭???賡???")
                    continue
                elif Press((CheckIf(screen, 'spellskill/'+skillspell))):
                    logger.info(f"雿輻???{skillspell}")
                    castAndPressOK = doubleConfirmCastSpell()
                    castSpellSkill = True
                    if castAndPressOK and setting._AOE_ONCE and ((skillspell in SECRET_AOE_SKILLS) or (skillspell in FULL_AOE_SKILLS)):
                        runtimeContext._AOE_CAST_TIME += 1
                        if runtimeContext._AOE_CAST_TIME >= setting._AOE_TIME:
                            runtimeContext._ENOUGH_AOE = True
                            runtimeContext._AOE_CAST_TIME = 0
                        logger.info(f"撌脩??鈭?甈∪雿oe.")
                    break
            if not castSpellSkill:
                Press(CheckIf(ScreenShot(),'combatClose'))
                Press([850,1100])
                Sleep(0.5)
                Press([850,1100])
                Sleep(3)
    def StateMap_FindSwipeClick(targetInfo : TargetInfo):
        ### return = None: 閫蛹瘝⊥?? 憭抒漲蝑??格??寧???
        ### return = [x,y]: 閫蛹?曉, [x,y]?臬???
        target = targetInfo.target
        roi = targetInfo.roi
        for i in range(len(targetInfo.swipeDir)):
            scn = ScreenShot()
            if not CheckIf(scn,'mapFlag'):
                raise KeyError("?啣銝??")

            swipeDir = targetInfo.swipeDir[i]
            if swipeDir!=None:
                logger.debug(f"??啣:{swipeDir[0]} {swipeDir[1]} {swipeDir[2]} {swipeDir[3]}")
                DeviceShell(f"input swipe {swipeDir[0]} {swipeDir[1]} {swipeDir[2]} {swipeDir[3]}")
                Sleep(2)
                scn = ScreenShot()
            
            targetPos = None
            if target == 'position':
                logger.info(f"敶??格?: ?啁{roi}")
                targetPos = CheckIf_ReachPosition(scn,targetInfo)
            elif target.startswith("stair"):
                logger.info(f"敶??格?: 璆潭０{target}")
                targetPos = CheckIf_throughStair(scn,targetInfo)
            else:
                logger.info(f"?揣{target}...")
                if targetPos:=CheckIf(scn,target,roi):
                    logger.info(f'?曉鈭?{target}! {targetPos}')
                    if (target == 'chest') and (swipeDir!= None):
                        logger.debug(f"摰拳?剖??? ?啣:{setting._FARMTARGET} ?孵?:{swipeDir} 雿蔭:{targetPos}")
                    if not roi:
                        # 憒?瘝⊥???roi ?賑雿輻鈭活蝖株恕
                        # logger.debug(f"?: {targetPos[0]},{targetPos[1]} -> 450,800")
                        # DeviceShell(f"input swipe {targetPos[0]} {targetPos[1]} {(targetPos[0]+450)//2} {(targetPos[1]+800)//2}")
                        # 鈭活蝖株恕銋??鈭?憭芸捆?圻?ug
                        Sleep(2)
                        Press([1,1255])
                        targetPos = CheckIf(ScreenShot(),target,roi)
                    break
        return targetPos
    def StateMoving_CheckFrozen():
        runtimeContext._RESUMEAVAILABLE = True
        lastscreen = None
        dungState = None
        logger.info("?Ｗ?? 蝘餃.")
        while 1:
            Sleep(3)
            _, dungState,screen = IdentifyState()
            if dungState == DungeonState.Map:
                logger.info(f"撘憪宏?典仃韐? 銝????亙??Ｗ??")
                FindCoordsOrElseExecuteFallbackAndWait("dungFlag",[[280,1433],[1,1]],1)
                dungState = dungState.Dungeon
                break
            if dungState != DungeonState.Dungeon:
                logger.info(f"撌脤?箇宏?函?? 敶??嗆? {dungState}.")
                break
            if lastscreen is not None:
                gray1 = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                gray2 = cv2.cvtColor(lastscreen, cv2.COLOR_BGR2GRAY)
                mean_diff = cv2.absdiff(gray1, gray2).mean()/255
                logger.debug(f"蝘餃?迫璉??{mean_diff:.2f}")
                if mean_diff < 0.1:
                    dungState = None
                    logger.info("撌脤?箇宏?函?? 餈??嗆???..")
                    break
            lastscreen = screen
        return dungState
    def StateSearch(waitTimer, targetInfoList : list[TargetInfo]):
        normalPlace = ['harken','chest','leaveDung','position']
        targetInfo = targetInfoList[0]
        target = targetInfo.target
        # ?啣撌脩???.
        map = ScreenShot()
        if not CheckIf(map,'mapFlag'):
                return None,targetInfoList # ??鈭?霂?
        try:
            searchResult = StateMap_FindSwipeClick(targetInfo)
        except KeyError as e:
            logger.info(f"?秤: {e}") # 銝?祆霂渲??隡????啣銝??
            return None, targetInfoList
    
        if not CheckIf(map,'mapFlag'):
                return None,targetInfoList # ??鈭?霂? 摨砲?航???鈭?
        if searchResult == None:
            if target == 'chest':
                # 蝏?, 撘孵.
                targetInfoList.pop(0)
                logger.info(f"瘝⊥??曉摰拳.\n?迫璉蝝Ｗ?蝞?")
            elif (target == 'position' or target.startswith('stair')):
                # 蝏?, 撘孵.
                targetInfoList.pop(0)
                logger.info(f"撌脩??菔噢?格??啁??未撅?")
            else:
                # 餈??嗅?隞祈恕銝箇?甇?仃韐乩?. ?隞乩?撘孵.
                # 敶, ?游末??瘜隡inish??()
                logger.info(f"?芣?啁?target}.")

            return DungeonState.Map,  targetInfoList
        else:
            if target in normalPlace or target.endswith("_quit") or target.startswith('stair'):
                Press(searchResult)
                Press([136,1431]) # automove
                return StateMoving_CheckFrozen(),targetInfoList
            else:
                if (CheckIf_FocusCursor(ScreenShot(),target)): #瘜冽? 餈???鈭活蝖株恕 ?賑?臭誑??格??啁 ???舀?葉???                    logger.info("蝏?撖寞?銝剖??箏?, 蝖株恕瘝⊥??菔噢.")
                    Press(searchResult)
                    Press([136,1431]) # automove
                    return StateMoving_CheckFrozen(),targetInfoList
                else:
                    if setting._DUNGWAITTIMEOUT == 0:
                        logger.info("蝏?撖寞?銝剖??箏?, ?斗銝箸颲曄???")
                        logger.info("??蝑?, 敶??格?撌脣???")
                        targetInfoList.pop(0)
                        return DungeonState.Map,  targetInfoList
                    else:
                        logger.info("蝏?撖寞?銝剖??箏?, ?斗銝箸颲曄???")
                        logger.info('撘憪?敺?..蝑?...')
                        PressReturn()
                        Sleep(0.5)
                        PressReturn()
                        while 1:
                            if setting._DUNGWAITTIMEOUT-time.time()+waitTimer<0:
                                logger.info("蝑?憭?鈭? ?格??啁摰?.")
                                targetInfoList.pop(0)
                                Sleep(1)
                                Press([777,150])
                                return None,  targetInfoList
                            logger.info(f'餈?閬?敺setting._DUNGWAITTIMEOUT-time.time()+waitTimer}蝘?')
                            if StateCombatCheck(ScreenShot()):
                                return DungeonState.Combat,targetInfoList
        return DungeonState.Map,  targetInfoList
    def StateChest():
        nonlocal runtimeContext
        availableChar = [0, 1, 2, 3, 4, 5]
        disarm = [515,934]  # 527,920隡??唳?香鈭?450 1000隡??唳???445,1050餈隡??唳???        haveBeenTried = False

        if runtimeContext._TIME_CHEST==0:
            runtimeContext._TIME_CHEST = time.time()

        while 1:
            FindCoordsOrElseExecuteFallbackAndWait(
                ['dungFlag','combatActive','chestOpening','whowillopenit','RiseAgain'],
                [[1,1],[1,1],'chestFlag'],
                1)
            scn = ScreenShot()

            if CheckIf(scn,'whowillopenit'):
                while 1:
                    pointSomeone = setting._WHOWILLOPENIT - 1
                    if (pointSomeone != -1) and (pointSomeone in availableChar) and (not haveBeenTried):
                        whowillopenit = pointSomeone # 憒???鈭?銝芾??脣僎銝砲閫?舐撟嗡?瘝∪?霂?, 雿輻摰?                    else:
                        whowillopenit = random.choice(availableChar) # ?血?隞?銵券????銝?                    pos = [258+(whowillopenit%3)*258, 1161+((whowillopenit)//3)%2*184]
                    # logger.info(f"{availableChar},{pos}")
                    if CheckIf(scn,'chestfear',[[pos[0]-125,pos[1]-82,250,164]]):
                        if whowillopenit in availableChar:
                            availableChar.remove(whowillopenit) # 憒??鈭??? ?餈葵閫.
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
                    ['dungFlag','combatActive','chestFlag','RiseAgain'], # 憒?餈葵fallback?鈭? ??蝞勗?隡?交?憭? ?箸?蝞勗?隡chestFlag
                    [disarm,disarm,disarm,disarm,disarm,disarm,disarm,disarm],
                    1)
            
            if CheckIf(scn,'RiseAgain'):
                RiseAgainReset(reason = 'chest')
                return None
            if CheckIf(scn,'dungFlag'):
                return DungeonState.Dungeon
            if StateCombatCheck(scn):
                return DungeonState.Combat
            
            TryPressRetry(scn)
    def StateDungeon(targetInfoList : list[TargetInfo]):
        gameFrozen_none = []
        gameFrozen_map = 0
        dungState = None
        shouldRecover = False
        waitTimer = time.time()
        needRecoverBecauseCombat = False
        needRecoverBecauseChest = False
        
        nonlocal runtimeContext
        runtimeContext._SHOULDAPPLYSPELLSEQUENCE = True
        while 1:
            logger.info("----------------------")
            if setting._FORCESTOPING.is_set():
                logger.info("?喳??迫?...")
                dungState = DungeonState.Quit
            logger.info(f"敶??嗆??唬???: {dungState}")

            match dungState:
                case None:
                    s, dungState,scn = IdentifyState()
                    if (s == State.Inn) or (dungState == DungeonState.Quit):
                        break
                    gameFrozen_none, result = GameFrozenCheck(gameFrozen_none,scn)
                    if result:
                        logger.info("?曹??駁?⊥香, ?究tate:None銝剝???")
                        restartGame()
                    MAXTIMEOUT = 400
                    if (runtimeContext._TIME_CHEST != 0 ) and (time.time()-runtimeContext._TIME_CHEST > MAXTIMEOUT):
                        logger.info("?曹?摰拳?冽餈?, ?究tate:None銝剝???")
                        restartGame()
                    if (runtimeContext._TIME_COMBAT != 0) and (time.time()-runtimeContext._TIME_COMBAT > MAXTIMEOUT):
                        logger.info("?曹????冽餈?, ?究tate:None銝剝???")
                        restartGame()
                case DungeonState.Quit:
                    break
                case DungeonState.Dungeon:
                    Press([1,1])
                    ########### COMBAT RESET
                    # ??蝏?鈭? ?賑撠?鈭挽蝵桀?雿?                    if setting._AOE_ONCE:
                        runtimeContext._ENOUGH_AOE = False
                        runtimeContext._AOE_CAST_TIME = 0
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
                        logger.info(f"蝎蝏恣: 摰拳{spend_on_chest:.2f}蝘? ??{spend_on_combat:.2f}蝘?")
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
                        logger.info("餈?撘?臬?蝞勗??憭?")
                        runtimeContext._COUNTERCHEST+=1
                        needRecoverBecauseChest = False
                        runtimeContext._MEET_CHEST_OR_COMBAT = True
                        if not setting._SKIPCHESTRECOVER:
                            logger.info("?曹??Ｘ?蔭, 餈?撘?臬?蝞勗??Ｗ?.")
                            shouldRecover = True
                        else:
                            logger.info("?曹??Ｘ?蔭, 頝唾?鈭??臬?蝞勗??Ｗ?.")
                    if needRecoverBecauseCombat:
                        runtimeContext._COUNTERCOMBAT+=1
                        needRecoverBecauseCombat = False
                        runtimeContext._MEET_CHEST_OR_COMBAT = True
                        if (not setting._SKIPCOMBATRECOVER):
                            logger.info("?曹??Ｘ?蔭, 餈????Ｗ?.")
                            shouldRecover = True
                        else:
                            logger.info("?曹??Ｘ?蔭, 頝唾?鈭????Ｗ?.")
                    if runtimeContext._RECOVERAFTERREZ == True:
                        shouldRecover = True
                        runtimeContext._RECOVERAFTERREZ = False
                    if shouldRecover:
                        Press([1,1])
                        counter_trychar = -1
                        while 1:
                            counter_trychar += 1
                            scn=ScreenShot()
                            if (CheckIf(scn,'dungflag') and not CheckIf(scn,'mapFlag')) and (counter_trychar <=30):
                                Press([36+(counter_trychar%3)*286,1425])
                                Sleep(1)
                                continue
                            elif CheckIf(scn,'trait'):
                                if CheckIf(scn,'story', [[676,800,220,108]]):
                                    Press([725,850])
                                else:
                                    Press([830,850])
                                Sleep(1)
                                FindCoordsOrElseExecuteFallbackAndWait(['recover','combatActive',],[833,843],1)
                                if CheckIf(ScreenShot(),'recover'):
                                    Sleep(1.5)
                                    Press([600,1200])
                                    Sleep(1)
                                    for _ in range(5):
                                        t = time.time()
                                        PressReturn()
                                        if time.time()-t<0.3:
                                            Sleep(0.3-(time.time()-t))
                                    shouldRecover = False
                                    break
                            else:
                                logger.info("?芸??撘虜, 銝剜迫?祆活??.")
                                break
                    ########### ?脫迫頧砍?
                    if not runtimeContext._STEPAFTERRESTART:
                        Press([27,950])
                        Sleep(1)
                        Press([853,950])

                        runtimeContext._STEPAFTERRESTART = True
                    ########### 撠?resume
                    if runtimeContext._RESUMEAVAILABLE and Press(CheckIf(ScreenShot(),'resume')):
                        logger.info("resume?舐. 雿輻resume.")
                        lastscreen = ScreenShot()
                        for counter in range(30):
                            Sleep(3)
                            _, dungState,screen = IdentifyState()
                            if dungState != DungeonState.Dungeon:
                                logger.info(f"撌脤?箇宏?函?? 敶??嗆蛹{dungState}.")
                                break
                            elif lastscreen is not None:
                                gray1 = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                                gray2 = cv2.cvtColor(lastscreen, cv2.COLOR_BGR2GRAY)
                                mean_diff = cv2.absdiff(gray1, gray2).mean()/255
                                logger.debug(f"蝘餃?迫璉??{mean_diff:.2f}")
                                if mean_diff < 0.1:
                                    runtimeContext._RESUMEAVAILABLE = False
                                    logger.info(f"撌脤?箇宏?函?? 敶??嗆蛹{dungState}.")
                                    break
                                lastscreen = screen
                            if counter == 29:
                                # 頧砍??航 ?.
                                restartGame()
                    ########### 憒?resume憭梯揖銝蛹?唬???                    if dungState == DungeonState.Dungeon:
                        dungState = DungeonState.Map
                case DungeonState.Map:
                    ########### ?蔭?賣?摨? - 暺恕??蝚砌?甈????臬?摨??湔摨摨?
                    if runtimeContext._SHOULDAPPLYSPELLSEQUENCE: 
                        runtimeContext._SHOULDAPPLYSPELLSEQUENCE = False
                        if targetInfoList[0].activeSpellSequenceOverride:
                            logger.info("?蛹???? 憭鈭瘜???")
                            runtimeContext._ACTIVESPELLSEQUENCE = copy.deepcopy(quest._SPELLSEQUENCE)

                    ########### 銝?撘?啣, ?扯??芸摰拳
                    if targetInfoList[0] and (targetInfoList[0].target == "chest_auto"):
                        lastscreen = ScreenShot()
                        if not Press(CheckIf(lastscreen,"chest_auto",[[710,250,180,180]])):
                            Press(CheckIf(lastscreen,"mapflag"))
                            Press([664,329])
                            Sleep(1)
                            lastscreen = ScreenShot()
                            if not Press(CheckIf(lastscreen,"chest_auto",[[710,250,180,180]])):
                                dungState = None
                                continue
                        Sleep(1.5)
                        _, dungState,screen = IdentifyState()
                        gray1 = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                        gray2 = cv2.cvtColor(lastscreen, cv2.COLOR_BGR2GRAY)
                        mean_diff = cv2.absdiff(gray1, gray2).mean()/255
                        if mean_diff < 0.05:
                            logger.info(f"?迫蝘餃. 霂臬榆:{mean_diff}. 敶??嗆蛹{dungState}.")
                            if dungState == DungeonState.Dungeon:
                                targetInfoList.pop(0)
                                logger.info(f"??箏?蝞望?蝝?")
                        else:
                            lastscreen = screen
                            while 1:
                                Sleep(3)
                                _, dungState,screen = IdentifyState()
                                if dungState != DungeonState.Dungeon:
                                    logger.info(f"撌脤?箇宏?函?? 敶??嗆蛹{dungState}.")
                                    break
                                elif lastscreen is not None:
                                    gray1 = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                                    gray2 = cv2.cvtColor(lastscreen, cv2.COLOR_BGR2GRAY)
                                    mean_diff = cv2.absdiff(gray1, gray2).mean()/255
                                    logger.debug(f"蝘餃?迫璉??{mean_diff:.2f}")
                                    if mean_diff < 0.05:
                                        logger.info(f"?迫蝘餃. 霂臬榆:{mean_diff}. 敶??嗆蛹{dungState}.")
                                        break
                                    lastscreen = screen
                    else: 
                        Sleep(1)
                        Press([777,150])

                        dungState, newTargetInfoList = StateSearch(waitTimer,targetInfoList)
                        
                        if newTargetInfoList == targetInfoList:
                            gameFrozen_map +=1
                            logger.info(f"?啣?⊥香璉瘚?{gameFrozen_map}")
                        else:
                            gameFrozen_map = 0
                        if gameFrozen_map > 50:
                            gameFrozen_map = 0
                            restartGame()

                        if (targetInfoList==None) or (targetInfoList == []):
                            logger.info("?唬?????? ?唬??????(隞?隞餃璅∪?.)")
                            break

                        if (newTargetInfoList != targetInfoList):
                            if newTargetInfoList[0].activeSpellSequenceOverride:
                                logger.info("?蛹?格?靽⊥?, ?憭鈭瘜???")
                                runtimeContext._ACTIVESPELLSEQUENCE = copy.deepcopy(quest._SPELLSEQUENCE)
                            else:
                                logger.info("?蛹?格?靽⊥?, 皜征鈭瘜???")
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
            logger.info("憟? 隞餃??撌脩??乩?.")
            FindCoordsOrElseExecuteFallbackAndWait('Inn',['return',[1,1]],1)

    def DungeonFarm():
        nonlocal runtimeContext
        state = None
        while 1:
            logger.info("======================")
            Sleep(1)
            if setting._FORCESTOPING.is_set():
                logger.info("?喳??迫?...")
                break
            logger.info(f"敶??嗆? {state}")
            match state:
                case None:
                    def _identifyState():
                        nonlocal state
                        state=IdentifyState()[0]
                    RestartableSequenceExecution(
                        lambda: _identifyState()
                        )
                    logger.info(f"銝??嗆? {state}")
                    if state ==State.Quit:
                        logger.info("?喳??迫?...")
                        break
                case State.Inn:
                    DungeonCompletionCounter()
                    if not runtimeContext._MEET_CHEST_OR_COMBAT:
                        logger.info("?蛹瘝⊥??????蝞? 頝唾?雿挪.")
                    elif not setting._ACTIVE_REST:
                        logger.info("?蛹?Ｘ霈曄蔭, 頝唾?雿挪.")
                    elif ((runtimeContext._COUNTERDUNG-1) % (setting._RESTINTERVEL+1) != 0):
                        logger.info("餈?霈詨??唬????? ?Ｗ?? ?啣餈??賭??臬.")
                    else:
                        logger.info("隡?園??")
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
                    targetInfoList = quest._TARGETINFOLIST.copy()
                    RestartableSequenceExecution(
                        lambda: StateDungeon(targetInfoList)
                        )
                    state = None
        setting._FINISHINGCALLBACK()
    def QuestFarm():
        nonlocal setting # 撘箏?芸?? 蝑?.
        nonlocal runtimeContext
        match setting._FARMTARGET:
            case '7000G':
                while 1:
                    if setting._FORCESTOPING.is_set():
                        break

                    starttime = time.time()
                    runtimeContext._COUNTERDUNG += 1
                    def stepMain():
                        logger.info("蝚砌?甇? 撘憪?????..")
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
                    logger.info("蝚砌?甇? 餈?閬?...")
                    RestartableSequenceExecution(
                        lambda: FindCoordsOrElseExecuteFallbackAndWait('Inn',['returntotown','returnText','leaveDung','dialogueChoices/blessing',[1,1]],2)
                        )

                    logger.info("蝚砌?甇? ????...")
                    RestartableSequenceExecution(
                        lambda:TeleportFromCityToWorldLocation('RoyalCityLuknalia', 'input swipe 450 150 500 150'),
                        lambda:FindCoordsOrElseExecuteFallbackAndWait('guild',['RoyalCityLuknalia',[1,1]],1),
                        )

                    logger.info("蝚砍?甇? 蝏?!(隡豢?)")
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
                    logger.info(f"蝚洌runtimeContext._COUNTERDUNG}甈﹏"7000G\"摰?. 霂交活?梯晶?園{costtime:.2f}, 瘥??嗥?:{7000/costtime:.2f}Gps.",
                                extra={"summary": True})
            case 'fordraig':
                quest._SPECIALDIALOGOPTION = ['fordraig/thedagger','fordraig/InsertTheDagger']
                while 1:
                    if setting._FORCESTOPING.is_set():
                        break
                    runtimeContext._COUNTERDUNG += 1
                    setting._SYSTEMAUTOCOMBAT = True
                    starttime = time.time()
                    logger.info('蝚砌?甇? 霂?銋?...')
                    RestartableSequenceExecution(
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait('cursedWheel',['ruins',[1,1]],1)),
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait('Fordraig/Leap',['specialRequest',[1,1]],1)),
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait('OK','leap',1)),
                        )
                    Sleep(15)

                    RestartableSequenceExecution(
                        lambda: logger.info('蝚砌?甇? 憸?隞餃.'),
                        lambda: StateAcceptRequest('fordraig/RequestAccept',[350,180])
                        )

                    logger.info('蝚砌?甇? 餈?唬???')
                    TeleportFromCityToWorldLocation('fordraig/labyrinthOfFordraig','input swipe 450 150 500 150')
                    Press(FindCoordsOrElseExecuteFallbackAndWait('fordraig/Entrance',['fordraig/labyrinthOfFordraig',[1,1]],1))
                    FindCoordsOrElseExecuteFallbackAndWait('dungFlag',['fordraig/Entrance','GotoDung',[1,1]],1)

                    logger.info('蝚砍?甇? ?琿.')
                    RestartableSequenceExecution(
                        lambda:StateDungeon([
                            TargetInfo('position',"撌虫?",[721,448]),
                            TargetInfo('position',"撌虫?",[720,608])]), # ??蝚砌?銝芷??                        lambda:FindCoordsOrElseExecuteFallbackAndWait("dungFlag","return",1), # ?喲?啣
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait("fordraig/TryPushingIt",["input swipe 100 250 800 250",[400,800],[400,800],[400,800]],1)), # 頧砍??亙??舀??                        )
                    logger.info('撌脣??洵銝銝芷??')

                    RestartableSequenceExecution(
                        lambda:StateDungeon([
                            TargetInfo('stair_down',"撌虫?",[721,236]),
                            TargetInfo('position',"撌虫?", [240,921])]), #??蝚砌?銝芷??                        lambda:FindCoordsOrElseExecuteFallbackAndWait("dungFlag","return",1), # ?喲?啣
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait("fordraig/TryPushingIt",["input swipe 100 250 800 250",[400,800],[400,800],[400,800]],1)), # 頧砍??亙??舀??                        )
                    logger.info('撌脣??洵鈭葵?琿.')

                    RestartableSequenceExecution(
                        lambda:StateDungeon([
                            TargetInfo("position","撌虫?",[33,1238]),
                            TargetInfo("stair_down","撌虫?",[453,1027]),
                            TargetInfo("position","撌虫?",[187,1027]),
                            TargetInfo("stair_teleport","撌虫?",[80,1026])
                            ]), #??蝚砌?銝芷??                        )
                    logger.info('撌脣??洵銝葵?琿.')

                    StateDungeon([TargetInfo('position','撌虫?',[508,1025])]) # ??boss???                    setting._SYSTEMAUTOCOMBAT = False
                    StateDungeon([TargetInfo('position','撌虫?',[720,1025])]) # ??boss??
                    setting._SYSTEMAUTOCOMBAT = True
                    StateDungeon([TargetInfo('stair_teleport','撌虫?',[665,395])]) # 蝚砍?撅??                    FindCoordsOrElseExecuteFallbackAndWait("dungFlag","return",1)
                    Press(FindCoordsOrElseExecuteFallbackAndWait("ReturnText",["leaveDung",[455,1200]],3.75)) # ??
                    # 3.75隞銋???甇?虜敺芰??蝘???甈∪?霂隡??迨3.75蝘?銝甈∪??末.
                    Press(FindCoordsOrElseExecuteFallbackAndWait("RoyalCityLuknalia",['return',[1,1]],1)) # ??
                    FindCoordsOrElseExecuteFallbackAndWait("Inn",[1,1],1)

                    costtime = time.time()-starttime
                    logger.info(f"蝚洌runtimeContext._COUNTERDUNG}甈﹏"曏?\"摰?. 霂交活?梯晶?園{costtime:.2f}.",
                            extra={"summary": True})
            case 'repelEnemyForces':
                if not setting._ACTIVE_REST:
                    logger.info("瘜冽?, \"隡?湧?\"?批餈賒??憭?甈∪???. 敶??芸?其??? 撘箏霈曄蔭銝?.")
                    setting._RESTINTERVEL = 1
                if setting._RESTINTERVEL == 0:
                    logger.info("瘜冽?, \"隡?湧?\"?批餈賒??憭?甈∪???. 敶???銝箸??? ?雿蛹1.")
                    setting._RESTINTERVEL = 1
                logger.info("瘜冽?, 霂交?蝔???園頝唾???遙?? 霂瑞＆靽?遙?∪?????")
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
                        lambda : StateDungeon([TargetInfo('position','撌虫?',[559,599]),
                                               TargetInfo('position','撌虫?',[186,813])])
                    )
                    logger.info('撌脫颲曄??? 撘憪???')
                    FindCoordsOrElseExecuteFallbackAndWait('dungFlag',['return',[1,1]],1)
                    for i in range(setting._RESTINTERVEL):
                        logger.info(f"蝚洌i+1}頧桀?憪?")
                        secondcombat = False
                        while 1:
                            Press(FindCoordsOrElseExecuteFallbackAndWait(['icanstillgo','combatActive'],['input swipe 400 400 400 100',[1,1]],1))
                            Sleep(1)
                            if setting._AOE_ONCE:
                                runtimeContext._ENOUGH_AOE = False
                                runtimeContext._AOE_CAST_TIME = 0
                            while 1:
                                scn=ScreenShot()
                                if TryPressRetry(scn):
                                    continue
                                if CheckIf(scn,'icanstillgo'):
                                    break
                                if StateCombatCheck(scn):
                                    StateCombat()
                                else:
                                    Press([1,1])
                            if not secondcombat:
                                logger.info(f"蝚??箸?????")
                                secondcombat = True
                                Press(CheckIf(ScreenShot(),'icanstillgo'))
                            else:
                                logger.info(f"蝚??箸?????")
                                Press(CheckIf(ScreenShot(),'letswithdraw'))
                                Sleep(1)
                                break
                        logger.info(f"蝚洌i+1}頧桃???")
                    RestartableSequenceExecution(
                        lambda:StateDungeon([TargetInfo('position','撌虫?',[612,448])])
                    )
                    RestartableSequenceExecution(
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait('returnText',[[1,1],'leaveDung','return'],3))
                    )
                    RestartableSequenceExecution(
                        lambda:FindCoordsOrElseExecuteFallbackAndWait('Inn',['return',[1,1]],1)
                    )
                    counter+=1
                    logger.info(f"蝚洌counter}x{setting._RESTINTERVEL}頧娉"?駁??"摰?, ?梯恣{counter*setting._RESTINTERVEL*2}?箸??? 霂交活?梯晶?園{(time.time()-t):.2f}蝘?",
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
                                logger.info("?曹??駁?⊥香, ?究tate:None銝剝???")
                                restartGame()
                            MAXTIMEOUT = 400
                            if (runtimeContext._TIME_CHEST != 0 ) and (time.time()-runtimeContext._TIME_CHEST > MAXTIMEOUT):
                                logger.info("?曹?摰拳?冽餈?, ?究tate:None銝剝???")
                                restartGame()
                            if (runtimeContext._TIME_COMBAT != 0) and (time.time()-runtimeContext._TIME_COMBAT > MAXTIMEOUT):
                                logger.info("?曹????冽餈?, ?究tate:None銝剝???")
                                restartGame()
                        case DungeonState.Dungeon:
                            Press([1,1])
                            ########### COMBAT RESET
                            # ??蝏?鈭? ?賑撠?鈭挽蝵桀?雿?                            if setting._AOE_ONCE:
                                runtimeContext._ENOUGH_AOE = False
                                runtimeContext._AOE_CAST_TIME = 0
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
                                logger.info(f"蝎蝏恣: 摰拳{spend_on_chest:.2f}蝘? ??{spend_on_combat:.2f}蝘?")
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
                                logger.info("餈?撘?臬?蝞勗??憭?")
                                runtimeContext._COUNTERCHEST+=1
                                needRecoverBecauseChest = False
                                runtimeContext._MEET_CHEST_OR_COMBAT = True
                                if not setting._SKIPCHESTRECOVER:
                                    logger.info("?曹??Ｘ?蔭, 餈?撘?臬?蝞勗??Ｗ?.")
                                    shouldRecover = True
                                else:
                                    logger.info("?曹??Ｘ?蔭, 頝唾?鈭??臬?蝞勗??Ｗ?.")
                            if needRecoverBecauseCombat:
                                runtimeContext._COUNTERCOMBAT+=1
                                needRecoverBecauseCombat = False
                                runtimeContext._MEET_CHEST_OR_COMBAT = True
                                if (not setting._SKIPCOMBATRECOVER):
                                    logger.info("?曹??Ｘ?蔭, 餈????Ｗ?.")
                                    shouldRecover = True
                                else:
                                    logger.info("?曹??Ｘ?蔭, 頝唾?鈭????Ｗ?.")
                            if shouldRecover:
                                Press([1,1])
                                FindCoordsOrElseExecuteFallbackAndWait( # ?孵??鈭箇?Ｘ??賭?鋡急?????                                    ['trait','combatActive','chestFlag','combatClose'],
                                    [[36,1425],[322,1425],[606,1425]],
                                    1
                                    )
                                if CheckIf(ScreenShot(),'trait'):
                                    Press([833,843])
                                    Sleep(1)
                                    FindCoordsOrElseExecuteFallbackAndWait(
                                        ['recover','combatActive'],
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
                        logger.info(f"蝚洌runtimeContext._COUNTERDUNG}甈∩????? ?祆活?冽:{round(time.time()-runtimeContext._LAPTIME,2)}蝘? 蝝航恣撘蝞勗?{runtimeContext._COUNTERCHEST}, 蝝航恣??{runtimeContext._COUNTERCOMBAT}, 蝝航恣?冽{round(runtimeContext._TOTALTIME,2)}蝘?",
                                    extra={"summary": True})
                    runtimeContext._LAPTIME = time.time()
                    runtimeContext._COUNTERDUNG+=1

                    RestartableSequenceExecution(
                        lambda: logger.info('蝚砌?甇? ?蔭??'),
                        lambda: CursedWheelTimeLeap(None,'LBC/symbolofalliance',[['LBC/EnaWasSaved',2,1,0]])
                        )
                    Sleep(10)
                    RestartableSequenceExecution(
                        lambda: logger.info("蝚砌?甇? 餈?閬?"),
                        lambda: FindCoordsOrElseExecuteFallbackAndWait('Inn',['returntotown','returnText','leaveDung','dialogueChoices/blessing',[1,1]],2)
                        )
                    RestartableSequenceExecution(
                        lambda: logger.info("蝚砌?甇? ????"),
                        lambda: TeleportFromCityToWorldLocation('RoyalCityLuknalia','input swipe 450 150 500 150'),
                        lambda: FindCoordsOrElseExecuteFallbackAndWait('guild',['RoyalCityLuknalia',[1,1]],1),
                        )
               
                    RestartableSequenceExecution(
                        lambda: logger.info('蝚砍?甇? 憸?隞餃'),
                        lambda: StateAcceptRequest('LBC/Request',[266,257]),
                    )
                    RestartableSequenceExecution(
                        lambda: logger.info('蝚砌?甇? 餈??'),
                        lambda: TeleportFromCityToWorldLocation('LBC/LBC','input swipe 400 400 400 500')
                        )

                    Gorgon1 = TargetInfo('position','撌虫?',[134,342])
                    Gorgon2 = TargetInfo('position','?喃?',[500,395])
                    Gorgon3 = TargetInfo('position','?喃?',[340,1027])
                    LBC_quit = TargetInfo('LBC/LBC_quit')
                    if setting._ACTIVE_REST:
                        RestartableSequenceExecution(
                            lambda: logger.info('蝚砍甇? ?餅?銝??),
                            lambda: StateDungeon([Gorgon1,LBC_quit])
                            )
                        RestartableSequenceExecution(
                            lambda: logger.info('蝚砌?甇? ??∟?'),
                            lambda: StateInn()
                            )
                        RestartableSequenceExecution(
                            lambda: logger.info('蝚砍甇? ???'),
                            lambda: TeleportFromCityToWorldLocation('LBC/LBC','input swipe 400 400 400 500')
                            )
                        RestartableSequenceExecution(
                            lambda: logger.info('蝚砌?甇? ?餅?鈭?'),
                            lambda: StateDungeon([Gorgon2,Gorgon3,LBC_quit])
                            )
                    else:
                        logger.info('頝唾???隡.')
                        RestartableSequenceExecution(
                            lambda: logger.info('蝚砍甇? 餈?銝?'),
                            lambda: StateDungeon([Gorgon1,Gorgon2,Gorgon3,LBC_quit])
                            )
            case 'SSC-goldenchest':
                while 1:
                    quest._SPECIALDIALOGOPTION = ['SSC/dotdotdot','SSC/shadow']
                    if setting._FORCESTOPING.is_set():
                        break
                    if runtimeContext._LAPTIME!= 0:
                        runtimeContext._TOTALTIME = runtimeContext._TOTALTIME + time.time() - runtimeContext._LAPTIME
                        logger.info(f"蝚洌runtimeContext._COUNTERDUNG}甈∪?瘣??? ?祆活?冽:{round(time.time()-runtimeContext._LAPTIME,2)}蝘? 蝝航恣撘蝞勗?{runtimeContext._COUNTERCHEST}, 蝝航恣??{runtimeContext._COUNTERCOMBAT}, 蝝航恣?冽{round(runtimeContext._TOTALTIME,2)}蝘?",
                                    extra={"summary": True})
                    runtimeContext._LAPTIME = time.time()
                    runtimeContext._COUNTERDUNG+=1
                    RestartableSequenceExecution(
                        lambda: logger.info('蝚砌?甇? ?蔭??'),
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait('cursedWheel',['ruins',[1,1]],1)),
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait('SSC/Leap',['specialRequest',[1,1]],1)),
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait('OK','leap',1)),
                        )
                    Sleep(10)
                    RestartableSequenceExecution(
                        lambda: logger.info("蝚砌?甇? ????"),
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
                        lambda: logger.info('蝚砌?甇? 憸?隞餃'),
                        lambda: stepThree()
                        )

                    RestartableSequenceExecution(
                        lambda: logger.info('蝚砍?甇? 餈敹?'),
                        lambda: TeleportFromCityToWorldLocation('SSC/SSC','input swipe 700 500 600 600')
                        )
                    RestartableSequenceExecution(
                        lambda: logger.info('蝚砌?甇? ?喲?琿'),
                        lambda:FindCoordsOrElseExecuteFallbackAndWait('SSC/trapdeactived',['input swipe 450 1050 450 850',[445,721]],4),
                        lambda:FindCoordsOrElseExecuteFallbackAndWait('dungFlag',[1,1],1)
                    )
                    quest._SPECIALDIALOGOPTION = ['SSC/dotdotdot','SSC/shadow']
                    RestartableSequenceExecution(
                        lambda: logger.info('蝚砍甇? 蝚砌?銝芰拳摮?),
                        lambda: StateDungeon([
                                TargetInfo('position',     '撌虫?', [719,1088]),
                                TargetInfo('position',     '撌虫?', [346,874]),
                                TargetInfo('chest',        '撌虫?', [[0,0,900,1600],[640,0,260,1600],[506,0,200,700]]),
                                TargetInfo('chest',        '?喃?', [[0,0,900,1600],[0,0,407,1600]]),
                                TargetInfo('chest',        '?喃?', [[0,0,900,1600],[0,0,900,800]]),
                                TargetInfo('chest',        '撌虫?', [[0,0,900,1600],[650,0,250,811],[507,166,179,165]]),
                                TargetInfo('SSC/SSC_quit', '?喃?', None)
                            ])
                        )
            case 'CaveOfSeperation':
                while 1:
                    if setting._FORCESTOPING.is_set():
                        break
                    if runtimeContext._LAPTIME!= 0:
                        runtimeContext._TOTALTIME = runtimeContext._TOTALTIME + time.time() - runtimeContext._LAPTIME
                        logger.info(f"蝚洌runtimeContext._COUNTERDUNG}甈∠漲摰????? ?祆活?冽:{round(time.time()-runtimeContext._LAPTIME,2)}蝘? 蝝航恣撘蝞勗?{runtimeContext._COUNTERCHEST}, 蝝航恣??{runtimeContext._COUNTERCOMBAT}, 蝝航恣?冽{round(runtimeContext._TOTALTIME,2)}蝘?",
                                    extra={"summary": True})
                    runtimeContext._LAPTIME = time.time()
                    runtimeContext._COUNTERDUNG+=1
                    RestartableSequenceExecution(
                        lambda: logger.info('蝚砌?甇? ?蔭??'),
                        lambda: CursedWheelTimeLeap(None,'COS/ArnasPast')
                        )
                    Sleep(10)
                    RestartableSequenceExecution(
                        lambda: logger.info("蝚砌?甇? 餈?閬?"),
                        lambda: FindCoordsOrElseExecuteFallbackAndWait('Inn',['returntotown','returnText','leaveDung','dialogueChoices/blessing',[1,1]],2)
                        )
                    RestartableSequenceExecution(
                        lambda: logger.info("蝚砌?甇? ????"),
                        lambda: TeleportFromCityToWorldLocation('RoyalCityLuknalia','input swipe 450 150 500 150'),
                        lambda: FindCoordsOrElseExecuteFallbackAndWait('guild',['RoyalCityLuknalia',[1,1]],1),
                        )
                    
                    RestartableSequenceExecution(
                        lambda: logger.info('蝚砍?甇? 憸?隞餃'),
                        lambda: FindCoordsOrElseExecuteFallbackAndWait(['COS/Okay','guildRequest'],['guild',[1,1]],1),
                        lambda: FindCoordsOrElseExecuteFallbackAndWait('Inn',['COS/Okay','return',[1,1]],1),
                        lambda: StateInn(),
                        )
                    
                    RestartableSequenceExecution(
                        lambda: logger.info('蝚砌?甇? 餈瘣?'),
                        lambda: Press(FindCoordsOrElseExecuteFallbackAndWait('COS/COS',['EdgeOfTown',[1,1]],1)),
                        lambda: Press(FindCoordsOrElseExecuteFallbackAndWait('COS/COSENT',[1,1],1))
                        )
                    quest._SPECIALDIALOGOPTION = ['COS/takehimwithyou']
                    cosb1f = [TargetInfo('position',"?喃?",[286-54,440]),
                              TargetInfo('position',"?喃?",[819,653+54]),
                              TargetInfo('position',"?喃?",[659-54,501]),
                              TargetInfo('stair_2',"?喃?",[126-54,342]),
                        ]
                    RestartableSequenceExecution(
                        lambda: logger.info('蝚砍甇? 1撅鈭?),
                        lambda: StateDungeon(cosb1f)
                        )

                    quest._SPECIALFORCESTOPINGSYMBOL = ['COS/EnaTheAdventurer']
                    cosb2f = [TargetInfo('position',"?喃?",[340+54,448]),
                              TargetInfo('position',"?喃?",[500-54,1088]),
                              TargetInfo('position',"撌虫?",[398+54,766]),
                        ]
                    RestartableSequenceExecution(
                        lambda: logger.info('蝚砌?甇? 2撅鈭?),
                        lambda: StateDungeon(cosb2f)
                        )

                    quest._SPECIALFORCESTOPINGSYMBOL = ['COS/requestwasfor'] 
                    cosb3f = [TargetInfo('stair_3',"撌虫?",[720,822]),
                              TargetInfo('position',"撌虫?",[239,600]),
                              TargetInfo('position',"撌虫?",[185,1185]),
                              TargetInfo('position',"撌虫?",[560,652]),
                              ]
                    RestartableSequenceExecution(
                        lambda: logger.info('蝚砍甇? 3撅鈭?),
                        lambda: StateDungeon(cosb3f)
                        )

                    quest._SPECIALFORCESTOPINGSYMBOL = None
                    quest._SPECIALDIALOGOPTION = ['COS/requestwasfor'] 
                    cosback2f = [
                                 TargetInfo('stair_2',"撌虫?",[827,547]),
                                 TargetInfo('position',"?喃?",[340+54,448]),
                                 TargetInfo('position',"?喃?",[500-54,1088]),
                                 TargetInfo('position',"撌虫?",[398+54,766]),
                                 TargetInfo('position',"撌虫?",[559,1087]),
                                 TargetInfo('stair_1',"撌虫?",[666,448]),
                                 TargetInfo('position', "?喃?",[660,919])
                        ]
                    RestartableSequenceExecution(
                        lambda: logger.info('蝚砌?甇? 蝳餃?瘣庖'),
                        lambda: StateDungeon(cosback2f)
                        )
                    Press(FindCoordsOrElseExecuteFallbackAndWait("guild",['return',[1,1]],1)) # ??
                    FindCoordsOrElseExecuteFallbackAndWait("Inn",['return',[1,1]],1)
                    
                pass
            case 'gaintKiller':
                while 1:
                    if setting._FORCESTOPING.is_set():
                        break
                    if runtimeContext._LAPTIME!= 0:
                        runtimeContext._TOTALTIME = runtimeContext._TOTALTIME + time.time() - runtimeContext._LAPTIME
                        logger.info(f"蝚洌runtimeContext._COUNTERDUNG}甈∪楊鈭箏??? ?祆活?冽:{round(time.time()-runtimeContext._LAPTIME,2)}蝘? 蝝航恣撘蝞勗?{runtimeContext._COUNTERCHEST}, 蝝航恣??{runtimeContext._COUNTERCOMBAT}, 蝝航恣?冽{round(runtimeContext._TOTALTIME,2)}蝘?",
                                    extra={"summary": True})
                    runtimeContext._LAPTIME = time.time()
                    runtimeContext._COUNTERDUNG+=1

                    quest._EOT = [
                        ["press","impregnableFortress",["EdgeOfTown",[1,1]],1],
                        ["press","fortressb7f",[1,1],1]]
                    RestartableSequenceExecution(
                        lambda: StateEoT()
                        )
                    
                    # RestartableSequenceExecution(
                    #     lambda: StateDungeon([TargetInfo('position','撌虫?',[560,928])]),
                    #     lambda: FindCoordsOrElseExecuteFallbackAndWait('dungFlag','return',1)
                    # )

                    # counter_candelabra = 0
                    # for _ in range(3):
                    #     scn = ScreenShot()
                    #     if CheckIf(scn,"gaint_candelabra_1") or CheckIf(scn,"gaint_candelabra_2"):
                    #         counter_candelabra+=1
                    #     Sleep(1)
                    # if counter_candelabra != 0:
                    #     logger.info("瘝∪??啣楊鈭?")
                    #     RestartableSequenceExecution(
                    #     lambda: StateDungeon([TargetInfo('harken2','撌虫?')]),
                    #     lambda: FindCoordsOrElseExecuteFallbackAndWait('Inn',['returntotown','returnText','leaveDung','dialogueChoices/blessing',[1,1]],2)
                    # )
                    #     continue
                    
                    # logger.info("?鈭楊鈭?")
                    logger.info("頝唾?鈭楊鈭箸?瘚?? ?啣暺恕?餅?餅??舀?")
                    RestartableSequenceExecution(
                        lambda: StateDungeon([TargetInfo('position','撌虫?',[560,928+54],True),
                                              TargetInfo('harken2','撌虫?')]),
                        lambda: FindCoordsOrElseExecuteFallbackAndWait('Inn',['returntotown','returnText','leaveDung','dialogueChoices/blessing',[1,1]],2)
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
                    logger.info("蝚砌?甇? 餈?閬?...")
                    RestartableSequenceExecution(
                        lambda: FindCoordsOrElseExecuteFallbackAndWait('Inn',['returntotown','returnText','leaveDung','dialogueChoices/blessing',[1,1]],2)
                        )

                    logger.info("蝚砌?甇? ????...")
                    RestartableSequenceExecution(
                        lambda:TeleportFromCityToWorldLocation('RoyalCityLuknalia','input swipe 450 150 500 150'),
                        )

                    logger.info("蝚砍?甇? ?祈??剜?")
                    RestartableSequenceExecution(
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait('guildRequest',['guild',[1,1]],1)),
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait('Bounties',['guild','guildRequest','input swipe 600 1400 300 1400',[1,1]],1)),
                        lambda:FindCoordsOrElseExecuteFallbackAndWait('EdgeOfTown',['return',[1,1]],1)
                        )

                    logger.info("蝚砌?甇? ?餅??戊")
                    RestartableSequenceExecution(
                        lambda:FindCoordsOrElseExecuteFallbackAndWait('dungFlag',['EdgeOfTown','beginningAbyss','B2FTemple','GotoDung',[1,1]],1),
                    )
                    RestartableSequenceExecution(
                        lambda:StateDungeon([TargetInfo('position','撌虫?',[505,760]),
                                             TargetInfo('position','撌虫?',[506,821])]),
                        )
                    
                    logger.info("蝚砍甇? ?漱?祈?")
                    RestartableSequenceExecution(
                        lambda:FindCoordsOrElseExecuteFallbackAndWait("guild",['return',[1,1]],1),
                    )
                    RestartableSequenceExecution(
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait('CompletionReported',['guild','guildRequest','input swipe 600 1400 300 1400','Bounties',[1,1]],1))
                        )
                    RestartableSequenceExecution(
                        lambda:FindCoordsOrElseExecuteFallbackAndWait('EdgeOfTown',['return',[1,1]],1)
                        )
                    
                    logger.info("蝚砌?甇? 隡")
                    if ((runtimeContext._COUNTERDUNG-1) % (setting._RESTINTERVEL+1) == 0):
                        RestartableSequenceExecution(
                            lambda:StateInn()
                            )
                        
                    costtime = time.time()-starttime
                    total_time = total_time + costtime
                    logger.info(f"蝚洌runtimeContext._COUNTERDUNG}甈﹏"?祈?:?戊\"摰?. \n霂交活?梯晶?園{costtime:.2f}s.\n?餉恣?冽{total_time:.2f}s.\n撟喳??冽{total_time/runtimeContext._COUNTERDUNG:.2f}",
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
                        StateDungeon([TargetInfo('position','撌虫?',[131,769]),
                                    TargetInfo('position','撌虫?',[827,447]),
                                    TargetInfo('position','撌虫?',[131,769]),
                                    TargetInfo('position','撌虫?',[719,1080]),
                                    ])
                                  )
                    
                    if ((runtimeContext._COUNTERDUNG-1) % (setting._RESTINTERVEL+1) == 0):
                        RestartableSequenceExecution(
                            lambda:StateInn()
                            )
                    costtime = time.time()-starttime
                    total_time = total_time + costtime
                    logger.info(f"蝚洌runtimeContext._COUNTERDUNG}甈﹏"?Ｚ??墦"摰?. \n霂交活?梯晶?園{costtime:.2f}s.\n?餉恣?冽{total_time:.2f}s.\n撟喳??冽{total_time/runtimeContext._COUNTERDUNG:.2f}",
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
                    logger.info("蝚砌?甇? 餈?閬?...")
                    RestartableSequenceExecution(
                        lambda: FindCoordsOrElseExecuteFallbackAndWait('Inn',['returntotown','returnText','leaveDung','dialogueChoices/blessing',[1,1]],2)
                        )

                    logger.info("蝚砌?甇? ????...")
                    RestartableSequenceExecution(
                        lambda:TeleportFromCityToWorldLocation('RoyalCityLuknalia','input swipe 450 150 500 150'),
                        )

                    logger.info("蝚砍?甇? ?祈??剜?")
                    RestartableSequenceExecution(
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait('guildRequest',['guild',[1,1]],1)),
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait('Bounties',['guild','guildRequest','input swipe 600 1400 300 1400',[1,1]],1)),
                        lambda:FindCoordsOrElseExecuteFallbackAndWait('EdgeOfTown',['return',[1,1]],1)
                        )

                    logger.info("蝚砌?甇? ??撠秩????)
                    RestartableSequenceExecution(
                        lambda:FindCoordsOrElseExecuteFallbackAndWait('dungFlag',['EdgeOfTown','beginningAbyss','B4FLabyrinth','GotoDung',[1,1]],1)
                        )
                    RestartableSequenceExecution( 
                        lambda:StateDungeon([TargetInfo('position','撌虫?',[452,1026]),
                                             TargetInfo('harken','撌虫?',None)]),
                        )
                    
                    logger.info("蝚砍甇? ?漱?祈?")
                    RestartableSequenceExecution(
                        lambda:FindCoordsOrElseExecuteFallbackAndWait("guild",['return',[1,1]],1),
                    )
                    RestartableSequenceExecution(
                        lambda:Press(FindCoordsOrElseExecuteFallbackAndWait('CompletionReported',['guild','guildRequest','input swipe 600 1400 300 1400','Bounties',[1,1]],1))
                        )
                    RestartableSequenceExecution(
                        lambda:FindCoordsOrElseExecuteFallbackAndWait('EdgeOfTown',['return',[1,1]],1)
                        )
                    
                    logger.info("蝚砌?甇? 隡")
                    if ((runtimeContext._COUNTERDUNG-1) % (setting._RESTINTERVEL+1) == 0):
                        RestartableSequenceExecution(
                            lambda:StateInn()
                            )
                        
                    costtime = time.time()-starttime
                    total_time = total_time + costtime
                    logger.info(f"蝚洌runtimeContext._COUNTERDUNG}甈﹏"?祈?:??\"摰?. \n霂交活?梯晶?園{costtime:.2f}s.\n?餉恣?冽{total_time:.2f}s.\n撟喳??冽{total_time/runtimeContext._COUNTERDUNG:.2f}",
                            extra={"summary": True})
            # case 'test':
            #     while 1:
            #         quest._SPECIALDIALOGOPTION = ["bounty/Slayhim"]
            #         # StateDungeon([TargetInfo('position','撌虫?',[612,1132])])
            #         StateDungeon([TargetInfo('position','?喃?',[553,821])])
        setting._FINISHINGCALLBACK()
        return
    def Farm(set:FarmConfig):
        nonlocal quest
        nonlocal setting # ????        nonlocal runtimeContext
        runtimeContext = RuntimeContext()

        setting = set

        Sleep(1) # 瘝⊥?蝑tils??????        
        ResetADBDevice()

        quest = LoadQuest(setting._FARMTARGET)
        if quest:
            if quest._TYPE =="dungeon":
                DungeonFarm()
            else:
                QuestFarm()
        else:
            setting._FINISHINGCALLBACK()
    return Farm
