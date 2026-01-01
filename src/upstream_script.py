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
FULL_AOE_SKILLS = ["LAERLIK", "LAMIGAL","LAZELOS", "LACONES", "LAFOROS","LAHALITO", "LAFERU", "千戀萬花"]
ROW_AOE_SKILLS = ["maerlik", "mahalito", "mamigal","mazelos","maferu", "macones","maforos","終焉之刻"]
PHYSICAL_SKILLS = ["動靜一擊","全力一擊","死死連葬","tzalik","居合","精密攻擊","鎖腹刺","破甲","星光裂","遲鈍連攜擊","強襲","重裝一擊","眩暈打擊","幻影狩獵"]

ALL_SKILLS = CC_SKILLS + SECRET_AOE_SKILLS + FULL_AOE_SKILLS + ROW_AOE_SKILLS +  PHYSICAL_SKILLS
ALL_SKILLS = [s for s in ALL_SKILLS if s in list(set(ALL_SKILLS))]

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
    _TIME_COMBAT= 0
    _TIME_COMBAT_TOTAL = 0
    _TIME_CHEST = 0
    _TIME_CHEST_TOTAL = 0
    #### 其他臨時參數
    _MEET_CHEST_OR_COMBAT = False
    _ENOUGH_AOE = False
    _AOE_CAST_TIME = 0
    _COMBATSPD = False
    _SUICIDE = False # 當有兩個人死亡的時候(multipeopledead), 在戰鬥中嘗試自殺.
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
        # 當訪問不存在的屬性時，拋出AttributeError
        raise AttributeError(f"FarmQuest對象沒有屬性'{name}'")
