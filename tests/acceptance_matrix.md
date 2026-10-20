# MVP-001 驗收結果矩陣

執行日期：2026-10-21 Asia/Taipei。命令：`python -m unittest discover -s tests -v`。完整輸出：`tests/results/mvp001-tests.log`。

| 驗收 | 結果 | 測試證據 |
|---|---|---|
| T01 跨組作品隔離 | PASS | G01 查詢 S002 observation 回 403 |
| T02 初答前禁止提示 | PASS | 無 pre_ai 的 hints 回 409 |
| T03 初答/原稿不可覆寫 | PASS | 再送 pre_ai 回 409；更正以 observation 新版及 revised 版本追加；SQLite trigger 阻止原記錄 UPDATE/DELETE |
| T04 裝置冪等上報 | PASS | 同批重送 5 筆，全部回 duplicate_count=5，未新增歷史列；相同 key 不同 payload 回 409 |
| T05 缺測不是零 | PASS | humidity value=null 與 quality_flag=missing 被保留 |
| T06 離線偵測 | PASS | 2020 舊觀測時間回報後，Z02 仍標為 offline |
| T07 UTC 時間 | PASS | `+08:00` 觀測時間正規化成 `+00:00` |
| T08 共用光源群組 | PASS | 匯出 sensor_readings 保留 light_group_id |
| T09 AI 引導安全 | PASS | 最多三個 Mock 問題、版本/來源/不確定性標記；不生成 CER；無效 CER 證據拒絕 |
| T10 同意/去識別匯出 | PASS | S002 未同意作品與 G02/Z02 感測值均排除；自由文字被省略；ZIP 無觀察原文 |
| T11 評量/匯出稽核 | PASS | audit 包含 teacher.rubric_score、research.export、observation、intervention、CER 操作 |
| T12 無外部服務閉環 | PASS | E2E 使用本機 Mock 與合成設備 API；health 顯示 external_ai=false |
| E01 假名/九格 | PASS | S001/G01；九格 API 與 synthetic dataset 標記 |
| E02 觀察與 pre_ai 版本 | PASS | O001、追加 O002；pre_ai 再提交拒絕，revised 新版成功 |
| E03 AI 介入追蹤 | PASS | intervention 保存 pre-AI version、Mock provider、prompt version、安全旗標；revision followup 可回溯；教師覆核成功 |
| E04 感測批次品質 | PASS | 有效/缺測/重複/舊時間設備資料均驗證，保留 source 與 ingest_batch_id |
| E05 可追溯圖表 | PASS | 同一溫度單位兩點分析成功，圖表資料點帶 reading_id；UI SVG 以 data-reading-id 標記每點 |
| E06 CER/教師評量 | PASS | CER 引用 O001、讀值、分析；教師 Rubric 1–4 級存檔並稽核 |
| E07 匿名研究 ZIP | PASS | consent filter 同時限制學生作品與 group-zone sensor readings；JSON/CSV、字典、篩選規則、檔案 SHA-256 重算相符 |
| E08 重新登入恢復/拒絕越權 | PASS | workspace API 可恢復六階段；G02/G01 查詢及 C02 教師授權外存取皆拒絕 |

測試層級目前是一個可重現的 HTTP E2E 串接測試，加上資料庫不可變 trigger、遷移重跑及 ZIP 雜湊驗證。這不是 OWASP 全面安全審查或效能基準。

補充驗證：`python -m py_compile app/server.py tests/test_e2e.py` 通過；抽取 `web/index.html` inline script 後執行 `node --check` 通過；空白 SQLite 資料庫連續執行 `initialize(); initialize()` 回 `initialize_twice=ok`。既有 Sprint 1 SQLite 實際啟動升級後，migration ledger 記錄 `0002_mvp_evidence_closure.sql` 至 `0005_consent_zone_scope.sql`，並確認 device liveness、sensor provenance 與 9 筆 zone/group 授權列存在。實際啟動服務後 health=ok、首頁 HTTP 200、external_ai=false。
