# 劇本生成 DSE 研究報告

**日期**：2026-03-25
**任務背景**：為羅臻的劇本寫作需求設計可複用的 AI Skill/Workflow
**研究方法**：Web Search + 架構分析

---

## 研究發現

### 1. 劇本結構框架

#### 三幕劇（Three-Act Structure）
最通用、最基礎的劇本結構，被好萊塢 90% 以上的電影採用。

| 幕次 | 內容 | 佔比 | 關鍵 |
|------|------|------|------|
| **第一幕（Setup）** | 交代主角、背景、衝突起因 | 0-25% | 建立人物關係與世界觀 |
| **第二幕（Confrontation）** | 主角追求目標、面對障礙、危機升級 | 25-75% | 內外衝突並行、不斷升高張力 |
| **第三幕（Resolution）** | 危機爆發、衝突解決、人物蛻變 | 75-100% | 情感高潮、主角改變或命運逆轉 |

**Syd Field 經典模型**：
- Setup + Inciting Incident (pp. 1-10)
- Confrontation + Midpoint Turn (pp. 10-60)
- Resolution + Climax (pp. 60-120)

#### 五幕劇（Five-Act Structure / Freytag's Pyramid）
源自古羅馬劇作家賀瑞斯（Horace），後由德國劇作家弗雷塔格（Freytag）分析完善。

| 幕次 | 內容 |
|------|------|
| **第一幕（Exposition）** | 介紹背景、人物、衝突伏筆 |
| **第二幕（Rising Action）** | 衝突逐漸升級 |
| **第三幕（Climax）** | 故事最高潮 |
| **第四幕（Falling Action）** | 危機緩解、結局逼近 |
| **第五幕（Resolution）** | 最終解決、人物命運確定 |

**適用場景**：舞台劇、文學改編、長篇敘事。

#### 實務選擇
- **三幕劇**：電影、短篇、電視單集（推薦 MUSEON Skill 採用）
- **五幕劇**：舞台劇、話劇、小說改編
- **七幕劇**：電視連續劇（每幕對應一個商業區間）

**關鍵洞見**：結構決定劇本生死，結構好的劇本天然具備張力、節奏感、觀眾期待感。

---

### 2. 情緒線與張力設計

#### 情緒弧線（Emotional Arc）
不只在結尾讓觀眾哭笑，而是在整個故事中刻意安排情緒起伏。

**情緒進展邏輯**：
1. **與主角目標綁定**：觀眾為主角的成功/失敗而喜怒哀樂
2. **與衝突升級同步**：衝突越激化 → 情感越濃烈
3. **內外衝突交織**：外部敵人 + 角色內心掙扎 = 雙重張力
4. **多個小高潮疊加**：不是線性上升，而是波浪式（低谷→小高潮→更低谷→更大高潮）

**目標情感模式**：
- 第一幕：建立共鳴（觀眾喜歡/同情主角）
- 第二幕：製造挫折感（危機逼近、主角陷入困境）
- 第三幕：釋放張力（超越期待的解決、淚點、笑點、驚喜）

#### 內在衝突（Internal Conflict）是引擎
劇本不是「主角 vs 敵人」，而是「主角 vs 自己」（欲望 vs 恐懼、責任 vs 夢想、信念 vs 現實）。

**張力設計三層**：
1. **內在張力**：角色對自己的懷疑、成長的痛苦
2. **人際張力**：人物間的衝突、利益對立
3. **情節張力**：時間倒計時、突發事件、高賭注決策

**實戰例**：《鐵達尼號》傑克vs玫瑰的愛情，背後是「階級執念 vs 真摯感情」的衝突，越衝突越動人。

#### 關鍵引擎機制
每一場景必須：
- ✓ 推進衝突（一個問題沒解決，新問題出現）
- ✓ 暴露角色傷口（為什麼這個角色會這樣做？）
- ✓ 移動情感指針（比上一場景更害怕、更希望、更絕望）

---

### 3. 劇本場景與道具設計原則

#### 場景設計（Staging）
場景是舞台、佈景、燈光、空間安排的綜合體，負責「視覺敘事」。

**場景三要素**：
1. **環境信號**：空間暗示故事時代、社會階級、心理狀態
2. **視覺節奏**：開放空間 vs 密閉空間產生不同心理壓力
3. **對稱與破壞**：井然有序的場景突然混亂 = 衝突激化的視覺表達

**各類型場景策略**：
| 類型 | 美學 | 目的 |
|------|------|------|
| **悲劇** | 極簡主義、冷色調、視線受限 | 強調無力感、困頓感 |
| **喜劇** | 亮色、開放、物件豐富 | 營造輕鬆、混亂的笑點機會 |
| **現實主義** | 細節繁複、日常雜亂 | 拉近觀眾與生活的距離 |
| **戲劇化** | 對比強烈、極端元素 | 強化情緒、製造視覺衝擊 |

#### 道具設計（Props）
道具不只是「東西」，而是「角色的延伸 × 故事的視覺符號」。

**道具的三重功能**：
1. **敘事功能**：道具本身就說故事（破舊的手錶 = 時光流逝、失去、懷舊）
2. **角色功能**：透過如何使用道具揭示人物性格（粗魯 vs 溫柔、強勢 vs 退縮）
3. **情節功能**：道具成為關鍵物件（鑰匙、信件、老照片），驅動情節轉折

**道具設計清單原則**：
- ✓ 每個道具必須有「為什麼存在」的理由
- ✓ 道具應該在不同場景反覆出現（強化象徵性）
- ✓ 道具磨損程度、顏色、大小都傳遞信息
- ✓ 極簡主義：用最少道具表達最多意思（省成本、聚焦觀眾）

