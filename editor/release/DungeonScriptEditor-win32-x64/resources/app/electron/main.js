const { app, BrowserWindow } = require('electron');
const path = require('path');

// 判斷是否為開發模式
const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged;

function createWindow() {
    const mainWindow = new BrowserWindow({
        width: 1400,
        height: 900,
        minWidth: 1000,
        minHeight: 600,
        title: 'Dungeon Script Editor',
        icon: path.join(__dirname, '../assets/icon.png'),
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
        },
        // 現代化視窗外觀
        backgroundColor: '#1a1b1e',
        show: false,
    });

    // 載入應用程式
    if (isDev) {
        // 開發模式：連接 Vite 開發伺服器
        mainWindow.loadURL('http://localhost:3000');
        mainWindow.webContents.openDevTools();
    } else {
        // 生產模式：載入打包後的靜態檔案
        mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
    }

    // 視窗準備好後顯示，避免白屏閃爍
    mainWindow.once('ready-to-show', () => {
        mainWindow.show();
    });

    // 設定視窗標題
    mainWindow.on('page-title-updated', (e) => {
        e.preventDefault();
    });
}

// 當 Electron 初始化完成時建立視窗
app.whenReady().then(() => {
    createWindow();

    app.on('activate', () => {
        // macOS 特性：點擊 dock 圖示時重新建立視窗
        if (BrowserWindow.getAllWindows().length === 0) {
            createWindow();
        }
    });
});

// 所有視窗關閉時退出應用程式（macOS 除外）
app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        app.quit();
    }
});
