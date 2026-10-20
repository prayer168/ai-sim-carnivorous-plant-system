# AI-SIM × 食蟲植物
智慧探究實驗室開發規格書 V1.1
Codex-ready｜學生探究工作台 × 九格感測資料庫 × AI 提問與 CER 科學論證引擎
文件日期：2026-10-20  ｜  學年度：115（2026/08–2027/07）  ｜  狀態：可執行開發規格，非已驗收成品
需求來源：AI-SIM 核心白皮書 V1.0、AI-SIM × 食蟲植物整合實施計畫書 V1.0。優先保留原計畫的 36 週課程、8 次教師社群、24 位學生／6 組、九格三層監測、含稅硬體上限 NT$65,000；此預算不自動涵蓋雲端模型及軟體維運。
## 1. 執行摘要與範圍
第一期以一個可實際操作的教學研究閉環為成功定義：教師建立食蟲植物任務 → 學生獨立作答並鎖定原稿 → 感測資料/影像形成來源明確的證據 → AI 僅提供引導問題 → 學生修訂 CER → 教師人工評閱 → 研究者依授權取得匿名化資料。
## 2. 使用者、權限及成果
認證：本機開發可以使用種子帳號與假名資料，正式環境須支援安全登入與最小權限。租戶/校別、班級、群組的存取在 API 及查詢層雙重驗證；直接猜測 URL ID 不可越權。
## 3. 核心畫面與使用流程
## 4. AI-SIM 矩陣與課程對應
保留原25格 M01–M25 編碼；V1.1 先完整實作六格：M01 提問、M09 變因、M13 影像觀察證據登錄（初版人工標註）、M19 時間序列資料建模、M24 CER 檢查、M25 學習反思。M13 第一版不宣稱視覺模型已完成。
## 5. 九格設備、資料品質與科學實驗有效性
3層×3格，zone_id=Z01–Z09，對應 level_index=1..3、position_index=1..3。device_id與zone_id不是同一個欄位；裝置更換需保留安裝生效與失效時間。上層/同層燈源可共用：新增 environment_cluster_id、light_group_id 和 treatment_id；分析時不將同一共享環境的數格視為獨立處理複本。
每筆資料保留 server_received_at（UTC）、observed_at（附偏移量轉UTC）、metric、value、unit、calibration_ref、quality_flag、ingest_batch_id、raw_payload_hash。顯示端用 Asia/Taipei。
感測上報至少支援溫度與相對濕度示範資料；光照、pH及其他指標先以可設定 capability 方式管理。不得假設採購型號或測量精度。
建立品質旗標 valid / missing / out_of_range / suspect / uncalibrated / duplicate / clock_skew；不使用0代替缺值。
設備離線由 last_seen_at 與預期頻率判定。離線緩存重新上報採 idempotency_key 去重；資料寫入只追加，不允許更新歷史測值；更正以 correction records 指向原紀錄。
每張影像附 zone_id、plant_id、captured_at、檔案SHA-256、拍攝裝置類別及使用授權；兒童照片不得上傳公開儲存桶。
教師/學生圖表明確標示：影響光照的實驗需要獨立重複、隨機化、植株狀態與光照實測；監測曲線本身不能證明因果。
## 6. 系統架構與部署選擇
建議技術基準（可按既有Repo調整）：前端 Next.js + TypeScript；後端 FastAPI + Python；PostgreSQL；S3相容私有物件儲存；Docker Compose 本機開發；AI Gateway 以 adapter 隔離外部模型。若既有repo已有成熟技術，Codex 必須先盤點，經評估後選最少重工的同等方案。
架構：Browser(Student/Teacher) → API/Auth RBAC → PostgreSQL + Private Object Storage；ESP32/Simulator → ingestion API（專用 token） → immutable sensor_readings；AI Gateway → safety guard → provider/mock → teacher review/audit；Research Export → consent filter → de-identification → report artifact。
系統應預設完全離線的 Mock AI/Simulator 路徑，無外部金鑰也能啟動示範與執行測試。硬體採購、正式部署與AI供應商選擇不在本開發階段擅自決定。
## 7. 資料模型與限制
## 8. API 契約與處理規則
錯誤契約：統一 {error:{code,message,request_id}}，至少401未登入、403越權、409版本衝突/重覆、422資料驗證、429限流、503模型不可用。寫入操作需 trace_id；裝置API不可用學生命名空間。
## 9. AI Gateway 提示規範（供 Codex 實作）
AI 系統層：你是國小自然科學探究的蘇格拉底式引導者。對已提出觀察的學生提供最多3個短問題，不直接輸出可繳交的完整研究設計、CER答案或科學結論。不臆造數據、文獻、照片觀察或引用；若原始證據不足，明確標示待驗證。標記 evidence_ids、prompt_version、safety_flags。所有評分是供教師參考，不是正式成績。
若學生尚未提交 pre_ai 回應，API 必須拒絕 hints；若模型逾時或風險觸發，返回可解釋的安全模板或由教師覆核，不得靜默產生假資料。AI不得寫入 sensor_readings 或直接修改 student_responses。
## 10. 90天工程里程碑與交付
## 11. 測試策略與 Definition of Done
單元：變因表、Rubric等級、時間帶轉換、品質旗標、提示政策；測試基準是規格，不是模型主觀表現。
整合：重覆測值上報冪等、時間戳偏移、裝置無權讀學生資料、授權班級隔離、AI無法修改原稿、匯出同意過濾。
端到端：教師指派M01→學生初答→Mock AI引導→M09實驗計畫→模擬器九格入庫→M19圖表→M24 CER→教師評閱→M25反思→匿名匯出。
性能目標（開發基線）：本機100,000筆測值分頁查詢P95<2秒，標準條件需寫入benchmarks；負載、硬體及限制皆須揭露。
安全：至少 OWASP 常見風險（權限、輸入、金鑰與日誌）檢查；備份還原演練、裝置密鑰輪替；依賴掃描。
完成標準：README安裝成功、migration可重跑、mock無外部服務、CI全綠、示範錄影/截圖、測試記錄、未完成項目與風險清單。
## 12. 課堂試行與研究資料治理
第1年度24名/6組屬先導試行，重點是可行性、學習軌跡、工具穩定與評量一致性，不聲稱準實驗因果效果。紀錄CER四級規準（主張/證據/推理）、原稿/修訂/教師評分及可追溯的時間與任務版本。為保護學生，教學同意與研究同意分開，未同意者也能正常參與課程但不進研究匯出。研究者存取須經角色與目的授權；資料保留與刪除期限依校方核定，尚未核定前用合成資料。
第一輪研究指標：任務完成比例、初答保存完整率、來源可追溯比例、有效感測資料占比、教師評閱時間、CER前後變化、雙評分者一致性。未設定前不宣稱已達成任何成果。
## 13. 交付結構、Code Review與操作順序
交付建議 repo：apps/web, services/api, packages/contracts, db/migrations, simulator, curricula, prompts, tests, research, docs/adr, docs/runbooks, infra。優先提供可跑的單一repo，不在第一輪拆分大量微服務。
Codex執行規則：先讀README與現有系統，先給檔案樹/風險/實作順序；之後逐Sprint提交實際程式碼與測試，不應只輸出計畫。不得擅自部署、採購、使用真學生資料，亦不得把裝置或模型密鑰寫入repo。
## 14. 重要決策與待確認條件
實際九格ESP32模組的廠牌/感測器接線/上報頻率尚需廠商或現場實測；API先與硬體解耦。
原有36週、8次社群與2027年6月成果發表的正式日期，仍以核定文件為準。
65,000元為九格硬體含稅上限，不代表軟體開發/AI推論已有經費來源。
正式研究使用的學生資料、人體研究倫理/校內審查與研究同意須先完備。
線上發表僅使用獲授權且去識別化的示範材料。
## 附錄：6 組學生示範情境
例：G03 學生選 Z02 毛氈苔，先記錄「黏液減少可能是因為光照」；AI提示「是否有濕度或水分差異？」；學生新增兩種可檢驗假說，選取光照/濕度時間序列並排除缺測；在CER中引用具來源ID的數據；教師依規準評分。所有資料在開發版均為合成資料。