import os
import sys
import json
import hashlib
import threading
from urllib.request import urlopen, Request
from urllib.error import URLError
import subprocess
import time
from tkinter import ttk
import tkinter as tk
import queue
from utils import *


class CancelException(Exception):
    """自定義取消異常"""
    pass

class Progressbar(tk.Toplevel):
    def __init__(self,parent, title="進度", max_size = 1):
        self.canceled = False
        super().__init__(parent)
        self.title(title)
        self.geometry(f"300x100")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        
        # 創建進度條
        self.bar = ttk.Progressbar(self, length=300-20, mode="determinate")
        self.bar.pack(pady=20)
        
        self.downloaded_size_var = tk.IntVar(value = "")
        label = ttk.Label(self, textvariable= self.downloaded_size_var)
        label.pack()

        # 最大值
        self.max_size = max_size

    def _on_cancel(self):
        """取消按鈕回調函數"""
        self.canceled = True
        self.quit()
        self.destroy()

    def update_progress(self, value):
        """設置進度值並檢查取消狀態"""
        if self.canceled:
            raise CancelException("用戶取消操作")

        percent = round((value / self.max_size) * 100, 2)
        self.bar["value"] = percent

        def short_byte_string(bytes:int):
            if bytes >= 1024*1024*1024:
                return f"{round(bytes/1024/1024/1024,2)} GB"
            if bytes >= 1024*1024:
                return f"{round(bytes/1024/1024,2)} MB"
            if bytes >= 1024:
                return f"{round(bytes/1024,2)} KB"
            return f"{bytes} B"

        self.downloaded_size_var.set(f"{short_byte_string(value)} / {short_byte_string(self.max_size)} ({percent}%)")
        
        if self.canceled:
            raise CancelException("用戶取消操作")

