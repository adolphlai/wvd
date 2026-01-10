---
description: 撤回 GitHub 最新版本 (刪除 Release/Tag 並同步退回代碼版號)
---

此流程將完整刪除 GitHub 上的 Release 與 Tag，並自動將本地 `src/main.py` 的版號回退到前一個正確標籤。

1. 獲取並顯示擬撤回的 Tag
   * 執行指令：`git describe --tags --abbrev=0`

2. 使用 GitHub CLI 刪除遠端 Release 與 Tag
   // turbo
   ```powershell
   $targetTag = git describe --tags --abbrev=0; Write-Host "Deleting Release & Tag: $targetTag"; gh release delete $targetTag --cleanup-tag -y
   ```

3. 刪除本地 Tag 與同步移除代碼版號
   // turbo
   ```powershell
   $targetTag = git describe --tags --abbrev=0;
   # 刪除本地標籤
   git tag -d $targetTag;
   
   # 找尋刪除後的「新」最新標籤
   $prevTag = git describe --tags --abbrev=0;
   $prevVersion = $prevTag -replace '^v', '';
   Write-Host "Reverting source code version to: $prevVersion";
   
   # 修改 src/main.py (使用 PowerShell 替換)
   (Get-Content src/main.py) -replace "__version__\s*=\s*['\"].*['\"]", "__version__ = '$prevVersion'" | Set-Content src/main.py
   
   # 修改 CHANGES_LOG.md (移除失效的區塊 - 建議手動微調或由 AI 協助)
   Write-Host "Done. Please check CHANGES_LOG.md to remove the $targetTag section."
   ```

4. 提交版號回退紀錄
   // turbo
   ```powershell
   git add src/main.py; git commit -m "chore: revert version to $prevVersion"
   ```
