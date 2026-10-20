# ADR 0001：先以標準庫單程序交付本機垂直切片

- 狀態：Accepted for Sprint 1
- 日期：2026-10-21

## 背景

repo 初始沒有應用程式或既有技術棧；規格建議 Next.js/FastAPI/PostgreSQL，但本機沒有 Docker，且第一輪目標是能以假資料跑閉環。

## 決策

Python 3.11 標準庫 HTTP server + SQLite + 靜態 HTML/JS，提供 Dockerfile/Compose 後續封裝。所有身份、作品和感測資料只用合成代碼與資料。固定 demo token 僅讓本機頁面切換角色。

## 後果

零套件可啟動且具備實際 API/資料閉環；同時不適合多人併發、公開網路、正式登入或校方正式資料。後續可替換 FastAPI/Postgres，但先以使用案例、合約和測試穩定資料邊界。
