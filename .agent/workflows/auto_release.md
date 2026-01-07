---
description: 自動更新版本、生成 AI Changelog 並推送 Tag 觸發 GitHub Actions
---

### 第一步：環境檢查與版本讀取
1. 讀取 `src/main.py` 中的 `__version__` 變量。
2. 執行 `git log` 獲取自上個版本以來的所有 Commit 紀錄。

### 第二步：AI 生成更新日誌
1. 使用 AI 分析 Commit 紀錄，總結功能新增與修復。
2. 將總結內容寫入 `CHANGES_LOG.md` 的頂部，保留歷史紀錄。
   - **格式要求**：包含日期、新版本號、分類好的功能清單。

### 第三步：遞增版本號
1. 根據變動程度（預設為 patch，除非用戶指定）計算新版本號（例如 `1.9.25` -> `1.9.26`）。
2. **修改文件**：將新版本號寫回 `src/main.py` 的 `__version__` 字段。

### 第四步：執行 Git 提交與打標籤 (關鍵步驟)
1. 執行終端指令：
   - `git add src/main.py CHANGES_LOG.md`
   - `git commit -m "chore: release v[新版本號]"`
   - `git tag v[新版本號]`
2. 提示用戶確認後執行推送：
   - `git push origin main`
   - `git push origin v[新版本號]`

### 第五步：通知
1. 完成後告知用戶：「已推送標籤 v[新版本號]，GitHub Actions 已開始構建可執行文件。」