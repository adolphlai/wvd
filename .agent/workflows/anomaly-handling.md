---
description: IdentifyState 異常處理與自動恢復邏輯
---

# 異常處理邏輯 (IdentifyState)

## 觸發條件
當狀態識別循環計數器 `counter >= 4` 時，執行以下恢復操作。

## 1. 自動恢復與重置
- **死而復生 (RiseAgain)**: 偵測到復活界面時調用 `RiseAgainReset(reason='combat')`
- **世界地圖縮放**: 偵測到 `worldmapflag` 時，嘗試縮放調整
- **沙男恢復 (sandman_recover)**: 偵測到標誌時點擊並重新識別
- **時間跳躍中斷**: 偵測到 `cursedWheel_timeLeap` 時發送 `turn_to_7000G` 消息

## 2. 善惡值 (Karma) 調整
- **伏擊 (ambush)**: `_KARMAADJUST` 以 `-` 開頭時點擊伏擊按鈕
- **積善 (ignore)**: `_KARMAADJUST` 以 `+` 開頭時點擊忽略按鈕

## 3. 對話選項自動清理
偵測並點擊以下對話按鈕：
- `adventurersbones` (冒險者骨頭)
- `halfBone` (屍油)
- `nothanks` (不必了)
- `strange_things`, `blessing`, `DontBuyIt`...

## 4. 嚴重異常處理
- **多人死亡 (multipeopledead)**: 設置 `_SUICIDE = True`
- **下載更新 (startdownload)**: 自動點擊確認下載
- **返回標題 (totitle)**: 網路故障時點擊返回
- **黑屏檢測 (counter > 15)**: 準備重啟
- **重啟遊戲 (counter >= 25)**: 調用 `restartGame()`

## 5. 畫面盲點嘗試 (counter >= 4)
點擊 `[1, 1]` (左上角) 三次，每次間隔 0.25 秒。
