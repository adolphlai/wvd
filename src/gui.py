import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import os
import logging
from script import *
from auto_updater import *
from utils import *

############################################
class ConfigPanelApp(tk.Toplevel):
    def __init__(self, master_controller, version, msg_queue):
        self.URL = "https://github.com/arnold2957/wvd"
        self.TITLE = f"WvDAS 巫術daphne自動刷怪 v{version} @德德Dellyla(B站)"
        self.INTRODUCTION = f"遇到問題? 請訪問:\n{self.URL} \n或加入Q羣: 922497356."

        RegisterQueueHandler()
        StartLogListener()

        super().__init__(master_controller)
        self.controller = master_controller
        self.msg_queue = msg_queue
        self.geometry('880x640')  # 調整視窗大小以配合縮小的日誌區域
        
        self.title(self.TITLE)

        self.adb_active = False

        # 關閉時退出整個程序
        self.protocol("WM_DELETE_WINDOW", self.controller.on_closing)

        # --- 任務狀態 ---
        self.quest_active = False

        # --- ttk Style ---
        #
        self.style = ttk.Style()
        self.style.configure("custom.TCheckbutton")
        self.style.map("Custom.TCheckbutton",
            foreground=[("disabled selected", "#8CB7DF"),("disabled", "#A0A0A0"), ("selected", "#196FBF")])
        self.style.configure("BoldFont.TCheckbutton", font=("微軟雅黑", 9,"bold"))
        self.style.configure("LargeFont.TCheckbutton", font=("微軟雅黑", 12,"bold"))

        # --- UI 變量 ---
        self.config = LoadConfigFromFile()
        for attr_name, var_type, var_config_name, var_default_value in CONFIG_VAR_LIST:
            if issubclass(var_type, tk.Variable):
                setattr(self, attr_name, var_type(value = self.config.get(var_config_name,var_default_value)))
            else:
                setattr(self, attr_name, var_type(self.config.get(var_config_name,var_default_value)))

        # === 技能分組預設配置 ===
        self.character_skill_presets = self.config.get("_SKILL_PRESETS", [])
        # 如果預設列表為空，嘗試從當前配置遷移
        if not self.character_skill_presets:
            current_cfg = self.config.get("_CHARACTER_SKILL_CONFIG", [])
            if isinstance(current_cfg, list) and any(c.get("character") for c in current_cfg):
                self.character_skill_presets.append(current_cfg)
                # 設定第一個名字為 "預設配置"
                names = list(self.skill_preset_names_var.get())
                if names:
                    names[0] = "預設配置"
                    self.skill_preset_names_var.set(names)
            
        # 確保有 10 組預設
        while len(self.character_skill_presets) < 10:
            empty_preset = []
            for _ in range(6):
                empty_preset.append({
                    "character": "", "skill_first": "", "level_first": "關閉",
                    "skill_after": "", "level_after": "關閉"
                })
            self.character_skill_presets.append(empty_preset)

        # 當前活躍的配置（從當前預設索引載入）
        idx = self.current_skill_preset_index_var.get()
        if idx < 0 or idx >= 10:
            idx = 0
            self.current_skill_preset_index_var.set(0)
        
        self.character_skill_config = self.character_skill_presets[idx]
        self.character_skill_rows = []  # 會在 _create_skills_tab 中填充

        self.create_widgets()
        self.update_organize_backpack_state()  # 初始化整理背包狀態

        

        logger.info("**********************************")
        logger.info(f"當前版本: {version}")
        logger.info(self.INTRODUCTION, extra={"summary": True})
        logger.info("**********************************")
        
        if self.last_version.get() != version:
            self.last_version.set(version)
            self.save_config()

    def save_config(self):
        def standardize_karma_input():
          if self.karma_adjust_var.get().isdigit():
              valuestr = self.karma_adjust_var.get()
              self.karma_adjust_var.set('+' + valuestr)
        standardize_karma_input()

        emu_path = self.emu_path_var.get()
        emu_path = emu_path.replace("HD-Adb.exe", "HD-Player.exe")
        self.emu_path_var.set(emu_path)

        for attr_name, var_type, var_config_name, _ in CONFIG_VAR_LIST:
            if issubclass(var_type, tk.Variable):
                self.config[var_config_name] = getattr(self, attr_name).get()

        if self.farm_target_text_var.get() in DUNGEON_TARGETS:
            self.farm_target_var.set(DUNGEON_TARGETS[self.farm_target_text_var.get()])
        else:
            self.farm_target_var.set(None)

        # 儲存角色技能配置
        self.config["_CHARACTER_SKILL_CONFIG"] = self.character_skill_config
        self.config["_SKILL_PRESETS"] = self.character_skill_presets
        self.config["_SKILL_PRESET_NAMES"] = list(self.skill_preset_names_var.get())

        SaveConfigToFile(self.config)

    def updata_config(self):
        config = LoadConfigFromFile()
        if '_KARMAADJUST' in config:
            self.karma_adjust_var.set(config['_KARMAADJUST'])

    def create_widgets(self):
        # 設定 grid 權重讓日誌區域自動填滿右側空間
        self.columnconfigure(1, weight=1)  # column 1 (日誌區) 自動擴展
        self.rowconfigure(0, weight=1)     # row 0 自動擴展
        
        # === 右側容器 (包含過濾器 + LOG 顯示區域) ===
        right_frame = ttk.Frame(self)
        right_frame.grid(row=0, column=1, rowspan=2, sticky=(tk.N, tk.S, tk.E, tk.W), padx=5, pady=5)
        
        # === 日誌過濾器 checkbox ===
        log_filter_frame = ttk.Frame(right_frame)
        log_filter_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(log_filter_frame, text="日誌過濾:").pack(side=tk.LEFT, padx=(5, 2))
        
        # 創建 filter 實例（用於動態過濾）
        self.log_level_filter = LogLevelFilter()
        
        # checkbox 變數
        self.show_debug_var = tk.BooleanVar(value=False)
        self.show_info_var = tk.BooleanVar(value=True)
        self.show_warning_var = tk.BooleanVar(value=True)
        self.show_error_var = tk.BooleanVar(value=True)
        
        def update_log_filter():
            """更新 filter 的顯示狀態"""
            self.log_level_filter.show_debug = self.show_debug_var.get()
            self.log_level_filter.show_info = self.show_info_var.get()
            self.log_level_filter.show_warning = self.show_warning_var.get()
            self.log_level_filter.show_error = self.show_error_var.get()
        
        ttk.Checkbutton(log_filter_frame, text="DEBUG", variable=self.show_debug_var,
                        command=update_log_filter).pack(side=tk.LEFT, padx=2)
        ttk.Checkbutton(log_filter_frame, text="INFO", variable=self.show_info_var,
                        command=update_log_filter).pack(side=tk.LEFT, padx=2)
        ttk.Checkbutton(log_filter_frame, text="WARN", variable=self.show_warning_var,
                        command=update_log_filter).pack(side=tk.LEFT, padx=2)
        ttk.Checkbutton(log_filter_frame, text="ERROR", variable=self.show_error_var,
                        command=update_log_filter).pack(side=tk.LEFT, padx=2)

        # === 日誌顯示區域 ===
        scrolled_text_formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s', datefmt='%H:%M:%S')
        self.log_display = scrolledtext.ScrolledText(right_frame, wrap=tk.WORD, state=tk.DISABLED, bg='#ffffff', bd=2, relief=tk.FLAT, width=55, height=28)
        self.log_display.pack(fill=tk.BOTH, expand=True)
        self.scrolled_text_handler = ScrolledTextHandler(self.log_display)
        self.scrolled_text_handler.setLevel(logging.DEBUG)  # 降低 level 讓 DEBUG 訊息能通過
        self.scrolled_text_handler.setFormatter(scrolled_text_formatter)
        self.scrolled_text_handler.addFilter(self.log_level_filter)  # 添加動態過濾器
        logger.addHandler(self.scrolled_text_handler)

        # === 摘要顯示區域 ===
        self.summary_log_display = scrolledtext.ScrolledText(right_frame, wrap=tk.WORD, state=tk.DISABLED, bg="#C6DBF4", bd=2, width=55)
        self.summary_log_display.pack(fill=tk.X, pady=(5, 0))
        self.summary_text_handler = ScrolledTextHandler(self.summary_log_display)
        self.summary_text_handler.setLevel(logging.INFO)
        self.summary_text_handler.setFormatter(scrolled_text_formatter)
        self.summary_text_handler.addFilter(SummaryLogFilter())
        original_emit = self.summary_text_handler.emit
        def new_emit(record):
            self.summary_log_display.configure(state='normal')
            self.summary_log_display.delete(1.0, tk.END)
            self.summary_log_display.configure(state='disabled')
            original_emit(record)
        self.summary_text_handler.emit = new_emit
        logger.addHandler(self.summary_text_handler)

        # === 主框架（左側）===
        self.main_frame = ttk.Frame(self, padding="10")
        self.main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # === 分頁控件 ===
        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 創建五個分頁
        self.tab_general = ttk.Frame(self.notebook, padding=10)
        self.tab_skills = ttk.Frame(self.notebook, padding=10)
        self.tab_advanced = ttk.Frame(self.notebook, padding=10)
        self.tab_test = ttk.Frame(self.notebook, padding=10)

        self.notebook.add(self.tab_general, text="一般設定")
        self.notebook.add(self.tab_skills, text="技能設定")
        self.notebook.add(self.tab_advanced, text="進階設定")
        self.notebook.add(self.tab_test, text="測試")

        # 驗證命令（數字輸入）
        vcmd_non_neg = self.register(lambda x: ((x=="")or(x.isdigit())))

        # checkcommand 用於多個地方
        def checkcommand():
            self.save_config()

        # =============================================
        # Tab 1: 一般設定
        # =============================================
        self._create_general_tab(vcmd_non_neg)

        # =============================================
        # Tab 3: 技能設定
        # =============================================
        self._create_skills_tab(vcmd_non_neg)

        # =============================================
        # Tab 4: 進階設定
        # =============================================
        self._create_advanced_tab(vcmd_non_neg, checkcommand)

        # =============================================
        # Tab 5: 測試
        # =============================================
        self._create_test_tab()

        # === 更新提示區域（默認隱藏）===
        self.update_sep = ttk.Separator(self.main_frame, orient='horizontal')
        self.update_sep.grid(row=1, column=0, columnspan=3, sticky='ew', pady=10)

        frame_row_update = tk.Frame(self.main_frame)
        frame_row_update.grid(row=2, column=0, sticky=tk.W)

        self.find_update = ttk.Label(frame_row_update, text="發現新版本:",foreground="red")
        self.find_update.grid(row=0, column=0, sticky=tk.W)

        self.update_text = ttk.Label(frame_row_update, textvariable=self.latest_version,foreground="red")
        self.update_text.grid(row=0, column=1, sticky=tk.W)

        self.button_auto_download = ttk.Button(
            frame_row_update,
            text="自動下載",
            width=7
            )
        self.button_auto_download.grid(row=0, column=2, sticky=tk.W, padx= 5)

        def open_url():
            url = os.path.join(self.URL, "releases")
            if sys.platform == "win32":
                os.startfile(url)
            elif sys.platform == "darwin":
                os.system(f"open {url}")
            else:
                os.system(f"xdg-open {url}")
        self.button_manual_download = ttk.Button(
            frame_row_update,
            text="手動下載最新版",
            command=open_url,
            width=7
            )
        self.button_manual_download.grid(row=0, column=3, sticky=tk.W)

        self.update_sep.grid_remove()
        self.find_update.grid_remove()
        self.update_text.grid_remove()
        self.button_auto_download.grid_remove()
        self.button_manual_download.grid_remove()

    def _create_general_tab(self, vcmd_non_neg):
        """一般設定分頁：模擬器連接、地下城目標、開箱人選"""
        tab = self.tab_general
        row = 0

        # --- 模擬器連接 ---
        frame_adb = ttk.LabelFrame(tab, text="模擬器連接", padding=5)
        frame_adb.grid(row=row, column=0, sticky="ew", pady=5)

        self.adb_status_label = ttk.Label(frame_adb)
        self.adb_status_label.grid(row=0, column=0, padx=5)

        # 隱藏的Entry用於存儲變量
        adb_entry = ttk.Entry(frame_adb, textvariable=self.emu_path_var)
        adb_entry.grid_remove()

        def selectADB_PATH():
            path = filedialog.askopenfilename(
                title="選擇ADB執行檔",
                filetypes=[("Executable", "*.exe"), ("All files", "*.*")]
            )
            if path:
                self.emu_path_var.set(path)
                self.save_config()

        self.adb_path_change_button = ttk.Button(frame_adb, text="修改", command=selectADB_PATH, width=5)
        self.adb_path_change_button.grid(row=0, column=1, padx=2)

        def update_adb_status(*args):
            if self.emu_path_var.get():
                self.adb_status_label.config(text="已設置模擬器", foreground="green")
            else:
                self.adb_status_label.config(text="未設置模擬器", foreground="red")

        self.emu_path_var.trace_add("write", lambda *args: update_adb_status())
        update_adb_status()

        ttk.Label(frame_adb, text="端口:").grid(row=0, column=2, padx=(10, 2))
        self.adb_port_entry = ttk.Entry(frame_adb, textvariable=self.adb_port_var, validate="key",
                                        validatecommand=(vcmd_non_neg, '%P'), width=6)
        self.adb_port_entry.grid(row=0, column=3)
        self.button_save_adb_port = ttk.Button(frame_adb, text="儲存", command=self.save_config, width=5)
        self.button_save_adb_port.grid(row=0, column=4, padx=2)

        # --- 地下城目標 ---
        row += 1
        frame_target = ttk.LabelFrame(tab, text="地下城目標", padding=5)
        frame_target.grid(row=row, column=0, sticky="ew", pady=5)

        ttk.Label(frame_target, text="目標:").grid(row=0, column=0, padx=5)
        self.farm_target_combo = ttk.Combobox(frame_target, textvariable=self.farm_target_text_var,
                                              values=list(DUNGEON_TARGETS.keys()), state="readonly", width=28)
        self.farm_target_combo.grid(row=0, column=1, sticky="ew", padx=5)
        self.farm_target_combo.bind("<<ComboboxSelected>>", lambda e: self.save_config())

        # --- 開箱人選 ---
        row += 1
        frame_chest = ttk.LabelFrame(tab, text="開箱設定", padding=5)
        frame_chest.grid(row=row, column=0, sticky="ew", pady=5)

        ttk.Label(frame_chest, text="開箱人選:").grid(row=0, column=0, padx=5)
        self.open_chest_mapping = {
            0:"隨機", 1:"左上", 2:"中上", 3:"右上",
            4:"左下", 5:"中下", 6:"右下",
        }
        self.who_will_open_text_var = tk.StringVar(value=self.open_chest_mapping[self.who_will_open_it_var.get()])
        self.who_will_open_combobox = ttk.Combobox(
            frame_chest,
            textvariable=self.who_will_open_text_var,
            values=list(self.open_chest_mapping.values()),
            state="readonly",
            width=6
        )
        self.who_will_open_combobox.grid(row=0, column=1, padx=5)

        def handle_open_chest_selection(event=None):
            open_chest_reverse_mapping = {v: k for k, v in self.open_chest_mapping.items()}
            self.who_will_open_it_var.set(open_chest_reverse_mapping[self.who_will_open_text_var.get()])
            self.save_config()
        self.who_will_open_combobox.bind("<<ComboboxSelected>>", handle_open_chest_selection)

        # --- 啟動/停止按鈕 ---
        row += 1
        ttk.Separator(tab, orient='horizontal').grid(row=row, column=0, sticky="ew", pady=10)
        
        row += 1
        button_frame = ttk.Frame(tab)
        button_frame.grid(row=row, column=0, sticky="ew", pady=5)
        button_frame.columnconfigure(0, weight=1)

        s = ttk.Style()
        s.configure('start.TButton', font=('微軟雅黑', 15), padding=(0, 5))
        
        def btn_command():
            self.save_config()
            self.toggle_start_stop()
        
        self.start_stop_btn = ttk.Button(
            button_frame,
            text="腳本, 啟動!",
            command=btn_command,
            style='start.TButton',
        )
        self.start_stop_btn.grid(row=0, column=0, sticky='ew', padx=5, pady=10)

        # --- 即時監控面板 ---
        row += 1
        self.monitor_frame = ttk.LabelFrame(tab, text="即時監控", padding=5)
        self.monitor_frame.grid(row=row, column=0, sticky="ew", pady=5)

        # 第一行：狀態 / 目標
        ttk.Label(self.monitor_frame, text="監控狀態:", font=("微軟雅黑", 9, "bold")).grid(row=0, column=0, sticky=tk.W, padx=2)
        self.monitor_state_var = tk.StringVar(value="-")
        ttk.Label(self.monitor_frame, textvariable=self.monitor_state_var, width=12).grid(row=0, column=1, sticky=tk.W)

        ttk.Label(self.monitor_frame, text="當前目標:", font=("微軟雅黑", 9, "bold")).grid(row=0, column=2, sticky=tk.W, padx=(20, 2))
        self.monitor_target_var = tk.StringVar(value="-")
        ttk.Label(self.monitor_frame, textvariable=self.monitor_target_var, width=15).grid(row=0, column=3, sticky=tk.W)

        # 第二行：完成地城 / 運行時間
        ttk.Label(self.monitor_frame, text="完成次數:", font=("微軟雅黑", 9, "bold")).grid(row=1, column=0, sticky=tk.W, padx=2)
        self.monitor_dungeon_count_var = tk.StringVar(value="0 次")
        ttk.Label(self.monitor_frame, textvariable=self.monitor_dungeon_count_var, width=12).grid(row=1, column=1, sticky=tk.W)

        ttk.Label(self.monitor_frame, text="運行時間:", font=("微軟雅黑", 9, "bold")).grid(row=1, column=2, sticky=tk.W, padx=(20, 2))
        self.monitor_total_time_var = tk.StringVar(value="0 秒")
        ttk.Label(self.monitor_frame, textvariable=self.monitor_total_time_var, width=15).grid(row=1, column=3, sticky=tk.W)

        # 第三行：寶箱 / 寶箱效率
        ttk.Label(self.monitor_frame, text="寶箱總數:", font=("微軟雅黑", 9, "bold")).grid(row=2, column=0, sticky=tk.W, padx=2)
        self.monitor_chest_count_var = tk.StringVar(value="0 個")
        ttk.Label(self.monitor_frame, textvariable=self.monitor_chest_count_var, width=12).grid(row=2, column=1, sticky=tk.W)

        ttk.Label(self.monitor_frame, text="寶箱效率:", font=("微軟雅黑", 9, "bold")).grid(row=2, column=2, sticky=tk.W, padx=(20, 2))
        self.monitor_chest_efficiency_var = tk.StringVar(value="-")
        ttk.Label(self.monitor_frame, textvariable=self.monitor_chest_efficiency_var, width=15).grid(row=2, column=3, sticky=tk.W)

        # 第四行：戰鬥 / 戰鬥效率
        ttk.Label(self.monitor_frame, text="戰鬥次數:", font=("微軟雅黑", 9, "bold")).grid(row=3, column=0, sticky=tk.W, padx=2)
        self.monitor_combat_count_var = tk.StringVar(value="0 次")
        ttk.Label(self.monitor_frame, textvariable=self.monitor_combat_count_var, width=12).grid(row=3, column=1, sticky=tk.W)

        ttk.Label(self.monitor_frame, text="戰鬥效率:", font=("微軟雅黑", 9, "bold")).grid(row=3, column=2, sticky=tk.W, padx=(20, 2))
        self.monitor_combat_efficiency_var = tk.StringVar(value="-")
        ttk.Label(self.monitor_frame, textvariable=self.monitor_combat_efficiency_var, width=15).grid(row=3, column=3, sticky=tk.W)

        # 第五行：死亡 / 總效率
        ttk.Label(self.monitor_frame, text="死亡次數:", font=("微軟雅黑", 9, "bold")).grid(row=4, column=0, sticky=tk.W, padx=2)
        self.monitor_death_count_var = tk.StringVar(value="0 次")
        ttk.Label(self.monitor_frame, textvariable=self.monitor_death_count_var, width=12).grid(row=4, column=1, sticky=tk.W)

        ttk.Label(self.monitor_frame, text="總計效率:", font=("微軟雅黑", 9, "bold")).grid(row=4, column=2, sticky=tk.W, padx=(20, 2))
        self.monitor_total_efficiency_var = tk.StringVar(value="-")
        ttk.Label(self.monitor_frame, textvariable=self.monitor_total_efficiency_var, width=15).grid(row=4, column=3, sticky=tk.W)

        # 第六行：本地戰鬥 / 靜止計數
        ttk.Label(self.monitor_frame, text="本次戰鬥:", font=("微軟雅黑", 9, "bold")).grid(row=5, column=0, sticky=tk.W, padx=2)
        self.monitor_battle_var = tk.StringVar(value="第 0 戰")
        ttk.Label(self.monitor_frame, textvariable=self.monitor_battle_var, width=12).grid(row=5, column=1, sticky=tk.W)

        ttk.Label(self.monitor_frame, text="卡死偵測:", font=("微軟雅黑", 9, "bold")).grid(row=5, column=2, sticky=tk.W, padx=(20, 2))
        self.monitor_detection_var = tk.StringVar(value="靜止0/10 重試0/5")
        ttk.Label(self.monitor_frame, textvariable=self.monitor_detection_var, width=18).grid(row=5, column=3, sticky=tk.W)

        # 第七行：軟超時進度條
        # 第七行：軟超時進度條
        ttk.Label(self.monitor_frame, text="軟超時:", font=("微軟雅黑", 9, "bold")).grid(row=6, column=0, sticky=tk.W, padx=2)
        self.monitor_soft_timeout_progress = ttk.Progressbar(self.monitor_frame, length=200, mode='determinate', maximum=100)
        self.monitor_soft_timeout_progress.grid(row=6, column=1, columnspan=2, sticky=tk.W)
        self.monitor_soft_timeout_label = tk.StringVar(value="0/60s")
        ttk.Label(self.monitor_frame, textvariable=self.monitor_soft_timeout_label, width=8).grid(row=6, column=3, sticky=tk.W)

        # 第八行：硬超時進度條
        ttk.Label(self.monitor_frame, text="硬超時:", font=("微軟雅黑", 9, "bold")).grid(row=7, column=0, sticky=tk.W, padx=2)
        self.monitor_hard_timeout_progress = ttk.Progressbar(self.monitor_frame, length=200, mode='determinate', maximum=100)
        self.monitor_hard_timeout_progress.grid(row=7, column=1, columnspan=2, sticky=tk.W)
        self.monitor_hard_timeout_label = tk.StringVar(value="0/90s")
        ttk.Label(self.monitor_frame, textvariable=self.monitor_hard_timeout_label, width=8).grid(row=7, column=3, sticky=tk.W)

        # 第九行：地城識別
        ttk.Label(self.monitor_frame, text="地城移動:", font=("微軟雅黑", 9, "bold")).grid(row=8, column=0, sticky=tk.W, padx=2)
        self.monitor_flag_dung_var = tk.StringVar(value="0%")
        self.monitor_flag_dung_label = ttk.Label(self.monitor_frame, textvariable=self.monitor_flag_dung_var, width=6)
        self.monitor_flag_dung_label.grid(row=8, column=1, sticky=tk.W)
        
        ttk.Label(self.monitor_frame, text="地圖開啟:", font=("微軟雅黑", 9, "bold")).grid(row=8, column=2, sticky=tk.W, padx=(10, 2))
        self.monitor_flag_map_var = tk.StringVar(value="0%")
        self.monitor_flag_map_label = ttk.Label(self.monitor_frame, textvariable=self.monitor_flag_map_var, width=6)
        self.monitor_flag_map_label.grid(row=8, column=3, sticky=tk.W)

        # 第十行：寶箱/戰鬥識別
        ttk.Label(self.monitor_frame, text="寶箱開啟:", font=("微軟雅黑", 9, "bold")).grid(row=9, column=0, sticky=tk.W, padx=2)
        self.monitor_flag_chest_var = tk.StringVar(value="0%")
        self.monitor_flag_chest_label = ttk.Label(self.monitor_frame, textvariable=self.monitor_flag_chest_var, width=6)
        self.monitor_flag_chest_label.grid(row=9, column=1, sticky=tk.W)
        
        ttk.Label(self.monitor_frame, text="戰鬥開始:", font=("微軟雅黑", 9, "bold")).grid(row=9, column=2, sticky=tk.W, padx=(10, 2))
        self.monitor_flag_combat_var = tk.StringVar(value="0%")
        self.monitor_flag_combat_label = ttk.Label(self.monitor_frame, textvariable=self.monitor_flag_combat_var, width=6)
        self.monitor_flag_combat_label.grid(row=9, column=3, sticky=tk.W)

        # 第十一行：世界地圖識別
        ttk.Label(self.monitor_frame, text="世界地圖:", font=("微軟雅黑", 9, "bold")).grid(row=10, column=0, sticky=tk.W, padx=2)
        self.monitor_flag_world_var = tk.StringVar(value="0%")
        self.monitor_flag_world_label = ttk.Label(self.monitor_frame, textvariable=self.monitor_flag_world_var, width=6)
        self.monitor_flag_world_label.grid(row=10, column=1, sticky=tk.W)

        ttk.Label(self.monitor_frame, text="寶箱移動:", font=("微軟雅黑", 9, "bold")).grid(row=10, column=2, sticky=tk.W, padx=(10, 2))
        self.monitor_flag_chest_auto_var = tk.StringVar(value="0%")
        self.monitor_flag_chest_auto_label = ttk.Label(self.monitor_frame, textvariable=self.monitor_flag_chest_auto_var, width=6)
        self.monitor_flag_chest_auto_label.grid(row=10, column=3, sticky=tk.W)

        # 第十二行：AUTO比對
        ttk.Label(self.monitor_frame, text="AUTO比對:", font=("微軟雅黑", 9, "bold")).grid(row=11, column=0, sticky=tk.W, padx=2)
        self.monitor_flag_auto_var = tk.StringVar(value="0%")
        self.monitor_flag_auto_label = ttk.Label(self.monitor_frame, textvariable=self.monitor_flag_auto_var, width=6)
        self.monitor_flag_auto_label.grid(row=11, column=1, sticky=tk.W)

        ttk.Label(self.monitor_frame, text="血量偵測:", font=("微軟雅黑", 9, "bold")).grid(row=11, column=2, sticky=tk.W, padx=(10, 2))
        self.monitor_hp_status_var = tk.StringVar(value="--")
        self.monitor_hp_status_label = ttk.Label(self.monitor_frame, textvariable=self.monitor_hp_status_var, width=8)
        self.monitor_hp_status_label.grid(row=11, column=3, sticky=tk.W)

        # 第十三行：警告區域
        self.monitor_warning_var = tk.StringVar(value="")
        self.monitor_warning_label = ttk.Label(self.monitor_frame, textvariable=self.monitor_warning_var, foreground="red")
        self.monitor_warning_label.grid(row=12, column=0, columnspan=4, sticky=tk.W, pady=(5, 0))

        # 第十四行：角色比對
        ttk.Label(self.monitor_frame, text="角色:", font=("微軟雅黑", 9, "bold")).grid(row=13, column=0, sticky=tk.W, padx=2)
        self.monitor_character_var = tk.StringVar(value="未找到")
        self.monitor_character_label = ttk.Label(self.monitor_frame, textvariable=self.monitor_character_var, width=20)
        self.monitor_character_label.grid(row=13, column=1, columnspan=3, sticky=tk.W)

        # 保留未顯示但被引用的變數
        self.monitor_dungeon_state_var = tk.StringVar(value="-")
        self.monitor_karma_var = tk.StringVar(value="-")
        self.monitor_aoe_var = tk.StringVar(value="-")

        # 啟動監控更新定時器
        self._start_monitor_update()





    def _create_skills_tab(self, vcmd_non_neg):
        """技能設定分頁：按角色配置技能施放，6組角色配置"""
        tab = self.tab_skills
        row = 0

        # --- 配置預設管理 ---
        frame_presets = ttk.LabelFrame(tab, text="配置預設管理", padding=5)
        frame_presets.grid(row=row, column=0, sticky="ew", pady=5)

        ttk.Label(frame_presets, text="選擇預設:").grid(row=0, column=0, padx=5, sticky=tk.W)
        
        self.preset_combo = ttk.Combobox(
            frame_presets, 
            textvariable=tk.StringVar(value=""), # 暫時的值，稍後初始化
            values=list(self.skill_preset_names_var.get()),
            state="readonly", 
            width=20
        )
        self.preset_combo.current(self.current_skill_preset_index_var.get())
        self.preset_combo.grid(row=0, column=1, padx=5, sticky=tk.W)

        def on_preset_change(event=None):
            idx = self.preset_combo.current()
            if idx != -1:
                # 切換前先保存當前配置到原來的位置
                self._save_skill_config()
                
                # 更新索引並載入新預設
                self.current_skill_preset_index_var.set(idx)
                self.character_skill_config = self.character_skill_presets[idx]
                
                # 更新介面上的變數
                self._load_preset_to_ui()
                self.save_config()
                logger.info(f"已切換至預設: {self.preset_combo.get()}")

        self.preset_combo.bind("<<ComboboxSelected>>", on_preset_change)

        def rename_preset():
            idx = self.preset_combo.current()
            if idx == -1: return
            
            from tkinter import simpledialog
            old_name = self.preset_combo.get()
            new_name = simpledialog.askstring("重新命名預設", f"請輸入預設 '{old_name}' 的新名稱:", initialvalue=old_name)
            
            if new_name:
                names = list(self.skill_preset_names_var.get())
                names[idx] = new_name
                self.skill_preset_names_var.set(names)
                self.preset_combo['values'] = names
                self.preset_combo.current(idx)
                self.save_config()
                logger.info(f"預設已重新命名為: {new_name}")

        btn_rename = ttk.Button(frame_presets, text="重新命名", command=rename_preset, width=10)
        btn_rename.grid(row=0, column=2, padx=5)

        def clear_preset():
            idx = self.preset_combo.current()
            if idx == -1: return
            
            if messagebox.askyesno("清空預設", f"確定要清空預設 '{self.preset_combo.get()}' 嗎？"):
                empty_preset = []
                for _ in range(6):
                    empty_preset.append({
                        "character": "", "skill_first": "", "level_first": "關閉",
                        "skill_after": "", "level_after": "關閉"
                    })
                self.character_skill_presets[idx] = empty_preset
                self.character_skill_config = empty_preset
                self._load_preset_to_ui()
                self.save_config()
                logger.info(f"預設 '{self.preset_combo.get()}' 已清空")

        btn_clear = ttk.Button(frame_presets, text="清空預設", command=clear_preset, width=10)
        btn_clear.grid(row=0, column=3, padx=5)

        def save_preset():
            self._save_skill_config()
            logger.info(f"已手動儲存預設: {self.preset_combo.get()}")
            messagebox.showinfo("儲存成功", f"預設 '{self.preset_combo.get()}' 已儲存")

        btn_save = ttk.Button(frame_presets, text="儲存配置", command=save_preset, width=10)
        btn_save.grid(row=0, column=4, padx=5)

        row += 1

        # --- 自動戰鬥模式 ---
        frame_auto = ttk.LabelFrame(tab, text="自動戰鬥模式", padding=5)
        frame_auto.grid(row=row, column=0, sticky="ew", pady=5)

        ttk.Label(frame_auto, text="模式:").grid(row=0, column=0, padx=5, sticky=tk.W)
        auto_combat_options = ["完全自動", "1 場後自動", "2 場後自動", "3 場後自動", "完全手動"]
        self.auto_combat_mode_combo = ttk.Combobox(
            frame_auto, textvariable=self.auto_combat_mode_var,
            values=auto_combat_options, state="readonly", width=12
        )
        self.auto_combat_mode_combo.grid(row=0, column=1, padx=5, sticky=tk.W)
        self.auto_combat_mode_combo.bind("<<ComboboxSelected>>", lambda e: self.save_config())

        ttk.Label(frame_auto, text="※ 完全自動=進入戰鬥即開自動，2場後自動=前2場手動施法", foreground="gray").grid(
            row=1, column=0, columnspan=3, sticky=tk.W, pady=(2, 0))

        # --- 角色技能設定 ---
        row += 1
        frame_char_skill = ttk.LabelFrame(tab, text="角色技能設定", padding=10)
        frame_char_skill.grid(row=row, column=0, sticky="ew", pady=5)

        # Row 0: 觸發間隔
        ttk.Label(frame_char_skill, text="觸發間隔:").grid(row=0, column=0, sticky=tk.W)
        self.ae_caster_interval_entry = ttk.Entry(
            frame_char_skill, textvariable=self.ae_caster_interval_var,
            validate="key", validatecommand=(vcmd_non_neg, '%P'), width=5
        )
        self.ae_caster_interval_entry.grid(row=0, column=1, padx=2, sticky=tk.W)

        ttk.Label(frame_char_skill, text="※ 0=每場觸發，N=每N+1場觸發", foreground="gray").grid(
            row=0, column=2, columnspan=5, sticky=tk.W, padx=10)

        # Row 1: 說明文字
        ttk.Label(frame_char_skill,
                  text="※ 未識別角色時使用單體技能。新增角色請將頭像放入 resources/images/character/ 並重啟",
                  foreground="gray").grid(row=1, column=0, columnspan=8, sticky=tk.W, pady=(2, 8))

        # 類別選項與等級選項
        category_options = ["", "普攻", "單體", "橫排", "全體", "秘術", "群控"]
        level_options = ["關閉", "LV2", "LV3", "LV4", "LV5", "LV6", "LV7", "LV8", "LV9"]
        char_options = [""] + AVAILABLE_CHARACTERS

        # 表頭
        header_row = 2
        ttk.Label(frame_char_skill, text="", width=6).grid(row=header_row, column=0, sticky=tk.W)
        ttk.Label(frame_char_skill, text="角色", font=("微軟雅黑", 9, "bold")).grid(row=header_row, column=1, sticky=tk.W, padx=2)
        ttk.Label(frame_char_skill, text="類別", font=("微軟雅黑", 9, "bold")).grid(row=header_row, column=2, sticky=tk.W, padx=2)
        ttk.Label(frame_char_skill, text="技能", font=("微軟雅黑", 9, "bold")).grid(row=header_row, column=3, sticky=tk.W, padx=2)
        ttk.Label(frame_char_skill, text="等級", font=("微軟雅黑", 9, "bold")).grid(row=header_row, column=4, sticky=tk.W, padx=2)

        # 6 組角色配置，每組 2 行（首戰、二戰後）
        self.character_skill_groups = []  # 儲存6組配置的控件引用
        self.skill_combos_all = []  # 用於 set_controls_state

        def make_category_callback(group_idx, battle_type, category_var, skill_var, skill_combo):
            """類別變更時更新技能下拉選單"""
            def callback(event=None):
                category = category_var.get()
                if category == "":
                    skill_options = [""]
                    skill_var.set("")
                elif category == "普攻":
                    skill_options = ["", "attack"]
                    skill_var.set("attack")  # 自動選擇普攻
                else:
                    skills_from_folder = SKILLS_BY_CATEGORY.get(category, [])
                    skill_options = [""] + skills_from_folder
                    if skill_var.get() not in skill_options:
                        skill_var.set("")

                skill_combo['values'] = skill_options
                self._save_skill_config()
            return callback

        def make_save_callback():
            def callback(event=None):
                self._save_skill_config()
            return callback

        # 建立 6 組角色配置
        for group_idx in range(6):
            # 從配置載入此組的設定
            group_config = self.character_skill_config[group_idx] if group_idx < len(self.character_skill_config) else {}

            group_data = {
                'char_var': tk.StringVar(value=group_config.get("character", "")),
                'category_first_var': tk.StringVar(value=""),
                'skill_first_var': tk.StringVar(value=group_config.get("skill_first", "")),
                'level_first_var': tk.StringVar(value=group_config.get("level_first", "關閉")),
                'category_after_var': tk.StringVar(value=""),
                'skill_after_var': tk.StringVar(value=group_config.get("skill_after", "")),
                'level_after_var': tk.StringVar(value=group_config.get("level_after", "關閉")),
            }

            # === 首戰行 ===
            first_grid_row = header_row + 1 + group_idx * 2
            ttk.Label(frame_char_skill, text="首戰", font=("微軟雅黑", 9)).grid(
                row=first_grid_row, column=0, sticky=tk.W, pady=2)

            # 角色下拉（只在首戰行顯示）
            char_combo = ttk.Combobox(frame_char_skill, textvariable=group_data['char_var'],
                                      values=char_options, state="readonly", width=8)
            char_combo.grid(row=first_grid_row, column=1, padx=2, sticky=tk.W, pady=2)
            char_combo.bind("<<ComboboxSelected>>", make_save_callback())
            group_data['char_combo'] = char_combo

            # 首戰類別
            category_first_combo = ttk.Combobox(frame_char_skill, textvariable=group_data['category_first_var'],
                                                values=category_options, state="readonly", width=6)
            category_first_combo.grid(row=first_grid_row, column=2, padx=2, sticky=tk.W, pady=2)
            category_first_combo.bind("<<ComboboxSelected>>", make_category_callback(
                group_idx, "first", group_data['category_first_var'],
                group_data['skill_first_var'], None))  # skill_combo 稍後設定
            group_data['category_first_combo'] = category_first_combo

            # 首戰技能
            skill_first_combo = ttk.Combobox(frame_char_skill, textvariable=group_data['skill_first_var'],
                                             values=[""], state="readonly", width=16)
            skill_first_combo.grid(row=first_grid_row, column=3, padx=2, sticky=tk.W, pady=2)
            skill_first_combo.bind("<<ComboboxSelected>>", make_save_callback())
            group_data['skill_first_combo'] = skill_first_combo

            # 更新 category callback 的 skill_combo 引用
            category_first_combo.unbind("<<ComboboxSelected>>")
            category_first_combo.bind("<<ComboboxSelected>>", make_category_callback(
                group_idx, "first", group_data['category_first_var'],
                group_data['skill_first_var'], skill_first_combo))

            # 首戰等級
            level_first_combo = ttk.Combobox(frame_char_skill, textvariable=group_data['level_first_var'],
                                             values=level_options, state="readonly", width=5)
            level_first_combo.grid(row=first_grid_row, column=4, padx=2, sticky=tk.W, pady=2)
            level_first_combo.bind("<<ComboboxSelected>>", make_save_callback())
            group_data['level_first_combo'] = level_first_combo

            # === 二戰後行 ===
            after_grid_row = header_row + 2 + group_idx * 2
            ttk.Label(frame_char_skill, text="二戰後", font=("微軟雅黑", 9)).grid(
                row=after_grid_row, column=0, sticky=tk.W, pady=2)

            # 二戰後沒有角色下拉（共用首戰的角色）
            ttk.Label(frame_char_skill, text="", width=8).grid(
                row=after_grid_row, column=1, padx=2, sticky=tk.W, pady=2)

            # 二戰後類別
            category_after_combo = ttk.Combobox(frame_char_skill, textvariable=group_data['category_after_var'],
                                                values=category_options, state="readonly", width=6)
            category_after_combo.grid(row=after_grid_row, column=2, padx=2, sticky=tk.W, pady=2)
            group_data['category_after_combo'] = category_after_combo

            # 二戰後技能
            skill_after_combo = ttk.Combobox(frame_char_skill, textvariable=group_data['skill_after_var'],
                                             values=[""], state="readonly", width=16)
            skill_after_combo.grid(row=after_grid_row, column=3, padx=2, sticky=tk.W, pady=2)
            skill_after_combo.bind("<<ComboboxSelected>>", make_save_callback())
            group_data['skill_after_combo'] = skill_after_combo

            # 綁定二戰後類別 callback
            category_after_combo.bind("<<ComboboxSelected>>", make_category_callback(
                group_idx, "after", group_data['category_after_var'],
                group_data['skill_after_var'], skill_after_combo))

            # 二戰後等級
            level_after_combo = ttk.Combobox(frame_char_skill, textvariable=group_data['level_after_var'],
                                             values=level_options, state="readonly", width=5)
            level_after_combo.grid(row=after_grid_row, column=4, padx=2, sticky=tk.W, pady=2)
            level_after_combo.bind("<<ComboboxSelected>>", make_save_callback())
            group_data['level_after_combo'] = level_after_combo

            self.character_skill_groups.append(group_data)

            # 收集所有 combo 控件供 set_controls_state 使用
            self.skill_combos_all.extend([
                char_combo, category_first_combo, skill_first_combo, level_first_combo,
                category_after_combo, skill_after_combo, level_after_combo
            ])

            # 初始化：反推類別
            self._init_skill_combo_from_saved(
                group_config.get("skill_first", ""),
                group_data['category_first_var'], skill_first_combo)
            self._init_skill_combo_from_saved(
                group_config.get("skill_after", ""),
                group_data['category_after_var'], skill_after_combo)

    def _migrate_old_skill_config(self, old_config):
        """將舊版 dict 格式配置遷移到新版 list 格式"""
        # 舊格式: {"first": {character, skill, level}, "after": {character, skill, level}}
        # 新格式: [{character, skill_first, level_first, skill_after, level_after}, ...]
        result = []

        first_cfg = old_config.get("first", {})
        after_cfg = old_config.get("after", {})

        # 如果舊配置有設定，轉換為第一組
        if first_cfg.get("character") or after_cfg.get("character"):
            # 使用首戰的角色名稱，若無則使用二戰後的
            char_name = first_cfg.get("character") or after_cfg.get("character") or ""
            result.append({
                "character": char_name,
                "skill_first": first_cfg.get("skill", ""),
                "level_first": first_cfg.get("level", "關閉"),
                "skill_after": after_cfg.get("skill", ""),
                "level_after": after_cfg.get("level", "關閉"),
            })

        return result

    def _init_skill_combo_from_saved(self, saved_skill, category_var, skill_combo):
        """根據儲存的技能反推類別並初始化下拉選單"""
        if saved_skill:
            if saved_skill == "attack":
                category_var.set("普攻")
                skill_combo['values'] = ["", "attack"]
            else:
                for cat, skills in SKILLS_BY_CATEGORY.items():
                    if saved_skill in skills:
                        category_var.set(cat)
                        skill_combo['values'] = [""] + skills
                        break
                else:
                    skill_combo['values'] = [""]
        else:
            category_var.set("")
            skill_combo['values'] = [""]

    def _save_skill_config(self):
        """儲存技能配置（列表格式，共6組）"""
        self.character_skill_config = []
        for group_data in self.character_skill_groups:
            self.character_skill_config.append({
                "character": group_data['char_var'].get(),
                "skill_first": group_data['skill_first_var'].get(),
                "level_first": group_data['level_first_var'].get(),
                "skill_after": group_data['skill_after_var'].get(),
                "level_after": group_data['level_after_var'].get(),
            })
        # 更新預設列表中的對應項
        idx = self.current_skill_preset_index_var.get()
        if 0 <= idx < len(self.character_skill_presets):
            self.character_skill_presets[idx] = self.character_skill_config
            
        self.save_config()

    def _load_preset_to_ui(self):
        """將 character_skill_config 的數據載入到 UI 控件中"""
        for i, group_data in enumerate(self.character_skill_groups):
            if i < len(self.character_skill_config):
                cfg = self.character_skill_config[i]
                group_data['char_var'].set(cfg.get("character", ""))
                group_data['skill_first_var'].set(cfg.get("skill_first", ""))
                group_data['level_first_var'].set(cfg.get("level_first", "關閉"))
                group_data['skill_after_var'].set(cfg.get("skill_after", ""))
                group_data['level_after_var'].set(cfg.get("level_after", "關閉"))
                
                # 初始化類別反推
                self._init_skill_combo_from_saved(
                    cfg.get("skill_first", ""),
                    group_data['category_first_var'], group_data['skill_first_combo'])
                self._init_skill_combo_from_saved(
                    cfg.get("skill_after", ""),
                    group_data['category_after_var'], group_data['skill_after_combo'])
            else:
                # 預設清空
                group_data['char_var'].set("")
                group_data['skill_first_var'].set("")
                group_data['level_first_var'].set("關閉")
                group_data['skill_after_var'].set("")
                group_data['level_after_var'].set("關閉")
                group_data['category_first_var'].set("")
                group_data['category_after_var'].set("")


    def _create_advanced_tab(self, vcmd_non_neg, checkcommand):
        """進階設定分頁：旅店休息、善惡調整、凱旋、因果"""
        tab = self.tab_advanced
        row = 0

        # --- 旅店設定（回城時自動執行）---
        frame_rest = ttk.LabelFrame(tab, text="旅店設定", padding=5)
        frame_rest.grid(row=row, column=0, sticky="ew", pady=5)

        ttk.Label(frame_rest, text="※ 回城時會自動執行以下設定", foreground="gray").grid(
            row=0, column=0, columnspan=3, sticky=tk.W, pady=(0, 5))

        # 新增：旅店休息 (原連續刷地城)
        ttk.Label(frame_rest, text="旅店休息:").grid(row=1, column=0, padx=5, sticky=tk.W)
        self.dungeon_repeat_limit_spinbox = ttk.Spinbox(
            frame_rest, from_=0, to=99, width=4,
            textvariable=self.dungeon_repeat_limit_var,
            command=self.save_config
        )
        self.dungeon_repeat_limit_spinbox.grid(row=1, column=1, padx=5, sticky=tk.W)

        ttk.Label(frame_rest, text="※ 0=每次回村，N=刷N次才回村", foreground="gray").grid(
            row=1, column=2, padx=10, sticky=tk.W)

        self.active_royalsuite_rest = ttk.Checkbutton(
            frame_rest, variable=self.active_royalsuite_rest_var,
            text="住豪華房", command=checkcommand,
            style="Custom.TCheckbutton"
        )
        self.active_royalsuite_rest.grid(row=2, column=0, sticky=tk.W, pady=2)

        # 自動補給選項
        self.auto_refill_check = ttk.Checkbutton(
            frame_rest, variable=self.auto_refill_var,
            text="自動補給", command=checkcommand,
            style="Custom.TCheckbutton"
        )
        self.auto_refill_check.grid(row=2, column=1, sticky=tk.W, pady=2)

        # --- 整理背包 ---
        row += 1
        frame_organize = ttk.LabelFrame(tab, text="整理背包", padding=5)
        frame_organize.grid(row=row, column=0, sticky="ew", pady=5)

        self.organize_backpack_check = ttk.Checkbutton(
            frame_organize, variable=self.organize_backpack_enabled_var,
            text="啟用整理背包", command=self.update_organize_backpack_state,
            style="Custom.TCheckbutton"
        )
        self.organize_backpack_check.grid(row=0, column=0, padx=5)

        ttk.Label(frame_organize, text="人數:").grid(row=0, column=1, padx=(10, 2))
        self.organize_backpack_count_spinbox = ttk.Spinbox(
            frame_organize, from_=1, to=6, width=3,
            textvariable=self.organize_backpack_count_var,
            command=self.save_config
        )
        self.organize_backpack_count_spinbox.grid(row=0, column=2)
        
        ttk.Label(frame_organize, text="(將 Organize 資料夾內的物品放入倉庫)").grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=2)

        # --- 善惡調整 ---
        row += 1
        frame_karma = ttk.LabelFrame(tab, text="善惡調整", padding=5)
        frame_karma.grid(row=row, column=0, sticky="ew", pady=5)

        self.karma_adjust_mapping = {
            "維持現狀": "+0",
            "惡→中立,中立→善": "+17",
            "善→中立,中立→惡": "-17",
        }
        times = int(self.karma_adjust_var.get())
        if times == 0:
            self.karma_adjust_text_var = tk.StringVar(value="維持現狀")
        elif times > 0:
            self.karma_adjust_text_var = tk.StringVar(value="惡→中立,中立→善")
        else:
            self.karma_adjust_text_var = tk.StringVar(value="善→中立,中立→惡")

        ttk.Label(frame_karma, text="方向:").grid(row=0, column=0, padx=5)
        self.karma_adjust_combobox = ttk.Combobox(
            frame_karma, textvariable=self.karma_adjust_text_var,
            values=list(self.karma_adjust_mapping.keys()),
            state="readonly", width=16
        )
        self.karma_adjust_combobox.grid(row=0, column=1, padx=5)

        def handle_karma_adjust_selection(event=None):
            karma_adjust_left = int(self.karma_adjust_var.get())
            karma_adjust_want = int(self.karma_adjust_mapping[self.karma_adjust_text_var.get()])
            if (karma_adjust_left == 0 and karma_adjust_want == 0) or (karma_adjust_left * karma_adjust_want > 0):
                return
            self.karma_adjust_var.set(self.karma_adjust_mapping[self.karma_adjust_text_var.get()])
            self.save_config()
        self.karma_adjust_combobox.bind("<<ComboboxSelected>>", handle_karma_adjust_selection)

        ttk.Label(frame_karma, text="還需").grid(row=0, column=2, padx=2)
        ttk.Label(frame_karma, textvariable=self.karma_adjust_var).grid(row=0, column=3)
        ttk.Label(frame_karma, text="點").grid(row=0, column=4, padx=2)

        self.active_csc = ttk.Checkbutton(
            frame_karma, variable=self.active_csc_var,
            text="嘗試調整因果", command=checkcommand,
            style="Custom.TCheckbutton"
        )
        self.active_csc.grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=5)

        # --- 恢復設定 ---
        row += 1
        frame_recover = ttk.LabelFrame(tab, text="恢復設定", padding=5)
        frame_recover.grid(row=row, column=0, sticky="ew", pady=5)

        self.skip_recover_check = ttk.Checkbutton(
            frame_recover, text="跳過戰後恢復",
            variable=self.skip_recover_var, command=self.save_config,
            style="Custom.TCheckbutton"
        )
        self.skip_recover_check.grid(row=0, column=0, padx=5)

        self.skip_chest_recover_check = ttk.Checkbutton(
            frame_recover, text="跳過開箱後恢復",
            variable=self.skip_chest_recover_var, command=self.save_config,
            style="Custom.TCheckbutton"
        )
        self.skip_chest_recover_check.grid(row=0, column=1, padx=5)

        self.lowhp_recover_check = ttk.Checkbutton(
            frame_recover, text="低血量恢復",
            variable=self.lowhp_recover_var, command=self.save_config,
            style="Custom.TCheckbutton"
        )
        self.lowhp_recover_check.grid(row=0, column=2, padx=5)

        # --- 其他進階選項 ---
        row += 1
        frame_other = ttk.LabelFrame(tab, text="其他", padding=5)
        frame_other.grid(row=row, column=0, sticky="ew", pady=5)

        self.active_triumph = ttk.Checkbutton(
            frame_other, variable=self.active_triumph_var,
            text="跳躍到\"凱旋\"(需要解鎖凱旋)",
            command=checkcommand, style="Custom.TCheckbutton"
        )
        self.active_triumph.grid(row=0, column=0, sticky=tk.W)

    def _create_test_tab(self):
        """測試分頁：提供快速測試功能（完全獨立運行）"""
        tab = self.tab_test
        row = 0

        # --- 說明 ---
        ttk.Label(tab, text="測試功能（獨立運行，不需啟動主任務）", font=("微軟雅黑", 10, "bold")).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=5)
        row += 1

        # --- ADB 連接狀態 ---
        self.test_adb_status = tk.StringVar(value="未連接")
        ttk.Label(tab, text="ADB 狀態:").grid(row=row, column=0, sticky=tk.W, pady=2)
        ttk.Label(tab, textvariable=self.test_adb_status).grid(row=row, column=1, sticky=tk.W, pady=2)
        row += 1

        # --- 測試按鈕區域 ---
        frame_test = ttk.LabelFrame(tab, text="Inn 流程測試", padding=5)
        frame_test.grid(row=row, column=0, columnspan=2, sticky="ew", pady=5)

        # 測試整理背包按鈕
        self.test_organize_btn = ttk.Button(
            frame_test,
            text="測試整理背包",
            command=self._test_organize_backpack_standalone
        )
        self.test_organize_btn.grid(row=0, column=0, padx=5, pady=5)

        # 測試住宿流程按鈕
        self.test_state_inn_btn = ttk.Button(
            frame_test,
            text="測試住宿流程",
            command=self._test_state_inn_standalone
        )
        self.test_state_inn_btn.grid(row=0, column=1, padx=5, pady=5)

        # --- 小地圖樓梯偵測測試 ---
        row += 1
        frame_minimap = ttk.LabelFrame(tab, text="小地圖樓梯偵測測試", padding=5)
        frame_minimap.grid(row=row, column=0, columnspan=2, sticky="ew", pady=5)

        # 第一行：樓層圖片名稱
        ttk.Label(frame_minimap, text="樓層圖片:").grid(row=0, column=0, padx=5, sticky=tk.W)
        self.minimap_floor_image_var = tk.StringVar(value="DH-R5-minimap")
        self.minimap_floor_image_entry = ttk.Entry(frame_minimap, textvariable=self.minimap_floor_image_var, width=18)
        self.minimap_floor_image_entry.grid(row=0, column=1, padx=5)

        # 第二行：樓梯座標
        ttk.Label(frame_minimap, text="樓梯座標:").grid(row=1, column=0, padx=5, sticky=tk.W)
        self.minimap_stair_coords_var = tk.StringVar(value="294,239")
        self.minimap_stair_coords_entry = ttk.Entry(frame_minimap, textvariable=self.minimap_stair_coords_var, width=10)
        self.minimap_stair_coords_entry.grid(row=1, column=1, padx=5, sticky=tk.W)

        # 第三行：滑動方向
        ttk.Label(frame_minimap, text="滑動方向:").grid(row=2, column=0, padx=5, sticky=tk.W)
        self.minimap_swipe_dir_var = tk.StringVar(value="右上")
        self.minimap_swipe_dir_combo = ttk.Combobox(frame_minimap, textvariable=self.minimap_swipe_dir_var,
                                                     values=["左上", "右上", "左下", "右下", "無"], state="readonly", width=8)
        self.minimap_swipe_dir_combo.grid(row=2, column=1, padx=5, sticky=tk.W)

        # 測試按鈕
        self.test_minimap_stair_btn = ttk.Button(
            frame_minimap,
            text="測試完整流程",
            command=self._test_minimap_stair_standalone
        )
        self.test_minimap_stair_btn.grid(row=0, column=2, rowspan=3, padx=10, pady=5)

        ttk.Label(frame_minimap, text="流程：開地圖→滑動→點樓梯→監控小地圖", foreground="gray").grid(row=3, column=0, columnspan=3, sticky=tk.W, pady=2)

        # --- 串流截圖功能 ---
        row += 1
        frame_screenshot = ttk.LabelFrame(tab, text="串流截圖", padding=5)
        frame_screenshot.grid(row=row, column=0, columnspan=2, sticky="ew", pady=5)

        ttk.Label(frame_screenshot, text="檔名:").grid(row=0, column=0, padx=5, sticky=tk.W)
        self.screenshot_filename_var = tk.StringVar(value="screenshot")
        self.screenshot_filename_entry = ttk.Entry(frame_screenshot, textvariable=self.screenshot_filename_var, width=20)
        self.screenshot_filename_entry.grid(row=0, column=1, padx=5)
        ttk.Label(frame_screenshot, text=".png").grid(row=0, column=2, sticky=tk.W)

        self.screenshot_btn = ttk.Button(
            frame_screenshot,
            text="擷取截圖",
            command=self._capture_streaming_screenshot
        )
        self.screenshot_btn.grid(row=0, column=3, padx=10, pady=5)

        self.capture_char_btn = ttk.Button(
            frame_screenshot,
            text="擷取角色(ROI)",
            command=self._capture_character_roi
        )
        self.capture_char_btn.grid(row=0, column=4, padx=5, pady=5)

        self.screenshot_status_var = tk.StringVar(value="")
        ttk.Label(frame_screenshot, textvariable=self.screenshot_status_var, foreground="green").grid(row=1, column=0, columnspan=4, sticky=tk.W, pady=2)

        # ROI 設定區域 (讓你自定義裁切範圍)
        # frame_roi = ttk.LabelFrame(frame_screenshot, text="ROI 設定 (x,y,w,h)", padding=2)
        # frame_roi.grid(row=2, column=0, columnspan=6, sticky=tk.W, pady=2)
        
        self.roi_x = tk.IntVar(value=89)
        self.roi_y = tk.IntVar(value=53)
        self.roi_w = tk.IntVar(value=106)
        self.roi_h = tk.IntVar(value=47)
        
        # ttk.Label(frame_roi, text="X:").pack(side=tk.LEFT, padx=2)
        # ttk.Entry(frame_roi, textvariable=self.roi_x, width=5).pack(side=tk.LEFT)
        # ttk.Label(frame_roi, text="Y:").pack(side=tk.LEFT, padx=2)
        # ttk.Entry(frame_roi, textvariable=self.roi_y, width=5).pack(side=tk.LEFT)
        # ttk.Label(frame_roi, text="W:").pack(side=tk.LEFT, padx=2)
        # ttk.Entry(frame_roi, textvariable=self.roi_w, width=5).pack(side=tk.LEFT)
        # ttk.Label(frame_roi, text="H:").pack(side=tk.LEFT, padx=2)
        # ttk.Entry(frame_roi, textvariable=self.roi_h, width=5).pack(side=tk.LEFT)
        
        ttk.Label(frame_screenshot, text="※ 使用串流方式截圖，儲存至 resources/images/character/", foreground="gray").grid(row=3, column=0, columnspan=5, sticky=tk.W, pady=2)

        row += 1
        ttk.Label(tab, text="注意：\n1. 點擊測試按鈕會自動連接 ADB\n2. 測試小地圖偵測：請確保遊戲在地城中\n3. 不需要啟動主任務",
                  foreground="gray", justify=tk.LEFT).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=5)

    def _test_organize_backpack_standalone(self):
        """測試整理背包功能（完全獨立運行）"""
        import threading
        
        # 禁用按鈕防止重複點擊
        self.test_organize_btn.config(state="disabled")
        self.test_adb_status.set("正在連接...")
        
        def run_test():
            try:
                logger.info("=== 開始獨立測試整理背包 ===")
                
                # 初始化設定
                setting = FarmConfig()
                config = LoadConfigFromFile()
                for attr_name, var_type, var_config_name, var_default_value in CONFIG_VAR_LIST:
                    setattr(setting, var_config_name, config.get(var_config_name, var_default_value))
                
                # 設置停止信號
                from threading import Event
                setting._FORCESTOPING = Event()
                
                # 使用 TestFactory 執行測試
                test_func = TestFactory()
                count = self.organize_backpack_count_var.get()
                if count <= 0:
                    count = 1
                
                # 更新狀態
                self.test_adb_status.set("已連接，執行中...")
                
                test_func(setting, "organize_backpack", count=count)
                
                self.test_adb_status.set("測試完成")
                logger.info("=== 測試整理背包完成 ===")
                
            except Exception as e:
                logger.error(f"測試失敗: {e}")
                self.test_adb_status.set(f"失敗: {e}")
            finally:
                # 重新啟用按鈕
                self.test_organize_btn.config(state="normal")
        
        thread = threading.Thread(target=run_test, daemon=True)
        thread.start()

    def _test_state_inn_standalone(self):
        """測試完整住宿流程（住宿 → 補給 → 整理背包）"""
        import threading

        # 禁用按鈕防止重複點擊
        self.test_state_inn_btn.config(state="disabled")
        self.test_organize_btn.config(state="disabled")
        self.test_adb_status.set("正在連接...")

        def run_test():
            try:
                logger.info("=== 開始測試住宿流程 ===")

                # 初始化設定
                setting = FarmConfig()
                config = LoadConfigFromFile()
                for attr_name, var_type, var_config_name, var_default_value in CONFIG_VAR_LIST:
                    setattr(setting, var_config_name, config.get(var_config_name, var_default_value))

                # 設置停止信號
                from threading import Event
                setting._FORCESTOPING = Event()

                # 使用 TestFactory 執行測試
                test_func = TestFactory()
                count = self.organize_backpack_count_var.get()
                use_royal_suite = self.active_royalsuite_rest_var.get()

                # 更新狀態
                self.test_adb_status.set("已連接，執行中...")

                test_func(setting, "state_inn", count=count, use_royal_suite=use_royal_suite)

                self.test_adb_status.set("測試完成")
                logger.info("=== 測試住宿流程完成 ===")

            except Exception as e:
                logger.error(f"測試失敗: {e}")
                self.test_adb_status.set(f"失敗: {e}")
            finally:
                # 重新啟用按鈕
                self.test_state_inn_btn.config(state="normal")
                self.test_organize_btn.config(state="normal")

        thread = threading.Thread(target=run_test, daemon=True)
        thread.start()

    def _test_minimap_stair_standalone(self):
        """測試小地圖樓梯偵測功能（完全獨立運行）"""
        import threading

        # 禁用按鈕防止重複點擊
        self.test_minimap_stair_btn.config(state="disabled")
        self.test_adb_status.set("正在連接...")

        def run_test():
            try:
                logger.info("=== 開始測試小地圖樓梯偵測 ===")

                # 初始化設定
                setting = FarmConfig()
                config = LoadConfigFromFile()
                for attr_name, var_type, var_config_name, var_default_value in CONFIG_VAR_LIST:
                    setattr(setting, var_config_name, config.get(var_config_name, var_default_value))

                # 設置停止信號
                from threading import Event
                setting._FORCESTOPING = Event()

                # 使用 TestFactory 執行測試
                test_func = TestFactory()
                
                # 取得參數
                floor_image = self.minimap_floor_image_var.get() or "DH-R5-minimap"
                
                # 解析樓梯座標
                coords_str = self.minimap_stair_coords_var.get() or "73,1240"
                try:
                    parts = coords_str.replace(" ", "").split(",")
                    stair_coords = [int(parts[0]), int(parts[1])]
                except:
                    logger.error(f"座標格式錯誤: {coords_str}，使用預設值 [73,1240]")
                    stair_coords = [73, 1240]
                
                # 取得滑動方向
                swipe_dir = self.minimap_swipe_dir_var.get()
                if swipe_dir == "無":
                    swipe_dir = None

                # 更新狀態
                self.test_adb_status.set("已連接，執行中...")

                test_func(setting, "minimap_stair", 
                         floor_image=floor_image, 
                         stair_coords=stair_coords, 
                         swipe_dir=swipe_dir)

                self.test_adb_status.set("測試完成")
                logger.info("=== 測試小地圖樓梯偵測完成 ===")

            except Exception as e:
                logger.error(f"測試失敗: {e}")
                self.test_adb_status.set(f"失敗: {e}")
            finally:
                # 重新啟用按鈕
                self.test_minimap_stair_btn.config(state="normal")

        thread = threading.Thread(target=run_test, daemon=True)
        thread.start()

    def _capture_streaming_screenshot(self):
        """使用串流方式擷取截圖並儲存到 resources/images/"""
        import threading
        import cv2
        import os

        # 禁用按鈕防止重複點擊
        self.screenshot_btn.config(state="disabled")
        self.screenshot_status_var.set("正在連接...")

        def run_capture():
            try:
                filename = self.screenshot_filename_var.get().strip()
                if not filename:
                    filename = "screenshot"
                
                # 初始化設定
                setting = FarmConfig()
                config = LoadConfigFromFile()
                for attr_name, var_type, var_config_name, var_default_value in CONFIG_VAR_LIST:
                    setattr(setting, var_config_name, config.get(var_config_name, var_default_value))
                
                # 設置停止信號
                from threading import Event
                setting._FORCESTOPING = Event()
                
                # 使用 TestFactory 來連接並取得截圖
                test_func = TestFactory()
                
                self.screenshot_status_var.set("正在連接並擷取...")
                
                # 呼叫 test factory 取得截圖
                frame = test_func(setting, "screenshot")
                
                if frame is None:
                    self.screenshot_status_var.set("❌ 無法取得串流畫面")
                    return
                
                # 儲存到 resources/images/
                save_dir = os.path.join(os.path.dirname(__file__), "..", "resources", "images")
                os.makedirs(save_dir, exist_ok=True)
                save_path = os.path.join(save_dir, f"{filename}.png")
                
                # 儲存 (frame 是 BGR 格式)
                cv2.imwrite(save_path, frame)
                
                abs_path = os.path.abspath(save_path)
                self.screenshot_status_var.set(f"✓ 已儲存: {filename}.png")
                logger.info(f"串流截圖已儲存: {abs_path}")
                
            except Exception as e:
                logger.error(f"串流截圖失敗: {e}")
                self.screenshot_status_var.set(f"❌ 失敗: {e}")
            finally:
                self.screenshot_btn.config(state="normal")

        thread = threading.Thread(target=run_capture, daemon=True)
        thread.start()

    def _capture_character_roi(self):
        """使用串流方式擷取角色 ROI 並儲存到 resources/images/character/"""
        import threading
        import cv2
        import os

        # 禁用按鈕防止重複點擊
        self.capture_char_btn.config(state="disabled")
        self.screenshot_status_var.set("正在連接...")

        def run_capture():
            try:
                filename = self.screenshot_filename_var.get().strip()
                if not filename:
                    filename = "new_character"
                
                # 初始化設定
                setting = FarmConfig()
                config = LoadConfigFromFile()
                for attr_name, var_type, var_config_name, var_default_value in CONFIG_VAR_LIST:
                    setattr(setting, var_config_name, config.get(var_config_name, var_default_value))
                
                # 設置停止信號
                from threading import Event
                setting._FORCESTOPING = Event()
                
                # 使用 TestFactory 來連接並取得截圖
                test_func = TestFactory()
                
                self.screenshot_status_var.set("正在連接並擷取...")
                
                # 呼叫 test factory 取得截圖 (使用串流方式)
                frame = test_func(setting, "screenshot")
                
                if frame is None:
                    self.screenshot_status_var.set("❌ 無法取得畫面")
                    return
                
                # 讀取 ROI 設定
                try:
                    x = self.roi_x.get()
                    y = self.roi_y.get()
                    w = self.roi_w.get()
                    h = self.roi_h.get()
                except:
                    self.screenshot_status_var.set("❌ ROI 格式錯誤")
                    return

                # 執行裁切 ROI
                # frame[y:y+h, x:x+w]
                roi_img = frame[y:y+h, x:x+w]
                
                if roi_img.size == 0:
                     self.screenshot_status_var.set("❌ ROI 裁切失敗")
                     return

                # 決定儲存路徑
                # 如果當前目錄下有 _internal (通常是打包後的 OneDir 環境)，優先使用
                if os.path.exists("_internal"):
                    base_dir = "_internal"
                else:
                    # 开发环境：src/gui.py -> ../resources
                    base_dir = os.path.join(os.path.dirname(__file__), "..")
                
                save_dir = os.path.join(base_dir, "resources", "images", "character")
                os.makedirs(save_dir, exist_ok=True)
                save_path = os.path.join(save_dir, f"{filename}.png")
                
                # 使用 PIL 儲存，指定 DPI 為 144 (與手動處理的圖片一致)
                from PIL import Image
                img_pil = Image.fromarray(cv2.cvtColor(roi_img, cv2.COLOR_BGR2RGB))
                img_pil.save(save_path, dpi=(144, 144))
                
                abs_path = os.path.abspath(save_path)
                self.screenshot_status_var.set(f"✓ 已儲存角色: {filename}.png")
                logger.info(f"角色截圖已儲存: {abs_path}")
                
            except Exception as e:
                logger.error(f"角色截圖失敗: {e}")
                self.screenshot_status_var.set(f"❌ 失敗: {e}")
            finally:
                self.capture_char_btn.config(state="normal")
        
        thread = threading.Thread(target=run_capture, daemon=True)
        thread.start()

    def _start_monitor_update(self):
        """啟動監控面板定時更新"""
        self._update_monitor()

    def _update_monitor(self):
        """更新監控面板顯示（每秒執行一次）"""
        try:
            # 更新狀態資訊（使用四個字描述當前模式）
            current_state = MonitorState.current_state or ""
            current_dungeon_state = MonitorState.current_dungeon_state or ""
            current_target = MonitorState.current_target or ""
            is_gohome = MonitorState.is_gohome_mode
            
            # 根據狀態組合決定顯示的四字描述
            if current_state == "Dungeon":
                if current_dungeon_state == "Combat":
                    state_display = "戰鬥監控"
                elif current_dungeon_state == "Chest":
                    state_display = "寶箱監控"
                elif current_dungeon_state == "Map":
                    state_display = "地圖監控"
                else:
                    state_display = "地城監控"
            elif current_state == "Inn":
                state_display = "旅館待機"
            elif current_state == "EoT":
                state_display = "回合結束"
            elif current_state == "Scanning":
                state_display = "識別中.."
            elif current_state == "Idle":
                state_display = "待機中.."
            elif current_state == "Connecting":
                state_display = "連接中.."
            elif current_state == "Starting":
                state_display = "啟動中.."
            elif current_state == "Harken":
                state_display = "哈肯傳送"
            else:
                state_display = "-"
            
            # 目標顯示：根據 current_target 決定
            if current_target:
                if is_gohome:
                    target_display = "回城撤離"
                elif current_target == "chest_auto":
                    target_display = "寶箱移動"
                elif current_target == "position":
                    target_display = "地城移動"
                elif current_target == "harken":
                    target_display = "傳點移動"
                elif current_target.startswith("stair"):
                    target_display = "樓梯移動"
                elif current_target == "gohome":
                    target_display = "回城撤離"
                else:
                    target_display = current_target[:4]  # 取前四個字
            else:
                target_display = "-"
            
            self.monitor_state_var.set(state_display)
            self.monitor_dungeon_state_var.set(current_dungeon_state or "-")
            self.monitor_target_var.set(target_display)

            # 更新戰鬥資訊
            self.monitor_battle_var.set(f"第 {MonitorState.battle_count} 戰")

            # 更新統計資訊
            self.monitor_dungeon_count_var.set(f"{MonitorState.dungeon_count} 次")
            self.monitor_combat_count_var.set(f"{MonitorState.combat_count} 次")
            self.monitor_chest_count_var.set(f"{MonitorState.chest_count} 個")

            # 更新死亡
            self.monitor_death_count_var.set(f"{MonitorState.death_count} 次")
            
            # 更新卡死偵測指標
            still_count = MonitorState.still_count
            still_max = MonitorState.still_max
            resume_count = MonitorState.resume_count
            resume_max = MonitorState.resume_max
            self.monitor_detection_var.set(f"靜止{still_count}/{still_max} 重試{resume_count}/{resume_max}")
            
            # 計算寶箱效率（秒/箱）
            if MonitorState.chest_count > 0 and MonitorState.chest_time_total > 0:
                chest_eff = MonitorState.chest_time_total / MonitorState.chest_count
                self.monitor_chest_efficiency_var.set(f"{chest_eff:.1f}秒/箱")
            else:
                self.monitor_chest_efficiency_var.set("-")
            
            # 計算戰鬥效率（秒/戰）
            if MonitorState.combat_count > 0 and MonitorState.combat_time_total > 0:
                combat_eff = MonitorState.combat_time_total / MonitorState.combat_count
                self.monitor_combat_efficiency_var.set(f"{combat_eff:.1f}秒/戰")
            else:
                self.monitor_combat_efficiency_var.set("-")
            
            # 計算總效率（秒/箱）
            if MonitorState.chest_count > 0 and MonitorState.total_time > 0:
                seconds_per_chest = MonitorState.total_time / MonitorState.chest_count
                self.monitor_total_efficiency_var.set(f"{seconds_per_chest:.1f}秒/箱")
            else:
                self.monitor_total_efficiency_var.set("-")

            # 更新運行時間
            if MonitorState.total_time > 0:
                total_seconds = int(MonitorState.total_time)
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                if hours > 0:
                    self.monitor_total_time_var.set(f"{hours}時{minutes}分{seconds}秒")
                elif minutes > 0:
                    self.monitor_total_time_var.set(f"{minutes}分{seconds}秒")
                else:
                    self.monitor_total_time_var.set(f"{seconds}秒")
            else:
                self.monitor_total_time_var.set("0 秒")
            
            # 更新軟/硬超時進度條
            soft_timeout = 60  # 軟超時 60 秒
            hard_timeout = 90  # 硬超時 90 秒
            
            # 當有 current_target 時表示正在移動，顯示進度
            if MonitorState.state_start_time > 0 and MonitorState.current_target:
                elapsed = time.time() - MonitorState.state_start_time
                
                # 軟超時進度
                soft_progress = min(100, (elapsed / soft_timeout) * 100)
                self.monitor_soft_timeout_progress['value'] = soft_progress
                self.monitor_soft_timeout_label.set(f"{int(elapsed)}/{soft_timeout}s")
                
                # 硬超時進度
                hard_progress = min(100, (elapsed / hard_timeout) * 100)
                self.monitor_hard_timeout_progress['value'] = hard_progress
                self.monitor_hard_timeout_label.set(f"{int(elapsed)}/{hard_timeout}s")
            else:
                # 不在移動狀態，重置進度條
                self.monitor_soft_timeout_progress['value'] = 0
                self.monitor_soft_timeout_label.set("0/60s")
                self.monitor_hard_timeout_progress['value'] = 0
                self.monitor_hard_timeout_label.set("0/90s")

            # 更新 Flag 相似度顯示（超過門檻值變紅）
            d = MonitorState.flag_dungFlag
            m = MonitorState.flag_mapFlag
            c = MonitorState.flag_chestFlag
            b = MonitorState.flag_combatActive
            
            current_time = time.time()
            def get_display_value(val, threshold_val, flag_name):
                # 檢查數據是否過期 (超過 2 秒未更新視為過期)
                last_update = MonitorState.flag_updates.get(flag_name, 0)
                if current_time - last_update > 2.0:
                    return "--", "black"
                return f"{val}%", "red" if val >= threshold_val else "black"

            # 地城：閾值 75%
            d_text, d_color = get_display_value(d, 75, 'dungFlag')
            self.monitor_flag_dung_var.set(d_text)
            self.monitor_flag_dung_label.configure(foreground=d_color)
            
            # 地圖：閾值 80%
            m_text, m_color = get_display_value(m, 80, 'mapFlag')
            self.monitor_flag_map_var.set(m_text)
            self.monitor_flag_map_label.configure(foreground=m_color)
            
            # 寶箱：閾值 80%
            c_text, c_color = get_display_value(c, 80, 'chestFlag')
            self.monitor_flag_chest_var.set(c_text)
            self.monitor_flag_chest_label.configure(foreground=c_color)
            
            # 戰鬥：閾值 70%
            b_text, b_color = get_display_value(b, 70, 'combatActive')
            self.monitor_flag_combat_var.set(b_text)
            self.monitor_flag_combat_label.configure(foreground=b_color)
            
            # 世界地圖：閾值 80%
            w = MonitorState.flag_worldMap
            w_text, w_color = get_display_value(w, 80, 'worldMap')
            self.monitor_flag_world_var.set(w_text)
            self.monitor_flag_world_label.configure(foreground=w_color)

            # 寶箱移動：閾值 80%
            ca = MonitorState.flag_chest_auto
            ca_text, ca_color = get_display_value(ca, 80, 'chest_auto')
            self.monitor_flag_chest_auto_var.set(ca_text)
            self.monitor_flag_chest_auto_label.configure(foreground=ca_color)

            # AUTO 比對：閾值 80%
            a = MonitorState.flag_auto_text
            a_text, a_color = get_display_value(a, 80, 'AUTO')
            self.monitor_flag_auto_var.set(a_text)
            self.monitor_flag_auto_label.configure(foreground=a_color)

            # 血量偵測：只在地城移動時顯示
            if current_target == "position":  # 地城移動狀態
                if MonitorState.flag_low_hp:
                    self.monitor_hp_status_var.set("低血量")
                    self.monitor_hp_status_label.configure(foreground="red")
                else:
                    self.monitor_hp_status_var.set("正常")
                    self.monitor_hp_status_label.configure(foreground="green")
            else:
                self.monitor_hp_status_var.set("--")
                self.monitor_hp_status_label.configure(foreground="gray")

            # 更新警告
            if MonitorState.warnings:
                self.monitor_warning_var.set(" | ".join(MonitorState.warnings))
            else:
                self.monitor_warning_var.set("")

            # 更新角色比對
            self.monitor_character_var.set(MonitorState.current_character or "未找到")
        except Exception as e:
            logger.debug(f"監控更新異常: {e}")

        # 每秒更新一次
        self.after(1000, self._update_monitor)

    def update_organize_backpack_state(self):
        if self.organize_backpack_enabled_var.get():
            self.organize_backpack_count_spinbox.config(state="normal")
        else:
            self.organize_backpack_count_spinbox.config(state="disable")
        self.save_config()



    def set_controls_state(self, state):
        self.button_and_entry = [
            self.adb_path_change_button,
            self.who_will_open_combobox,
            self.skip_recover_check,
            self.skip_chest_recover_check,
            self.karma_adjust_combobox,
            self.adb_port_entry,
            self.active_triumph,
            self.active_royalsuite_rest,
            self.button_save_adb_port,
            self.active_csc,
            self.organize_backpack_check,
            self.organize_backpack_count_spinbox,
            self.auto_refill_check,  # 自動補給
            # 戰鬥設定
            self.auto_combat_mode_combo,
            self.dungeon_repeat_limit_spinbox,
            # 技能施放設定
            self.ae_caster_interval_entry,
            ] + self.skill_combos_all

        if state == tk.DISABLED:
            self.farm_target_combo.configure(state="disabled")
            for widget in self.button_and_entry:
                widget.configure(state="disabled")
        else:
            self.farm_target_combo.configure(state="readonly")
            for widget in self.button_and_entry:
                widget.configure(state="normal")
            self.update_organize_backpack_state()


    def toggle_start_stop(self):
        if not self.quest_active:
            self.start_stop_btn.config(text="停止")
            self.set_controls_state(tk.DISABLED)
            setting = FarmConfig()
            config = LoadConfigFromFile()
            for attr_name, var_type, var_config_name, var_default_value in CONFIG_VAR_LIST:
                setattr(setting, var_config_name, config[var_config_name])
            # 複製角色技能配置
            setting._CHARACTER_SKILL_CONFIG = config.get("_CHARACTER_SKILL_CONFIG", [])
            setting._FINISHINGCALLBACK = self.finishingcallback
            self.msg_queue.put(('start_quest', setting))
            self.quest_active = True
        else:
            self.msg_queue.put(('stop_quest', None))

    def finishingcallback(self):
        logger.info("已停止.")
        self.start_stop_btn.config(text="腳本, 啟動!")
        self.set_controls_state(tk.NORMAL)
        self.updata_config()
        self.quest_active = False

    def turn_to_7000G(self):
        self.summary_log_display.config(bg="#F4C6DB" )
        self.main_frame.grid_remove()
        summary = self.summary_log_display.get("1.0", "end-1c")
        if self.INTRODUCTION in summary:
            summary = "唔, 看起來一次成功的地下城都沒有完成."
        text = f"你的隊伍已經耗盡了所有的再起之火.\n在耗盡再起之火前,\n你的隊伍已經完成了如下了不起的壯舉:\n\n{summary}\n\n不過沒關係, 至少, 你還可以找公主要錢.\n\n讚美公主殿下!\n"
        turn_to_7000G_label = ttk.Label(self, text = text)
        turn_to_7000G_label.grid(row=0, column=0,)