class AutoUpdater():
    def __init__(self, msg_queue: queue.Queue, github_user: str, github_repo: str, current_version: str):
        self.github_user = github_user
        self.github_repo = github_repo
        self.current_version = current_version
        self.msg_queue = msg_queue

    def _is_newer_version(self, new_version):
        # 分割版本號
        new_parts = new_version.split('.')[:3]  # 只取前三個部分

        withoutbeta = self.current_version.split('-')[:1][0]  # 只取前三個部分
        current_parts = withoutbeta.split('.')[:3]  # 只取前三個部分
        
        # 確保兩個列表都有3個元素（不足的補0）
        while len(new_parts) < 3:
            new_parts.append('0')
        while len(current_parts) < 3:
            current_parts.append('0')
        
        # 逐段比較版本號
        for i in range(3):
            new_num = int(new_parts[i])
            current_num = int(current_parts[i])
            
            if new_num > current_num:
                return True
            elif new_num < current_num:
                return False
        
        return False  # 所有部分都相等

    def check_for_updates(self):
        """執行更新檢查邏輯"""
        update_url = f"https://{self.github_user}.github.io/{self.github_repo}/release.json"
        try:
            req = Request(update_url, headers={'Cache-Control': 'no-cache'})
            with urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
            
            if self._is_newer_version(data['version']):
                print(f"發現新版本: {data['version']}")
                self.update_data = data
                self.msg_queue.put(('update_available', data))

        except (URLError, ValueError, json.JSONDecodeError) as e:
            # 發生錯誤，同樣通過隊列報告。
            error_message = f"檢查更新失敗: {e}"
            logger.error(error_message)
            # self.msg_queue.put(('error', error_message))

    def download(self):
        try:
            # 創建臨時目錄
            temp_dir = "__update_temp__"
            os.makedirs(temp_dir, exist_ok=True)
            
            # 下載壓縮包
            download_url = self.update_data['download_url']
            archive_name = os.path.basename(download_url)
            archive_path = os.path.join(temp_dir, archive_name)
            
            self._download_bar_and_retry(download_url,archive_path)
            
            # 驗證MD5
            if not self._verify_md5(archive_path, self.update_data['md5']):
                self.msg_queue.put(('error', "文件校驗失敗，請手動更新"))
                return
                
            # 解壓到臨時目錄的子文件夾
            unpack_dir = os.path.join(temp_dir, "unpacked")
            os.makedirs(unpack_dir, exist_ok=True)
            self._extract_archive(archive_path, unpack_dir)
            
            # 生成重啓腳本
            restart_script = self._create_restart_script(unpack_dir)
            
            # 發送重啓信號.
            self.msg_queue.put(('restart_ready', restart_script))
                
        except Exception as e:
            self.msg_queue.put(('error', f"更新失敗: {str(e)}"))
    
    def _download_bar_and_retry(self, download_url, archive_path):
        max_retries = 3
        retry_count = 0
        success = False

        while retry_count <= max_retries and not success:
            try:
                # 打開網絡連接
                with urlopen(download_url) as response:
                    # 獲取文件總大小（字節）
                    total_size = int(response.headers.get('Content-Length', 0))
                    
                    self.msg_queue.put(('download_started', total_size))
                    
                    # 打開本地文件
                    with open(archive_path, 'wb') as out_file:
                        downloaded = 0
                        # 分塊讀取數據（每次800KB）
                        while True:
                            chunk = response.read(819200)  # 800KB緩衝區
                            if not chunk:
                                break  # 數據讀取完成
                            
                            # 寫入本地文件
                            out_file.write(chunk)
                            downloaded += len(chunk)
                            
                            self.msg_queue.put(('progress', downloaded))
                        
                        # 下載完成標記
                        success = True
                self.msg_queue.put(('download_complete', None))
                
            except (URLError, IOError, ConnectionResetError) as e:
                # 網絡或IO異常處理
                retry_count += 1
                
                if retry_count > max_retries:
                    # 重試次數耗盡，拋出原始異常
                    raise e
                else:
                    # 顯示重試信息
                    print(f"下載中斷，正在重試 ({retry_count}/{max_retries})...")
                    time.sleep(2)  # 重試前等待2秒


    def _extract_archive(self, archive_path, target_dir):
        """解壓壓縮包"""
        if archive_path.lower().endswith('.zip'):
            # 使用Python內置zipfile模塊解壓
            import zipfile
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                zip_ref.extractall(target_dir)
        else:
            raise Exception(f"不支持的壓縮格式: {os.path.splitext(archive_path)[1]}")

    def _verify_md5(self, file_path, expected_md5):
        """驗證文件MD5哈希值"""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest() == expected_md5

    def _create_restart_script(self, unpack_dir):
        """創建重啓腳本(跨平臺), 並返回啓動腳本的路徑或指令."""
        if sys.platform == "win32":
            script = f"""@echo off
REM 等待原始程序退出
timeout /t 2 /nobreak >nul

REM 複製解壓後的文件到當前目錄
xcopy /E /Y /Q "{unpack_dir}\\*" "."

REM 啓動新版本程序
start "" "{os.path.basename(sys.argv[0])}"

REM 清理臨時文件
rmdir /S /Q "__update_temp__"

REM 刪除自身
del "%~f0"
    """
            with open("_update_restart.bat", "w") as f:
                f.write(script)
            return "_update_restart.bat"
        else:  # Linux/macOS
            script = f"""#!/bin/bash
    # 等待原始程序退出
    sleep 2

    # 移動解壓後的文件到當前目錄
    mv -f "{unpack_dir}"/* .

    # 添加執行權限（如果需要）
    chmod +x "{os.path.basename(sys.argv[0])}"

    # 啓動新版本程序
    nohup ./{os.path.basename(sys.argv[0])} >/dev/null 2>&1 &

    # 清理臨時文件
    rm -rf "__update_temp__"

    # 刪除自身
    rm -- "$0"
    """
            with open("_update_restart.sh", "w") as f:
                f.write(script)
            return "nohup ./_update_restart.sh &"