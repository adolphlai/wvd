---
description: 撤回 GitHub 最新版本 (利用 GitHub CLI 完整刪除 Release 與 Tag)
---

此流程將會使用 `gh` 指令刪除 GitHub 上的 Release 及其對應的 Tag，並同步刪除本地 Tag。

1. 獲取並顯示當前最新的 Tag
   * 執行指令：`git describe --tags --abbrev=0`

2. 使用 GitHub CLI 刪除遠端 Release 與 Tag
   * 這會連同 Release 頁面與上傳的檔案一併刪除，並從遠端移除 Tag。
   * **警告**：此操作不可逆。

   // turbo
   ```powershell
   $tag = git describe --tags --abbrev=0; Write-Host "Deleting Release & Tag: $tag"; gh release delete $tag --cleanup-tag -y
   ```

3. 同步刪除本地 Tag
   * 確保本地 git 狀態與遠端一致。
   
   // turbo
   ```powershell
   $tag = git describe --tags --abbrev=0; git tag -d $tag
   ```
