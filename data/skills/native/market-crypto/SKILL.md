---
name: market-crypto
type: on-demand
layer: market
io:
  inputs:
    - from: market-core
      field: framework
      required: true
    - from: user
      field: crypto_query
      required: false
  outputs:
    - to: market-core
      field: crypto_analysis
      trigger: always
    - to: user
      field: crypto_report
      trigger: always
connects_to:
  - market-core
  - investment-masters
memory:
  writes:
    - knowledge-lattice
  reads:
    - knowledge-lattice
description: >
  Market-Crypto（加密貨幣與預測市場分析衛星）— DNA27 核心的外掛模組，
  market-core 的加密貨幣特化衛星，專為 BTC/ETH/主流幣、DeFi 協議、
  預測市場（Polymarket 等）、鏈上數據分析設計。
  在 market-core 五層通用框架之上注入加密市場特有維度：鏈上數據分析（大戶動向、
  交易所資金流）、DeFi 協議健康度、預測市場定價偏差掃描、加密情緒指標、
  監管風險即時追蹤。
  語言深度預設全白話：所有區塊鏈術語必須附帶生活化解釋。
  觸發時機：(1) market-core 偵測到加密貨幣/區塊鏈類標的時自動載入；
  (2) /crypto 指令強制啟動；(3) 自然語言偵測——提到 BTC、ETH、比特幣、
  以太坊、加密貨幣、區塊鏈、DeFi、NFT、預測市場等時自動啟用。
  涵蓋觸發詞：比特幣、BTC、以太坊、ETH、加密貨幣、區塊鏈、DeFi、
  NFT、Polymarket、預測市場、穩定幣、USDT、USDC、交易所、
  幣安、Coinbase、鏈上數據、鯨魚、減半、質押、流動性。
  依賴 market-core 通用框架，不可脫離 market-core 獨立運作。
  與 market-core 互補：core 管通用框架，crypto 管加密市場特有邏輯。
  與 market-macro 互補：macro 提供利率環境判斷，加密市場對流動性極度敏感。
  與 xmodel 互補：多空路徑推演時可調用破框視角。
---

# Market-Crypto：加密貨幣與預測市場分析衛星

> **加密市場是全球流動性的放大器——央行灑水它最先漲，央行收水它最先跌。搞懂規則，才不會在別人的遊戲裡當韭菜。**

## 外掛合約

此 Skill 為 market-core 的場景衛星模組（satellite module）。

**依賴**：
- dna27 skill（母體 AI OS）
- market-core skill（通用市場分析引擎——提供五層蒐集、多空對稱、風險矩陣、報告模板）

**本模組職責**：
- 在 market-core 的各層注入加密市場特有的分析維度
- 提供鏈上數據的白話解讀（大戶在幹嘛、交易所資金動向）
- 追蹤預測市場（Polymarket 等）的定價與資訊
- 監控加密市場特有的情緒指標
- 即時追蹤全球加密貨幣監管動態

**本模組不做**：
- 不做 market-core 已覆蓋的通用分析邏輯
- 不做自動交易或套利策略執行
- 不做具體的「買哪個幣」建議
- 不做智能合約審計或程式碼安全分析
- 不推薦特定交易所或 DeFi 協議

---

## 觸發與入口

**指令觸發**：
- /crypto — 強制啟動加密市場分析模式
- /crypto [幣種] — 指定幣種分析（例：/crypto BTC、/crypto ETH）
- /crypto onchain — 專注鏈上數據分析
- /crypto defi — 專注 DeFi 生態分析
- /crypto predict — 專注預測市場分析

**自動載入**：
當 market-core 的衛星路由偵測到以下關鍵字時自動掛載：
- 幣種名稱（BTC、ETH、比特幣、以太坊、SOL、XRP 等）
- 平台名稱（幣安、Coinbase、Polymarket、Uniswap 等）
- 概念詞（加密貨幣、區塊鏈、DeFi、NFT、穩定幣、鏈上、鯨魚）

