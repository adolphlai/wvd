---
description: 打包與發布流程（本地打包與 GitHub Actions）
---

# 打包與發布說明

> **重要**: 由於 pyscrcpy/av 無法在 GitHub Actions CI 安裝，發布必須本地打包後手動上傳。

## 本地打包

### 使用方式
```batch
localpack.bat
```

### 前置條件
1. 安裝 Anaconda
2. 創建 `vpy` 虛擬環境
3. 修改 `localpack.bat` 中的 `ANACONDA_PATH`
4. (可選) 安裝串流支援: `pip install pyscrcpy av`

### 輸出
`dist/wvd/wvd.exe`

## 發布流程

1. **更新版本號** (`src/main.py`)
   ```python
   __version__ = '1.9.26'  # 正式版
   __version__ = '1.9.26-beta.1'  # 預發布版
   ```

2. **提交並推送代碼**
   ```bash
   git add -A && git commit -m "release: v1.9.26" && git push
   ```

3. **創建並推送 Tag**
   ```bash
   git tag v1.9.26 && git push origin v1.9.26
   ```

4. **本地打包並上傳**
   - 運行 `localpack.bat`
   - 壓縮 `dist/wvd/` 為 `wvd.zip`
   - 到 GitHub Release 手動上傳替換

## 版本號規則

| 代碼版本號 | Git Tag | 狀態 |
|-----------|---------|------|
| `1.9.25` | `v1.9.25` | **Latest** |
| `1.9.25-beta.1` | `v1.9.25-beta.1` | Pre-release |

版本號包含 `-` 就是 Pre-release。
