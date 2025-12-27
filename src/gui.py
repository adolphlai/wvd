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
        self.TITLE = f"WvDAS 巫术daphne自动刷怪 v{version} @德德Dellyla(B站)"
        self.INTRODUCTION = f"遇到问题? 请访问:\n{self.URL} \n或加入Q群: 922497356."

        RegisterQueueHandler()
        StartLogListener()

        super().__init__(master_controller)
        self.controller = master_controller
        self.msg_queue = msg_queue
        self.geometry('800x550')  # 加寬視窗以容納日誌過濾器
        
        self.title(self.TITLE)

        self.adb_active = False

        # 关闭时退出整个程序
        self.protocol("WM_DELETE_WINDOW", self.controller.on_closing)

        # --- 任务状态 ---
        self.quest_active = False

        # --- ttk Style ---
        #
        self.style = ttk.Style()
        self.style.configure("custom.TCheckbutton")
        self.style.map("Custom.TCheckbutton",
            foreground=[("disabled selected", "#8CB7DF"),("disabled", "#A0A0A0"), ("selected", "#196FBF")])
        self.style.configure("BoldFont.TCheckbutton", font=("微软雅黑", 9,"bold"))
        self.style.configure("LargeFont.TCheckbutton", font=("微软雅黑", 12,"bold"))

        # --- UI 变量 ---
        self.config = LoadConfigFromFile()
        for attr_name, var_type, var_config_name, var_default_value in CONFIG_VAR_LIST:
            if issubclass(var_type, tk.Variable):
                setattr(self, attr_name, var_type(value = self.config.get(var_config_name,var_default_value)))
            else:
                setattr(self, attr_name, var_type(self.config.get(var_config_name,var_default_value)))
        
        for btn,_,spellskillList,_,_ in SPELLSEKILL_TABLE:
            for item in spellskillList:
                if item not in self._spell_skill_config_internal:
                    setattr(self,f"{btn}_var",tk.BooleanVar(value = False))
                    break
                setattr(self,f"{btn}_var",tk.BooleanVar(value = True))             

        self.create_widgets()
        self.update_system_auto_combat()
        self.update_active_rest_state() # 初始化时更新旅店住宿entry.
        self.update_organize_backpack_state()  # 初始化整理背包狀態
        

        logger.info("**********************************")
        logger.info(f"当前版本: {version}")
        logger.info(self.INTRODUCTION, extra={"summary": True})
        logger.info("**********************************")
        
        if self.last_version.get() != version:
            ShowChangesLogWindow()
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
        if self.system_auto_combat_var.get():
            self.config["_SPELLSKILLCONFIG"] = []
        else:
            self.config["_SPELLSKILLCONFIG"] = [s for s in ALL_SKILLS if s in list(set(self._spell_skill_config_internal))]

        if self.farm_target_text_var.get() in DUNGEON_TARGETS:
            self.farm_target_var.set(DUNGEON_TARGETS[self.farm_target_text_var.get()])
        else:
            self.farm_target_var.set(None)
        
        SaveConfigToFile(self.config)

    def updata_config(self):
        config = LoadConfigFromFile()
        if '_KARMAADJUST' in config:
            self.karma_adjust_var.set(config['_KARMAADJUST'])

    def create_widgets(self):
        # === 右側容器 (包含過濾器 + LOG 顯示區域) ===
        right_frame = ttk.Frame(self)
        right_frame.grid(row=0, column=1, rowspan=2, sticky=(tk.N, tk.S, tk.E), padx=5, pady=5)
        
        # === 日志过滤器 checkbox ===
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

        # === 日志显示区域 ===
        scrolled_text_formatter = logging.Formatter('%(levelname)s: %(message)s')
        self.log_display = scrolledtext.ScrolledText(right_frame, wrap=tk.WORD, state=tk.DISABLED, bg='#ffffff', bd=2, relief=tk.FLAT, width=34, height=28)
        self.log_display.pack(fill=tk.BOTH, expand=True)
        self.scrolled_text_handler = ScrolledTextHandler(self.log_display)
        self.scrolled_text_handler.setLevel(logging.DEBUG)  # 降低 level 讓 DEBUG 訊息能通過
        self.scrolled_text_handler.setFormatter(scrolled_text_formatter)
        self.scrolled_text_handler.addFilter(self.log_level_filter)  # 添加動態過濾器
        logger.addHandler(self.scrolled_text_handler)

        # === 摘要顯示區域 ===
        self.summary_log_display = scrolledtext.ScrolledText(right_frame, wrap=tk.WORD, state=tk.DISABLED, bg="#C6DBF4", bd=2, width=34)
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

        # === 主框架（左侧）===
        self.main_frame = ttk.Frame(self, padding="10")
        self.main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # === 分页控件 ===
        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 创建五个分页
        self.tab_general = ttk.Frame(self.notebook, padding=10)
        self.tab_battle = ttk.Frame(self.notebook, padding=10)
        self.tab_skills = ttk.Frame(self.notebook, padding=10)
        self.tab_advanced = ttk.Frame(self.notebook, padding=10)
        self.tab_test = ttk.Frame(self.notebook, padding=10)

        self.notebook.add(self.tab_general, text="一般設定")
        self.notebook.add(self.tab_battle, text="戰鬥設定")
        self.notebook.add(self.tab_skills, text="技能設定")
        self.notebook.add(self.tab_advanced, text="進階設定")
        self.notebook.add(self.tab_test, text="測試")

        # 验证命令（数字输入）
        vcmd_non_neg = self.register(lambda x: ((x=="")or(x.isdigit())))

        # checkcommand 用于多个地方
        def checkcommand():
            self.update_active_rest_state()
            self.save_config()

        # =============================================
        # Tab 1: 一般设定
        # =============================================
        self._create_general_tab(vcmd_non_neg)

        # =============================================
        # Tab 2: 战斗设定
        # =============================================
        self._create_battle_tab()

        # =============================================
        # Tab 3: 技能设定
        # =============================================
        self._create_skills_tab()

        # =============================================
        # Tab 4: 进阶设定
        # =============================================
        self._create_advanced_tab(vcmd_non_neg, checkcommand)

        # =============================================
        # Tab 5: 测试
        # =============================================
        self._create_test_tab()

        # === 启动/停止按钮区域 ===
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        start_frame = ttk.Frame(self)
        start_frame.grid(row=1, column=0, sticky="nsew")
        start_frame.columnconfigure(0, weight=1)
        start_frame.rowconfigure(1, weight=1)

        ttk.Separator(start_frame, orient='horizontal').grid(row=0, column=0, columnspan=3, sticky="ew", padx=10)

        button_frame = ttk.Frame(start_frame)
        button_frame.grid(row=1, column=0, columnspan=3, pady=5, sticky="nsew")
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=1)
        button_frame.columnconfigure(2, weight=1)

        label1 = ttk.Label(button_frame, text="",  anchor='center')
        label1.grid(row=0, column=0, sticky='nsew', padx=5, pady=5)

        label3 = ttk.Label(button_frame, text="",  anchor='center')
        label3.grid(row=0, column=2, sticky='nsew', padx=5, pady=5)

        s = ttk.Style()
        s.configure('start.TButton', font=('微软雅黑', 15), padding = (0,5))
        def btn_command():
            self.save_config()
            self.toggle_start_stop()
        self.start_stop_btn = ttk.Button(
            button_frame,
            text="腳本, 啟動!",
            command=btn_command,
            style='start.TButton',
        )
        self.start_stop_btn.grid(row=0, column=1, sticky='nsew', padx=5, pady= 26)

        # === 更新提示区域（默认隐藏）===
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

        # 隐藏的Entry用于存储变量
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

    def _create_battle_tab(self):
        """戰鬥設定分頁：自動戰鬥、恢復、強力技能、AOE"""
        tab = self.tab_battle
        row = 0

        # --- 自動戰鬥主開關 ---
        frame_auto = ttk.LabelFrame(tab, text="自動戰鬥", padding=5)
        frame_auto.grid(row=row, column=0, sticky="ew", pady=5)

        self.system_auto_check = ttk.Checkbutton(
            frame_auto,
            text="啟用自動戰鬥",
            variable=self.system_auto_combat_var,
            command=self.update_system_auto_combat,
            style="Custom.TCheckbutton"
        )
        self.system_auto_check.grid(row=0, column=0, sticky=tk.W, pady=5)

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

        self.enable_resume_optimization_check = ttk.Checkbutton(
            frame_recover, text="啟用Resume按鈕優化",
            variable=self.enable_resume_optimization_var, command=self.save_config,
            style="Custom.TCheckbutton"
        )
        self.enable_resume_optimization_check.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=5)

        # --- 強力技能模式 ---
        row += 1
        frame_force = ttk.LabelFrame(tab, text="強力技能模式", padding=5)
        frame_force.grid(row=row, column=0, sticky="ew", pady=5)

        self.force_physical_first_combat_check = ttk.Checkbutton(
            frame_force, text="重啟後首戰使用強力技能",
            variable=self.force_physical_first_combat_var, command=self.save_config,
            style="Custom.TCheckbutton"
        )
        self.force_physical_first_combat_check.grid(row=0, column=0, sticky=tk.W)

        self.force_physical_after_inn_check = ttk.Checkbutton(
            frame_force, text="返回後首戰使用強力技能",
            variable=self.force_physical_after_inn_var, command=self.save_config,
            style="Custom.TCheckbutton"
        )
        self.force_physical_after_inn_check.grid(row=1, column=0, sticky=tk.W)

        self.force_aoe_first_combat_check = ttk.Checkbutton(
            frame_force, text="重啟後首戰使用全體技能",
            variable=self.force_aoe_first_combat_var, command=self.save_config,
            style="Custom.TCheckbutton"
        )
        self.force_aoe_first_combat_check.grid(row=0, column=1, sticky=tk.W, padx=(20, 0))

        self.force_aoe_after_inn_check = ttk.Checkbutton(
            frame_force, text="返回後首戰使用全體技能",
            variable=self.force_aoe_after_inn_var, command=self.save_config,
            style="Custom.TCheckbutton"
        )
        self.force_aoe_after_inn_check.grid(row=1, column=1, sticky=tk.W, padx=(20, 0))

        # --- AOE 設定 ---
        row += 1
        frame_aoe = ttk.LabelFrame(tab, text="AOE 設定", padding=5)
        frame_aoe.grid(row=row, column=0, sticky="ew", pady=5)

        def aoe_once_command():
            if self.aoe_once_var.get():
                if self.btn_enable_full_aoe_var.get() != True:
                    self.btn_enable_full_aoe.invoke()
                if self.btn_enable_secret_aoe_var.get() != True:
                    self.btn_enable_secret_aoe.invoke()
            self.update_change_aoe_once_check()
            self.save_config()

        self.aoe_once_check = ttk.Checkbutton(
            frame_aoe, text="一場戰鬥中僅釋放一次全體AOE",
            variable=self.aoe_once_var, command=aoe_once_command,
            style="BoldFont.TCheckbutton"
        )
        self.aoe_once_check.grid(row=0, column=0, sticky=tk.W)

        self.auto_after_aoe_check = ttk.Checkbutton(
            frame_aoe, text="全體AOE後開啟自動戰鬥",
            variable=self.auto_after_aoe_var, command=self.save_config,
            style="BoldFont.TCheckbutton"
        )
        self.auto_after_aoe_check.grid(row=1, column=0, sticky=tk.W)

    def _create_skills_tab(self):
        """技能設定分頁：6個技能按鈕組"""
        tab = self.tab_skills

        frame_skills = ttk.LabelFrame(tab, text="技能選擇", padding=10)
        frame_skills.grid(row=0, column=0, sticky="ew", pady=5)

        self.skills_button_frame = frame_skills
        for buttonName, buttonText, buttonSpell, btn_row, btn_col in SPELLSEKILL_TABLE:
            setattr(self, buttonName, ttk.Checkbutton(
                self.skills_button_frame,
                text=f"啟用{buttonText}",
                variable=getattr(self, f"{buttonName}_var"),
                command=lambda spell=buttonSpell, btnN=buttonName, btnT=buttonText: self.update_spell_config(spell, btnN, btnT),
                style="Custom.TCheckbutton"
            ))
            getattr(self, buttonName).grid(row=btn_row, column=btn_col, padx=10, pady=5, sticky=tk.W)

        # --- AE 手設定 ---
        frame_ae_caster = ttk.LabelFrame(tab, text="AE 手設定（首戰機制）", padding=5)
        frame_ae_caster.grid(row=1, column=0, sticky="ew", pady=5)

        # 先制設定
        ttk.Checkbutton(
            frame_ae_caster, text="隊伍有先制角色",
            variable=self.has_preemptive_var,
            command=self.save_config
        ).grid(row=0, column=0, columnspan=3, sticky=tk.W)

        # 技能選項（attack = 普攻）
        skill_options = ["", "attack"] + ALL_AOE_SKILLS
        order_options = ["關閉", "1", "2", "3", "4", "5", "6"]
        level_options = ["關閉", "LV2", "LV3", "LV4", "LV5"]

        # AE 手 1
        ttk.Label(frame_ae_caster, text="AE 手 1:").grid(row=1, column=0, sticky=tk.W)
        ttk.Label(frame_ae_caster, text="順序").grid(row=1, column=1, sticky=tk.W)
        self.ae_caster_1_order_combo = ttk.Combobox(
            frame_ae_caster, textvariable=self.ae_caster_1_order_var,
            values=order_options, state="readonly", width=5
        )
        self.ae_caster_1_order_combo.grid(row=1, column=2, padx=2, sticky=tk.W)
        self.ae_caster_1_order_combo.bind("<<ComboboxSelected>>", lambda e: self.save_config())

        ttk.Label(frame_ae_caster, text="技能").grid(row=1, column=3, padx=(10, 0), sticky=tk.W)
        self.ae_caster_1_skill_combo = ttk.Combobox(
            frame_ae_caster, textvariable=self.ae_caster_1_skill_var,
            values=skill_options, state="readonly", width=15
        )
        self.ae_caster_1_skill_combo.grid(row=1, column=4, padx=2, sticky=tk.W)
        self.ae_caster_1_skill_combo.bind("<<ComboboxSelected>>", lambda e: self.save_config())

        ttk.Label(frame_ae_caster, text="等級").grid(row=1, column=5, padx=(10, 0), sticky=tk.W)
        self.ae_caster_1_level_combo = ttk.Combobox(
            frame_ae_caster, textvariable=self.ae_caster_1_level_var,
            values=level_options, state="readonly", width=5
        )
        self.ae_caster_1_level_combo.grid(row=1, column=6, padx=2, sticky=tk.W)
        self.ae_caster_1_level_combo.bind("<<ComboboxSelected>>", lambda e: self.save_config())

        # AE 手 2
        ttk.Label(frame_ae_caster, text="AE 手 2:").grid(row=2, column=0, sticky=tk.W, pady=(5, 0))
        ttk.Label(frame_ae_caster, text="順序").grid(row=2, column=1, sticky=tk.W, pady=(5, 0))
        self.ae_caster_2_order_combo = ttk.Combobox(
            frame_ae_caster, textvariable=self.ae_caster_2_order_var,
            values=order_options, state="readonly", width=5
        )
        self.ae_caster_2_order_combo.grid(row=2, column=2, padx=2, sticky=tk.W, pady=(5, 0))
        self.ae_caster_2_order_combo.bind("<<ComboboxSelected>>", lambda e: self.save_config())

        ttk.Label(frame_ae_caster, text="技能").grid(row=2, column=3, padx=(10, 0), sticky=tk.W, pady=(5, 0))
        self.ae_caster_2_skill_combo = ttk.Combobox(
            frame_ae_caster, textvariable=self.ae_caster_2_skill_var,
            values=skill_options, state="readonly", width=15
        )
        self.ae_caster_2_skill_combo.grid(row=2, column=4, padx=2, sticky=tk.W, pady=(5, 0))
        self.ae_caster_2_skill_combo.bind("<<ComboboxSelected>>", lambda e: self.save_config())

        ttk.Label(frame_ae_caster, text="等級").grid(row=2, column=5, padx=(10, 0), sticky=tk.W, pady=(5, 0))
        self.ae_caster_2_level_combo = ttk.Combobox(
            frame_ae_caster, textvariable=self.ae_caster_2_level_var,
            values=level_options, state="readonly", width=5
        )
        self.ae_caster_2_level_combo.grid(row=2, column=6, padx=2, sticky=tk.W, pady=(5, 0))
        self.ae_caster_2_level_combo.bind("<<ComboboxSelected>>", lambda e: self.save_config())

    def _create_advanced_tab(self, vcmd_non_neg, checkcommand):
        """進階設定分頁：旅店休息、善惡調整、凱旋、因果"""
        tab = self.tab_advanced
        row = 0

        # --- 旅店休息 ---
        frame_rest = ttk.LabelFrame(tab, text="旅店休息", padding=5)
        frame_rest.grid(row=row, column=0, sticky="ew", pady=5)

        self.active_rest_check = ttk.Checkbutton(
            frame_rest, variable=self.active_rest_var,
            text="啟用旅店休息", command=checkcommand,
            style="Custom.TCheckbutton"
        )
        self.active_rest_check.grid(row=0, column=0, padx=5)

        ttk.Label(frame_rest, text="間隔:").grid(row=0, column=1, padx=(10, 2))
        self.rest_intervel_entry = ttk.Entry(frame_rest, textvariable=self.rest_intervel_var,
                                             validate="key", validatecommand=(vcmd_non_neg, '%P'), width=5)
        self.rest_intervel_entry.grid(row=0, column=2)
        self.button_save_rest_intervel = ttk.Button(frame_rest, text="儲存", command=self.save_config, width=4)
        self.button_save_rest_intervel.grid(row=0, column=3, padx=2)

        self.active_royalsuite_rest = ttk.Checkbutton(
            frame_rest, variable=self.active_royalsuite_rest_var,
            text="住豪華房", command=checkcommand,
            style="Custom.TCheckbutton"
        )
        self.active_royalsuite_rest.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=5)

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
        ttk.Label(tab, text="測試功能（獨立運行，不需啟動主任務）", font=("微软雅黑", 10, "bold")).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=5)
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
                use_royal_suite = self.active_rest_var.get()

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

    def update_active_rest_state(self):
        if self.active_rest_var.get():
            self.rest_intervel_entry.config(state="normal")
            self.button_save_rest_intervel.config(state="normal")
        else:
            self.rest_intervel_entry.config(state="disable")
            self.button_save_rest_intervel.config(state="disable")

    def update_organize_backpack_state(self):
        if self.organize_backpack_enabled_var.get():
            self.organize_backpack_count_spinbox.config(state="normal")
        else:
            self.organize_backpack_count_spinbox.config(state="disable")
        self.save_config()

    def update_change_aoe_once_check(self):
        if self.aoe_once_var.get()==False:
            self.auto_after_aoe_var.set(False)
            self.auto_after_aoe_check.config(state="disabled")
        if self.aoe_once_var.get():
            self.auto_after_aoe_check.config(state="normal")

    def update_system_auto_combat(self):
        is_system_auto = self.system_auto_combat_var.get()

        # 更新技能列表
        if is_system_auto:
            self._spell_skill_config_internal = ["systemAuto"]
        else:
            if self._spell_skill_config_internal == ["systemAuto"]:
                self._spell_skill_config_internal = []
                for buttonName,buttonText,buttonSpell, row, col in SPELLSEKILL_TABLE:
                    if getattr(self,f"{buttonName}_var").get():
                        self._spell_skill_config_internal += buttonSpell
        
        # 更新其他按钮信息
        button_state = tk.DISABLED if is_system_auto else tk.NORMAL
        for buttonName,_,_, _, _ in SPELLSEKILL_TABLE:
            getattr(self,buttonName).config(state=button_state)
        self.aoe_once_check.config(state = button_state)
        if is_system_auto:
            self.auto_after_aoe_check.config(state = button_state)
        else:
            self.update_change_aoe_once_check()
        
        # 更新按钮颜色并保存
        self.save_config()

    def update_spell_config(self, skills_to_process, buttonName, buttonText):
        if self.system_auto_combat_var.get():
            return

        skills_to_process_set = set(skills_to_process)

        if buttonName == "btn_enable_all":
            if getattr(self,f"{buttonName}_var").get():
                self._spell_skill_config_internal = list(skills_to_process_set)
                logger.info(f"已启用所有技能: {self._spell_skill_config_internal}")
                for btn,_,_,_,_ in SPELLSEKILL_TABLE:
                    if btn!=buttonName:
                        getattr(self,f"{btn}_var").set(True)
            else:
                self._spell_skill_config_internal = []
                for btn,_,_,_,_ in SPELLSEKILL_TABLE:
                    if btn!=buttonName:
                        getattr(self,f"{btn}_var").set(False)
                logger.info("已取消所有技能。")
        else:
            if getattr(self,f"{buttonName}_var").get():
                for skill in skills_to_process:
                    if skill not in self._spell_skill_config_internal:
                        self._spell_skill_config_internal.append(skill)
                logger.info(f"已启用{buttonText}技能. 当前技能: {self._spell_skill_config_internal}")
            else:
                self._spell_skill_config_internal = [s for s in self._spell_skill_config_internal if s not in skills_to_process_set]
                logger.info(f"已禁用{buttonText}技能. 当前技能: {self._spell_skill_config_internal}")

        # 保证唯一性，但保留顺序
        self._spell_skill_config_internal = list(dict.fromkeys(self._spell_skill_config_internal))

        self.save_config()

    def set_controls_state(self, state):
        self.button_and_entry = [
            self.adb_path_change_button,
            self.who_will_open_combobox,
            self.system_auto_check,
            self.aoe_once_check,
            self.auto_after_aoe_check,
            self.skip_recover_check,
            self.skip_chest_recover_check,
            self.enable_resume_optimization_check,
            self.force_physical_first_combat_check,
            self.force_physical_after_inn_check,
            self.active_rest_check,
            self.rest_intervel_entry,
            self.button_save_rest_intervel,
            self.karma_adjust_combobox,
            self.adb_port_entry,
            self.active_triumph,
            self.active_royalsuite_rest,
            self.button_save_adb_port,
            self.active_csc,
            self.organize_backpack_check,
            self.organize_backpack_count_spinbox,
            ]

        if state == tk.DISABLED:
            self.farm_target_combo.configure(state="disabled")
            for widget in self.button_and_entry:
                widget.configure(state="disabled")
        else:
            self.farm_target_combo.configure(state="readonly")
            for widget in self.button_and_entry:
                widget.configure(state="normal")
            self.update_active_rest_state()
            self.update_change_aoe_once_check()
            self.update_organize_backpack_state()

        if not self.system_auto_combat_var.get():
            widgets = [
                *[getattr(self,buttonName) for buttonName,_,_,_,_ in SPELLSEKILL_TABLE]
            ]
            for widget in widgets:
                if isinstance(widget, ttk.Widget):
                    widget.state([state.lower()] if state != tk.NORMAL else ['!disabled'])

    def toggle_start_stop(self):
        if not self.quest_active:
            self.start_stop_btn.config(text="停止")
            self.set_controls_state(tk.DISABLED)
            setting = FarmConfig()
            config = LoadConfigFromFile()
            for attr_name, var_type, var_config_name, var_default_value in CONFIG_VAR_LIST:
                setattr(setting, var_config_name, config[var_config_name])
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
            summary = "唔, 看起来一次成功的地下城都没有完成."
        text = f"你的队伍已经耗尽了所有的再起之火.\n在耗尽再起之火前,\n你的队伍已经完成了如下了不起的壮举:\n\n{summary}\n\n不过没关系, 至少, 你还可以找公主要钱.\n\n赞美公主殿下!\n"
        turn_to_7000G_label = ttk.Label(self, text = text)
        turn_to_7000G_label.grid(row=0, column=0,)
