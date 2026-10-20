# Sprint 1 交付紀錄

日期：2026-10-21（Asia/Taipei）

## Repo 盤點

- 起始 Git：`master`，沒有任何 commit；只有空白 Git metadata。開發包是工作目錄中的未追蹤附件，未見既有產品程式、部署配置或 CI。
- 技術棧：起始 repo 無技術棧。採 Python 3.11 標準庫 `http.server`、SQLite、HTML/JS，保留 Docker Compose 包裝。
- 執行環境：Python 3.11.15、Node 24.15.0 可用；Docker CLI 未安裝。依賴零 pip 套件。
- 可重用：開發包規格、API 草案、資料表草案及 T01–T12 驗收情境；不把草案 SQL 直接當正式遷移部署。

## Sprint 計畫

1. **S1 本機匿名垂直閉環（本輪）**：九格、角色示範 token、隔離檢查、append-only 讀值、冪等上報、任務/初答/Mock hints/CER/人工評閱/同意匯出、網頁與 E2E。
2. **S2 治理與資料完整性**：正式 migrations、角色/班級/群組雙層授權、修正紀錄、影像標註授權、offline 定時判斷、錯誤限流/安全檢查、完整 OpenAPI。
3. **S3 教學流程及研究驗證**：M01–M25 導航與 M01/M09/M13/M19/M24/M25 明確學習頁、時間序列篩選/缺測視覺化、研究匯出報表、裝置離線復原情境與更完整 E2E。
4. **S4 部署候選**：Docker 驗證、CI、依賴/備份還原/負載基線、正式登入與私有物件儲存評估；需要校方核定的治理設定仍用 stub。

## 本 Sprint 交付

- 新增可啟動的單頁工作台與 API、SQLite 示範資料、Compose/Dockerfile、匿名九格上報路徑、角色切換、初答鎖定與版本、Mock 引導、CER 結構提醒、教師四級評閱、同意範圍 JSON 匯出及稽核紀錄。
- M13 僅有資料表 stub，尚未提供影像上傳/標註 UI。M19 僅能讀取時間排序感測紀錄，尚無圖表。M09/M25 可透過 matrix task 和作品階段記錄，但尚未有完整專屬教學互動。

### 變更檔案

- `README.md`, `.env.example`, `.gitignore`, `Dockerfile`, `docker-compose.yml`
- `app/__init__.py`, `app/server.py`, `web/index.html`
- `tests/test_e2e.py`
- `docs/SPRINT_LOG.md`, `docs/TEACHER_GUIDE.md`, `docs/DATA_DICTIONARY.md`, `docs/OPERATIONS.md`, `docs/RISKS.md`, `docs/adr/0001-local-runtime.md`

### 啟動方式

```powershell
cd AI_SIM_V1_1_Codex_Package
python -m app.server
```

瀏覽 `http://127.0.0.1:8000`。Docker 使用 `docker compose up --build`（需 Docker Desktop；本機本輪無法實測）。

### 測試指令及結果

- `python -m unittest discover -s tests -v`：1 個 E2E 測試通過，驗證未登入拒絕、提示需要初答、初答不可覆寫、跨學生資料拒絕、學生不可建任務、設備不可讀作品、上報冪等、null/missing、教師評閱與稽核、未同意學生排除、保留共用燈源欄位。
- 實際啟動 `python -m app.server`：`GET /api/v1/health` 回 `ok/synthetic-local`；`GET /` HTTP 200；區域 API 回傳 9 格。
- 透過設備 token 對 9 格各寫溫度、濕度，共 18 筆；讀值 API 查到 18 筆、涵蓋 9 區。
- Docker/Compose 尚未測試，因環境沒有 Docker CLI。

### 已知風險和下一輪

- 本輪是單程序示範，token 是固定公開的假名 demo token，沒有安全登入、租戶隔離、CSRF 保護或正式 TLS；只可本機合成資料。
- SQLite 檔案沒有 migrations、備份排程或正式權限分層。APP 的 `data/` 僅保存假資料。
- 完成 S2 資料/安全治理與 S3 教學頁及可視化，再進行容器和部署驗證。

## MVP-001 驗收增補（第二輪）

依 AISIM-MVP-001 acceptance contract 將最高優先級改為六階段證據閉環。

### 新增/修改檔案

- `app/server.py`, `web/index.html`, `Dockerfile`
- `db/migrations/0002_mvp_evidence_closure.sql`, `db/migrations/0003_device_liveness.sql`
- `db/migrations/0004_sensor_provenance.sql`
- `db/migrations/0005_consent_zone_scope.sql`
- `tests/test_e2e.py`, `tests/acceptance_matrix.md`, `tests/results/mvp001-tests.log`
- `README.md`, `docs/TEACHER_GUIDE.md`, `docs/DATA_DICTIONARY.md`, `docs/RISKS.md`, `docs/SPRINT_LOG.md`

### 六階段交付

1. observation 追加版控、假名/區域/原始版本 ID。
2. AI intervention 保存 pre-AI response ID、Mock/provider、prompt 版本、追問、不確定性及安全旗標；教師可用 API 覆核。
3. readings 保持 append-only，冪等去重、UTC、null 缺測；由最新觀測時間判斷離線。
4. analysis 需要至少兩筆同指標/單位且有效的 reading；API 及 SVG 點均帶 reading_id。
5. CER 每個證據逐筆查資料庫來源並檢查學生權限；教師人工 rubric 寫入 audit。
6. research ZIP 只包含有同意的假名；省略自由文字，含 JSON/CSV、資料字典、篩選規則、檔案 SHA-256 和 audit。

### 實際測試

- `python -m unittest discover -s tests -v`：E2E `OK`，完整 T01–T12、E01–E08 對照見 `tests/acceptance_matrix.md`，原始輸出存 `tests/results/mvp001-tests.log`。
- 獨立 SQLite 測試資料執行 `initialize(); initialize()`：`initialize_twice=ok`，migration 可重複啟動。
- Docker CLI 仍未安裝，容器建置/Compose 啟動維持 BLOCKED；未部署任何服務。

### 下一輪

正式登入與校別租戶、M13 私有影像上傳/授權、教師 UI 覆核、裝置能力與校正修正紀錄、正式 DB/備份、完整 API schema、安全和負載驗證。
