import tkinter as tk
from tkinter import ttk, scrolledtext
import json
import os
import logging
import logging.handlers
import sys
import cv2
import time
import threading
import queue
import numpy as np

# 基礎模塊包括:
# LOGGER. 將輸入寫入到logger.txt文件中.
# CONFIG. 保存和寫入設置.
# CHANGES LOG. 彈窗展示更新文檔.
# TOOLTIP. 鼠標懸停時的提示.

############################################
THREE_DAYS_AGO = time.time() - 3 * 24 * 60 * 60
LOGS_FOLDER_NAME = "logs"
os.makedirs(LOGS_FOLDER_NAME, exist_ok=True)
for filename in os.listdir(LOGS_FOLDER_NAME):
    file_path = os.path.join(LOGS_FOLDER_NAME, filename)
    
    # 獲取最後修改時間
    creation_time = os.path.getmtime(file_path)
    
    # 如果文件創建時間早於3天前，且是文件，則刪除
    if os.path.isfile(file_path) and creation_time < THREE_DAYS_AGO:
        os.remove(file_path)
############################################
LOG_FILE_PREFIX = LOGS_FOLDER_NAME + "/log"
logger = logging.getLogger('WvDASLogger')

# ===========================================
# TRACE 日誌級別（低於 DEBUG，用於超詳細記錄）
# ===========================================
TRACE = 5
logging.addLevelName(TRACE, 'TRACE')

def trace(self, message, *args, **kwargs):
    """記錄 TRACE 級別日誌（超詳細，僅輸出到詳細日誌文件）"""
    if self.isEnabledFor(TRACE):
        self._log(TRACE, message, args, **kwargs)

# 將 trace 方法添加到 Logger 類
logging.Logger.trace = trace

# ===========================================
# 日誌文件路徑（全局變數，用於雙文件共享時間戳）
# ===========================================
_current_log_time = None

def _get_log_time():
    """獲取當前日誌時間戳（確保普通版和詳細版使用相同時間戳）"""
    global _current_log_time
    if _current_log_time is None:
        _current_log_time = time.strftime("%y%m%d-%H%M%S")
    return _current_log_time

def reset_log_time():
    """重置日誌時間戳（用於重新啟動日誌系統）"""
    global _current_log_time
    _current_log_time = None

