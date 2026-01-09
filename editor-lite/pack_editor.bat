@echo off
echo [INFO] Packaging Editor Lite...

REM 1. 切換到腳本所在目錄
cd /d "%~dp0"

REM 2. 檢查 PyInstaller 是否安裝
py -3.11 -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] PyInstaller not found! Please install it using: pip install pyinstaller
    pause
    exit /b 1
)

REM 強制關閉正在運行的實例
taskkill /F /IM DungeonEditor.exe >nul 2>&1

REM 3. 執行 PyInstaller 打包 start_editor.py
REM 使用 --onefile 打包成單一執行檔
REM 使用 --noconsole 隱藏黑窗 (如果你想要看到 log，可以拿掉這個參數)
REM 使用 --icon 指定圖示 (如果有 icon 的話，這裡先省略)
REM 指定名稱為 DungeonEditor
echo [INFO] Building executable...
py -3.11 -m PyInstaller --onefile --name DungeonEditor --noconsole start_editor.py

REM 4. 移動生成的 exe 到當前目錄
if exist "dist\DungeonEditor.exe" (
    move /Y "dist\DungeonEditor.exe" "."
    echo [SUCCESS] DungeonEditor.exe created!
) else (
    echo [ERROR] Build failed!
    pause
    exit /b 1
)

REM 5. 清理暫存檔 (請勿刪除 dist，因為裡面有網頁檔案)
echo [INFO] Cleaning up...
rd /s /q build
del /q DungeonEditor.spec

echo [DONE] You can now move this folder to another PC.
echo Keep 'dist' folder along with 'DungeonEditor.exe'.
pause
