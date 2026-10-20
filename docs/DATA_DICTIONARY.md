# 資料字典（Sprint 1）

| 實體 | 欄位 | 定義 |
|---|---|---|
| zone | id | Z01–Z09；列/層 `level_index`、欄 `position_index` |
| zone | environment_cluster_id, light_group_id | 共享環境、層級光源群組；不可把同組格位視為獨立處理 |
| device | id, zone_id, installed_at, removed_at | 假名設備及有效安裝區域時間；本輪僅種子安裝 |
| reading | observed_at, received_at | 感測時間與伺服器接收時間，RFC3339 含偏移後存 UTC |
| reading | metric, value, unit | temperature/humidity/light/ph；缺值 `value=null` |
| reading | quality_flag | valid/missing/out_of_range/suspect/uncalibrated/duplicate/clock_skew |
| reading | calibration_ref, idempotency_key, payload_hash, source, ingest_batch_id | 校正參照、冪等識別、原始 payload SHA-256、來源類別、可重現匯入批次 |
| task | matrix_code, prompt_version | M01–M25 任務矩陣代碼與任務版本 |
| response | phase, version_no, content, submitted_at | pre_ai/revised/cer/reflection 各階段追加版本；初答不可覆寫 |
| consent | student_id, scope, permission, consent_version | 合成假名的用途同意範圍及版本 |
| score | rubric | 教師人工 CER 主張/證據/推理 1–4 級，不是自動分數 |
| audit | actor_role, action, target_id, trace_id | 匯出、評閱、任務、作品、上報事件追蹤 |
| observation | id, project_id, actor pseudonym, zone_id, original_version_id, version_no | 觀察追加版本；自由文字只留教學環境，不進研究匯出 |
| intervention | pre-AI version, prompt/model version, request time, questions, uncertainty, safety flags | Mock 引導事件與教師覆核狀態 |
| analysis | reading_ids, chart_config, explanation | 可重現的簡化圖表設定及明確來源 ID |
| CER / evidence | claim, reasoning, version, evidence_type, evidence_id | 每筆引用在提交時驗證到 observation、reading 或 analysis；不允許不存在來源 |
| research_exports | export id, file_path, manifest, created_at | ZIP 輸出位置及版本/篩選/雜湊 manifest |
| student_profiles / zone_group_access | student pseudonym-to-group; zone-to-authorized group | 研究匯出依同意假名所屬小組限制感測區域 |

SQLite schema 在 `app/server.py` 初始化。這不是正式資料遷移或校方核定的資料保留模型。
