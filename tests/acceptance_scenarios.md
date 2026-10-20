# 驗收情境（必要）

- T01 學生G01不可讀G02受限作品。
- T02 不存在pre_ai版本的作業，AI提示API拒絕。
- T03 學生pre_ai提交後不能被更新，只能增加新版本。
- T04 相同device_id和idempotency_key僅入庫一次。
- T05 sensor value=null配missing，不顯示為0。
- T06 斷線超過設定閾值顯示offline。
- T07 時間序列以UTC存、Asia/Taipei顯示；原始值不改寫。
- T08 同light_group_id在研究匯出保留群組資訊，避免偽重複。
- T09 AI不輸出虛構資料或可直接提交之CER全文；教師可覆核。
- T10 研究匯出排除無同意的學生，且不含真名、臉與聲音。
- T11 研究匯出和教師評分皆留audit log。
- T12 完全無外部模型API/實體裝置，Mock情境仍可完成E2E閉環。
