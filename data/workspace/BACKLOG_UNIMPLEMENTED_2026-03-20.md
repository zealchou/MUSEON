# 尚未落地的迭代功能備份
**備份日期：** 2026-03-20
**資料來源：** Telegram 3/18-3/20 對話紀錄（私訊 + 群組）

---

## A. 系統架構迭代（私訊深度討論）

### #1 MemGPT × Knowledge Lattice 對接
- **討論內容：** 分層記憶（in-context/external/archival）與 DAG Crystal 直接對接，用共振指數決定哪些 Crystal 預載入 context window
- **狀態：** 概念驗證階段，當天反覆探討 3 次
- **關鍵技術：** MemGPT 分層記憶架構、Knowledge Lattice DAG、Crystal 共振指數（RI）、context window 預載
- **來源：** telegram_6969045906.json（Museon 心脈推送 07:10, 07:30, 09:10, 15:10, 17:10, 21:10）

### #2 混合檢索實作（Hybrid Retrieval）
- **討論內容：** Qdrant 稀疏向量 + vector_bridge.py 改造
- **狀態：** 方向明確，未動手
- **關鍵技術：** Qdrant 稀疏向量（sparse vector）、BM25 + 語義向量融合、vector_bridge.py 改造
- **來源：** telegram_6969045906.json（探索軌跡中多次提及）

### #3 GraphRAG / 知識圖譜融合
- **討論內容：** 微軟 GraphRAG「社群摘要」機制 → 解決 MUSEON 跨案例連結缺失問題
- **狀態：** 研究階段
- **關鍵技術：** GraphRAG 社群摘要、圖遍歷、跨文件全域問答
- **來源：** telegram_6969045906.json（推送 02:13 深度探索報告）

### #4 四層衰減機制驗證
- **討論內容：** 已實裝的四層衰減是否真的在跑？
  - 結晶衰減：46 個結晶中有沒有 RI < 0.05 被歸檔的紀錄？
  - 記憶降級：L1→L0 是否有實際觸發？
  - 健康分數衰減：半衰期 2h 是否生效？
  - 推薦引擎衰減：近因性 7d + λ=0.95 是否實際運作？
- **狀態：** 3 項待驗證，零結果
- **關鍵檔案：** knowledge_lattice.py, memory_manager.py, dendritic_scorer.py, recommender.py
- **來源：** dispatch_20260320_154948_telegram.json（失敗的 dispatch）

### #5 Morphenix L3 提案
- **討論內容：** 進化建議候審中，尚未審核
- **狀態：** 待審核
- **來源：** telegram_6969045906.json（推送 07:30 提到）

---

## B. MCP 工具串接

### #6 圖像處理 MCP（證件照降維打擊）
- **需串接：** rembg + Pillow + OpenCV
- **用途：** 給攝影師客戶自動生成證件照初稿
- **預估時間：** 半天到一天
- **來源：** telegram_group_5107045509.json

### #7 Email MCP
- **用途：** 自動寄信/回信（會員催繳、廠商確認等）
- **來源：** telegram_group_5107045509.json（Feng 需求）

### #8 LINE Bot 串接
- **用途：** 會員自動回覆
- **來源：** telegram_group_5107045509.json（Feng 需求）

### #9 Bot 定時提醒排程
- **用途：** Scheduled Reminder 機制（Zeal 親自要求）
- **來源：** telegram_group_5107045509.json

---

## C. 業務交付物

### #10 證件照裁切指引推 GitHub
- **本地檔案：** ~/MUSEON/data/workspace/certification_photo_guide.html
- **目標：** push 到 museon-reports repo
- **卡點：** ~/museon-reports 不存在

### #11 Threads 爬取管線（輿情監控+競品追蹤）
- **DSE 分析：** 已完成（四條路徑比較）
- **待回答：** 目標、競品數量、整合需求
- **來源：** telegram_6969045906.json

### #12 韋辰正式報價單
- **現有：** 通用骨架 + 舊報價單（麻豆鄭公館）檢查結果
- **卡點：** 等韋辰提供新設計圖

---

## D. 系統維運

### #13 uploads/ 60 個上傳檔案清理
- **來源：** telegram_6969045906.json（推送 10:10）

### #14 Skill 註冊表 vs 拓撲文件差異檢查
- **來源：** telegram_6969045906.json（推送 12:11）

### #15 2 個 failed dispatch 修復
- **檔案：** dispatch_20260320_152152_telegram.json, dispatch_20260320_154948_telegram.json
- **原因：** 迭代重啟中斷（Recovered after restart）
