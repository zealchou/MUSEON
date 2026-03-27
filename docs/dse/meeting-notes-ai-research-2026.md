現在我已收集到足夠的資料，來撰寫完整的研究報告。

---

# AI 會議記錄工具技術方法論研究報告

## 一、Plaud Note / Plaud NotePin

### 關鍵發現

- **產品架構**：硬體裝置（NotePin S 僅 0.61oz、20 小時續航、64GB 儲存）+ Plaud App + AWS 雲端。採用振動傳導感測器（VCS）和 MEMS 麥克風陣列進行高保真收音，最遠可達 16.4 英尺（Note Pro）
- **ASR 引擎**：非自研，而是整合多家頂級 LLM——目前支援 **GPT-5.1、Claude Sonnet 4、Gemini 3 Pro**，用於轉錄和摘要生成。語音轉文字支援 **112 種語言**，含說話者標記和自訂詞彙
- **逐字稿後處理**：採用 **RAG（檢索增強生成）架構**，將錄音轉化為個人知識圖譜、心智圖和待辦事項。支援「多維度摘要」——從同一段對話生成不同角色視角的輸出（業務的行動項目、團隊的回饋、主管的策略概覽）
- **模板系統**：提供 **10,000+ 專業模板**，涵蓋會議/訪談/演講/通話等情境，並有模板社群讓使用者分享自建模板。使用者可按職業角色或產業選擇模板
- **多語言/中英夾雜**：112 語言支援，但使用者回報在口音重或語速快時準確度會下降至 90-95%，且偶有語言混淆問題（同一份逐字稿內出現錯誤語言）
- **使用者評價**：Amazon 4.3/5（1,060 則），TrustPilot 4.6/5（899 則）。優點：硬體設計精良、轉錄準確度高。缺點：App 連線不穩、訂閱費用高、NotePin 觸發錄音困難、AI 不會從使用者偏好中學習
- **基礎設施**：與 AWS 戰略合作，跨區域同步部署，將延遲降低 80%。全球已部署超過 150 萬台裝置

### 對 Meeting Notes Skill 的啟示

1. 多維度摘要是殺手級功能——同一段會議可以產出不同角色需要的版本
2. 模板社群模式值得參考——讓使用者定義自己的摘要結構
3. RAG + 知識圖譜的架構適合 MUSEON 的長期記憶整合

### 來源

