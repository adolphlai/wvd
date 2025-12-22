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
        self.geometry('600x550')  # 适中的窗口大小
        
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
        # === 日志显示区域（右侧）===
        scrolled_text_formatter = logging.Formatter('%(message)s')
        self.log_display = scrolledtext.ScrolledText(self, wrap=tk.WORD, state=tk.DISABLED, bg='#ffffff',bd=2,relief=tk.FLAT, width = 34, height = 30)
        self.log_display.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.scrolled_text_handler = ScrolledTextHandler(self.log_display)
        self.scrolled_text_handler.setLevel(logging.INFO)
        self.scrolled_text_handler.setFormatter(scrolled_text_formatter)
        logger.addHandler(self.scrolled_text_handler)

        self.summary_log_display = scrolledtext.ScrolledText(self, wrap=tk.WORD, state=tk.DISABLED, bg="#C6DBF4",bd=2, width = 34, )
        self.summary_log_display.grid(row=1, column=1, pady=5)
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

        # 创建四个分页
        self.tab_general = ttk.Frame(self.notebook, padding=10)
        self.tab_battle = ttk.Frame(self.notebook, padding=10)
        self.tab_skills = ttk.Frame(self.notebook, padding=10)
        self.tab_advanced = ttk.Frame(self.notebook, padding=10)

        self.notebook.add(self.tab_general, text="一般設定")
        self.notebook.add(self.tab_battle, text="戰鬥設定")
        self.notebook.add(self.tab_skills, text="技能設定")
        self.notebook.add(self.tab_advanced, text="進階設定")

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

    def update_active_rest_state(self):
        if self.active_rest_var.get():
            self.rest_intervel_entry.config(state="normal")
            self.button_save_rest_intervel.config(state="normal")
        else:
            self.rest_intervel_entry.config(state="disable")
            self.button_save_rest_intervel.config(state="disable")

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
            self.active_csc
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
