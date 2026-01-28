---
description: 自動更新版本、生成 AI Changelog 並推送 Tag 觸發 GitHub Actions
---

### 第一步：環境檢查與版本讀取
1. 讀取 `src/main.py` 中的 `__version__` 變量。
2. 執行 `git log` 獲取自上個版本以來的所有 Commit 紀錄。

### 第二步：AI 生成更新日誌
1.  **AI 角色設定**：請扮演「遊戲社群管理員」，為玩家撰寫通俗易懂的更新日誌。
2.  **內容篩選與轉譯**：
    - **絕對禁止**使用技術術語：如 `refactor`, `thread`, `lock`, `syntax`, `variable`, `logic`, `pyscrcpy`, `stoppable`, `lambda` 等。
    - 將程式變更「轉譯」為玩家感受：例如「優化停止響應」而非「加入 check_stop_signal」、「修復關閉卡死」而非「修正 mutex lock」。
    - 忽略純技術重構或細微代碼修正。
3.  **格式與風格**：
    - 參考文件中 v1.9.xx 或更早以前的**原作者簡潔風格**。
    - 將總結內容寫入 `CHANGES_LOG.md` 的頂部，保留歷史紀錄。
    - **同步更新 `README.md`**：將本次更新的精簡摘要同步至 `README.md` 的「版本更新記錄」最上方。
    - **格式要求**：包含日期、新版本號、分類好的功能清單。

### 第三步：遞增版本號
1. 根據變動程度（預設為 patch，除非用戶指定）計算新版本號（例如 `1.9.25` -> `1.9.26`）。
2. **修改文件**：將新版本號寫回 `src/main.py` 的 `__version__` 字段。

### 第四步：執行 Git 提交與打標籤 (關鍵步驟)
1. 執行終端指令：
   - `git add src/main.py CHANGES_LOG.md README.md`
   - `git commit -m "chore: release v[新版本號]"`
   - `git tag v[新版本號]`
2. 提示用戶確認後執行推送：
   - `git push origin master`
   - `git push origin v[新版本號]`

### 第五步：通知
1. 完成後告知用戶：「已推送標籤 v[新版本號]，GitHub Actions 已開始構建可執行文件。」