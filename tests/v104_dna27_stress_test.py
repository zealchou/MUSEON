#!/usr/bin/env python3
"""DNA27 v10.4 壓力測試 — 20 情境 × 3 輪互動.

測試重點：
  1. Route A (Semantic Router) — 語義偵測準確率
  2. Route B (MoE Decay) — skill 使用頻率衰減
  3. Route C (State Conditioning) — 跨輪路由記憶
  4. 27 RC 叢集覆蓋面
  5. 三輪互動中的路由連續性

情境設計原則：
  - 20 個全新情境（與 v10.0-v10.3 不同）
  - 每情境 3 輪互動，基於前輪回應調整
  - 訊息長度 50-400 字交錯
  - 涵蓋 Tier A-E 全部 5 層
"""

import json
import time
import hashlib
import requests
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

GATEWAY_URL = "http://127.0.0.1:8765/webhook"
USER_ID = "stress_test_v104"

# ═══════════════════════════════════════════
# 20 個全新測試情境
# ═══════════════════════════════════════════

SCENARIOS = [
    # ── S01: 創業者資金鏈斷裂（A3+A4 不可逆+風險 → D1 行動轉向）──
    {
        "id": "S01",
        "name": "創業者資金鏈斷裂",
        "target_clusters": ["RC-A3", "RC-A4", "RC-D1"],
        "rounds": [
            {
                "content": "我的公司帳上只剩三個月現金了，投資人也說不投了。我很認真在考慮要不要把房子抵押去撐，這樣至少可以再多半年時間等轉機。",
                "expect_tier": "A",
                "expect_rc": ["RC-A3", "RC-A4"],
                "len_target": 70,
            },
            {
                "content": "你說的對，抵押房子太冒險了。但我的團隊十幾個人在等我做決定，如果收掉公司，他們都要失業了。這個責任我扛不起。不知道有沒有其他方法可以先穩住三個月的。",
                "expect_tier": "A",
                "expect_rc": ["RC-B4", "RC-D1"],
                "len_target": 100,
            },
            {
                "content": "好，那我想試試你說的這個方向。具體第一步要怎麼做？先從哪裡開始比較好？",
                "expect_tier": "D",
                "expect_rc": ["RC-D1", "RC-D4"],
                "len_target": 50,
            },
        ],
    },

    # ── S02: 深夜情緒崩塌（A1+A2 → C3 認知不確定 → E4 節奏恢復）──
    {
        "id": "S02",
        "name": "深夜情緒崩塌",
        "target_clusters": ["RC-A1", "RC-A2", "RC-E4"],
        "rounds": [
            {
                "content": "凌晨三點了還睡不著。已經連續兩週這樣了，白天上班整個人像殭屍，晚上又焦慮到翻來覆去。感覺自己快撐不住了，身體跟精神都到極限了。有時候會覺得，是不是放棄這份工作比較好，但房貸車貸壓著，根本不敢動。",
                "expect_tier": "A",
                "expect_rc": ["RC-A1", "RC-A2"],
                "len_target": 140,
            },
            {
                "content": "嗯…你說的那些我好像都知道，但就是做不到。不清楚到底是心理的問題還是身體的問題，整個人很模糊。",
                "expect_tier": "C",
                "expect_rc": ["RC-C3"],
                "len_target": 60,
            },
            {
                "content": "也許你說得對，我需要先慢下來。不用急著解決所有問題，先讓自己喘口氣再說。",
                "expect_tier": "E",
                "expect_rc": ["RC-E4"],
                "len_target": 55,
            },
        ],
    },

    # ── S03: 職涯十字路口（B3+B5 逃避vs主權 → C4 動機釐清 → D1 實驗）──
    {
        "id": "S03",
        "name": "職涯十字路口",
        "target_clusters": ["RC-B3", "RC-B5", "RC-C4", "RC-D1"],
        "rounds": [
            {
                "content": "在同一家公司做了八年了，最近收到一個新公司的 offer，薪水多 30%，但要去大陸駐點兩年。老婆跟小孩都在台灣，又不想放棄這個機會。算了不想了太煩了。",
                "expect_tier": "B",
                "expect_rc": ["RC-B3"],
                "len_target": 100,
            },
            {
                "content": "你問我為什麼想換？說實話我不確定。可能是覺得在這裡看不到未來，但新的那個也未必更好。到底是逃避還是追求，我自己都搞不清楚。",
                "expect_tier": "C",
                "expect_rc": ["RC-C4", "RC-C3"],
                "len_target": 85,
            },
            {
                "content": "你這個問法很好。我確實沒有認真想過我到底想要什麼樣的生活。也許在做決定之前，先花一個月時間認真想清楚自己的核心需求是什麼。可以教我怎麼做這樣的自我探索嗎？",
                "expect_tier": "D",
                "expect_rc": ["RC-D1", "RC-B5"],
                "len_target": 120,
            },
        ],
    },

    # ── S04: AI 焦慮症（C1+C5 過度確信vs不確定 → D1 研究）──
    {
        "id": "S04",
        "name": "AI 取代焦慮",
        "target_clusters": ["RC-C1", "RC-C5", "RC-D1"],
        "rounds": [
            {
                "content": "我朋友說 AI 一定會在三年內取代所有設計師，百分之百的事情，不可能不發生。他已經開始轉行了。我是不是也該現在就行動？",
                "expect_tier": "C",
                "expect_rc": ["RC-C1"],
                "len_target": 80,
            },
            {
                "content": "你的意思是不要那麼絕對？但我看到的所有新聞都在講 AI 多厲害，難道他們都錯了嗎？我覺得風險是不是被我低估了。",
                "expect_tier": "C",
                "expect_rc": ["RC-C5", "RC-C1"],
                "len_target": 75,
            },
            {
                "content": "好吧，也許真的不用那麼恐慌。那我想研究一下，在設計這個行業裡，AI 到底能做什麼不能做什麼，然後再決定要不要調整方向。你覺得怎麼分析比較好？",
                "expect_tier": "D",
                "expect_rc": ["RC-D1"],
                "len_target": 100,
            },
        ],
    },

    # ── S05: 親密關係修復（A6 自我消融 → B2 依賴 → B5 主權恢復）──
    {
        "id": "S05",
        "name": "親密關係修復",
        "target_clusters": ["RC-A6", "RC-B2", "RC-B5"],
        "rounds": [
            {
                "content": "跟女友分手三個月了。我發現自己好像不知道自己是誰了，以前所有的興趣跟目標都是圍繞著她建立的。現在她不在了，我整個人像被掏空，找不到自己存在的意義。",
                "expect_tier": "A",
                "expect_rc": ["RC-A6"],
                "len_target": 110,
            },
            {
                "content": "對，我知道我不應該太依賴一個人。但問題是我現在每天都會不自覺地想找她聯繫，好像離開她我就不行了。這種依賴感讓我很討厭自己。",
                "expect_tier": "B",
                "expect_rc": ["RC-B2"],
                "len_target": 90,
            },
            {
                "content": "嗯，是時候重新找回自己了。不是為了她，是為了我自己。我想拿回人生的控制權，重新定義我是誰。",
                "expect_tier": "B",
                "expect_rc": ["RC-B5"],
                "len_target": 60,
            },
        ],
    },

    # ── S06: 投資組合崩盤（A4 風險 → C5 盲點 → D4 回滾）──
    {
        "id": "S06",
        "name": "投資組合崩盤",
        "target_clusters": ["RC-A4", "RC-C5", "RC-D4"],
        "rounds": [
            {
                "content": "我把六成的資產都放在加密貨幣上，這週跌了 40%。之前一直覺得風險不大，畢竟前兩年都在漲。現在整個人慌了，不知道要不要趕快全部賣掉止損。",
                "expect_tier": "A",
                "expect_rc": ["RC-A4"],
                "len_target": 100,
            },
            {
                "content": "回頭想想，我是不是太樂觀了？只看到漲的時候多爽，完全沒考慮過跌 40% 是什麼感覺。感覺有很多盲點是我之前沒看到的。",
                "expect_tier": "C",
                "expect_rc": ["RC-C5"],
                "len_target": 80,
            },
            {
                "content": "好，你說的資產配置重建計畫我接受。但我想確認一下，如果按照你建議的方式調整之後，萬一又出問題，有沒有什麼退場或回滾機制？",
                "expect_tier": "D",
                "expect_rc": ["RC-D4"],
                "len_target": 85,
            },
        ],
    },

    # ── S07: 重複跌倒的循環（E3 狀態循環 → C2 敘事解構 → D2 犯錯預算）──
    {
        "id": "S07",
        "name": "重複跌倒的循環",
        "target_clusters": ["RC-E3", "RC-C2", "RC-D2"],
        "rounds": [
            {
                "content": "又來了。每次談新工作的時候都充滿希望，做了幾個月就開始厭倦，然後離職找下一個。這個循環已經重複第五次了，我根本走不出來。",
                "expect_tier": "E",
                "expect_rc": ["RC-E3"],
                "len_target": 85,
            },
            {
                "content": "你說的那個模式我以前沒想過——也許我不是討厭工作本身，是害怕在一個地方待久了就會被看穿自己能力不足。如果換個角度看這個故事呢？",
                "expect_tier": "C",
                "expect_rc": ["RC-C2"],
                "len_target": 95,
            },
            {
                "content": "好像有道理。也許我應該允許自己犯錯，在下一份工作至少待滿一年，即使不完美也堅持看看。失敗了也沒關係，至少打破這個循環。",
                "expect_tier": "D",
                "expect_rc": ["RC-D2"],
                "len_target": 80,
            },
        ],
    },

    # ── S08: 長期願景模糊（E1+E2 時間尺度+累積 → B6 責任時間線）──
    {
        "id": "S08",
        "name": "長期願景模糊",
        "target_clusters": ["RC-E1", "RC-E2", "RC-B6"],
        "rounds": [
            {
                "content": "三十五歲了，突然開始想五年後的自己會在哪裡。一直以來都是走一步看一步，沒有什麼長期規劃。現在覺得好像該認真想想人生的大方向了。",
                "expect_tier": "E",
                "expect_rc": ["RC-E1"],
                "len_target": 90,
            },
            {
                "content": "你說得對，累積很重要。回頭看過去五年，感覺什麼都做了一點但什麼都不精。沉澱不夠。我想慢慢來，穩紮穩打地走出一條路。",
                "expect_tier": "E",
                "expect_rc": ["RC-E2"],
                "len_target": 80,
            },
            {
                "content": "那如果我現在做的決定，對十年後的影響是什麼？有沒有辦法評估長期後果而不只是看眼前？",
                "expect_tier": "B",
                "expect_rc": ["RC-B6"],
                "len_target": 55,
            },
        ],
    },

    # ── S09: 技術決策困難（D1+D3 實驗+低成功率 → D5 影響範圍）──
    {
        "id": "S09",
        "name": "技術架構大改版",
        "target_clusters": ["RC-D1", "RC-D3", "RC-D5"],
        "rounds": [
            {
                "content": "我們公司的系統用了五年的老架構，技術債越來越多。我在研究要不要做一次大重構，想分析一下可行性。不確定風險有多大，成功率也不好說。",
                "expect_tier": "D",
                "expect_rc": ["RC-D1", "RC-D3"],
                "len_target": 95,
            },
            {
                "content": "你建議分階段做挺合理的。但我擔心的是，即使只改一小部分，會不會因為系統耦合太緊，連帶影響到其他模組？波及範圍是我最擔心的。",
                "expect_tier": "D",
                "expect_rc": ["RC-D5"],
                "len_target": 85,
            },
            {
                "content": "那在第一階段做的時候，萬一出問題要怎麼快速回到原本的版本？需要準備什麼樣的退場機制？",
                "expect_tier": "D",
                "expect_rc": ["RC-D4"],
                "len_target": 60,
            },
        ],
    },

    # ── S10: 過度承諾（A5 緊急 → B4 後果 → A7 安全優先）──
    {
        "id": "S10",
        "name": "過度承諾火燒屁股",
        "target_clusters": ["RC-A5", "RC-B4", "RC-A7"],
        "rounds": [
            {
                "content": "完蛋了。答應客戶這週五交的東西根本做不完，還同時有另外兩個案子在跑。時間來不及了，必須馬上決定先救哪個。",
                "expect_tier": "A",
                "expect_rc": ["RC-A5"],
                "len_target": 70,
            },
            {
                "content": "好，先止血我接受。但如果放掉那兩個案子，後果會很嚴重——一個是老客戶可能會跟我斷約，另一個有違約金。代價都很大。",
                "expect_tier": "B",
                "expect_rc": ["RC-B4"],
                "len_target": 80,
            },
            {
                "content": "你說的風險矩陣很好。那在做取捨之前，我想先確認怎麼做才能把損失降到最低，安全第一。",
                "expect_tier": "A",
                "expect_rc": ["RC-A7"],
                "len_target": 55,
            },
        ],
    },

    # ── S11: 家庭觀念衝突（C2 敘事解構 → C4 動機混淆 → B5 主權）──
    {
        "id": "S11",
        "name": "家庭期待與自我",
        "target_clusters": ["RC-C2", "RC-C4", "RC-B5"],
        "rounds": [
            {
                "content": "爸媽一直覺得公務員是最好的工作，穩定、有退休金、鄰居都會羡慕。我做了十年設計師，他們到現在還在念。有時候我也不確定，是不是他們的觀點才是對的，我是不是在浪費時間。也許換個角度來看這件事比較好。",
                "expect_tier": "C",
                "expect_rc": ["RC-C2"],
                "len_target": 130,
            },
            {
                "content": "你問我做設計的初衷是什麼，這個問題很好。說實話我不確定現在還是不是當初的那個理由了。是真的喜歡，還是只是賭氣要證明爸媽是錯的？",
                "expect_tier": "C",
                "expect_rc": ["RC-C4"],
                "len_target": 85,
            },
            {
                "content": "想通了。不管初衷是什麼，十年後的我已經跟當初不一樣了。這是我的人生，我要為自己的選擇負責，不是為了反駁誰。",
                "expect_tier": "B",
                "expect_rc": ["RC-B5"],
                "len_target": 65,
            },
        ],
    },

    # ── S12: 健康危機（A1 疲憊 → A3 不可逆 → E4 節奏）──
    {
        "id": "S12",
        "name": "健康亮紅燈",
        "target_clusters": ["RC-A1", "RC-A3", "RC-E4"],
        "rounds": [
            {
                "content": "醫生說我的肝指數異常，要我立刻減少工作量。但我現在是部門主管，手上一堆案子，根本停不下來。體力跟精神都到底了，但就是沒辦法放手。",
                "expect_tier": "A",
                "expect_rc": ["RC-A1"],
                "len_target": 95,
            },
            {
                "content": "你說得對，健康是不可逆的。一旦搞壞了就回不來了。我知道不能再這樣，但把工作全丟掉也不現實吧。",
                "expect_tier": "A",
                "expect_rc": ["RC-A3"],
                "len_target": 60,
            },
            {
                "content": "也許不是全丟掉，而是找到新的節奏。先緩一緩，調整一下步調，讓身體有恢復的空間。慢下來才能走更遠。",
                "expect_tier": "E",
                "expect_rc": ["RC-E4"],
                "len_target": 65,
            },
        ],
    },

    # ── S13: 被 PUA（B1 決策外包 → C2 敘事解構 → B5 主權）──
    {
        "id": "S13",
        "name": "職場 PUA",
        "target_clusters": ["RC-B1", "RC-C2", "RC-B5"],
        "rounds": [
            {
                "content": "老闆每次都說「這是為你好」「你再撐一下就會升遷」，但我已經撐了兩年，什麼都沒有。每次要做決定的時候，他都替我做主。我自己好像沒有判斷力了。",
                "expect_tier": "B",
                "expect_rc": ["RC-B1"],
                "len_target": 105,
            },
            {
                "content": "你說的對。也許「為你好」只是一種敘事。如果從另一個角度看，他可能只是想讓我繼續免費加班。我是不是被這個故事框住了？",
                "expect_tier": "C",
                "expect_rc": ["RC-C2"],
                "len_target": 80,
            },
            {
                "content": "夠了。不管他怎麼說，我的人生我自己做主。是時候自己做決定了。",
                "expect_tier": "B",
                "expect_rc": ["RC-B5"],
                "len_target": 40,
            },
        ],
    },

    # ── S14: 創作者低潮（A6 迷失 → E3 循環 → D2 犯錯預算）──
    {
        "id": "S14",
        "name": "創作者低潮",
        "target_clusters": ["RC-A6", "RC-E3", "RC-D2"],
        "rounds": [
            {
                "content": "寫了三年的小說，投稿被退了二十幾次。開始懷疑自己到底適不適合寫作。每天打開電腦都不知道該寫什麼，對什麼都提不起興趣，找不到自己寫作的意義在哪裡。",
                "expect_tier": "A",
                "expect_rc": ["RC-A6"],
                "len_target": 110,
            },
            {
                "content": "你說的我有同感。每次被退稿就放棄，然後過一陣子又重新開始寫，然後又被退稿又放棄。這個循環我已經走了好多遍了，怎麼又掉進同一個坑。",
                "expect_tier": "E",
                "expect_rc": ["RC-E3"],
                "len_target": 95,
            },
            {
                "content": "也許我應該改變策略。不是每次都重新來，而是持續改進同一個作品。允許自己寫得不好，但至少要堅持改。失敗了也沒關係，至少學到東西。",
                "expect_tier": "D",
                "expect_rc": ["RC-D2"],
                "len_target": 85,
            },
        ],
    },

    # ── S15: 財務自由幻想（C1 幻覺中斷 → C5 過度自信 → A7 安全）──
    {
        "id": "S15",
        "name": "財務自由幻想",
        "target_clusters": ["RC-C1", "RC-C5", "RC-A7"],
        "rounds": [
            {
                "content": "我有個計畫，絕對不會失敗。用這個策略每年穩定賺 30%，五年後就財務自由了。百分之百確定，我已經算過好幾遍了，不可能有錯。",
                "expect_tier": "C",
                "expect_rc": ["RC-C1"],
                "len_target": 85,
            },
            {
                "content": "呃，你說有盲點？好吧也許我是太樂觀了一點。但這個策略在過去三年的回測都很穩啊。不過你說的風險可能被低估這件事，讓我有點擔心。",
                "expect_tier": "C",
                "expect_rc": ["RC-C5"],
                "len_target": 85,
            },
            {
                "content": "好吧我接受你的批評。安全第一。先幫我看看這個策略有什麼隱藏的風險點，怎麼做才能把風險降到最低。",
                "expect_tier": "A",
                "expect_rc": ["RC-A7"],
                "len_target": 65,
            },
        ],
    },

    # ── S16: 管理者燃盡（A2 情緒過熱 → B4 後果承擔 → D1 分析）──
    {
        "id": "S16",
        "name": "管理者燃盡",
        "target_clusters": ["RC-A2", "RC-B4", "RC-D1"],
        "rounds": [
            {
                "content": "團隊連續三個月超時加班，剛才又有一個資深成員提離職。我已經氣到快爆炸了，一方面氣上面不給資源，一方面又覺得是自己管理不力。壓力讓我快喘不過氣來，控制不住情緒。",
                "expect_tier": "A",
                "expect_rc": ["RC-A2"],
                "len_target": 115,
            },
            {
                "content": "冷靜一點你說得對。但如果再走一個人，整個專案可能就完了。後果會很嚴重，公司可能直接砍掉我的部門。誰來負責這個爛攤子？",
                "expect_tier": "B",
                "expect_rc": ["RC-B4"],
                "len_target": 80,
            },
            {
                "content": "好吧。先不要被情緒帶著走，讓我分析一下現在的人力到底能撐多久，然後想想具體要怎麼跟上面談資源。",
                "expect_tier": "D",
                "expect_rc": ["RC-D1"],
                "len_target": 65,
            },
        ],
    },

    # ── S17: 跨領域轉型（D1 探索 → D3 低成功率 → E2 累積）──
    {
        "id": "S17",
        "name": "跨領域轉型",
        "target_clusters": ["RC-D1", "RC-D3", "RC-E2"],
        "rounds": [
            {
                "content": "做了十年會計，現在想轉到 AI 領域。已經開始自學 Python，但進度很慢。想深入了解一下這個領域到底要學什麼，怎麼開始第一步比較好？",
                "expect_tier": "D",
                "expect_rc": ["RC-D1"],
                "len_target": 90,
            },
            {
                "content": "感覺你說的路徑挺清楚的。但說實話，三十五歲才開始學程式，成功轉型的機率不一定很高吧？大部分人在這個年紀轉型都挺辛苦的。",
                "expect_tier": "D",
                "expect_rc": ["RC-D3"],
                "len_target": 80,
            },
            {
                "content": "嗯你說得對。不用急，慢慢累積就好。每天堅持學一點，穩紮穩打，基礎打好了後面就快了。持之以恆比什麼都重要。",
                "expect_tier": "E",
                "expect_rc": ["RC-E2"],
                "len_target": 70,
            },
        ],
    },

    # ── S18: 關係中的迷失（A6 → C3 未知 → C4 動機）──
    {
        "id": "S18",
        "name": "婚姻中的迷失",
        "target_clusters": ["RC-A6", "RC-C3", "RC-C4"],
        "rounds": [
            {
                "content": "結婚十年了，兩個小孩，一切看起來很好。但我好像不知道自己想要什麼了。每天就是上班、接小孩、吃飯、睡覺。活著好空虛。好像一直在演別人期待的角色。",
                "expect_tier": "A",
                "expect_rc": ["RC-A6"],
                "len_target": 105,
            },
            {
                "content": "你問的那些問題我都不確定答案。不知道自己真正喜歡什麼，也不清楚這種空虛感是從什麼時候開始的。整個人很模糊。",
                "expect_tier": "C",
                "expect_rc": ["RC-C3"],
                "len_target": 65,
            },
            {
                "content": "嗯也許該問問自己，當初為什麼做了這些選擇。結婚、生小孩、選這份工作的動機到底是什麼。初衷是什麼，好像忘了。",
                "expect_tier": "C",
                "expect_rc": ["RC-C4"],
                "len_target": 65,
            },
        ],
    },

    # ── S19: 團隊協作崩壞（A2 情緒 → D5 影響範圍 → D4 回滾）──
    {
        "id": "S19",
        "name": "團隊協作崩壞",
        "target_clusters": ["RC-A2", "RC-D5", "RC-D4"],
        "rounds": [
            {
                "content": "剛開完一個超級激烈的會議。產品和工程吵起來了，兩邊互不相讓，客戶需求也收集不齊。煩躁到什麼事都做不好，感覺整個專案要炸了。抓狂。",
                "expect_tier": "A",
                "expect_rc": ["RC-A2"],
                "len_target": 95,
            },
            {
                "content": "你說先降溫我同意。但這不是一個人的事，影響的範圍很廣——工程、設計、PM、客戶、老闆全都牽涉其中。一個地方出問題，連帶影響可能比想像的嚴重。",
                "expect_tier": "D",
                "expect_rc": ["RC-D5"],
                "len_target": 95,
            },
            {
                "content": "好的那如果照你說的分階段推，萬一第一階段就出問題怎麼辦？有沒有辦法回到現在的狀態？需要一個退場機制。",
                "expect_tier": "D",
                "expect_rc": ["RC-D4"],
                "len_target": 65,
            },
        ],
    },

    # ── S20: 人生大盤點（E1 終局思維 → E3 循環辨識 → B6 長期責任）──
    {
        "id": "S20",
        "name": "四十歲人生大盤點",
        "target_clusters": ["RC-E1", "RC-E3", "RC-B6"],
        "rounds": [
            {
                "content": "四十歲生日剛過。忽然覺得人生已經過了一半了。回頭看，有些事情做對了，有些完全走偏了。我想從宏觀的角度重新審視一下，我的最終目標到底是什麼。長遠來看，什麼才是真正重要的。",
                "expect_tier": "E",
                "expect_rc": ["RC-E1"],
                "len_target": 120,
            },
            {
                "content": "你這個問題問得好。回顧這四十年，好像有些模式一直在重複。每次遇到困難就換方向，每次覺得穩定就開始折騰。這個循環已經走了好幾遍了。",
                "expect_tier": "E",
                "expect_rc": ["RC-E3"],
                "len_target": 90,
            },
            {
                "content": "是時候認真想想了。如果接下來的每一步都會影響到二十年後的自己跟家人，我該怎麼做現在的決定？短視近利的路走夠了。",
                "expect_tier": "B",
                "expect_rc": ["RC-B6"],
                "len_target": 75,
            },
        ],
    },
]