---

## 加密市場特化維度

### C1：鏈上數據分析框架

為什麼需要這個：區塊鏈是公開帳本——所有交易紀錄都是公開的。白話說，就像每個人的銀行帳戶都是透明的，你可以看到大戶在買還是在賣。這是傳統股市做不到的資訊優勢。

**核心鏈上指標**：

交易所流入/流出
- 搜尋：「[幣種] exchange inflow outflow [year]」
- 白話：大戶把幣搬進交易所（準備賣）還是搬出交易所（準備長抱）？
- 多方訊號：淨流出增加（幣從交易所被提走 = 不打算短期賣）
- 空方訊號：淨流入暴增（大量幣被送進交易所 = 有人準備拋售）

鯨魚動向（Whale Activity）
- 搜尋：「[幣種] whale transaction large transfer」
- 白話：持有大量幣的帳戶（鯨魚）最近在做什麼？
- 追蹤重點：大額轉帳到交易所 = 可能要賣；大額從交易所轉出 = 可能在囤貨
- 注意：不是所有大額轉帳都是買賣——可能只是在不同錢包之間搬家

活躍地址數（Active Addresses）
- 搜尋：「[幣種] active addresses trend」
- 白話：每天有多少人在用這個區塊鏈？人越多代表「這條路越熱鬧」
- 多方訊號：活躍地址持續增加（使用者在成長）
- 空方訊號：活躍地址持續下降（人在離開）

持有者分布
- 搜尋：「[幣種] holder distribution concentration」
- 白話：這個幣集中在少數人手上還是分散在很多人手上？太集中 = 風險高（少數人就能砸盤）

礦工/驗證者行為
- 搜尋：「[幣種] miner selling validator unstaking」
- 白話：挖礦或維護網路的人在賣幣嗎？他們是「源頭供應商」，大量賣出 = 壓力

**鏈上數據護欄**：
- 鏈上數據有解讀空間，同一筆轉帳可能有多種原因——必須附帶「可能的替代解釋」
- 不同區塊鏈的數據可得性不同（BTC 和 ETH 最完整，其他幣可能數據有限）
- 標注數據來源（Glassnode、CryptoQuant、Dune Analytics 等）

---

### C2：加密市場情緒指標

為什麼需要這個：加密市場比股市更容易受情緒驅動——暴漲暴跌往往是情緒先行、基本面後至。

**核心情緒指標**：

恐懼與貪婪指數（Crypto Fear & Greed Index）
- 搜尋：「crypto fear greed index today」
- 白話：0-100 的數字，0 = 極度恐懼（大家嚇壞了），100 = 極度貪婪（大家瘋搶）
- 反向指標邏輯：極度恐懼時往往是買點（別人恐懼時貪婪），極度貪婪時往往是賣點

資金費率（Funding Rate）
- 搜尋：「[幣種] funding rate perpetual」
- 白話：在永續合約市場（一種可以用槓桿做多或做空的工具），多方和空方之間定期付費。費率為正 = 做多的人付費給做空的人（代表市場偏多）；費率為負 = 反過來
- 極端正值 = 多方過度擁擠（小心反轉）

合約未平倉量（Open Interest）
- 搜尋：「[幣種] open interest futures」
- 白話：目前市場上還沒結清的期貨/合約總金額。越高代表賭注越大。
- 配合價格看：價格漲 + OI 漲 = 新資金進場做多（強勢）；價格漲 + OI 跌 = 空方在認賠（反彈可能有限）

清算數據（Liquidation）
- 搜尋：「crypto liquidation data 24h」
- 白話：過去 24 小時有多少用槓桿的人被「爆倉」（虧損到自動平倉）。大量清算 = 市場正在洗盤

