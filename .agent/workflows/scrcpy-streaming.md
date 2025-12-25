---
description: Scrcpy 串流截圖效能測試與整合說明
---

# Scrcpy 串流截圖效能測試

## 效能測試結果

| 方法 | 平均時間 | FPS | 加速比 |
|------|---------|-----|--------|
| ADB PNG | ~570ms | 1.7 | 1x |
| ADB RAW | ~185ms | 5.4 | 3x |
| **pyscrcpy 串流** | **~1ms** | **1000+** | **600x** |

## 技術實現

### ADB PNG 模式
```python
result = subprocess.run([adb, "exec-out", "screencap", "-p"], capture_output=True)
frame = cv2.imdecode(np.frombuffer(result.stdout, np.uint8), cv2.IMREAD_UNCHANGED)
```

### pyscrcpy 串流模式
```python
from pyscrcpy import Client
client = Client(max_fps=60, max_size=1600)
client.start(threaded=True)
frame = client.last_frame
```

## 依賴安裝

```bash
pip install pyscrcpy av adbutils --no-deps
pip install deprecation retry2 loguru win32-setctime
pip install av --only-binary=:all:
```

## 整合建議

### 退回機制實現
```python
def ScreenShot():
    if pyscrcpy_stream and pyscrcpy_stream.last_frame is not None:
        return pyscrcpy_stream.last_frame.copy()  # ~1ms
    else:
        return adb_screenshot()  # ~185ms
```

## 注意事項

1. pyscrcpy 需要保持連接狀態，斷線需重新連接
2. 串流模式會佔用系統資源
3. 模擬器視窗大小變化可能需要重啟串流
4. 網路連接效能可能與 USB 連接不同