# ===========================================
def setup_file_handler():
    """設置普通日誌文件處理器（DEBUG 級別以上）"""
    os.makedirs(LOGS_FOLDER_NAME, exist_ok=True)
    log_file_path = f"{LOG_FILE_PREFIX}_{_get_log_time()}.txt"
    
    file_handler = logging.FileHandler(log_file_path, mode='a', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)  # 只記錄 DEBUG 以上
    file_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - [%(module)s:%(funcName)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    return file_handler

def setup_verbose_file_handler():
    """設置詳細日誌文件處理器（TRACE 級別以上，包含所有詳細記錄）"""
    os.makedirs(LOGS_FOLDER_NAME, exist_ok=True)
    log_file_path = f"{LOG_FILE_PREFIX}_{_get_log_time()}_verbose.txt"
    
    file_handler = logging.FileHandler(log_file_path, mode='a', encoding='utf-8')
    file_handler.setLevel(TRACE)  # 記錄 TRACE 以上（包含所有）
    file_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - [%(module)s:%(funcName)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    return file_handler

# 使用線程安全的 Queue 而不是 multiprocessing.Queue
log_queue = queue.Queue(-1)
queue_listener = None

def StartLogListener():
    """啓動日誌監聽器（雙文件輸出）"""
    global queue_listener
    if queue_listener is None:
        reset_log_time()  # 重置時間戳，確保新日誌文件
        queue_listener = logging.handlers.QueueListener(
            log_queue,
            setup_file_handler(),         # 普通日誌（DEBUG 以上）
            setup_verbose_file_handler(), # 詳細日誌（TRACE 以上）
            respect_handler_level=True
        )
        queue_listener.start()
        logger.info(f"日誌系統啟動：普通版 log_{_get_log_time()}.txt / 詳細版 log_{_get_log_time()}_verbose.txt")


def StopLogListener():
    """停止日誌監聽器"""
    global queue_listener
    if queue_listener is not None:
        queue_listener.stop()
        queue_listener = None
#===========================================
class LoggerStream:
    """自定義流，將輸出重定向到logger"""
    def __init__(self, logger, log_level):
        self.logger = logger
        self.log_level = log_level
        self.buffer = ''  # 用於累積不完整的行
    
    def write(self, message):
        # 累積消息直到遇到換行符
        self.buffer += message
        while '\n' in self.buffer:
            line, self.buffer = self.buffer.split('\n', 1)
            if line:  # 跳過空行
                self.logger.log(self.log_level, line)
    
    def flush(self):
        # 處理緩衝區中剩餘的內容
        if self.buffer:
            self.logger.log(self.log_level, self.buffer)
            self.buffer = ''

def RegisterQueueHandler():
    """配置QueueHandler，將日誌發送到隊列"""
    # 保持原有的stdout/stderr重定向
    sys.stdout = LoggerStream(logger, logging.DEBUG)
    sys.stderr = LoggerStream(logger, logging.ERROR)
    
    # 創建QueueHandler並連接到全局隊列
    queue_handler = logging.handlers.QueueHandler(log_queue)
    queue_handler.setLevel(TRACE)  # 設為 TRACE 以捕獲所有日誌
    
    logger.setLevel(TRACE)  # logger 也設為 TRACE
    logger.addHandler(queue_handler)
    logger.propagate = False

def RegisterConsoleHandler():
    sys.stdout = sys.__stdout__
    sys.stderr = sys.__stderr__

    logger.setLevel(logging.DEBUG)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

class ScrolledTextHandler(logging.Handler):
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget
        self.text_widget.config(state=tk.DISABLED)

    def emit(self, record):
        msg = self.format(record)
        try:
            self.text_widget.config(state=tk.NORMAL)
            self.text_widget.insert(tk.END, msg + '\n')
            self.text_widget.see(tk.END)
            self.text_widget.config(state=tk.DISABLED)
        except Exception:
            self.handleError(record)
class SummaryLogFilter(logging.Filter):
    def filter(self, record):
        if hasattr(record, 'summary') and record.summary:
            return True
            
        return False

class LogLevelFilter(logging.Filter):
    """動態過濾日誌級別的 Filter，根據 checkbox 狀態決定是否顯示"""
    def __init__(self):
        super().__init__()
        # 預設顯示狀態: DEBUG=False, INFO=True, WARNING=True, ERROR=True
        self.show_debug = False
        self.show_info = True
        self.show_warning = True
        self.show_error = True
    
    def filter(self, record):
        level = record.levelno
        if level == logging.DEBUG:
            return self.show_debug
        elif level == logging.INFO:
            return self.show_info
        elif level == logging.WARNING:
            return self.show_warning
        elif level >= logging.ERROR:  # ERROR 和 CRITICAL
            return self.show_error
        return True  # 其他級別預設顯示
############################################
def ResourcePath(relative_path):
    """ 獲取資源的絕對路徑，適用於開發環境和 PyInstaller 打包環境 """
    try:
        # PyInstaller 創建一個臨時文件夾並將路徑存儲在 _MEIPASS 中
        base_path = sys._MEIPASS
    except Exception:
        # 未打包狀態 (開發環境)
        # 假設 script.py 位於 C:\Users\Arnold\Desktop\andsimscripts\src\
        # 並且 resources 位於 C:\Users\Arnold\Desktop\andsimscripts\resources\
        # 我們需要從 script.py 的目錄 (src) 回到上一級 (andsimscripts)
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        # 如果你的 script.py 和 resources 文件夾都在項目根目錄，則 base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)
def LoadJson(path):
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                loaded_config = json.load(f)
                return loaded_config
        else:
            return {}   
    except json.JSONDecodeError:
        logger.error(f"錯誤: 無法解析 {path}。將使用默認配置。")
        return {}
    except Exception as e:
        logger.error(f"錯誤: 加載配置時發生錯誤: {e}。將使用默認配置。")
        return {}
def LoadImage(path):
    try:
        # 嘗試讀取圖片
        img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
        # 手動拋出異常
            raise ValueError(f"[OpenCV 錯誤] 圖片加載失敗，路徑可能不存在或圖片損壞: {path}")
    except Exception as e:
        logger.error(f"加載圖片失敗: {str(e)}")
        return None
    return img
############################################
CONFIG_FILE = 'config.json'
def SaveConfigToFile(config_data):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=4)
        logger.info("配置已保存。")
        return True
    except Exception as e:
        logger.error(f"保存配置時發生錯誤: {e}")
        return False
def migrate_skill_config(config):
    """遷移舊版配置到新版角色配置

    新配置結構: {"first": {character, skill, level}, "after": {character, skill, level}}
    """
    needs_save = False

    # 檢查是否有舊版順序配置
    has_old_order_config = any(
        f"_AE_CASTER_{i}_SKILL_FIRST" in config
        for i in range(1, 7)
    )

    if has_old_order_config:
        logger.warning("[配置遷移] 偵測到舊版順序配置，已升級為角色配置模式")
        logger.warning("[配置遷移] 請重新設定技能配置")

        # 初始化空的角色配置
        config["_CHARACTER_SKILL_CONFIG"] = {
            "first": {"character": "", "skill": "", "level": "關閉"},
            "after": {"character": "", "skill": "", "level": "關閉"}
        }

        # 清理舊版欄位
        for i in range(1, 7):
            config.pop(f"_AE_CASTER_{i}_SKILL_FIRST", None)
            config.pop(f"_AE_CASTER_{i}_LEVEL_FIRST", None)
            config.pop(f"_AE_CASTER_{i}_SKILL_AFTER", None)
            config.pop(f"_AE_CASTER_{i}_LEVEL_AFTER", None)
        config.pop("_AE_CASTER_COUNT", None)
        needs_save = True

    # 若配置是舊版列表格式，轉換為新字典格式 - 已移除，因为 list 才是新格式
    # if "_CHARACTER_SKILL_CONFIG" in config:
    #    existing = config["_CHARACTER_SKILL_CONFIG"]
    #    if isinstance(existing, list):
    #        logger.warning("[配置遷移] 偵測到列表格式配置，已轉換為新格式")
    #        config["_CHARACTER_SKILL_CONFIG"] = {
    #            "first": {"character": "", "skill": "", "level": "關閉"},
    #            "after": {"character": "", "skill": "", "level": "關閉"}
    #        }
    #        needs_save = True

    if needs_save:
        SaveConfigToFile(config)

    return config

def LoadConfigFromFile(config_file_path = CONFIG_FILE):
    if config_file_path == None:
        config_file_path = CONFIG_FILE
    config = LoadJson((config_file_path))
    return migrate_skill_config(config)
def SetOneVarInConfig(var, value):
    data = LoadConfigFromFile()
    data[var] = value
    SaveConfigToFile(data)
###########################################
CHANGES_LOG = "CHANGES_LOG.md"
def ShowChangesLogWindow():
    log_window = tk.Toplevel()
    log_window.title("更新日誌")
    log_window.geometry("700x500")

    log_window.lift()  # 提升到最上層
    log_window.attributes('-topmost', True)  # 強制置頂
    log_window.after(100, lambda: log_window.attributes('-topmost', False))
    
    # 創建滾動文本框
    text_area = scrolledtext.ScrolledText(
        log_window, 
        wrap=tk.WORD,
        font=("Segoe UI", 10),
        padx=10,
        pady=10
    )
    text_area.pack(fill=tk.BOTH, expand=True)
    
    # 禁用文本編輯功能
    text_area.configure(state='disabled')
    
    # 嘗試讀取並顯示Markdown文件
    try:
        # 替換爲你的Markdown文件路徑
        with open(CHANGES_LOG, "r", encoding="utf-8") as file:
            markdown_content = file.read()
        
        # 臨時啓用文本框以插入內容
        text_area.configure(state='normal')
        text_area.delete(1.0, tk.END)
        text_area.insert(tk.INSERT, markdown_content)
        text_area.configure(state='disabled')
    
    except FileNotFoundError:
        text_area.configure(state='normal')
        text_area.insert(tk.INSERT, f"錯誤：未找到{CHANGES_LOG}文件")
        text_area.configure(state='disabled')
    
    except Exception as e:
        text_area.configure(state='normal')
        text_area.insert(tk.INSERT, f"讀取文件時出錯: {str(e)}")
        text_area.configure(state='disabled')
###########################################
QUEST_FILE = 'resources/quest/quest.json'
def BuildQuestReflection():
    try:
        data = LoadJson(ResourcePath(QUEST_FILE))
        
        quest_reflect_map = {}
        seen_names = set()
        
        # 遍歷所有任務代號
        for quest_code, quest_info in data.items():
            # 獲取本地化任務名稱
            quest_name = quest_info["questName"]
            
            # 檢查名稱是否重複
            if quest_name in seen_names:
                raise ValueError(f"Duplicate questName found: '{quest_name}'")
            
            # 添加到映射表和已見集合
            quest_reflect_map[quest_name] = quest_code
            seen_names.add(quest_name)
        
        return quest_reflect_map
    
    except KeyError as e:
        raise KeyError(f"不存在'questName'屬性: {e}.")
    except json.JSONDecodeError as e:
        logger.info(f"Error at line {e.lineno}, column {e.colno}: {e.msg}")
        logger.info(f"Problematic text: {e.doc[e.pos-30:e.pos+30]}")  # 顯示錯誤上下文
        exit()
    except FileNotFoundError as e:
        raise FileNotFoundError(f"{e}")
###########################################
IMAGE_FOLDER = fr'resources/images/'

# 全局模版快取 (In-Memory Cache)
_TEMPLATE_CACHE = {}

def LoadTemplateImage(shortPathOfTarget):
    global _TEMPLATE_CACHE
    
    # 1. 檢查快取
    if shortPathOfTarget in _TEMPLATE_CACHE:
        # logger.trace(f"[LoadTemplate] Hit Cache: {shortPathOfTarget}")
        return _TEMPLATE_CACHE[shortPathOfTarget]

    logger.trace(f"[LoadTemplate] Loading from disk: {shortPathOfTarget}")
    pathOfTarget = ResourcePath(os.path.join(IMAGE_FOLDER + f"{shortPathOfTarget}.png"))
    
    # 2. 讀取並解碼
    img = LoadImage(pathOfTarget)
    
    # 3. 存入快取 (即使是 None 也可以存，避免重複嘗試讀取不存在的檔案)
    if img is not None:
        _TEMPLATE_CACHE[shortPathOfTarget] = img
        
    return img

# 快取 combatActive 圖片列表（避免每次都掃描資料夾）
_COMBAT_ACTIVE_TEMPLATES_CACHE = None

def get_combat_active_templates():
    """自動掃描 images 資料夾中所有 combatActive* 圖片名稱
    Returns:
        list: 圖片名稱列表，例如 ['combatActive', 'combatActive_2', 'combatActive_3', 'combatActive_4']
    """
    global _COMBAT_ACTIVE_TEMPLATES_CACHE
    if _COMBAT_ACTIVE_TEMPLATES_CACHE is not None:
        return _COMBAT_ACTIVE_TEMPLATES_CACHE
    
    import glob
    images_path = ResourcePath(IMAGE_FOLDER)
    pattern = os.path.join(images_path, 'combatActive*.png')
    files = glob.glob(pattern)
    # 提取檔名（不含副檔名和路徑）
    templates = [os.path.splitext(os.path.basename(f))[0] for f in files]
    templates.sort()  # 確保順序一致
    _COMBAT_ACTIVE_TEMPLATES_CACHE = templates
    logger.debug(f"掃描到 combatActive 圖片: {templates}")
    return templates
###########################################
class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.widget.bind("<Enter>", self.show_tooltip)
        self.widget.bind("<Leave>", self.hide_tooltip)

    def show_tooltip(self, event=None):
        if self.tooltip_window:
            return
            
        # 獲取widget的位置和尺寸
        widget_x = self.widget.winfo_rootx()
        widget_y = self.widget.winfo_rooty()
        widget_width = self.widget.winfo_width()
        widget_height = self.widget.winfo_height()
        
        self.tooltip_window = tk.Toplevel(self.widget)
        self.tooltip_window.wm_overrideredirect(True)  # 移除窗口裝飾
        self.tooltip_window.attributes("-alpha", 0.95)  # 設置透明度
        
        # 創建標籤顯示文本
        label = ttk.Label(
            self.tooltip_window, 
            text=self.text, 
            background="#ffffe0", 
            relief="solid", 
            borderwidth=1,
            padding=(8, 4),
            font=("Arial", 10),
            justify="left",
            wraplength=300  # 自動換行寬度
        )
        label.pack()
        
        # 計算最佳顯示位置（默認在widget下方）
        x = widget_x + widget_width + 2
        y = widget_y + widget_height//2
        
        # 設置最終位置並顯示
        self.tooltip_window.wm_geometry(f"+{int(x)}+{int(y)}")
        self.tooltip_window.deiconify()

    def hide_tooltip(self, event=None):
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None

def CreateToolTip(widget, text):
    toolTip = Tooltip(widget, text)
    return toolTip