社群熱度
- 搜尋：「[幣種] social sentiment Twitter Reddit」
- 白話：社群媒體上對某個幣的討論量和情緒方向
- 注意：社群熱度是短期噪音，不能作為中長期論據

---

### C3：預測市場分析框架

為什麼需要這個：預測市場（如 Polymarket）讓人用真金白銀「押注」事件結果。市場價格 = 群眾對事件發生機率的即時估計。跟傳統民調不同，這裡的人「用錢投票」，理論上更誠實。

**預測市場分析維度**：

定價效率分析
- 搜尋：「Polymarket [事件] odds price」
- 白話：市場對某事件的定價是否合理？有沒有被高估或低估？
- 分析方法：比較預測市場價格 vs 多個獨立來源的機率評估，找出偏差

流動性與成交量
- 搜尋：「Polymarket [事件] volume liquidity」
- 白話：這個市場有多少人在交易？人越多、錢越多，價格越可靠
- 注意：低流動性市場的價格波動大，可能不反映真實機率

大額交易追蹤
- 搜尋：「Polymarket [事件] large trades whale」
- 白話：有沒有知情人士在大量押注某個方向？

時間序列分析
- 追蹤某事件的預測價格如何隨新聞變化，辨識「市場已經消化」vs「市場還沒反應」

**預測市場護欄**：
- 預測市場價格不等於真實機率——可能存在系統性偏差（如對小機率事件的高估）
- Polymarket 在部分國家地區有監管限制，使用者需自行了解當地法規
- 不做交易建議，只做資訊分析

---

### C4：DeFi 生態健康度

為什麼需要這個：DeFi（去中心化金融）是加密市場的「銀行系統」。它的健康程度直接影響整個加密市場的流動性和信心。

**DeFi 健康指標**：

TVL（Total Value Locked / 總鎖倉量）
- 搜尋：「DeFi TVL total value locked trend」
- 白話：有多少錢被存放在 DeFi 協議裡？就像銀行的存款總額。
- 趨勢意義：TVL 上升 = 信心增加（更多人把錢放進來）；下降 = 信心流失

穩定幣市值
- 搜尋：「stablecoin market cap USDT USDC trend」
- 白話：穩定幣（錨定美元的加密貨幣，如 USDT、USDC）的總市值。相當於加密市場的「子彈」——穩定幣多，代表場外有很多資金隨時準備買入。

借貸利率
- 搜尋：「DeFi lending rate Aave Compound」
- 白話：在 DeFi 借錢的利率。高利率 = 需求旺盛（人們想借錢去投機）；低利率 = 需求冷淡

協議風險事件
- 搜尋：「DeFi hack exploit [year]」「DeFi protocol risk」
- 白話：最近有沒有 DeFi 協議被駭客攻擊或出事？每次大型駭客事件都會短期打擊整個市場信心

---

### C5：加密貨幣監管追蹤

為什麼需要這個：加密市場最大的不確定性來自監管。一條法規可以讓幣價暴跌 20%，也可以讓它暴漲 30%。

**監管追蹤維度**：

美國 SEC / CFTC
- 搜尋：「SEC crypto regulation [year]」「CFTC cryptocurrency enforcement」
- 白話：美國證券監管機構對加密貨幣的態度。它們的決定影響全球市場，因為大部分加密交易量在美國。
- 關鍵議題：ETF 審批、交易所監管、穩定幣立法、DeFi 監管框架

歐盟 MiCA
- 搜尋：「EU MiCA regulation crypto [year]」
- 白話：歐盟的加密貨幣市場監管框架。是目前全球最完整的加密法規。

台灣金管會
- 搜尋：「台灣 金管會 加密貨幣 虛擬資產 法規 [年份]」
- 白話：台灣對加密貨幣的監管態度。目前以「自律」為主，但正在逐步立法。

中國
- 搜尋：「China crypto ban policy [year]」
- 白話：中國全面禁止加密貨幣交易和挖礦，但香港正在開放。