class TargetInfo:
    def __init__(self, target: str, swipeDir: list = None, roi=None, activeSpellSequenceOverride = False):
        self.target = target
        self.swipeDir = swipeDir
        # 注意 roi校驗需要target的值. 請嚴格保證roi在最後.
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
                time.sleep(2)

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
            time.sleep(2)
            KillEmulator(setting)
            KillAdb(setting)
            time.sleep(2)
        except Exception as e:
            logger.error(f"重啓ADB服務時出錯: {e}")
            time.sleep(2)
            KillEmulator(setting)
            KillAdb(setting)
            time.sleep(2)
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
        time.sleep(t)
    def ScreenShot():
        while True:
            try:
                # logger.debug('ScreenShot')
                screenshot = setting._ADBDEVICE.screencap()
                screenshot_np = np.frombuffer(screenshot, dtype=np.uint8)

                if screenshot_np.size == 0:
                    logger.error("截圖數據爲空！")
                    raise RuntimeError("截圖數據爲空")

                image = cv2.imdecode(screenshot_np, cv2.IMREAD_COLOR)

                if image is None:
                    logger.error("OpenCV解碼失敗：圖像數據損壞")
                    raise RuntimeError("圖像解碼失敗")

                if image.shape != (1600, 900, 3):  # OpenCV格式爲(高, 寬, 通道)
                    if image.shape == (900, 1600, 3):
                        logger.error(f"截圖尺寸錯誤: 當前{image.shape}, 爲橫屏.")
                        image = cv2.transpose(image)
                        restartGame(skipScreenShot = True) # 這裏直接重啓, 會被外部接收到重啓的exception
                    else:
                        logger.error(f"截圖尺寸錯誤: 期望(1600,900,3), 實際{image.shape}.")
                        raise RuntimeError("截圖尺寸異常")

                #cv2.imwrite('screen.png', image)
                return image
            except Exception as e:
                logger.debug(f"{e}")
                if isinstance(e, (AttributeError,RuntimeError, ConnectionResetError, cv2.error)):
                    logger.info("adb重啓中...")
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
                    logger.info(f"cv2異常.")
                    # timestamp = datetime.now().strftime("cv2_%Y%m%d_%H%M%S")  # 格式：20230825_153045
                    # file_path = os.path.join(LOGS_FOLDER_NAME, f"{timestamp}.png")
                    # cv2.imwrite(file_path, ScreenShot())
                    return None

        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if outputMatchResult:
            cv2.imwrite("origin.png", screenshot)
            cv2.rectangle(screenshot, max_loc, (max_loc[0] + template.shape[1], max_loc[1] + template.shape[0]), (0, 255, 0), 2)
            cv2.imwrite("matched.png", screenshot)

        logger.debug(f"搜索到疑似{shortPathOfTarget}, 匹配程度:{max_val*100:.2f}%")
        if max_val < threshold:
            logger.debug("匹配程度不足閾值.")
            return None
        if max_val<=0.9:
            logger.debug(f"警告: {shortPathOfTarget}的匹配程度超過了{threshold*100:.0f}%但不足90%")

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
        logger.debug(f"搜索到疑似{shortPathOfTarget}, 匹配程度:{max_val*100:.2f}%")
        if max_val >= threshold:
            if max_val<=0.9:
                logger.debug(f"警告: {shortPathOfTarget}的匹配程度超過了80%但不足90%")

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
            logger.debug(f"中心匹配檢查:{mean_diff:.2f}")

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

            logger.debug(f"目標格搜素{position}, 匹配程度:{max_val*100:.2f}%")
            if max_val > threshold:
                logger.debug("已達到檢測閾值.")
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

            logger.debug(f"搜索樓層標識{targetInfo.target}, 匹配程度:{max_val*100:.2f}%")
            if max_val > threshold:
                logger.info("樓層正確, 判定爲已通過")
                return None
            return position
            
        else: #equal: targetInfo.target IN stair_img
            template = LoadTemplateImage(targetInfo.target)
            result = cv2.matchTemplate(cropped, template, cv2.TM_CCOEFF_NORMED)
            threshold = 0.80
            _, max_val, _, _ = cv2.minMaxLoc(result)

            logger.debug(f"搜索樓梯{targetInfo.target}, 匹配程度:{max_val*100:.2f}%")
            if max_val > threshold:
                logger.info("判定爲樓梯存在, 尚未通過.")
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
            logger.info(f"快進未開啓, 即將開啓.{pos}")
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
        runtimeContext._STEPAFTERRESTART = False

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
                    op()
                return
            except RestartSignal:
                logger.info("任務進度重置中...")
                continue
    ##################################################################
    def getCursorCoordinates(input, threshold=0.8):
        """在本地圖片中查找模板位置"""
        template = LoadTemplateImage('cursor')
        if template is None:
            raise ValueError("無法加載模板圖片！")

        h, w = template.shape[:2]  # 獲取模板尺寸
        coordinates = []

        # 按指定順序讀取截圖文件
        img = input

        # 執行模板匹配
        result = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val > threshold:
            # 返回中心座標（相對於截圖左上角）
            center_x = max_loc[0] + w // 2
            coordinates = center_x
        else:
            coordinates = None
        return coordinates
    def findWidestRectMid(input):
        crop_area = (30,62),(880,115)
        # 轉換爲灰度圖
        gray = cv2.cvtColor(input, cv2.COLOR_BGR2GRAY)

        # 裁剪圖像 (y1:y2, x1:x2)
        (x1, y1), (x2, y2) = crop_area
        cropped = gray[y1:y2, x1:x2]

        # cv2.imwrite("Matched Result.png",cropped)

        # 返回結果
        column_means = np.mean(cropped, axis=0)
        aver = np.average(column_means)
        binary = column_means > aver

        # 離散化
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
            # 備選方法：傅里葉變換或手動設置初值
            p0 = 1.0  # 根據數據調整

        # 非線性最小二乘擬合
        p_opt, _ = curve_fit(
            triangularWave,
            t_data,
            x_data,
            p0=[p0,0],
            bounds=(0, np.inf)  # 確保週期爲正
        )
        estimated_p = p_opt[0]
        logger.debug(f"週期 p = {estimated_p:.4f}")
        estimated_c = p_opt[1]
        logger.debug(f"初始偏移 c = {estimated_c:.4f}")

        return p_opt[0], p_opt[1]
    def ChestOpen():
        logger.info("開始智能開箱(?)...")
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
            logger.debug(f"理論點: {triangularWave(t-t0,p,c)*900}")
            logger.debug(f"起始點: {x}")
            logger.debug(f"目標點: {target}")

            if x!=None:
                waittime = 0
                t_mod = np.mod(t-c, p)
                if t_mod<p/2:
                    # 正向移動, 向右
                    waittime = ((900-x)+(900-target))/spd
                    logger.debug("先向右再向左")
                else:
                    waittime = (x+target)/spd
                    logger.debug("先向左再向右")

                if waittime > 0.270 :
                    logger.debug(f"預計等待 {waittime}")
                    Sleep(waittime-0.270)
                    DeviceShell(f"input tap 527 920") # 這裏和retry重合, 也和to_title+retry重合.
                    Sleep(3)
                else:
                    logger.debug(f"等待時間過短: {waittime}")

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
        FindCoordsOrElseExecuteFallbackAndWait(['intoWorldMap','dungFlag','worldmapflag','openworldmap'],['closePartyInfo','closePartyInfo_fortress',[550,1]],1)
        
        if CheckIf(scn:=ScreenShot(), 'dungflag'):
            # 如果已經在副本里了 直接結束.
            # 因爲該函數預設了是從城市開始的.
            return
        
        if CheckIf(scn, 'openworldmap'):
            # 如果已經進入了洞窟, 直接結束.
            # 因爲這是無戰鬥無寶箱然後重新嘗試的情況.
            return
        
        if Press(CheckIf(scn,'intoWorldMap')):
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
            screen = ScreenShot()
            logger.info(f'狀態機檢查中...(第{counter+1}次)')

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
                AddImportantInfo("他們活了,活了!")
                for _ in range(5):
                    Press([400+random.randint(0,100),750+random.randint(0,100)])
                    Sleep(1)

            if Press(CheckIf(screen, "returnText")):
                Sleep(2)
                return IdentifyState()

            if CheckIf(screen,"returntoTown"):
                if runtimeContext._MEET_CHEST_OR_COMBAT:
                    FindCoordsOrElseExecuteFallbackAndWait('Inn',['return',[1,1]],1)
                    return State.Inn,DungeonState.Quit, screen
                else:
                    logger.info("由於沒有遇到任何寶箱或發生任何戰鬥, 跳過回城.")
                    return State.EoT,DungeonState.Quit,screen

            if pos:=(CheckIf(screen,"openworldmap")):
                if runtimeContext._MEET_CHEST_OR_COMBAT:
                    Press(pos)
                    return IdentifyState()
                else:
                    logger.info("由於沒有遇到任何寶箱或發生任何戰鬥, 跳過回城.")
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
                logger.info("看起來遇到了一些不太尋常的情況...")
                if (CheckIf(screen,'RiseAgain')):
                    RiseAgainReset(reason = 'combat')
                    return IdentifyState()
                if CheckIf(screen, 'worldmapflag'):
                    for _ in range(3):
                        Press([100,1500])
                        Sleep(0.5)
                    Press([250,1500])
                    # 這裏不需要continue或者遞歸 直接繼續進行就行
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

                    logger.info(f"即將進行善惡值調整. 剩餘次數:{new_str}")
                    AddImportantInfo(f"新的善惡:{new_str}")
                    setting._KARMAADJUST = new_str
                    SetOneVarInConfig("_KARMAADJUST",setting._KARMAADJUST)
                    Sleep(2)

                for op in DIALOG_OPTION_IMAGE_LIST:
                    if Press(CheckIf(screen, 'dialogueChoices/'+op)):
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
                    #logger.info(f"本次戰鬥已經釋放全體aoe, 由於面板配置, 不進行更多的技能釋放.")
                    continue
                elif Press((CheckIf(screen, 'spellskill/'+skillspell))):
                    logger.info(f"使用技能 {skillspell}")
                    castAndPressOK = doubleConfirmCastSpell()
                    castSpellSkill = True
                    if castAndPressOK and setting._AOE_ONCE and ((skillspell in SECRET_AOE_SKILLS) or (skillspell in FULL_AOE_SKILLS)):
                        runtimeContext._AOE_CAST_TIME += 1
                        if runtimeContext._AOE_CAST_TIME >= setting._AOE_TIME:
                            runtimeContext._ENOUGH_AOE = True
                            runtimeContext._AOE_CAST_TIME = 0
                        logger.info(f"已經釋放了首次全體aoe.")
                    break
            if not castSpellSkill:
                Press(CheckIf(ScreenShot(),'combatClose'))
                Press([850,1100])
                Sleep(0.5)
                Press([850,1100])
                Sleep(3)
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
            elif target.startswith("stair"):
                logger.info(f"當前目標: 樓梯{target}")
                targetPos = CheckIf_throughStair(scn,targetInfo)
            else:
                logger.info(f"搜索{target}...")
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
        runtimeContext._RESUMEAVAILABLE = True
        lastscreen = None
        dungState = None
        logger.info("面具男, 移動.")
        while 1:
            Sleep(3)
            _, dungState,screen = IdentifyState()
            if dungState == DungeonState.Map:
                logger.info(f"開始移動失敗. 不要停下來啊面具男!")
                FindCoordsOrElseExecuteFallbackAndWait("dungFlag",[[280,1433],[1,1]],1)
                dungState = dungState.Dungeon
                break
            if dungState != DungeonState.Dungeon:
                logger.info(f"已退出移動狀態. 當前狀態: {dungState}.")
                break
            if lastscreen is not None:
                gray1 = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                gray2 = cv2.cvtColor(lastscreen, cv2.COLOR_BGR2GRAY)
                mean_diff = cv2.absdiff(gray1, gray2).mean()/255
                logger.debug(f"移動停止檢查:{mean_diff:.2f}")
                if mean_diff < 0.1:
                    dungState = None
                    logger.info("已退出移動狀態. 進行狀態檢查...")
                    break
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
            return None, targetInfoList
    
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
            if target in normalPlace or target.endswith("_quit") or target.startswith('stair'):
                Press(searchResult)
                Press([136,1431]) # automove
                return StateMoving_CheckFrozen(),targetInfoList
            else:
                if (CheckIf_FocusCursor(ScreenShot(),target)): #注意 這裏通過二次確認 我們可以看到目標地點 而且是未選中的狀態
                    logger.info("經過對比中心區域, 確認沒有抵達.")
                    Press(searchResult)
                    Press([136,1431]) # automove
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
                            if setting._DUNGWAITTIMEOUT-time.time()+waitTimer<0:
                                logger.info("等得夠久了. 目標地點完成.")
                                targetInfoList.pop(0)
                                Sleep(1)
                                Press([777,150])
                                return None,  targetInfoList
                            logger.info(f'還需要等待{setting._DUNGWAITTIMEOUT-time.time()+waitTimer}秒.')
                            if StateCombatCheck(ScreenShot()):
                                return DungeonState.Combat,targetInfoList
        return DungeonState.Map,  targetInfoList
    def StateChest():
        nonlocal runtimeContext
        availableChar = [0, 1, 2, 3, 4, 5]
        disarm = [515,934]  # 527,920會按到接受死亡 450 1000會按到技能 445,1050還是會按到技能
        haveBeenTried = False

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
                        whowillopenit = pointSomeone # 如果指定了一個角色並且該角色可用並且沒嘗試過, 使用它
                    else:
                        whowillopenit = random.choice(availableChar) # 否則從列表裏隨機選一個
                    pos = [258+(whowillopenit%3)*258, 1161+((whowillopenit)//3)%2*184]
                    # logger.info(f"{availableChar},{pos}")
                    if CheckIf(scn,'chestfear',[[pos[0]-125,pos[1]-82,250,164]]):
                        if whowillopenit in availableChar:
                            availableChar.remove(whowillopenit) # 如果發現了恐懼, 刪除這個角色.
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
                    ['dungFlag','combatActive','chestFlag','RiseAgain'], # 如果這個fallback重啓了, 戰鬥箱子會直接消失, 固有箱子會是chestFlag
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
                logger.info("即將停止腳本...")
                dungState = DungeonState.Quit
            logger.info(f"當前狀態(地下城): {dungState}")

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
                case DungeonState.Quit:
                    break
                case DungeonState.Dungeon:
                    Press([1,1])
                    ########### COMBAT RESET
                    # 戰鬥結束了, 我們將一些設置復位
                    if setting._AOE_ONCE:
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
                            if CheckIf(ScreenShot(),'dungflag') and (counter_trychar <=20):
                                Press([36+(counter_trychar%3)*286,1425])
                                Sleep(1)
                            else:
                                logger.info("自動回覆失敗, 暫不進行回覆.")
                                break
                            if CheckIf(scn:=ScreenShot(),'trait'):
                                if CheckIf(scn,'story', [[676,800,220,108]]):
                                    Press([725,850])
                                else:
                                    Press([830,850])
                                Sleep(1)
                                FindCoordsOrElseExecuteFallbackAndWait(
                                    ['recover','combatActive',],
                                    [833,843],
                                    1
                                    )
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
                    ########### 防止轉圈
                    if not runtimeContext._STEPAFTERRESTART:
                        Press([27,950])
                        Sleep(1)
                        Press([853,950])

                        runtimeContext._STEPAFTERRESTART = True
                    ########### 嘗試resume
                    if runtimeContext._RESUMEAVAILABLE and Press(CheckIf(ScreenShot(),'resume')):
                        logger.info("resume可用. 使用resume.")
                        lastscreen = ScreenShot()
                        while 1:
                            Sleep(3)
                            _, dungState,screen = IdentifyState()
                            if dungState != DungeonState.Dungeon:
                                logger.info(f"已退出移動狀態. 當前狀態爲{dungState}.")
                                break
                            elif lastscreen is not None:
                                gray1 = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                                gray2 = cv2.cvtColor(lastscreen, cv2.COLOR_BGR2GRAY)
                                mean_diff = cv2.absdiff(gray1, gray2).mean()/255
                                logger.debug(f"移動停止檢查:{mean_diff:.2f}")
                                if mean_diff < 0.1:
                                    runtimeContext._RESUMEAVAILABLE = False
                                    logger.info(f"已退出移動狀態. 當前狀態爲{dungState}.")
                                    break
                                lastscreen = screen
                    ########### 如果resume失敗且爲地下城
                    if dungState == DungeonState.Dungeon:
                        dungState = DungeonState.Map
                case DungeonState.Map:
                    ########### 重置施法序列 - 默認值(第一次)和重啓後應當直接應用序列
                    if runtimeContext._SHOULDAPPLYSPELLSEQUENCE: 
                        runtimeContext._SHOULDAPPLYSPELLSEQUENCE = False
                        if targetInfoList[0].activeSpellSequenceOverride:
                            logger.info("因爲初始化, 複製了施法序列.")
                            runtimeContext._ACTIVESPELLSEQUENCE = copy.deepcopy(quest._SPELLSEQUENCE)

                    ########### 不打開地圖, 執行自動寶箱
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
                        Sleep(0.5)
                        while 1:
                            Sleep(3)
                            _, dungState,screen = IdentifyState()
                            if dungState != DungeonState.Dungeon:
                                logger.info(f"已退出移動狀態. 當前狀態爲{dungState}.")
                                break
                            elif lastscreen is not None:
                                gray1 = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                                gray2 = cv2.cvtColor(lastscreen, cv2.COLOR_BGR2GRAY)
                                mean_diff = cv2.absdiff(gray1, gray2).mean()/255
                                logger.debug(f"移動停止檢查:{mean_diff:.2f}")
                                if mean_diff < 0.05:
                                    logger.info(f"停止移動. 誤差:{mean_diff}. 當前狀態爲{dungState}.")
                                    if dungState == DungeonState.Dungeon:
                                        targetInfoList.pop(0)
                                    break
                                lastscreen = screen
                    else: 
                        Sleep(1)
                        Press([777,150])

                        dungState, newTargetInfoList = StateSearch(waitTimer,targetInfoList)
                        
                        if newTargetInfoList == targetInfoList:
                            gameFrozen_map +=1
                            logger.info(f"地圖卡死檢測:{gameFrozen_map}")
                        else:
                            gameFrozen_map = 0
                        if gameFrozen_map > 50:
                            gameFrozen_map = 0
                            restartGame()

                        if (targetInfoList==None) or (targetInfoList == []):
                            logger.info("地下城目標完成. 地下城狀態結束.(僅限任務模式.)")
                            break

                        if (newTargetInfoList != targetInfoList):
                            if newTargetInfoList[0].activeSpellSequenceOverride:
                                logger.info("因爲目標信息變動, 重新複製了施法序列.")
                                runtimeContext._ACTIVESPELLSEQUENCE = copy.deepcopy(quest._SPELLSEQUENCE)
                            else:
                                logger.info("因爲目標信息變動, 清空了施法序列.")
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
            logger.info("奇怪, 任務怎麼已經接了.")
            FindCoordsOrElseExecuteFallbackAndWait('Inn',['return',[1,1]],1)

    def DungeonFarm():
        nonlocal runtimeContext
        state = None
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
                        nonlocal state
                        state=IdentifyState()[0]
                    RestartableSequenceExecution(
                        lambda: _identifyState()
                        )
                    logger.info(f"下一狀態: {state}")
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
                            summary_text += f"累計戰鬥{runtimeContext._COUNTERCOMBAT}次.戰鬥平均用時{round(runtimeContext._TIME_COMBAT_TOTAL/runtimeContext._COUNTERCOMBAT,2)}秒."
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
                    targetInfoList = quest._TARGETINFOLIST.copy()
                    RestartableSequenceExecution(
                        lambda: StateDungeon(targetInfoList)
                        )
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
                        lambda: FindCoordsOrElseExecuteFallbackAndWait('Inn',['returntotown','returnText','leaveDung','dialogueChoices/blessing',[1,1]],2)
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
                                    ['trait','combatActive','chestFlag','combatClose'],
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
                        lambda: FindCoordsOrElseExecuteFallbackAndWait('Inn',['returntotown','returnText','leaveDung','dialogueChoices/blessing',[1,1]],2)
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
                        lambda: FindCoordsOrElseExecuteFallbackAndWait('Inn',['returntotown','returnText','leaveDung','dialogueChoices/blessing',[1,1]],2)
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
                        lambda: FindCoordsOrElseExecuteFallbackAndWait('Inn',['returntotown','returnText','leaveDung','dialogueChoices/blessing',[1,1]],2)
                    )
                        continue
                    
                    logger.info("發現了巨人.")
                    RestartableSequenceExecution(
                        lambda: StateDungeon([TargetInfo('position','左上',[560,928+54],True),
                                              TargetInfo('harken2','左上')]),
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
                    logger.info("第二步: 返回要塞...")
                    RestartableSequenceExecution(
                        lambda: FindCoordsOrElseExecuteFallbackAndWait('Inn',['returntotown','returnText','leaveDung','dialogueChoices/blessing',[1,1]],2)
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
                        lambda: FindCoordsOrElseExecuteFallbackAndWait('Inn',['returntotown','returnText','leaveDung','dialogueChoices/blessing',[1,1]],2)
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
        runtimeContext = RuntimeContext()

        setting = set

        Sleep(1) # 沒有等utils初始化完成
        
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