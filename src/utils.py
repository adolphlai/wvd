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
        # 標準讀取：使用 IMREAD_COLOR (3 通道 BGR)
        img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError(f"[OpenCV 錯誤] 圖片加載失敗: {path}")
    except Exception as e:
        logger.error(f"加載圖片失敗: {str(e)}")
        return None
    return img

def LoadImageWithAlpha(path):
    """讀取圖片並保留 Alpha 通道（用於技能圖片等需要透明度的場景）"""
    try:
        img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        if img is None:
            raise ValueError(f"[OpenCV 錯誤] 圖片加載失敗: {path}")
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
    # NOTE: 僅技能圖片使用 Alpha 通道讀取，其他圖片使用標準 BGR 讀取
    if "spellskill" in shortPathOfTarget:
        img = LoadImageWithAlpha(pathOfTarget)
    else:
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

def smart_clean_image(input_path, output_path=None, threshold=50):
    """對圖片進行智慧去背處理（亮度門檻 + 四角背景色排除）
    
    Args:
        input_path: 原始圖片路徑
        output_path: 輸出路徑，若為 None 則覆蓋原檔
        threshold: 背景色差閥值，越大則去背範圍越廣
        
    Returns:
        bool: 處理成功與否
    """
    try:
        img = cv2.imdecode(np.fromfile(input_path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            logger.error(f"[去背] 無法讀取圖片: {input_path}")
            return False
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # 1. 亮度門檻：文字通常是白色（高亮），背景亮度較低
        lumi_mask = np.where(gray > 90, 255, 0).astype(np.uint8)
        
        # 2. 多點背景色排除：偵測四個角落的背景色
        corners = [img[0, 0], img[0, -1], img[-1, 0], img[-1, -1]]
        color_masks = []
        for bg_color in corners:
            diff = np.sqrt(np.sum((img.astype(float) - bg_color.astype(float))**2, axis=2))
            color_masks.append(np.where(diff < threshold, 0, 255).astype(np.uint8))
        
        # 合併遮罩：必須同時滿足「非背景色」且「具有一定亮度」
        final_mask = lumi_mask
        for c_mask in color_masks:
            final_mask = cv2.bitwise_and(final_mask, c_mask)
        
        # 平滑處理
        final_mask = cv2.GaussianBlur(final_mask, (3, 3), 0)
        
        # 轉為 BGRA 並設定 Alpha 通道
        bgra = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
        bgra[:, :, 3] = final_mask
        
        # 輸出
        save_path = output_path if output_path else input_path
        success, encoded = cv2.imencode('.png', bgra)
        if success:
            with open(save_path, 'wb') as f:
                encoded.tofile(f)
            logger.info(f"[去背] 完成: {save_path}")
            return True
        else:
            logger.error(f"[去背] 編碼失敗: {save_path}")
            return False
            
    except Exception as e:
        logger.error(f"[去背] 處理失敗: {e}")
        return False

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

###########################################
# ===== Minimap 移動安全判斷 =====
###########################################

# 小地圖 ROI（用於 harken 避讓偵測）
MINIMAP_HARKEN_ROI = [722, 92, 802, 180]  # [x1, y1, x2, y2]

# 相似度閾值，> 0.8 判定為撞牆（小地圖沒變）
MINIMAP_SIMILARITY_THRESHOLD = 0.8

# 全域模板快取
_MINIMAP_AVOID_TEMPLATES = None
_MINIMAP_DIRECTION_TEMPLATES = None

def load_minimap_templates():
    """載入小地圖模板（harken 和方向圖標）

    Returns:
        tuple: (avoid_templates, direction_templates)
            - avoid_templates: list of (filename, image) for harken icons
            - direction_templates: dict {direction: image} for direction icons
    """
    global _MINIMAP_AVOID_TEMPLATES, _MINIMAP_DIRECTION_TEMPLATES

    # 如果已載入，直接返回快取
    if _MINIMAP_AVOID_TEMPLATES is not None and _MINIMAP_DIRECTION_TEMPLATES is not None:
        return _MINIMAP_AVOID_TEMPLATES, _MINIMAP_DIRECTION_TEMPLATES

    minimap_dir = ResourcePath("resources/images/minimap")

    # 載入 harken 模板
    avoid_files = ["minimap-bharken.png", "minimap-mharken.png", "minimap-sharken.png"]
    avoid_templates = []

    logger.debug("[Minimap] 載入 Harken 避讓圖案...")
    for fname in avoid_files:
        path = os.path.join(minimap_dir, fname)
        if os.path.exists(path):
            img = LoadImage(path)
            if img is not None:
                avoid_templates.append((fname, img))
                logger.debug(f"  - {fname} (已載入)")
            else:
                logger.warning(f"  - {fname} (讀取失敗)")
        else:
            logger.warning(f"  - {fname} (不存在: {path})")

    # 載入方向圖標
    direction_files = {
        "上": "minimap-up.png",
        "下": "minimap-down.png",
        "左": "minimap-left.png",
        "右": "minimap-right.png"
    }
    direction_templates = {}

    logger.debug("[Minimap] 載入方向圖標...")
    for direction, fname in direction_files.items():
        path = os.path.join(minimap_dir, fname)
        if os.path.exists(path):
            img = LoadImage(path)
            if img is not None:
                direction_templates[direction] = img
                logger.debug(f"  - {fname} ({direction}) (已載入)")
            else:
                logger.warning(f"  - {fname} (讀取失敗)")
        else:
            logger.warning(f"  - {fname} (不存在: {path})")

    # 快取結果
    _MINIMAP_AVOID_TEMPLATES = avoid_templates
    _MINIMAP_DIRECTION_TEMPLATES = direction_templates

    logger.info(f"[Minimap] 模板載入完成: {len(avoid_templates)} 個 Harken, {len(direction_templates)} 個方向")
    return avoid_templates, direction_templates


def get_minimap_roi(screen_image):
    """從截圖中提取小地圖 ROI 區域

    Args:
        screen_image: 完整螢幕截圖

    Returns:
        numpy.ndarray: 小地圖區域圖像
    """
    x1, y1, x2, y2 = MINIMAP_HARKEN_ROI
    return screen_image[y1:y2, x1:x2].copy()


def detect_character_direction(minimap_img, direction_templates=None):
    """偵測角色當前朝向（方向圖標）

    Args:
        minimap_img: 小地圖圖像
        direction_templates: 方向模板字典，若為 None 則自動載入

    Returns:
        str or None: "上" / "下" / "左" / "右" / None
    """
    if minimap_img is None:
        return None

    if direction_templates is None:
        _, direction_templates = load_minimap_templates()

    if not direction_templates:
        return None

    best_direction = None
    best_score = 0.0

    for direction, template in direction_templates.items():
        if template.shape[0] > minimap_img.shape[0] or template.shape[1] > minimap_img.shape[1]:
            continue

        res = cv2.matchTemplate(minimap_img, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(res)

        if max_val > best_score:
            best_score = max_val
            best_direction = direction

    if best_score > 0.8:
        return best_direction
    return None


def get_harken_absolute_direction(minimap_img, avoid_templates=None):
    """偵測 harken 相對於小地圖中心的絕對方位

    Args:
        minimap_img: 小地圖圖像
        avoid_templates: harken 模板列表，若為 None 則自動載入

    Returns:
        str or None: "上" / "下" / "左" / "右" / None
    """
    if minimap_img is None:
        return None

    if avoid_templates is None:
        avoid_templates, _ = load_minimap_templates()

    h, w = minimap_img.shape[:2]
    center_x, center_y = w // 2, h // 2

    for name, template in avoid_templates:
        if template.shape[0] > h or template.shape[1] > w:
            continue

        res = cv2.matchTemplate(minimap_img, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)

        if max_val > 0.9:
            # max_loc 是模板匹配的左上角，計算模板中心
            th, tw = template.shape[:2]
            harken_cx = max_loc[0] + tw // 2
            harken_cy = max_loc[1] + th // 2

            # 計算相對偏移
            dx = harken_cx - center_x
            dy = harken_cy - center_y

            # 判斷主要方位（取絕對值較大的軸）
            if abs(dx) > abs(dy):
                return "右" if dx > 0 else "左"
            else:
                return "下" if dy > 0 else "上"

    return None


def absolute_to_relative_direction(absolute_dir, facing):
    """將絕對方位轉換成相對於角色面向的方位

    移動方向是相對於角色面向的：
    - 角色面向「上」時，按「上」會往地圖上方走
    - 角色面向「下」時，按「上」會往地圖下方走（180度旋轉）
    - 角色面向「左」時，按「上」會往地圖左方走（90度逆時針）
    - 角色面向「右」時，按「上」會往地圖右方走（90度順時針）

    Args:
        absolute_dir: harken 的絕對方位（小地圖座標系）
        facing: 角色面向

    Returns:
        str or None: 會碰到 harken 的移動按鍵方向
    """
    if absolute_dir is None or facing is None:
        return None

    # 轉換表：facing -> {absolute_dir -> 會碰到的移動按鍵}
    transform = {
        "上": {"上": "上", "下": "下", "左": "左", "右": "右"},
        "下": {"上": "下", "下": "上", "左": "右", "右": "左"},
        "左": {"上": "右", "下": "左", "左": "上", "右": "下"},
        "右": {"上": "左", "下": "右", "左": "下", "右": "上"},
    }

    return transform.get(facing, {}).get(absolute_dir)


def is_safe_to_move(minimap_img, direction, avoid_templates=None, direction_templates=None):
    """檢查移動方向是否安全（避免進入 harken）

    邏輯：
    1. 偵測 harken 的絕對方位
    2. 偵測角色面向
    3. 計算哪個移動按鍵會碰到 harken
    4. 阻止該方向的移動

    Args:
        minimap_img: 小地圖圖像
        direction: 欲移動的方向（"上"/"下"/"左"/"右"）
        avoid_templates: harken 模板列表
        direction_templates: 方向模板字典

    Returns:
        tuple: (is_safe: bool, danger_direction: str or None)
    """
    if minimap_img is None:
        return False, None

    # 自動載入模板
    if avoid_templates is None or direction_templates is None:
        avoid_templates, direction_templates = load_minimap_templates()

    # 偵測 harken 絕對方位
    harken_abs = get_harken_absolute_direction(minimap_img, avoid_templates)

    if harken_abs is None:
        return True, None  # 沒有 harken，安全

    # 偵測角色面向
    facing = detect_character_direction(minimap_img, direction_templates)
    logger.debug(f"[Harken避讓] Harken 在絕對 {harken_abs} 方，角色面向 {facing}")

    if facing is None:
        logger.warning("[Harken避讓] 無法偵測角色面向，預設阻止移動")
        return False, harken_abs

    # 計算哪個按鍵會碰到 harken
    danger_direction = absolute_to_relative_direction(harken_abs, facing)
    logger.debug(f"[Harken避讓] 按「{danger_direction}」會碰到 harken")

    if danger_direction == direction:
        logger.info(f"[Harken避讓] 移動方向 ({direction}) 會碰到 harken，阻止")
        return False, danger_direction
    else:
        logger.debug(f"[Harken避讓] 移動方向 ({direction}) 不會碰到 harken，允許")
        return True, danger_direction


def compare_minimap_images(img1, img2):
    """比較兩張小地圖的相似度（SSIM）

    Args:
        img1: 第一張圖像
        img2: 第二張圖像

    Returns:
        float: 相似度 0.0-1.0，1.0 為完全相同
    """
    try:
        from skimage.metrics import structural_similarity as ssim
    except ImportError:
        logger.warning("[Minimap] skimage 未安裝，使用簡易比較")
        # 簡易比較：計算像素差異
        diff = cv2.absdiff(img1, img2)
        return 1.0 - (np.mean(diff) / 255.0)

    # 轉為灰階
    gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)

    # 計算 SSIM
    score, _ = ssim(gray1, gray2, full=True)
    return score