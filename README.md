# AI-SIM 食蟲植物智慧探究實驗室

本儲存庫由 V1.1 開發包落地為可本機操作的匿名教學示範。第一輪用 Python 3.11 標準庫、SQLite 和靜態網頁，不需要套件安裝、外部 AI 金鑰、ESP32 或雲端服務。

## 快速啟動

Windows PowerShell：

```powershell
cd ai-sim-mvp
python -m app.server
```

瀏覽 http://127.0.0.1:8000 。停止按 Ctrl+C。資料存在 `data/ai_sim.sqlite3`；重置示範資料可停止服務後刪除此檔，再啟動服務。

Docker Compose（需先安裝 Docker Desktop）：`docker compose up --build`，然後開啟同一網址。`.env.example` 列出可調整設定。

## 角色種子帳號

帳號以本機示範 Bearer token 代表，請在 UI 角色選單切換。G01/G02 的學生各有不同小組；教師僅看示範班，研究者匯出 consent=true 的假名資料，裝置服務帳號只可上報感測值。這不是正式登入或可部署的認證方式。

## MVP-001 六階段證據閉環

1. 學生提交觀察並取得原始 observation_id，初答提交後鎖定。
2. Mock AI 只回最多三個引導問題，留下介入版本/不確定性/安全旗標。
3. 九格設備模擬器寫入追加式感測資料；遲到、缺測、冪等及共用光源均保留來源資訊。
4. 同指標分析建立 SVG 時間序列；每個圖表點帶 reading_id。
5. CER 提交時逐筆確認 observation/readings/analysis ID 可回查。
6. 教師人工 Rubric 評閱，研究者取得只含同意範圍的 JSON/CSV/字典/雜湊 manifest ZIP。

所有示範讀值與學生作品均為合成資料。趨勢圖與簡單序列摘要不構成因果證據。

## API 與文件

- `GET /api/v1/health`, `GET /api/v1/zones`, `GET /api/v1/readings`
- `POST /api/v1/tasks`, `POST /api/v1/responses`, `POST /api/v1/ai/hints`
- `POST /api/v1/cer/feedback`, `POST /api/v1/rubric-scores`, `POST /api/v1/research/exports`
- `POST /api/v1/ingest/readings`（device role 專用）
- `GET /api/v1/audit`（教師/研究者）
- `GET /api/v1/openapi.json`

詳細操作、T01–T12/E01–E08 驗收矩陣、資料字典、備份還原與部署限制見 `docs/` 及 `tests/acceptance_matrix.md`。

## 測試

```powershell
python -m unittest discover -s tests -v
```

## Sprint 記錄

見 `docs/SPRINT_LOG.md`、`docs/adr/` 與 `docs/RISKS.md`。Docker Compose 定義已提供，但目前建置環境沒有 Docker CLI，尚未能實際驗證容器啟動。


