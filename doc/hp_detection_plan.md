# 血量偵測功能實作計畫

## 目標
在 GUI 即時監控面板新增「血量偵測」指標。

## 需求
1. **位置**：放在「AUTO比對」後面（第11行，第2-3列）
2. **顯示邏輯**：
   - 地城移動狀態下（`current_target == "position"`）→ 執行偵測
   - 如有角色紅色 **10%~20%** → 顯示「低血量」（紅色）
   - 否則 → 顯示「正常」（綠色）
3. **非地城移動狀態** → 顯示「--」

## 修改項目

### 1. MonitorState 類別 (script.py)

新增低血量旗標：
```python
flag_low_hp: bool = False  # 是否偵測到低血量角色
```

---

### 2. 新增 CheckLowHP 函數 (script.py)

```python
def CheckLowHP(screenImage):
    """檢查是否有角色處於低血量狀態 (紅色 10%~20%)"""
    rois = [
        (130, 1300, 60, 30),  # 角色0
        (420, 1300, 60, 30),  # 角色1
        (700, 1300, 60, 30),  # 角色2
        (130, 1485, 60, 20),  # 角色3
        (420, 1485, 60, 20),  # 角色4
        (700, 1485, 60, 20),  # 角色5
    ]
    # 檢查每個 ROI 的紅色百分比
    # 若 10% <= 紅色 <= 20% 則判定為低血量
```

---

### 3. GUI 新增顯示標籤 (gui.py)

在 AUTO比對 後面新增：
```python
ttk.Label(self.monitor_frame, text="血量偵測:").grid(row=11, column=2)
self.monitor_hp_status_var = tk.StringVar(value="--")
```

---

### 4. 更新顯示邏輯 (gui.py _update_monitor)

```python
if current_target == "position":  # 地城移動
    if MonitorState.flag_low_hp:
        顯示「低血量」（紅色）
    else:
        顯示「正常」（綠色）
else:
    顯示「--」
```

## 驗證方式
1. 啟動程式，確認監控面板顯示「血量偵測: --」
2. 進入地城移動狀態，確認顯示更新
3. 使用 lowhp_status 測試圖片驗證偵測準確度