**經典例**：莎士比亞作品中的手帕、匕首、毒藥不是裝飾，而是劇情催化劑 + 道德象徵。

---

### 4. AI 劇本生成工具現狀

#### 現有工具與限制
- **ChatGPT / Claude**：出色的創意助手，但生成的是「劇本風格文本」而非「製作藍圖」
- **專業軟體**（Final Draft、Celtx）：標準化格式，但不提供創意生成
- **AI 劇本生成器**：存在但品質參差不齊，多為「粗胚」

#### 關鍵限制
1. **不懂製作** → AI 生成的劇本缺少實際執行細節（道具清單、場景搭建成本、角色數限制）
2. **結構化不足** → 情緒線、張力點不明確，需人工補救
3. **文化適配** → 泛用 AI 不理解台灣本土文化背景、方言、風俗
4. **回收利用差** → 每次都是全新生成，缺少「版本管理、修改追蹤」

#### MUSEON 機會
與其複製通用 AI，不如做「結構化、可驗證、可複用、本土化的劇本生成引擎」。

---

### 5. 劇本寫作流程標準化

#### 專業劇本家的標準工作流
```
階段 1: 創意開發 (Concept)
  ↓ 確定題材、核心衝突、目標情感

階段 2: 構思 (Treatment)
  ↓ 三幕綱要、主要轉折點、角色弧線

階段 3: 大綱 (Outline)
  ↓ 場景清單、每場景的目的、對話骨架

階段 4: 初稿 (First Draft)
  ↓ 完整對白、舞台指示、節奏感

階段 5: 修改 (Revision)
  ↓ 檢查邏輯、情緒一致性、台詞自然度

階段 6: 終稿 (Final Polish)
  ↓ 格式統一、樣式檢查、製作清單完備
```

#### 可標準化的檢查清單
- [ ] 三幕結構完整性（起承轉合明確）
- [ ] 情緒弧線檢查（情感進展有邏輯）
- [ ] 衝突確認（內在 + 人際 + 情節 ≥2 層）
- [ ] 角色蛻變驗證（主角在結尾有改變）
- [ ] 場景數統計（時長與場景數匹配）
- [ ] 道具清單完整（所有提及的道具有設計說明）
- [ ] 對白檢查（每人物聲音不同、無說教）
- [ ] 視覺層檢查（場景、光線、動作有想像空間）

#### 格式標準
採用 **Fountain 格式**（通用劇本標記語言）或 **業界標準 PDF**，確保跨工具相容。

---

## 建議與行動方向

### 短期（給羅臻）
1. **結構優先**：先確定是三幕劇還是五幕劇，再生成其他細節
2. **情緒設計前置**：每場景問「觀眾此時應該感受什麼？」
3. **道具清單附帶**：生成劇本時同時附帶「製作成本估算、佈景需求」

### 中期（MUSEON Skill）
1. **結構化提示工程**：設計 prompt 讓 Claude 生成「角色檔案 → 情緒表 → 場景大綱 → 初稿」
2. **驗收流程**：自動檢查三幕完整性、情緒線連貫性、場景數合理性
3. **輸出格式**：Markdown（易編輯）+ HTML 預覽（美觀呈現）

### 長期（MUSEON DNA27）
1. **本土化劇本庫**：蒐集台灣廣告、短片、微劇本案例，建立「情感模式庫」
2. **多模態輸出**：不只文字，附帶「分鏡建議」「音樂情感線」「場景 3D 參考」
3. **版本控制**：整合 Git，讓劇本迭代可追蹤（誰改了什麼、為什麼改）

---

## 參考資源

### 結構框架
- [SoCreate - Breaking Down 3 Act and 5 Act Structures](https://www.socreate.it/en/blogs/screenwriting/breaking-down-3-act-and-5-act-structures-in-a-traditional-screenplay)
- [Final Draft - Building Screenplay Structure](https://www.finaldraft.com/learn/building-screenplay-structure/)

### 情緒線與張力
- [WriteAtlas - How to Write a Drama Screenplay: Emotional Depth and Conflict](https://writeatlas.com/how-to-write-a-drama-screenplay-emotional-depth-and-conflict/)
- [Filmmakers Academy - Emotional Arc: Breaking Down Your Screenplay](https://www.filmmakersacademy.com/emotional-arc/)

### 場景與道具設計
- [Shakespeare Insights - The Use of Props to Dramatic Effect](https://williamshakespeareinsights.com/the-use-of-props-to-dramatic-effect-in-shakespeares-plays/)
- [Grokipedia - Staging in Theatre, Film, Television](https://grokipedia.com/page/Staging_(theatre,_film,_television))

### AI 與工具化
- [Best Screenplay AI Prompts - DocsBot AI](https://docsbot.ai/prompts/tags?tag=Screenplay)
- [SudoWrite - Best AI for Screenwriters in 2026](https://sudowrite.com/blog/best-ai-for-screenwriters-in-2026-write-scripts-that-get-read/)

### 標準化流程
- [ClickUp - Free Script Writing Templates](https://clickup.com/blog/scriptwriting-templates/)
- [Celtx Blog - Movie Script Format: Complete Guide](https://blog.celtx.com/movie-script-format/)

---

## 結論

劇本生成不是「一鍵生成完美劇本」，而是「用結構化提示 + AI 補能 + 人工驗收」三層協作。
MUSEON 的優勢在於：
- **結構化流程**：三幕劇模板 + 情緒線檢查清單
- **情感智能**：理解「為什麼這場景讓人哭」不只是「發生了什麼」
- **可製作性**：同時輸出文本 + 道具清單 + 成本估算

下一步：建立 `screenplay-skill-spec.md` 與可執行工作流。
