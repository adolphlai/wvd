# Antigravity 通用工程規則（Rules）

## 一、語言與輸出約定

* 所有回覆、說明、注釋、文檔 **必須使用繁體**
* 代碼中的標識符保持英文，不使用拼音
* 錯誤信息、日志內容允許為英文


## 二、技術默認約定

* 前端：默認使用 **React + TypeScript**
* 後端：默認使用 **Python（優先 FastAPI）**
* 若無特殊說明，均遵循以上技術選型


## 三、通用代碼規範

### 命名規範

* 變量 / 函數：camelCase
* 類 / 組件：PascalCase
* 常量：UPPER_SNAKE_CASE
* 文件 / 文件夾：kebab-case

命名應語義清晰，禁止隨意縮寫。


### 注釋規範（強制）

* 注釋用於解釋「為什麽這樣設計」，而不是代碼字面含義
* 覆雜邏輯、業務判斷、邊界條件必須寫注釋
* 禁止無意義注釋

統一注釋標記：

```ts
// TODO: 待實現功能
// FIXME: 已知問題或潛在缺陷
// NOTE: 重要設計說明
// HACK: 臨時方案，後續必須重構
```

#### 函數注釋規範

前端（JSDoc）：

```ts
/**
 * 獲取用戶信息
 * @param userId 用戶 ID
 * @returns 用戶數據
 */
```

後端（Python Docstring）：

```python
def get_user(user_id: str):
    """
    根據用戶 ID 獲取用戶信息
    """
```


## 四、前端規範（React）

### 基本原則

* 使用函數組件，不使用類組件
* 單個組件只承擔單一職責
* 展示邏輯與業務邏輯分離
* 可覆用邏輯必須抽離為自定義 Hook


### 命名約定

* 組件名使用 PascalCase
* 文件名與組件名保持一致
* 自定義 Hook 必須以 `use` 開頭

```ts
function UserCard() {}
function useUserData() {}
```


### Hooks 使用規範

* 只能在函數組件或自定義 Hook 中調用
* 不允許在條件、循環中調用
* 一個 Hook 只處理一種職責


### Props 規範

* 必須使用 TypeScript 類型定義
* 使用解構方式接收 props
* 非必傳參數使用 `?`

```ts
interface UserCardProps {
  user: User
  onClick?: () => void
}
```


### 性能與結構要求

* 避免不必要的重覆渲染
* 合理使用 useMemo / useCallback
* 列表渲染必須提供穩定的 key
* 大數據列表使用虛擬滾動
* 路由與組件支持懶加載


## 五、後端規範（Python）

### 基本要求

* Python ≥ 3.10
* 優先使用 FastAPI
* 所有函數與方法必須標注類型
* 禁止使用裸 `except`
* 禁止使用 `print` 作為日志方式


### 分層結構（必須遵守）

* api：請求解析與響應封裝
* service：業務邏輯處理
* repository：數據庫訪問
* schema：請求 / 響應數據校驗
* model：ORM 模型定義

禁止在 api 層直接操作數據庫。


### 日志規範

* 使用 logging 模塊
* 合理區分日志級別（DEBUG / INFO / WARNING / ERROR）
* 日志中不得包含敏感信息


## 六、安全規範（重點）

### 通用安全原則

* 永遠不信任客戶端輸入
* 所有輸入必須進行校驗
* 敏感操作必須經過身份與權限校驗


### 前端安全

* 禁止使用 dangerouslySetInnerHTML
* 防止 XSS / CSRF 攻擊
* 不在前端存儲敏感信息
* Token 推薦使用 HttpOnly Cookie


### 後端安全

* 使用 Pydantic 進行參數校驗
* 權限校驗必須在 service 層完成
* 所有密鑰從環境變量中讀取

```python
import os
SECRET_KEY = os.getenv("SECRET_KEY")
```

* 敏感字段返回前需脫敏
* 密碼等敏感數據必須加密存儲


## 七、AI 協作使用規範

* 所有自動生成的代碼必須遵守本規則
* 生成結果應：

  * 結構清晰
  * 類型完整
  * 可維護
  * 安全
* 不生成不必要的覆雜實現

## Windows 命令行與 PowerShell 規範（必讀）
1. **拒絕使用 `&&` 或 `||`**：
   * 在預設的 PowerShell 5.1 中不支援此類分隔符。
   * **規範**：一律改用 `;` 作為多命令連接符。
2. **禁止直接在 `run_command` 呼叫 Unix 工具**：
   * **禁止指令**：`grep`, `find`, [sed](cci:1://file:///d:/Project/wvd/src/script.py:1826:4-1901:47), `awk`, `which`, `export`, `ls -la`, `rm -rf`。
   * **替代方案**：
     * `grep` -> 使用專用的 `grep_search` 工具，或 `Select-String`。
     * `find` -> 使用 `find_by_name` 工具，或 `Get-ChildItem -Recurse`。
     * `which` -> 使用 `Get-Command`。
     * `export` -> 使用 `$env:VARIABLE = "value"`。
     * `rm -rf` -> 使用 `Remove-Item -Recurse -Force`。
3. **路徑轉義與引號原則**：
   * PowerShell 對反斜槓 `\` 較為敏感，容易與轉義字元混淆。
   * **規範**：
     * 儘量使用正斜槓 `/`（PowerShell 原生支援且較穩定）。
     * 若必須使用包含空格或 `\` 的路徑，**必須**使用雙引號封裝：`"C:\Path\To\File"`。
4. **環境變數訪問**：
   * 使用 `$env:NAME` 而不是 `$NAME`。    

## 發布與版本控制規範
* **發布前強制同步**：在執行任何版本發布、Tag 或產生 Release 的操作前，**必須**先執行 `git pull` 確保本地代碼為最新狀態，避免分支衝突或 Release 內容過舊。
* **檢查變更日誌**：更新版本前，務必確認 [CHANGES_LOG.md](cci:7://file:///d:/Project/wvd/CHANGES_LOG.md:0:0-0:0)（注意檔案名稱）是否存在並已正確寫入新版本資訊。

## 停止信號機制規範（wvd 專案）

> [!IMPORTANT]
> 所有循環 (`while`/`for`) 開頭 **必須** 調用 `check_stop_signal()`，這是不可省略的強制要求。

### `@stoppable` 裝飾器

**用途**：自動在函數入口檢查停止信號，確保程式能優雅停止

**使用時機**：
- 所有包含 `while` 或 `for` 循環的函數
- 長時間執行的狀態處理函數（如 `StateXxx`）
- 遞歸調用的函數（如狀態機）
- 任何新增的業務邏輯函數

**使用方式**：
```python
@stoppable
def NewFunction():
    # 函數入口自動檢查停止信號
    ...
```

### 循環內檢查（強制）

**所有** `while` 和 `for` 循環開頭 **必須** 調用 `check_stop_signal()`：

```python
while True:
    check_stop_signal()  # 必須加入
    ...

for item in items:
    check_stop_signal()  # 必須加入
    ...
```

### 禁止事項

禁止直接使用 `if setting._FORCESTOPING.is_set(): return`，必須通過統一機制處理

### 代碼修改後自檢清單

每次修改 `script.py` 後，**必須** 確認：
- [ ] 新增的 `while`/`for` 循環是否已加入 `check_stop_signal()`
- [ ] 新增的函數是否需要 `@stoppable` 裝飾器