from gui import *
import argparse

__version__ = '1.11.25'
OWNER = "arnold2957"
REPO = "wvd"

class AppController(tk.Tk):
    def __init__(self, headless, config_path):
        super().__init__()
        self.withdraw()
        self.msg_queue = queue.Queue()
        self.main_window = None
        if not headless:
            if not self.main_window:
                self.main_window = ConfigPanelApp(self,
                                                  __version__,
                                                  self.msg_queue)
        else:
            HeadlessActive(config_path,
                           self.msg_queue)
            
        self.quest_threading = None
        self.quest_setting = None

        self.is_checking_for_update = False
        self.updater = AutoUpdater(
            msg_queue=self.msg_queue,
            github_user=OWNER,
            github_repo=REPO,
            current_version=__version__
        )
        # 禁用自動更新檢查以避免卡死問題
        # self.schedule_periodic_update_check()
        self.check_queue()

    def run_in_thread(self, target_func, *args):
        thread = threading.Thread(target=target_func, args=args, daemon=True)
        thread.start()
    def schedule_periodic_update_check(self):
        # 如果當前沒有在檢查或下載，則啓動一個新的檢查
        if not self.is_checking_for_update:
            # print("調度器：正在啓動一小時一次的後臺更新檢查...")
            self.is_checking_for_update = True  # 設置標誌，防止重複
            self.run_in_thread(self.updater.check_for_updates)
            self.is_checking_for_update = False
        else:
            # print("調度器：上一個檢查/下載任務尚未完成，跳過本次檢查。")
            None
        self.after(3600000, self.schedule_periodic_update_check)

    def on_closing(self):
        """處理窗口關閉事件，確保所有資源正確清理"""
        try:
            logger.info('=== 開始關閉程序 ===')

            # 1. 停止正在運行的任務
            if hasattr(self, 'quest_threading') and self.quest_threading and self.quest_threading.is_alive():
                logger.info('正在停止任務線程...')
                if hasattr(self.quest_setting, '_FORCESTOPING'):
                    self.quest_setting._FORCESTOPING.set()
                    logger.info('已設置停止信號')

                # 不等待線程結束，因為：
                # 1. 線程已設置為 daemon，主程序退出時會自動終止
                # 2. join() 可能會阻塞導致關閉緩慢
                # 3. 我們會立即調用 os._exit(0) 強制終止
                logger.info('跳過等待線程，daemon 線程會隨主程序退出')

            # 2. 停止 pyscrcpy 串流（關鍵：避免卡死）
            logger.info('正在停止 pyscrcpy 串流...')
            try:
                from script import cleanup_scrcpy_stream
                cleanup_scrcpy_stream()
            except Exception as e:
                print(f"停止 pyscrcpy 串流失敗: {e}")

            # 3. 停止日誌監聽器
            logger.info('正在停止日誌監聯器...')
            try:
                StopLogListener()
            except Exception as e:
                print(f"停止日誌監聽器失敗: {e}")

            # 4. 清理消息隊列
            try:
                while not self.msg_queue.empty():
                    self.msg_queue.get_nowait()
            except:
                pass

            logger.info('資源清理完成，程序即將退出')

        except Exception as e:
            print(f"清理過程中發生錯誤: {e}")
        finally:
            # 5. 銷毀 GUI
            try:
                self.destroy()
            except:
                pass

            # 6. 強制退出（確保進程完全終止）
            # 使用 os._exit() 而不是 sys.exit()，因為它會立即終止進程
            # 包括所有 daemon 線程，不會等待任何清理
            print('強制終止進程')  # 使用 print 因為 logger 可能已關閉
            os._exit(0)

    def check_queue(self):
        """處理來自AutoUpdater和其他服務的消息"""
        try:
            message = self.msg_queue.get_nowait()
            command, value = message
            
            # --- 這是處理更新邏輯的核心部分 ---
            match command:
                case 'start_quest':
                    self.quest_setting = value
                    self.quest_setting._MSGQUEUE = self.msg_queue
                    self.quest_setting._FORCESTOPING = Event()
                    Farm = Factory()
                    self.quest_threading = Thread(target=Farm,args=(self.quest_setting,), daemon=True)
                    self.quest_threading.start()
                    logger.info(f'啓動任務\"{self.quest_setting._FARMTARGET_TEXT}\"...')

                case 'stop_quest':
                    logger.info('停止任務...')
                    if hasattr(self, 'quest_threading') and self.quest_threading.is_alive():
                        if hasattr(self.quest_setting, '_FORCESTOPING'):
                            self.quest_setting._FORCESTOPING.set()
                    # 停止 pyscrcpy 串流以釋放資源
                    try:
                        from script import cleanup_scrcpy_stream
                        cleanup_scrcpy_stream()
                    except Exception as e:
                        logger.warning(f"停止 pyscrcpy 串流失敗: {e}")

                case 'task_finished':
                    # 從主線程調用 finishingcallback，避免 Tkinter 線程安全問題
                    if self.main_window:
                        self.main_window.finishingcallback()

                case 'turn_to_7000G':
                    logger.info('開始要錢...')
                    self.quest_setting._FARMTARGET = "7000G"
                    self.quest_setting._COUNTERDUNG = 0
                    while 1:
                        if not self.quest_threading.is_alive():
                            Farm = Factory()
                            self.quest_threading = Thread(target=Farm,args=(self.quest_setting,), daemon=True)
                            self.quest_threading.start()
                            break
                    if self.main_window:
                        self.main_window.turn_to_7000G()

                case 'update_available':
                    # 在面板上顯示提示
                    update_data = value
                    version = update_data['version']
                    if self.main_window:
                        self.main_window.find_update.grid()
                        self.main_window.update_text.grid()
                        self.main_window.latest_version.set(version)
                        self.main_window.button_auto_download.grid()
                        self.main_window.button_manual_download.grid()
                        self.main_window.update_sep.grid()
                        self.main_window.save_config()
                        width, height = map(int, self.main_window.geometry().split('+')[0].split('x'))
                        self.main_window.geometry(f'{width}x{height+50}')

                        self.main_window.button_auto_download.config(command=lambda:self.run_in_thread(self.updater.download))          
                case 'download_started':
                    # 控制器決定創建並顯示進度條窗口
                    if not hasattr(self, 'progress_window') or not self.progress_window.winfo_exists():
                        self.progress_window = Progressbar(self.main_window,title="下載中...",max_size = value)

                case 'progress':
                    # 控制器更新進度條UI
                    if hasattr(self, 'progress_window') and self.progress_window.winfo_exists():
                        self.progress_window.update_progress(value)
                        self.update()
                        None

                case 'download_complete':
                    # 控制器關閉進度條並顯示成功信息
                    if hasattr(self, 'progress_window') and self.progress_window.winfo_exists():
                        self.progress_window.destroy()

                case 'error':
                    # 控制器處理錯誤顯示
                    if hasattr(self, 'progress_window') and self.progress_window.winfo_exists():
                        self.progress_window.destroy()
                    messagebox.showerror("錯誤", value, parent=self.main_window)

                case 'restart_ready':
                    script_path = value
                    messagebox.showinfo(
                        "更新完成",
                        "新版本已準備就緒，應用程序即將重啓！",
                        parent=self.main_window
                    )
                    
                    if sys.platform == "win32":
                        subprocess.Popen([script_path], shell=True)
                    else:
                        os.system(script_path)
                    
                    self.destroy()
                    
                case 'no_update_found':
                    # （可選）可以給個安靜的提示，或什麼都不做
                    print("UI: 未發現更新。")

        except queue.Empty:
            pass
        finally:
            # 持續監聽
            self.after(100, self.check_queue)

def parse_args():
    """解析命令行參數"""
    parser = argparse.ArgumentParser(description='WvDAS命令行參數')
    
    # 添加-headless標誌參數
    parser.add_argument(
        '-headless', 
        '--headless', 
        action='store_true',  # 檢測到參數即標記爲True
        help='以無頭模式運行程序'
    )
    
    # 添加可選的config_path參數
    parser.add_argument(
        '-config', 
        '--config', 
        type=str,  # 自動轉換爲字符串
        default=None,  # 默認值設爲None
        help='配置文件路徑 (例如: c:/config.json)'
    )
    
    return parser.parse_args()

def main():
    args = parse_args()

    controller = AppController(args.headless, args.config)
    controller.mainloop()

def HeadlessActive(config_path,msg_queue):
    RegisterConsoleHandler()
    RegisterQueueHandler()
    StartLogListener()

    setting = FarmConfig()
    config = LoadConfigFromFile(config_path)
    for _, _, var_config_name, _ in CONFIG_VAR_LIST:
        setattr(setting, var_config_name, config[var_config_name])
    msg_queue.put(('start_quest', setting))


    logger.info(f"WvDAS 巫術daphne自動刷怪 v{__version__} @德德Dellyla(B站)")

if __name__ == "__main__":
    main()
