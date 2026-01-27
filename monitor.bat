@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion
title [穩定版] 巫術：達芙妮 守護進程

:: ============= 原始參數 =============
set "EMU_DIR=C:\Program Files\Netease\MuMuPlayer\nx_device\12.0\shell"
set "EMU_PATH=%EMU_DIR%\MuMuNxDevice.exe"
set "ADB_PATH=%EMU_DIR%\adb.exe"

set "EMU_PROCESS=MuMuNxDevice.exe"
set "EMU_SVC=MuMuVMMSVC.exe"
set "ADB_PORT=5555"
set "PKG_NAME=jp.co.drecom.wizardry.daphne"
:: ====================================

:MONITOR
cls
echo [%date% %time%] ------------------------------------
echo [步驟 1] 正在檢查 ADB 服務狀態...

:: A. 檢查是否 Offline (比照 script.py 869-878 行)
"%ADB_PATH%" devices > temp_devices.txt
findstr /i "127.0.0.1:%ADB_PORT%" temp_devices.txt > nul
if %errorlevel% equ 0 (
    findstr /i "offline" temp_devices.txt > nul
    if !errorlevel! equ 0 (
        echo [嚴重] 偵測到設備處於 Offline 狀態，判定為死機！
        goto FORCE_KILL_SEQUENCE
    )
)

:: B. 嘗試連接 (比照 script.py 889 行)
echo 正在嘗試連接 127.0.0.1:%ADB_PORT%...
"%ADB_PATH%" connect 127.0.0.1:%ADB_PORT% > temp_connect.txt 2>&1
type temp_connect.txt

:: C. 判定連接結果 (比照 script.py 896 行: refused 或 cannot connect)
findstr /i "refused cannot" temp_connect.txt > nul
if %errorlevel% equ 0 (
    echo [嚴重] 連接被拒絕或無法連接，判定模擬器未啟動或已崩潰！
    goto FORCE_KILL_SEQUENCE
)

:: D. 最終檢查 (比照 script.py 893 行: 確保有 connected 或 already)
findstr /i "connected already" temp_connect.txt > nul
if %errorlevel% neq 0 (
    echo [錯誤] 設備狀態不明，為了保險起見，執行強殺重啟...
    goto FORCE_KILL_SEQUENCE
)

echo [正常] ADB 已成功連線至模擬器.
goto CHECK_GAME


:FORCE_KILL_SEQUENCE
echo [動作] 執行強制終止程序 (完全同步 script.py 邏輯)...
:: 1. 殺死模擬器
taskkill /f /im %EMU_PROCESS%
timeout /t 1 > nul
:: 2. 殺死服務
taskkill /f /im %EMU_SVC%
timeout /t 1 > nul
:: 3. 殺死 ADB (同步 KillAdb 函數)
taskkill /f /im adb.exe
timeout /t 1 > nul
taskkill /f /im HD-Adb.exe > nul 2>&1

echo [動作] 重啟模擬器中...
start "" "%EMU_PATH%"
echo [等待] 給予 60 秒啟動緩衝...
timeout /t 60
goto START_GAME


:CHECK_GAME
echo [步驟 2] 檢查遊戲進程 (%PKG_NAME%)...
"%ADB_PATH%" shell pidof %PKG_NAME% > nul
if %errorlevel% neq 0 (
    echo [警告] 遊戲進程消失，啟動中...
    goto START_GAME
)

:: 檢查前台 (比照 _monitor_game_process)
"%ADB_PATH%" shell "dumpsys window | grep mCurrentFocus" | find /i "%PKG_NAME%" > nul
if %errorlevel% neq 0 (
    echo [資訊] 遊戲在背景，正在拉回前台...
    "%ADB_PATH%" shell monkey -p %PKG_NAME% 1
)
echo [正常] 遊戲運行中.
goto END_LOOP


:START_GAME
echo [遊戲] 啟動巫術...
"%ADB_PATH%" shell am force-stop %PKG_NAME%
timeout /t 2
"%ADB_PATH%" shell monkey -p %PKG_NAME% 1
timeout /t 25
goto MONITOR


:END_LOOP
del temp_devices.txt > nul 2>&1
del temp_connect.txt > nul 2>&1
echo --------------------------------------------------
echo [%time%] 監控正常，60 秒後執行下一輪巡檢.
timeout /t 60
goto MONITOR