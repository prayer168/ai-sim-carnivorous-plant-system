# 本機操作、部署與回復

## 本機

需要 Python 3.11+；不需 pip 安裝。由 repo 目錄執行 `python -m app.server`，預設只綁定 127.0.0.1:8000。`AI_SIM_HOST`、`AI_SIM_PORT`、`AI_SIM_DB` 可由環境變數設定。`.env.example` 是參考，標準庫伺服器不會自行解析 `.env`。

## Compose

安裝 Docker Desktop 後複製 `.env.example` 為 `.env`，執行 `docker compose up --build`。SQLite 放在具名 volume `ai_sim_data`。容器構建、重啟和 volume 行為尚未於此環境實測。

## 備份/還原（示範資料）

停止本機服務，複製 `data/ai_sim.sqlite3` 作為本地快照；還原時停服務後覆蓋同一路徑。容器資料可用 `docker compose down` 後保留 named volume；若執行 `docker compose down -v` 會刪除 volume。正式部署需另行設計加密、保留期限、驗證還原及稽核，不能直接採用此人工流程。

## API 說明

JSON API 根路徑 `/api/v1`；錯誤格式 `{error:{code,message,request_id}}`。角色使用 `Authorization: Bearer <demo-token>`。必要的成功操作回應包含 trace_id 或寫入 audit。用 `GET /api/v1/openapi.json` 取得簡化路徑目錄；完整 request/response schema 下一 Sprint 補齊。

MVP-001 routes: `GET /workspace`, `GET /zones`, `GET /readings`, `GET /devices/status`, `GET /observations`, `GET /analyses/{id}`, `GET /cers/{id}`, `GET /audit`; `POST /observations`, `/tasks`, `/responses`, `/ai/hints`, `/interventions/{id}/review`, `/ingest/readings`, `/analyses`, `/cers`, `/rubric-scores`, `/research/exports`; ZIP download via `GET /research/exports/{id}.zip`.

Research ZIP 中自由文字一律標成 redacted，避免把兒童可識別內容直接輸出。研究匯出必須 `scope=research`；教學同意不可作研究用途。`date_range` 的 `from`/`to` 必須是含時區的 ISO-8601。

研究匯出會依 `student_profiles` 和 `zone_group_access` 將感測資料限制在有研究同意的小組區域；目前合成設定為 G01→Z01、G02→Z02，其餘格位標成 SHARED，沒有同意群組授權時不輸出。