**監管事件影響評估格式**：
每個事件包含：事件名稱 + 白話描述、影響範圍（全球/區域/單一平台）、影響方向（利多/利空/中性）、影響時間（短期/中期/長期）、歷史類比。

---

## 加密市場特殊週期

### 比特幣減半週期

白話：比特幣每四年「減半」一次——挖礦產出的新幣數量減半。歷史上每次減半後 12-18 個月，BTC 都創了新高。但「歷史不代表未來」。

搜尋策略：「Bitcoin halving cycle [year] price history」「BTC halving supply shock」

分析維度：上次減半日期、當前距減半天數、歷史減半後價格走勢對比、供給衝擊量化、與前次週期的差異（制度環境、參與者結構）。

---

## 護欄

### 硬閘

**HG-CR-INHERIT-CORE**：繼承 market-core 的全部硬閘。

**HG-CR-NO-SHILL**：絕對不推薦或暗示任何特定幣種、協議、交易所。只分析市場結構和數據。

**HG-CR-SCAM-WARNING**：如果分析的標的有明顯的詐騙或跑路風險特徵（匿名團隊、不合理高收益、缺乏程式碼審計），必須明確警告。

**HG-CR-LEVERAGE-WARNING**：任何涉及槓桿交易的討論，必須附帶「槓桿可以放大獲利也放大虧損，可能導致本金全部歸零」的警告。

**HG-CR-REGULATION**：提醒使用者在台灣投資加密貨幣的法規現況，建議自行了解稅務義務和合規要求。

### 軟閘

**SG-CR-VOLATILITY**：加密市場波動率遠高於傳統市場（BTC 日波動 5-10% 是常態），報告中提醒使用者校準預期。

**SG-CR-DATA-DELAY**：鏈上數據可能有延遲，標注數據截止時間。

**SG-CR-CORRELATION**：加密市場與傳統市場的相關性時高時低——不能假設「美股漲加密就漲」。

---

## 適應性深度控制

| DNA27 迴圈 | 鏈上數據 | 情緒指標 | 預測市場 | DeFi | 監管 |
|------------|---------|---------|---------|------|------|
| fast_loop | 交易所流入流出 + 鯨魚 | 恐懼貪婪指數 | 跳過 | 跳過 | 重大事件 |
| exploration_loop | 全部核心指標 | 全部指標 | 主要事件 | TVL + 穩定幣 | 全覆蓋 |
| slow_loop | 全部 + 趨勢分析 | 全部 + 歷史對比 | 完整分析 | 全部指標 | 完整 + 政策路徑推演 |

---

## 系統指令

| 指令 | 效果 |
|------|------|
| /crypto | 啟動加密市場分析（自動判斷幣種） |
| /crypto [幣種] | 指定幣種分析 |
| /crypto onchain | 專注鏈上數據分析 |
| /crypto sentiment | 專注情緒指標 |
| /crypto predict | 專注預測市場分析 |
| /crypto defi | 專注 DeFi 生態分析 |
| /crypto regulation | 專注監管動態追蹤 |
| /crypto halving | 專注比特幣減半週期分析 |

---

## DNA27 親和對照

啟用 market-crypto 時：
- Persona 旋鈕：繼承 market-core 設定（NEUTRAL / STEADY / DRIVE）
- 偏好觸發的反射叢集：RC-C3（結構化思考）、RC-D1（外部工具優先）
- 限制使用的反射叢集：RC-B1（不替使用者做投資決策）、RC-A2（不被加密市場的極端敘事帶走）

與其他外掛的協同：
- **market-core**：core 啟動後路由到 crypto，crypto 在各層注入加密特化分析
- **market-macro**：利率環境和流動性判斷是加密市場的最大外部變量
- **market-equity**：部分加密相關股票（如 Coinbase、MicroStrategy）可交叉分析
- **xmodel**：多空路徑推演時調用破框視角
- **env-radar**：監管政策變動掃描