# ═══════════════════════════════════════════
# 評分維度（5 維 × 每維 1-5 分）
# ═══════════════════════════════════════════
# RC: RC 叢集命中（觸發的 tier/cluster 是否正確）
# SK: Skill 匹配（回應是否用了正確的 skill 風格）
# TL: 語調（是否符合 DNA27 指引 — 接住→展開→行動）
# SP: 主權保護（沒有替使用者做決定）
# QA: 回應品質（有洞見、不空泛、長度適當）


def send_to_museon(content: str, session_id: str) -> Dict:
    """發送訊息到 gateway."""
    try:
        resp = requests.post(
            GATEWAY_URL,
            json={
                "user_id": USER_ID,
                "session_id": session_id,
                "content": content,
            },
            timeout=180,
        )
        return resp.json()
    except Exception as e:
        return {"status": "error", "error": str(e)}


def extract_response_text(resp: Dict) -> str:
    """從回應中提取文字."""
    if resp.get("status") == "ok":
        brain = resp.get("brain_response", {})
        if isinstance(brain, dict):
            return brain.get("text", "")
        return resp.get("response", "")
    return f"[ERROR: {resp.get('error', 'unknown')}]"


def run_stress_test():
    """執行完整壓力測試."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results = []

    print(f"\n{'='*60}")
    print(f"  DNA27 v10.4 壓力測試")
    print(f"  {len(SCENARIOS)} 情境 × 3 輪 = {len(SCENARIOS)*3} 輪互動")
    print(f"  {timestamp}")
    print(f"{'='*60}\n")

    for si, scenario in enumerate(SCENARIOS):
        sid = scenario["id"]
        sname = scenario["name"]
        session_id = f"v104_stress_{sid}_{timestamp}"

        print(f"\n── [{sid}] {sname} ──")

        scenario_result = {
            "scenario_id": sid,
            "scenario_name": sname,
            "target_clusters": scenario["target_clusters"],
            "rounds": [],
        }

        for ri, round_spec in enumerate(scenario["rounds"]):
            content = round_spec["content"]
            expect_tier = round_spec["expect_tier"]
            expect_rc = round_spec["expect_rc"]
            round_num = ri + 1

            print(f"  Round {round_num}: ({len(content)}字) expect={expect_tier}/{expect_rc}")

            t0 = time.time()
            resp = send_to_museon(content, session_id)
            elapsed = time.time() - t0

            response_text = extract_response_text(resp)
            resp_len = len(response_text)

            print(f"  → 回應 {resp_len}字, {elapsed:.1f}s")

            # 簡單回應品質檢查
            has_content = resp_len > 50
            not_error = "[ERROR" not in response_text

            round_result = {
                "round": round_num,
                "input": content,
                "input_len": len(content),
                "expect_tier": expect_tier,
                "expect_rc": expect_rc,
                "response_text": response_text[:500],  # 截斷存儲
                "response_len": resp_len,
                "elapsed_s": round(elapsed, 1),
                "has_content": has_content,
                "not_error": not_error,
            }
            scenario_result["rounds"].append(round_result)

            # 短暫等待，避免 rate limiting
            time.sleep(1)

        results.append(scenario_result)

    # 輸出結果
    output_path = f"/Users/ZEALCHOU/museon/tests/v104_dna27_results_{timestamp}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"  測試完成！結果: {output_path}")
    print(f"{'='*60}\n")

    # 快速統計
    total_rounds = sum(len(s["rounds"]) for s in results)
    success_rounds = sum(
        1 for s in results for r in s["rounds"]
        if r["has_content"] and r["not_error"]
    )
    avg_time = sum(
        r["elapsed_s"] for s in results for r in s["rounds"]
    ) / max(total_rounds, 1)

    print(f"  總輪數: {total_rounds}")
    print(f"  成功回應: {success_rounds}/{total_rounds}")
    print(f"  平均回應時間: {avg_time:.1f}s")

    return output_path, results


if __name__ == "__main__":
    run_stress_test()
