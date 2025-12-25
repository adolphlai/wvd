@echo OFF
setlocal

set "ANACONDA_PATH=C:\P\Anaconda"

echo [INFO] Cleaning old build files...
rd /s /q "dist" 2>nul
rd /s /q "build" 2>nul

echo Activating Anaconda base environment...
call "%ANACONDA_PATH%\Scripts\activate.bat" base
if errorlevel 1 (
    echo Failed to activate base environment.
    pause
    exit /b 1
)

echo Initializing virtualenvwrapper...
call "%ANACONDA_PATH%\Scripts\virtualenvwrapper.bat"
if errorlevel 1 (
    echo Failed to initialize virtualenvwrapper.
    pause
    exit /b 1
)

echo Activating virtual environment 'vpy' using workon...
call workon vpy
if not defined VIRTUAL_ENV (
    echo Failed to activate virtual environment 'vpy' with workon.
    echo Ensure 'vpy' exists and WORKON_HOME is set correctly.
    pause
    exit /b 1
)
echo Successfully activated 'vpy'. VIRTUAL_ENV is %VIRTUAL_ENV%

echo Installing requirements (using pre-built wheels for av)...
pip install av --only-binary=:all:
pip install pyscrcpy --no-deps
pip install adbutils loguru deprecation retry2
pip install -r requirements.txt --ignore-installed av pyscrcpy
if errorlevel 1 (
    echo Warning: Some requirements may have failed, continuing...
)

for /f %%i in ('powershell -Command "Get-Date -Format 'yyyyMMddHHmm'"') do set timestamp=%%i

echo Building with PyInstaller (including pyscrcpy dependencies)...
py -3.11 -m PyInstaller --onedir --noconsole --noconfirm ^
    --add-data "resources;resources/" ^
    --hidden-import=pyscrcpy ^
    --hidden-import=pyscrcpy.core ^
    --hidden-import=av ^
    --hidden-import=adbutils ^
    --hidden-import=deprecation ^
    --hidden-import=retry2 ^
    --hidden-import=loguru ^
    --collect-all=pyscrcpy ^
    --collect-all=adbutils ^
    src/main.py -n wvd

if errorlevel 1 (
    echo Failed to run pyinstaller.
    pause
    exit /b 1
)

echo Script finished.
pause
endlocal