- [Plaud.ai 官網](https://www.plaud.ai/)
- [Plaud Intelligence](https://www.plaud.ai/pages/plaud-intelligence)
- [TechCrunch: Plaud CES 2026](https://techcrunch.com/2026/01/04/plaud-launches-a-new-ai-pin-and-a-desktop-meeting-notetaker/)
- [Plaud Templates Guide](https://www.plaud.ai/blogs/news/plaud-templates)
- [Plaud NotePin Review - tl;dv](https://tldv.io/blog/plaud-notepin-review/)
- [Plaud Review - Bluedot](https://www.bluedothq.com/blog/plaud-review)

---

## 二、Otter.ai

### 關鍵發現

- **即時轉錄**：近乎即時（僅幾秒延遲），準確度 85-95%（理想條件下 90-96%）。核心技術基於自研 ASR 引擎
- **說話者辨識**：使用語音特徵分析（音高、共振峰頻率、說話風格）進行 diarization，準確度 89-95%。系統會與會議參加者名單交叉比對，且**隨時間學習**常見與會者的聲音，逐步提升辨識準確度。弱點：多人同時說話（crosstalk）或音色相近者容易混淆
- **AI 摘要結構**：OtterPilot 自動生成：主題摘要（bullet points）、關鍵決議、行動項目、投影片截圖。提供 **Meeting Types** 功能，可按會議類型（銷售電話、站會、團隊會議）自訂摘要模板，指定要提取的資訊
- **Action Items 自動提取**：AI 從對話中提取並**自動指派**給相關參與者，每個待辦事項附帶回到原始對話片段的連結。提供跨會議的**統一行動項目匯總**和每週未完成提醒
- **整合方式**：OtterPilot 作為參與者加入會議（顯示名稱為「[名字] Notetaker (Otter.ai)」），支援自動行事曆同步和手動貼入會議連結。支援 Zoom、Teams、Google Meet
- **弱點**：**中文支援極弱**——台灣實測顯示「對中文處理能力較弱，甚至會出現完全無法辨識的情況」

### 對 Meeting Notes Skill 的啟示

1. 跨會議的行動項目追蹤和聚合是高價值功能
2. 說話者辨識「隨時間學習」的機制值得在 MUSEON 長期記憶中實作
3. Meeting Types 的概念——根據會議類型客製化摘要結構——是 Skill 模板設計的核心參考

### 來源

- [Otter.ai](https://otter.ai/)
- [Otter.ai Review - Bluedot](https://www.bluedothq.com/blog/otter-ai-review)
- [Otter Speaker Diarization Guide](https://summarizemeeting.com/en/faq/does-otter-ai-identify-speakers)
- [Otter Action Items](https://otter.ai/blog/otter-ai-new-feature-my-action-items)
- [Otter Meeting Types](https://otter.ai/blog/otter-meeting-types-get-smarter-tailored-summaries-for-every-meeting)

---

## 三、Fireflies.ai

### 關鍵發現

- **會議 Bot 架構**：自動加入 Zoom/Teams/Meet 作為參與者，架構流程為 **Ingest → Processing → Storage → Retrieval → System Sync**。即時轉錄 + 說話者標記，準確度 95%+，支援 100+ 語言
- **逐字稿後處理**：使用進階 NLP 生成結構化摘要、提取行動項目、辨識關鍵主題、浮現洞察
- **AI 摘要模板系統**：提供預建 AI App 模板庫，一鍵自動化摘要/洞察/跟進/CRM 更新。2025 年推出 **AskFred**（GPT 驅動聊天機器人），支援自然語言查詢會議內容
- **知識庫功能**：所有語音對話自動建構成**自更新知識庫**，按部門組織，可快速搜尋。**Topic Tracker** 追蹤自訂關鍵字（如「定價」「競品」「Bug」），自動標記所有會議中的出現次數
- **CRM 整合**：自動將通話記錄、筆記、逐字稿寫入 Salesforce/HubSpot 對應的聯絡人下，支援 40+ 整合。根據會議中提到的待辦事項自動在 Asana/Notion 等平台建立任務
- **2025 里程碑**：估值達 10 億美元（獨角獸），推出 **Talk to Fireflies** 語音 AI 助手（整合 Perplexity，在會議中即時搜尋網路）

### 對 Meeting Notes Skill 的啟示

1. Topic Tracker 的概念——跨會議追蹤特定主題——非常適合 MUSEON 的記憶系統
2. 「自更新知識庫」正是 MUSEON memory_v3 已具備的能力，可作為差異化賣點
3. CRM 式的自動寫回機制值得參考（會議→記憶→行動）

### 來源

- [Fireflies.ai](https://fireflies.ai)
- [Fireflies Review - ItsConvo](https://www.itsconvo.com/blog/fireflies-ai-review)
- [Fireflies Deep Dive - Startupik](https://startupik.com/fireflies-deep-dive-ai-transcription-and-meeting-intelligence/)
- [Fireflies Topic Tracker](https://fireflies.ai/blog/fireflies-topic-tracker/)
- [Fireflies CRM Integrations](https://fireflies.ai/integrations/crm)

---

## 四、Notion AI + 會議記錄

### 關鍵發現

- **三大組件**：AI 驅動轉錄與摘要 + 結構化模板與資料庫 + 自動化工作流整合
- **會議結束後自動生成**：完整逐字稿、結構化摘要、行動項目清單（含討論主題、決議、下一步）
- **模板系統**：預建模板涵蓋日常站會到季度回顧，可按會議類型（銷售電話、站會、團隊會議）自動調整摘要結構
- **2026 年 3 月最新**：推出 **Custom Instructions** 功能，讓使用者精確定義 AI 如何生成會議摘要格式
- **定價**：Business Plan $20/user/month 起

### 對 Meeting Notes Skill 的啟示

1. Custom Instructions 的設計模式——使用者可定義摘要規則——非常適合 MUSEON 的 Skill 參數化設計
2. 模板 + 資料庫 + 自動化三位一體的架構值得參考

### 來源

- [Notion AI Meeting Notes](https://www.notion.com/product/ai-meeting-notes)
- [Notion Custom Instructions Release](https://www.notion.com/releases/2026-03-18)
- [Notion Meeting Notes Guide - Speakwise](https://speakwiseapp.com/blog/notion-meeting-notes-ultimate-guide)

---

## 五、Granola（新興會議 AI）

### 關鍵發現

- **隱私設計**：不用 Bot 加入會議，而是直接**擷取裝置的系統音訊**——系統輸出（灰色泡泡，代表他人說話）+ 麥克風輸入（綠色泡泡，代表你）。音訊在轉錄後即刪除，SOC 2 Type 2 合規
- **筆記增強技術**：核心差異化——你在會議中打的粗略筆記 + AI 轉錄的逐字稿，一鍵合併成精煉的可分享摘要。**你的筆記引導 AI 增強方向**
- **Recipes 功能**（2025 年底推出）：類似「存好的 AI prompt」，由領域專家撰寫，透過特定角度處理會議筆記（如銷售視角、工程回顧視角等）
- **爆發成長**：2026 年估值從 2.5 億跳到 **15 億美元**，正從個人生產力工具擴展為企業級 AI 平台
- **弱點**：目前無 Android App（開發中）、不支援實體會議（需要 workaround）

### 對 Meeting Notes Skill 的啟示

1. **「使用者筆記 + AI 轉錄 = 增強筆記」的混合模式**是突破性設計——MUSEON 可以讓使用者先標記重點，再由 AI 填充上下文
2. Recipes 的概念（特定視角的 prompt 模板）與 Plaud 的多維度摘要異曲同工
3. 無 Bot 的隱私設計在台灣企業場景中會是重要賣點

### 來源

- [Granola.ai](https://www.granola.ai/)
- [Granola TechCrunch $125M Raise](https://techcrunch.com/2026/03/25/granola-raises-125m-hits-1-5b-valuation-as-it-expands-from-meeting-notetaker-to-enterprise-ai-app/)
- [Granola Transcription Docs](https://help.granola.ai/article/transcription)
- [Granola Review - Zack Proser](https://zackproser.com/blog/granola-ai-review)
- [Granola Review - tl;dv](https://tldv.io/blog/granola-review/)

---

## 六、核心技術拆解

### 6.1 語音轉文字（ASR）引擎比較

| 引擎 | WER (Word Error Rate) | 即時串流 | 中文支援 | 延遲 | 定價 |
|------|----------------------|---------|---------|------|------|
| **Deepgram Nova-3** | 5.26-6.84%（中位數） | 支援，sub-300ms | 45+ 語言含中文 | 最低 | $0.0077/min streaming |
| **OpenAI Whisper Large-v3** | ~10.6% | 不原生支援 | 100+ 語言含中文 | 較高（batch） | 開源免費 / API $0.006/min |
| **GPT-4o-transcribe** | 最低（整體第一） | 支援 | 多語言 | 中 | 較高 |
| **Google Cloud Speech** | 排名末段 | 支援 | Chirp 3 改善中 | 中 | $0.006-0.009/min |
| **Azure Speech** | 13-23% | 支援 | 多語言 | 中 | $0.01/min |

**關鍵發現**：
- Deepgram Nova-3 在生產環境中表現最穩，比 Whisper 低 36% WER
- Whisper 在噪音環境下最穩健，但不原生支援即時轉錄
- 中文因無空格、同音字多，使用 **CER（Character Error Rate）** 而非 WER 評估
- Whisper Large-v3 Turbo 在某些語言（泰語、粵語）有較大退化，中文表現需要微調才能最佳化
- 台灣有專門微調 Whisper 用於中文/台語的開源專案（ChineseTaiwaneseWhisper）

### 6.2 說話者辨識（Speaker Diarization）

**pyannote.audio**（最主流的開源方案）：
- 基於 PyTorch 的端到端神經網路管線，可組合與聯合優化
- 核心三階段：**VAD（語音活動偵測）→ 語音嵌入（高維向量捕捉音高、共振峰、說話風格）→ 聚類/分段**
- 2025 年推出 **pyannote.audio 4.0 + community-1** 模型
- 商業版 precision-2 管線比社群版快 2.2-2.6 倍

**其他方案**：
- Otter.ai 自研方案：89-95% 準確度，會與參加者名單交叉比對
- Deepgram：內建 Speaker Diarization，與 ASR 整合
- Google：提供雲端 Speaker Diarization API

### 6.3 去贅字演算法（Disfluency Removal）

**問題分類**：
- **填充詞（Filled Pauses）**：嗯、呃、um、uh
- **重複（Repetitions）**：我我我覺得 → 我覺得
- **修正（Revisions/Self-corrections）**：往左邊...不對往右邊走
- **不完整句（False Starts）**：開頭說了一半就放棄重來

**技術方法**：

| 方法 | 描述 | 效果 |
|------|------|------|
| **Sequence Labeling（CRF/BiLSTM）** | 傳統方法，用條件隨機場或雙向 LSTM 標記贅字位置 | 穩定，需訓練資料 |
| **LLM Prompting** | 直接用 GPT-4o/Claude/Gemini 標記並移除贅字 | 準確度達 82.68%（few-shot），GPT-4o 速度最快 |
| **Fine-tuned 小模型** | 如 BanglaBERT 等微調模型 | 最高 84.78% 準確度 |
| **LARD（人工贅字生成）** | 用 LLM 生成訓練資料，不需標註語料 | 新興方法，潛力大 |
| **ILP（整數線性規劃）** | 加入贅字結構約束 | 學術 SOTA |

**關鍵發現**：移除贅字後，下游 NLP 任務（情感分析、命名實體辨識、翻譯）可提升 8% 以上。對會議記錄而言，**LLM Prompting 方式最實用**——不需訓練資料，直接在摘要生成 prompt 中加入清理指令即可。

### 6.4 斷句與分段（Segmentation）

**句子邊界偵測**：
- ASR 輸出通常是連續文字流，無標點
- 方法：利用韻律特徵（停頓、語調下降）+ 語意特徵（句子完整性），或直接由 LLM 加標點
- 技術：Head/Tail 短語分析、SegNSP（Next Sentence Prediction）

**主題分段（Topic Segmentation）**：
- 會議逐字稿是最難的場景——因為大量話輪（utterances）執行對話功能但不含主題語意
- 傳統方法（TextTiling、C99）在會議上效果差
- 現代方法：用神經句子編碼器計算語意相似度，但在會議領域效果接近零
- **實務最佳方案**：讓 LLM 直接按語意分段，效果遠勝傳統 NLP 方法

### 6.5 摘要生成（Summarization）

**萃取式（Extractive）**：直接挑出原文關鍵句，保留原始措辭，適合法律/醫療等需精確用語的場景

**生成式（Abstractive）**：生成全新文字，更流暢易讀，適合會議筆記

**長文摘要策略**：

| 策略 | 描述 | 適用場景 |
|------|------|---------|
| **Chunk-then-Summarize** | 先切段分別摘要，再合併 | 超出 context window 的長逐字稿 |
| **Hierarchical Summarization** | 逐層遞進：chunk → section summary → global summary | 多小時會議 |
| **KMeans++ Clustering** | 嵌入→聚類→每群取中心段落摘要→Markov 排序 | 跨主題的長文 |
| **Sliding Window** | 每個 chunk 帶前面摘要的上下文 | 保持連貫性 |
| **Multi-stage Prompting** | 分步驟：識別主題→逐題展開→提取行動項→品質檢查 | 最高品質方案 |

**關鍵發現**：2025 年研究發現，在 ~2,500 tokens 處存在「context cliff」——回應品質顯著下降。建議 chunk size 400-512 tokens + 10-20% overlap 起步。

### 6.6 排版與格式化

**結構化會議摘要的標準格式**：
```
## 會議摘要
- 日期/時間/參與者
- 2-3 句總結

## 討論主題
### 主題一：[標題]
- 討論要點（bullet points）
- 相關引述（帶時間戳和說話者）

## 決議事項
- **決議**：[內容]（標記「Decision:」增加可見度）
- 簡短理由（避免冗長辯論記錄）

## 行動項目
- [ ] [具體任務] — **負責人**：[姓名] | **期限**：[日期]

## 停車場（Parking Lot）
- [離題但值得後續討論的議題]

## 下次會議
- 日期/議程
```

### 來源

- [Deepgram ASR Benchmarks](https://deepgram.com/learn/speech-to-text-benchmarks)
- [Deepgram Pricing](https://deepgram.com/pricing)
- [Speech-to-Text Accuracy 2025 - Dev.to](https://dev.to/albert_nahas_cdc8469a6ae8/speech-to-text-accuracy-in-2025-benchmarks-and-best-practices-6ia)
- [pyannote.audio GitHub](https://github.com/pyannote/pyannote-audio)
- [pyannoteAI](https://www.pyannote.ai/)
- [Disfluency Detection via LLMs - ACL](https://aclanthology.org/2024.stil-1.16.pdf)
- [Google Research: Disfluencies in Natural Speech](https://research.google/blog/identifying-disfluencies-in-natural-speech/)
- [LLM Summarization Strategies - Galileo](https://galileo.ai/blog/llm-summarization-strategies)
- [Multi-stage Meeting Notes - I'd Rather Be Writing](https://idratherbewriting.com/ai/prompt-engineering-summarizing-meeting-notes.html)
- [Transcript Optimization Prompts - BrassTranscripts](https://brasstranscripts.com/blog/powerful-llm-prompts-transcript-optimization)
- [Wrike Meeting Minutes Template](https://www.wrike.com/blog/action-items-with-meeting-notes-template/)

---

## 七、台灣/中文場景的特殊挑戰

### 中文語音辨識的技術難點

- **無空格分詞**：中文字之間無自然分隔，需 CER 而非 WER 評估
- **同音字眾多**：「其」「期」「騎」「棋」「旗」需靠上下文消歧
- **口語 vs 書面語差異巨大**：「然後他就醬子」→「接著他就這樣做了」
- **中英夾雜（Code-switching）**：三大挑戰——(1) 訓練資料稀缺 (2) 語言間音素差異 (3) 切換點的母語口音效應。成功大學建有早期中英 code-switching 語料庫（12.1 小時），2025 年新資料集 DOTA-ME-CS 提供更多開源資料

### 台灣口語特色

- **台語夾雜**：日常對話中大量台語（「很趴」「很古意」「歹勢」）
- **語氣詞**：「齁」「蛤」「欸」「對啊」「是喔」「好啦」——這些是文化語境標記，不能全部當贅字移除
- **晶晶體**：中英混用（「這個 case 很 tricky」「我 concern 的 point」）
- **口頭禪**：「那個」「就是」「然後」「對」——使用頻率遠高於英語填充詞

### 台灣在地 AI 會議記錄工具

| 工具 | 特色 | 中文表現 | 定價 |
|------|------|---------|------|
| **雅婷逐字稿** | 台灣自研、專為台灣口音開發 | 台灣國語+台語+中英夾雜 | NT$180/小時 |
| **Meeting Ink** | 速度+功能+在地化三面俱佳 | 台灣國語+台語+客語 | NT$549/月（40hr） |
| **SoundType AI** | 精準逐字稿、AI 聽寫 | 中文支援 | App 內購 |
| **Vocol.ai** | 彈性計費 | 中文支援 | ~NT$97/小時 |
| **Otter.ai** | 英語即時最強 | **中文極弱，常完全無法辨識** | 有免費版 |

**關鍵發現**：Meeting Ink 在 2026 年台灣實測中被評為「唯一在速度、功能、在地化三面都達到高水準」的工具。Otter.ai 在中文場景基本不可用。

### 來源

- [雅婷逐字稿](https://asr.yating.tw/)
- [Meeting Ink 2026 實測](https://ink.dwave.cc/zh-TW/news/85)
- [CS-Dialogue 中英 Code-switching 資料集](https://arxiv.org/html/2502.18913v1)
- [ChineseTaiwaneseWhisper GitHub](https://github.com/sandy1990418/ChineseTaiwaneseWhisper)
- [104 職場力 AI 語音筆記推薦](https://blog.104.com.tw/voicetotext_ai_tools/)

---

## 八、Prompt Engineering 角度

### 逐字稿→會議記錄的最佳 Prompt 策略

**核心原則**：單一 prompt 會導致截斷和品質下降。**必須拆成多階段**。

### 推薦的四階段 Pipeline

**Stage 1：清理（Clean）**
```
你是逐字稿清理專家。請清理以下逐字稿：
1. 移除填充詞（嗯、呃、那個、就是、然後（作為贅字時））
2. 合併重複（「我我我覺得」→「我覺得」）
3. 修正不完整句（保留語意，刪除 false starts）
4. 保留所有語氣詞如果它改變了承諾語氣（「可能」「不確定」要保留）
5. 保留所有專有名詞和技術詞彙
6. 加入標點和段落分隔
輸出格式：保留說話者標記 [Speaker X]，每段一行
```

**Stage 2：分段與主題識別（Segment）**
```
分析以下清理後逐字稿，識別所有討論主題。
輸出 JSON 格式：
[{"topic": "主題名稱", "start_speaker_turn": N, "end_speaker_turn": M, "summary": "一句話摘要"}]
```

**Stage 3：逐主題深入摘要（Summarize per topic）**
```
針對以下主題「{topic}」的逐字稿片段，生成詳細筆記：
- 使用 bullet points，盡量保留細節
- 標記決議（Decision:）
- 標記行動項目（Action:）含負責人和期限
- 包含關鍵引述（帶說話者）
- 如有分歧意見，記錄雙方立場
```

**Stage 4：組裝與格式化（Assemble）**
```
將以下各主題筆記組裝成完整會議記錄，格式如下：
[插入目標 Markdown 模板]
確保：
- 行動項目集中列表，含負責人和期限
- 決議事項醒目標記
- 停車場收集離題議題
- 2-3 句執行摘要在最上方
```

### 處理超長逐字稿的策略

| 逐字稿長度 | 策略 |
|-----------|------|
| < 4,000 tokens | 單次處理（直接進 Stage 1-4） |
| 4,000-50,000 tokens | Sliding Window：每 chunk 3,000 tokens + 500 overlap + 前段摘要作為 context |
| 50,000-200,000 tokens | Hierarchical：先 chunk 摘要 → 聚類 → 群組摘要 → 全局摘要 |
| > 200,000 tokens | Map-Reduce：平行處理所有 chunks → Reduce 合併 → 再 Reduce |

### 來源

- [Multi-stage Meeting Notes - I'd Rather Be Writing](https://idratherbewriting.com/ai/prompt-engineering-summarizing-meeting-notes.html)
- [LLM Summarization Strategies - Galileo](https://galileo.ai/blog/llm-summarization-strategies)
- [Chunking Strategies - Pinecone](https://www.pinecone.io/learn/chunking-strategies/)
- [Claude Context Windows Docs](https://platform.claude.com/docs/en/build-with-claude/context-windows)
- [Transcript Cleanup Prompts - PolarNotes](https://www.polarnotesai.com/students/prompts/organized-notes/chatgpt-transcript-cleanup/)
- [ChatGPT Meeting Notes - Bliro](https://www.bliro.io/en/blog/best-prompts-to-summarize-meeting-transcripts-using-chatgpt)

---

## 九、Meeting Notes Skill 設計建議清單

### 建議工作流程（五階段 Pipeline）

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  Stage 0    │ →  │  Stage 1    │ →  │  Stage 2    │ →  │  Stage 3    │ →  │  Stage 4    │
│  Ingest     │    │  Clean      │    │  Structure  │    │  Summarize  │    │  Deliver    │
│  收錄        │    │  清理        │    │  結構化      │    │  摘要生成    │    │  交付        │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
```

### 每階段技術選型

| 階段 | 功能 | 技術建議 | 備註 |
|------|------|---------|------|
| **Stage 0: Ingest** | 接收逐字稿 | 支援：(1) 純文字貼上 (2) 音檔上傳 → Whisper/Deepgram 轉錄 (3) 會議平台逐字稿匯入 | 音檔路徑：Whisper Large-v3（免費、中文可微調）或 Deepgram Nova-3（低延遲、付費） |
| **Stage 1: Clean** | 去贅字、加標點、修正 | LLM Prompting（Claude）：移除填充詞、合併重複、修正 false starts。中文特別處理：保留有意義的語氣詞，處理晶晶體 | 用 prompt 即可，不需額外模型 |
| **Stage 2: Structure** | 說話者辨識、主題分段、時間戳對齊 | (1) 若有說話者標記：直接用 (2) 若無：pyannote.audio 或 Deepgram diarization (3) 主題分段：LLM 語意分段 | 會議逐字稿的主題分段，LLM 遠勝傳統 NLP |
| **Stage 3: Summarize** | 多維度摘要生成 | Claude（MUSEON 核心 LLM）：Multi-stage prompting，支援模板系統。長逐字稿用 hierarchical summarization | 核心差異化：與 MUSEON 記憶系統整合 |
| **Stage 4: Deliver** | 格式化輸出 + 記憶寫入 | Markdown 結構化輸出 → Telegram 推播 / Notion 同步。行動項目寫入 MUSEON 任務系統。洞見寫入 memory_v3 | 閉環：會議→記憶→行動 |

### 台灣在地化需要特別處理什麼

1. **中文贅字清單**：建立台灣口語贅字辭典——「那個」「就是」「然後」「對」「嗯」「呃」「齁」，但需區分：
   - 純贅字（可移除）：「嗯...那個...就是說...」
   - 語氣標記（需保留或轉換）：「齁，這樣不太對吧」→ 保留語氣但不保留「齁」字
   - 確認語（需保留）：「對，我同意」→ 表示共識

2. **中英夾雜（晶晶體）處理**：
   - 保留專有名詞英文原形（API、AWS、Sprint）
   - 翻譯非必要英文（「concern 的 point」→「擔心的重點」），或保留但標記
   - 建立常見中英混用對照表

3. **台語處理**：
   - 辨識台語詞彙並標記或翻譯
   - 雅婷逐字稿的台語辨識能力可作為參考

4. **標點與斷句**：
   - 中文無空格，需要高品質的斷句
   - 使用逗號「，」和句號「。」而非英文標點
   - 注意引號使用「」而非 ""

### 與 MUSEON 現有 Skill 的協作方式

| 協作 Skill | 協作模式 | 說明 |
|-----------|---------|------|
| **Memory Crystallizer** | Meeting Notes → Crystal | 會議中的洞見和決策寫入結晶記憶 |
| **Task Tracker / 行動項目系統** | Meeting Notes → Tasks | 自動提取行動項目，含負責人和期限 |
| **Daily Briefing** | Tasks from Meetings → Briefing | 每日簡報納入未完成的會議行動項目 |
| **Knowledge Graph / memory_v3** | Meeting Insights → Memory | 跨會議的主題追蹤和知識累積（類似 Fireflies Topic Tracker） |
| **Nightly Reflection** | Today's Meetings → Reflection | 每日反思納入當日會議的決策和學習 |
| **Boss Messenger** | Meeting Summary → Telegram | 會議結束後推播摘要到使用者 |

### 差異化設計建議

1. **Granola 式混合模式**：允許使用者在會議中即時標記重點（透過 Telegram 快速輸入），AI 事後將這些標記與逐字稿合併增強
2. **多維度摘要**（學 Plaud）：同一份會議，自動生成「執行摘要」「詳細筆記」「行動項目清單」三個版本
3. **跨會議記憶**（學 Fireflies）：追蹤特定主題在多次會議中的演進，自動關聯相關決策
4. **Custom Templates**（學 Notion）：使用者可定義自己的摘要規則和格式
5. **減法哲學**：不要嘗試做 Otter/Fireflies 的即時轉錄 Bot，而是做好「收到逐字稿後的後處理+記憶整合」這個 MUSEON 獨有的價值點

---

以上就是完整的技術方法論研究。核心結論是：**MUSEON Meeting Notes Skill 的護城河不在 ASR（語音辨識），而在「逐字稿→精煉記錄→長期記憶整合→行動閉環」這條後處理管線**。ASR 用現成方案（Whisper/Deepgram），把精力集中在 Stage 1-4 的 LLM Pipeline 和 MUSEON 記憶系統的深度整合上。
NOT FOUND
