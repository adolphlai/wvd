# Scrcpy 串流截圖效能測試說明

## 概述

本測試比較了三種從 Android 模擬器獲取螢幕畫面的方法，為主程式優化截圖效能提供依據。

## 效能測試結果

| 方法 | 平均時間 | FPS | 加速比 | 說明 |
|------|---------|-----|--------|------|
| ADB PNG | ~570ms | 1.7 | 1x | 原始方式，包含 PNG 編碼 |
| ADB RAW | ~185ms | 5.4 | 3x | 原始像素格式，跳過 PNG 編碼 |
| **pyscrcpy 串流** | **~1ms** | **1000+** | **600x** | 視頻串流，即時獲取幀 |

## 測試檔案結構

```
test_minimap_package/
├── test_pyscrcpy.exe          # 編譯後的測試執行檔
├── test_full_performance.py   # 測試腳本源碼
├── scrcpy/                    # scrcpy 相關檔案
│   ├── adb.exe
│   ├── scrcpy.exe
│   └── ...
└── resources/images/          # 測試用模板圖片
    ├── DH-R5-minimap.png
    └── DH-R6-minimap.png
```

## 使用方式

### 方法 1：使用編譯好的執行檔

1. 複製以下檔案到測試機器：
   - `dist/test_pyscrcpy.exe`
   - `test_minimap_package/scrcpy/` (整個資料夾)
   - `test_minimap_package/resources/` (整個資料夾)

2. 確保目錄結構：
   ```
   測試資料夾/
   ├── test_pyscrcpy.exe
   ├── scrcpy/
   └── resources/images/
   ```

3. 確保模擬器已連接 (`adb devices` 可看到設備)

4. 雙擊 `test_pyscrcpy.exe` 執行

### 方法 2：使用 Python 腳本

1. 安裝依賴：
   ```bash
   pip install pyscrcpy av opencv-python numpy
   ```

2. 執行測試：
   ```bash
   python test_full_performance.py
   ```

## pyscrcpy 依賴安裝說明

pyscrcpy 需要以下依賴，可能需要手動安裝：

```bash
pip install pyscrcpy av adbutils deprecation retry2 loguru --no-deps
pip install deprecation retry2 loguru win32-setctime
```

**注意**：av (PyAV) 在某些 Python 版本可能無法編譯，建議使用預編譯版本：
```bash
pip install av --only-binary=:all:
```

## 技術實現

### ADB PNG 模式
```python
result = subprocess.run([adb, "exec-out", "screencap", "-p"], capture_output=True)
frame = cv2.imdecode(np.frombuffer(result.stdout, np.uint8), cv2.IMREAD_UNCHANGED)
```

### ADB RAW 模式
```python
result = subprocess.run([adb, "exec-out", "screencap"], capture_output=True)
# 解析原始 RGBA 像素數據
w = int.from_bytes(data[0:4], 'little')
h = int.from_bytes(data[4:8], 'little')
frame = np.frombuffer(data[12:], dtype=np.uint8).reshape((h, w, 4))
```

### pyscrcpy 串流模式
```python
from pyscrcpy import Client

client = Client(max_fps=60, max_size=1600)
client.on_frame(callback)
client.start(threaded=True)

# 獲取最新幀
frame = client.last_frame
```

## 整合到主程式的建議

1. **優先使用 pyscrcpy 串流模式**
   - 效能提升 600 倍
   - 適合需要頻繁截圖的場景

2. **退回機制**
   - 如果 pyscrcpy 不可用，使用 ADB RAW 模式
   - 如果 ADB RAW 失敗，使用 ADB PNG 模式

3. **實現示例**
   ```python
   def ScreenShot():
       if pyscrcpy_stream and pyscrcpy_stream.last_frame is not None:
           return pyscrcpy_stream.last_frame.copy()  # ~1ms
       else:
           return adb_screenshot()  # ~185ms
   ```

## 注意事項

1. pyscrcpy 需要保持連接狀態，斷線需要重新連接
2. 串流模式會佔用一些系統資源
3. 模擬器視窗大小變化可能導致需要重啟串流
4. 網路連接 (如 127.0.0.1:5555) 的效能可能與 USB 連接不同

## 相關檔案

- [test_full_performance.py](file:///d:/Project/wvd/test_minimap_package/test_full_performance.py) - 完整測試腳本
- [test_scrcpy_stream.py](file:///d:/Project/wvd/test_minimap_package/test_scrcpy_stream.py) - ADB 截圖測試
- [test_scrcpy_streaming.py](file:///d:/Project/wvd/test_minimap_package/test_scrcpy_streaming.py) - 串流測試

## 更新記錄

- 2025-12-24: 初始版本，完成三種方法的效能測試比較
