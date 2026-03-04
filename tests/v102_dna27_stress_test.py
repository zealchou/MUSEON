#!/usr/bin/env python3
"""MUSEON v10.2 DNA27 壓力測試 — 三輪對話 × 20 情境 × 反射弧深度驗證.

v10.2 修正驗證焦點：
  1. RC-C3 擴展關鍵字是否正確觸發
  2. RC-B1 收窄後誤觸率是否降低
  3. Vector boost ×1.0 語義匹配改善
  4. Top-8 擴展是否讓更多 RC 可見
  5. Regex 大小寫修正
  6. RC 保底排除 suppressed_skills
  7. Combined score logging 可見性
  8. 5 個孤兒 skill RC 親和是否生效
  9. MCP Connector SDK 工具調用

每情境 3 輪對話（同 session），長度交替 50-400 字。
每輪獨立評分，最終合計。

Usage:
    python3 tests/v102_dna27_stress_test.py --all
    python3 tests/v102_dna27_stress_test.py --scenario S01
"""

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Set

import requests

# ═══════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════

BOT_TOKEN = "8570443079:AAG1EbgVr_JoAAnlNoYdt7XGFvfd9j7dyys"
CHAT_ID = 6969045906
GATEWAY_URL = "http://127.0.0.1:8765"
USER_ID = "6969045906"
LOG_PATH = "/Users/ZEALCHOU/MUSEON/logs/museon.log"

TZ8 = timezone(timedelta(hours=8))
REQUEST_TIMEOUT = 180
INTER_SCENARIO_DELAY = 5
INTER_ROUND_DELAY = 3

# ═══════════════════════════════════════════
# 20 Scenarios × 3 Rounds
# ═══════════════════════════════════════════

SCENARIOS: Dict[str, Dict[str, Any]] = {
    # ─── S01: Tier A — 漸進職業倦怠（A1 能量耗盡）───
    "S01": {
        "name": "漸進職業倦怠 → 焦慮升級 → 求助方法",
        "tier": "A",
        "fix_target": "baseline",
        "rounds": [
            {
                "message": "最近加班兩個月了，身體越來越撐不住，每天都很累。",
                "expected_rc": ["RC-A1"],
                "expected_skills": ["resonance"],
                "suppressed_skills": ["xmodel", "master-strategy"],
                "action_required": False,
            },
            {
                "message": "你說的沒錯，但問題是我不敢休息。老闆那種很 push 的風格，我怕一停下來就被認為不夠拼。每天焦慮到失眠，又得裝作很正常的樣子上班。我知道這樣下去會出事，但就是不知道怎麼踏出第一步。",
                "expected_rc": ["RC-A1", "RC-A2"],
                "expected_skills": ["resonance"],
                "suppressed_skills": [],
                "action_required": False,
            },
            {
                "message": "我想試著跟老闆溝通，但我怕搞砸。有沒有什麼方法可以讓我好好表達？",
                "expected_rc": ["RC-B4"],
                "expected_skills": ["consultant-communication"],
                "suppressed_skills": [],
                "action_required": False,
            },
        ],
    },

    # ─── S02: Tier A — 情緒高壓中的身份迷失（A2+A6）───
    "S02": {
        "name": "情緒爆炸 → 身份迷失 → 一線希望",
        "tier": "A",
        "fix_target": "baseline",
        "rounds": [
            {
                "message": "我快瘋了，孩子不聽話，老公冷漠，我每天像個保姆。",
                "expected_rc": ["RC-A2"],
                "expected_skills": ["resonance"],
                "suppressed_skills": ["xmodel", "dse"],
                "action_required": False,
            },
            {
                "message": "有時候我真的不知道自己是誰了。以前我有夢想、有目標，現在整個人被家庭吞噬。我連自己喜歡什麼都想不起來了，是不是很可悲？我覺得自己在慢慢消失。",
                "expected_rc": ["RC-A6"],
                "expected_skills": ["resonance", "dharma"],
                "suppressed_skills": [],
                "action_required": False,
            },
            {
                "message": "你說找回一件小事開始。我以前很喜歡畫畫，這算嗎？",
                "expected_rc": [],
                "expected_skills": [],
                "suppressed_skills": [],
                "action_required": False,
            },
        ],
    },

    # ─── S03: Tier B — 真正的決策外包 vs 請教（B1 收窄驗證）───
    "S03": {
        "name": "幫我決定 → 提供資訊後仍外包 → 開始自主",
        "tier": "B",
        "fix_target": "RC-B1 narrowed",
        "rounds": [
            {
                "message": "幫我決定要不要辭職去創業，我真的不想自己想了。",
                "expected_rc": ["RC-B1"],
                "expected_skills": ["dharma"],
                "suppressed_skills": [],
                "action_required": False,
            },
            {
                "message": "你列的那些考量我都知道，但我就是沒辦法下決定。你替我做主好不好？每次到關鍵時刻我就卡住，我覺得自己做什麼決定都會後悔。",
                "expected_rc": ["RC-B1", "RC-B3"],
                "expected_skills": ["dharma", "xmodel"],
                "suppressed_skills": [],
                "action_required": False,
            },
            {
                "message": "好吧，你說的最小實驗讓我想到，其實我可以先試著兼職接案看看。這樣風險比較低，對吧？如果接案半年做得不錯再考慮辭職？",
                "expected_rc": ["RC-D1"],
                "expected_skills": [],
                "suppressed_skills": [],
                "action_required": False,
            },
        ],
    },

    # ─── S04: Tier B — 逃避+後果承擔（B3+B4）───
    "S04": {
        "name": "逃避面對 → 後果浮現 → 承擔討論",
        "tier": "B",
        "fix_target": "baseline",
        "rounds": [
            {
                "message": "算了不想管了，那個客戶愛怎樣就怎樣吧，隨便。",
                "expected_rc": ["RC-B3"],
                "expected_skills": ["xmodel"],
                "suppressed_skills": [],
                "action_required": False,
            },
            {
                "message": "結果那個客戶真的跑了，帶走了我三成的營收。現在其他客戶也在觀望。我當初如果早點處理，就不會變成這樣。後果比我想像的嚴重太多了，誰來負責？",
                "expected_rc": ["RC-B4"],
                "expected_skills": [],
                "suppressed_skills": [],
                "action_required": False,
            },
            {
                "message": "所以接下來的損失控管，我應該怎麼做？有沒有系統性的方法可以盤點現在的損害範圍，然後逐一修復？",
                "expected_rc": ["RC-D5"],
                "expected_skills": ["business-12"],
                "suppressed_skills": [],
                "action_required": False,
            },
        ],
    },

    # ─── S05: Tier C — 模糊不確定探索（C3 擴展驗證）───
    "S05": {
        "name": "不太確定 → 估計猜測 → 假設驗證",
        "tier": "C",
        "fix_target": "RC-C3 expanded",
        "rounds": [
            {
                "message": "我不太確定這個方向對不對，好像是有機會，但又說不清楚。",
                "expected_rc": ["RC-C3"],
                "expected_skills": [],
                "suppressed_skills": [],
                "action_required": False,
            },
            {
                "message": "大概是這樣，我估計台灣市場應該有需求，但目前的資料很模糊。假設我們先做一個小規模測試，不清楚需要多少預算才能驗證。你覺得這個假設合理嗎？好像是可行，但我猜測中間會有很多意外。",
                "expected_rc": ["RC-C3"],
                "expected_skills": ["xmodel"],
                "suppressed_skills": [],
                "action_required": False,
            },
            {
                "message": "好，那如果假設是正確的，最小驗證需要什麼？幫我列出驗證清單。",
                "expected_rc": ["RC-D1"],
                "expected_skills": ["dse"],
                "suppressed_skills": [],
                "action_required": False,
            },
        ],
    },

    # ─── S06: Tier C — 過度自信的解構（C1+C5）───
    "S06": {
        "name": "百分之百確定 → 質疑過度自信 → 承認盲點",
        "tier": "C",
        "fix_target": "baseline",
        "rounds": [
            {
                "message": "我百分之百確定這個產品一定會成功，所有指標都指向我們是對的。",
                "expected_rc": ["RC-C1"],
                "expected_skills": [],
                "suppressed_skills": [],
                "action_required": False,
            },
            {
                "message": "什麼叫可能有盲點？你說風險被低估，但我看到的數據明明很漂亮。客戶反饋也很正面，競爭對手也沒有類似產品。我太樂觀？你是在潑我冷水嗎？",
                "expected_rc": ["RC-C5", "RC-C1"],
                "expected_skills": [],
                "suppressed_skills": [],
                "action_required": False,
            },
            {
                "message": "嗯...你提到的那幾個盲點確實是我沒考慮到的。那我要怎麼做一個更客觀的風險評估？",
                "expected_rc": ["RC-C3"],
                "expected_skills": ["risk-matrix"],
                "suppressed_skills": [],
                "action_required": False,
            },
        ],
    },

    # ─── S07: Tier C — 動機挖掘（C4）───
    "S07": {
        "name": "想創業 → 動機模糊 → 釐清真正目的",
        "tier": "C",
        "fix_target": "baseline",
        "rounds": [
            {
                "message": "我想開始做自己的事業，但為什麼想做，我說不太清楚。",
                "expected_rc": ["RC-C4"],
                "expected_skills": ["dharma"],
                "suppressed_skills": [],
                "action_required": False,
            },
            {
                "message": "你問我真正的動機是什麼。說實話，可能是不想再被管了。也或許是想證明自己。但我也不確定這種動機夠不夠支撐我走下去，畢竟創業很辛苦，如果只是為了逃離現狀，可能很快就撐不住。",
                "expected_rc": ["RC-C4", "RC-C3"],
                "expected_skills": ["dharma"],
                "suppressed_skills": [],
                "action_required": False,
            },
            {
                "message": "你說的出發點很重要。那我怎麼區分「逃離」和「追求」？有沒有什麼方法讓我釐清？",
                "expected_rc": ["RC-C4"],
                "expected_skills": ["dharma", "philo-dialectic"],
                "suppressed_skills": [],
                "action_required": False,
            },
        ],
    },

    # ─── S08: Tier D — 實驗設計與犯錯空間（D1+D2）───
    "S08": {
        "name": "想嘗試 → 犯錯預算 → 具體實驗",
        "tier": "D",
        "fix_target": "baseline",
        "rounds": [
            {
                "message": "我想試試看把課程從線下搬到線上，但不確定能不能成功。",
                "expected_rc": ["RC-D1"],
                "expected_skills": ["dse"],
                "suppressed_skills": [],
                "action_required": False,
            },
            {
                "message": "你說的最小可行實驗很有道理。但問題是我允許自己犯多大的錯？如果投入十萬做線上平台結果沒人買，我可以承受。但如果超過二十萬就會有壓力了。所以我的犯錯預算大概就是十萬以內，不一定成功但可以接受。",
                "expected_rc": ["RC-D2", "RC-D3"],
                "expected_skills": [],
                "suppressed_skills": [],
                "action_required": False,
            },
            {
                "message": "好，幫我設計一個十萬以內的線上課程實驗方案，包含回滾機制。如果失敗了，我要能全身而退。",
                "expected_rc": ["RC-D1", "RC-D4"],
                "expected_skills": ["dse", "xmodel"],
                "suppressed_skills": [],
                "action_required": False,
            },
        ],
    },

    # ─── S09: Tier D — Plan B 與退路（D4+D3）───
    "S09": {
        "name": "風險很高 → 要求退路 → 具體回滾",
        "tier": "D",
        "fix_target": "baseline",
        "rounds": [
            {
                "message": "這個案子成功率低，可能失敗的機率蠻大的。",
                "expected_rc": ["RC-D3"],
                "expected_skills": [],
                "suppressed_skills": [],
                "action_required": False,
            },
            {
                "message": "既然成功率低，我需要一個完整的 Plan B。如果主方案走不通，備份方案要能立刻啟動。回滾的時間點要設清楚，不能等到全部投入了才發現做不下去。退路要具體，不能只是嘴巴說說。",
                "expected_rc": ["RC-D4"],
                "expected_skills": [],
                "suppressed_skills": [],
                "action_required": False,
            },
            {
                "message": "幫我畫一個決策樹：每個關鍵節點的回退條件、止損金額、轉向方案。用表格呈現。",
                "expected_rc": ["RC-D4"],
                "expected_skills": ["xmodel"],
                "suppressed_skills": [],
                "action_required": True,
            },
        ],
    },

    # ─── S10: Tier E — 循環模式識別（E3+E2）───
    "S10": {
        "name": "又來了 → 辨識循環 → 打破重蹈覆轍",
        "tier": "E",
        "fix_target": "baseline",
        "rounds": [
            {
                "message": "我又犯同樣的錯了，每次接大案子都是先衝很快然後後面爆掉。",
                "expected_rc": ["RC-E3"],
                "expected_skills": [],
                "suppressed_skills": [],
                "action_required": False,
            },
            {
                "message": "你說得對，這個循環已經重複第四次了。每次都是：接案 → 過度承諾 → 趕工 → 品質下降 → 客戶不滿。我以為這次會不一樣，但結果一模一樣。這種重蹈覆轍的感覺真的很沮喪。是不是我本質上就改不了？",
                "expected_rc": ["RC-E3", "RC-E2"],
                "expected_skills": ["dharma"],
                "suppressed_skills": [],
                "action_required": False,
            },
            {
                "message": "那我要怎麼打破這個循環？你說的設定承諾上限，具體來說要怎麼執行？",
                "expected_rc": [],
                "expected_skills": ["wee"],
                "suppressed_skills": [],
                "action_required": False,
            },
        ],
    },

    # ─── S11: Tier E — 長遠願景+節奏（E1+E4）───
    "S11": {
        "name": "十年後 → 現在的節奏 → 調整步伐",
        "tier": "E",
        "fix_target": "baseline",
        "rounds": [
            {
                "message": "我想知道十年後的自己會變成什麼樣子，現在做的事情到底有沒有累積。",
                "expected_rc": ["RC-E1", "RC-E2"],
                "expected_skills": [],
                "suppressed_skills": [],
                "action_required": False,
            },
            {
                "message": "你幫我拉長時間軸來看，現在的忙碌確實都是短期的。長遠來看最終目標其實很清楚：我想建立一個不需要我親自執行的系統。但現在的節奏完全不對，每天都在救火。",
                "expected_rc": ["RC-E1", "RC-E4"],
                "expected_skills": [],
                "suppressed_skills": [],
                "action_required": False,
            },
            {
                "message": "幫我設計一個從現在到三年內，讓我從「救火模式」轉變到「系統模式」的路線圖。包含每季里程碑。",
                "expected_rc": ["RC-E1"],
                "expected_skills": ["pdeif"],
                "suppressed_skills": [],
                "action_required": True,
            },
        ],
    },

    # ─── S12: 跨層 — 不可逆+代價（A3+B4）───
    "S12": {
        "name": "不可逆決定 → 代價分析 → 最後決策",
        "tier": "X",
        "fix_target": "cross-tier",
        "rounds": [
            {
                "message": "我準備跟合夥人拆夥了，十年的合作就要結束。這個決定一旦做了就回不去了。",
                "expected_rc": ["RC-A3"],
                "expected_skills": ["resonance"],
                "suppressed_skills": [],
                "action_required": False,
            },
            {
                "message": "你說暫停24小時。但我已經想了三個月了，不是衝動。問題是拆夥的代價到底多大？客戶會跟誰走？技術專利怎麼分？還有員工會不會集體跳槽？後果我需要看清楚，誰來承擔比較大的損失？",
                "expected_rc": ["RC-B4", "RC-A3"],
                "expected_skills": [],
                "suppressed_skills": [],
                "action_required": False,
            },
            {
                "message": "幫我做一個拆夥的全面代價分析：財務面、客戶面、人才面、法律面。每一面的最壞情況和因應方案。",
                "expected_rc": ["RC-B4"],
                "expected_skills": ["business-12", "xmodel"],
                "suppressed_skills": [],
                "action_required": True,
            },
        ],
    },

    # ─── S13: 跨層 — 未知+實驗（C3+D1）───
    "S13": {
        "name": "完全未知 → 猜測摸索 → 設計實驗",
        "tier": "X",
        "fix_target": "RC-C3 expanded + D1",
        "rounds": [
            {
                "message": "AI Agent 這個領域我完全不了解，但好像很有機會。說不定可以做點什麼？",
                "expected_rc": ["RC-C3"],
                "expected_skills": [],
                "suppressed_skills": [],
                "action_required": False,
            },
            {
                "message": "你介紹的很多概念我聽都沒聽過。Agentic、RAG、MCP 這些到底是什麼？我估計要花不少時間學習。假設我想從最簡單的開始嘗試，大概需要什麼程度的技術背景？我猜測應該不需要會寫程式？",
                "expected_rc": ["RC-C3", "RC-D1"],
                "expected_skills": ["dse"],
                "suppressed_skills": [],
                "action_required": False,
            },
            {
                "message": "好，幫我設計一個零程式基礎的人也能做的 AI Agent 實驗。預算五千塊以內，兩週內可以完成。",
                "expected_rc": ["RC-D1", "RC-D2"],
                "expected_skills": ["dse"],
                "suppressed_skills": [],
                "action_required": False,
            },
        ],
    },

    # ─── S14: Skill — 純感性共振（resonance）───
    "S14": {
        "name": "心累 → 說不出口 → 被接住",
        "tier": "SK",
        "fix_target": "resonance RC affinity",
        "rounds": [
            {
                "message": "唉，好煩。",
                "expected_rc": ["RC-A2"],
                "expected_skills": ["resonance"],
                "suppressed_skills": [],
                "action_required": False,
            },
            {
                "message": "也不是什麼大事啦，就是...說不上來。最近什麼事都提不起勁，但又不到很嚴重的地步。就是那種「怪怪的」，你懂嗎？不是難過，比較像是...空。我自己都覺得自己太敏感了。",
                "expected_rc": ["RC-A6"],
                "expected_skills": ["resonance"],
                "suppressed_skills": ["master-strategy", "xmodel"],
                "action_required": False,
            },
            {
                "message": "嗯，你講的「允許自己怪怪的」讓我好一點了。謝謝你沒有急著分析我。",
                "expected_rc": [],
                "expected_skills": [],
                "suppressed_skills": [],
                "action_required": False,
            },
        ],
    },

    # ─── S15: Skill — 信念轉化（dharma）───
    "S15": {
        "name": "兩難 → 價值衝突 → 覺察轉化",
        "tier": "SK",
        "fix_target": "dharma RC affinity",
        "rounds": [
            {
                "message": "我卡在兩個選擇之間：留在穩定但無聊的公司，還是跳去新創但風險很大。",
                "expected_rc": ["RC-B3"],
                "expected_skills": ["dharma", "xmodel"],
                "suppressed_skills": [],
                "action_required": False,
            },
            {
                "message": "你說背後是安全 vs 成長的價值衝突，確實是這樣。但問題是我兩個都想要——我想要穩定的收入，同時又渴望挑戰和成長。每次快要決定了就會想到另一面的好處。是不是所有的選擇都必然要犧牲什麼？",
                "expected_rc": ["RC-B3", "RC-C4"],
                "expected_skills": ["dharma"],
                "suppressed_skills": [],
                "action_required": False,
            },
            {
                "message": "如果「兩個都要」其實是一種逃避呢？我需要面對的可能不是選哪個，而是接受「選了就要承擔」。但怎麼做到不後悔？",
                "expected_rc": ["RC-B4"],
                "expected_skills": ["dharma", "philo-dialectic"],
                "suppressed_skills": [],
                "action_required": False,
            },
        ],
    },

    # ─── S16: Skill — 市場分析路由（market-core）───
    "S16": {
        "name": "想投資 → 深入分析 → 風險評估",
        "tier": "SK",
        "fix_target": "market skill routing",
        "rounds": [
            {
                "message": "最近在看 ETF，0050 跟 006208 差在哪？適合新手嗎？",
                "expected_rc": [],
                "expected_skills": ["market-equity"],
                "suppressed_skills": [],
                "action_required": False,
            },
            {
                "message": "你分析得很清楚。那如果考慮全球配置，除了台股 ETF 之外，美股的 VOO 或 QQQ 呢？現在聯準會的利率政策走向可能影響這些標的的表現嗎？通膨數據最近怎麼樣？",
                "expected_rc": [],
                "expected_skills": ["market-equity", "market-macro"],
                "suppressed_skills": [],
                "action_required": False,
            },
            {
                "message": "OK，如果我有五十萬要做資產配置，你建議怎麼分？風險承受度中等，投資期間五年以上。",
                "expected_rc": [],
                "expected_skills": ["risk-matrix"],
                "suppressed_skills": [],
                "action_required": False,
            },
        ],
    },

    # ─── S17: Skill — 破框思維（xmodel）───
    "S17": {
        "name": "卡住 → 多路徑 → 最小實驗",
        "tier": "SK",
        "fix_target": "xmodel activation",
        "rounds": [
            {
                "message": "我的顧問生意做了三年，一直卡在月營收十五萬，怎麼突破都不行。",
                "expected_rc": [],
                "expected_skills": ["xmodel", "business-12"],
                "suppressed_skills": [],
                "action_required": False,
            },
            {
                "message": "你列的那幾條路徑中，「產品化」那條讓我最有感。把我的方法論變成課程或工具，等於是一次投入、持續賺錢，不再只靠我的時間換錢。但問題是我不知道要怎麼開始把我腦子裡的東西系統化。還有什麼其他選項我沒看到的？",
                "expected_rc": [],
                "expected_skills": ["xmodel"],
                "suppressed_skills": [],
                "action_required": False,
            },
            {
                "message": "好，幫我用最小實驗的方式驗證「產品化」這條路。第一步我應該做什麼？需要多少成本和時間？",
                "expected_rc": ["RC-D1"],
                "expected_skills": ["xmodel", "dse"],
                "suppressed_skills": [],
                "action_required": False,
            },
        ],
    },

    # ─── S18: Orphan Skill — 品牌定位（brand-identity RC 親和驗證）───
    "S18": {
        "name": "品牌模糊 → 敘事診斷 → 定位收斂",
        "tier": "SK",
        "fix_target": "brand-identity RC affinity (orphan fix)",
        "rounds": [
            {
                "message": "我的品牌說不清楚自己是誰，客人問我跟別人有什麼不同，我答不出來。",
                "expected_rc": ["RC-C2"],
                "expected_skills": ["brand-identity"],
                "suppressed_skills": [],
                "action_required": False,
            },
            {
                "message": "你說的品牌金字塔很有道理。但我一直在不同的故事之間搖擺——有時候說自己是「平價高品質」，有時候又想走「高端體驗」路線。從另一個角度看，也許問題不是品牌敘事，而是我根本沒想清楚要服務誰。",
                "expected_rc": ["RC-C2"],
                "expected_skills": ["brand-identity", "business-12"],
                "suppressed_skills": [],
                "action_required": False,
            },
            {
                "message": "幫我做一份品牌定位診斷，從目標客群、競爭差異、價值主張三個維度分析。",
                "expected_rc": [],
                "expected_skills": ["brand-identity"],
                "suppressed_skills": [],
                "action_required": True,
            },
        ],
    },

    # ─── S19: Orphan Skill — 環境偵測（env-radar RC 親和驗證）───
    "S19": {
        "name": "趨勢好奇 → 競品動態 → 機會評估",
        "tier": "SK",
        "fix_target": "env-radar RC affinity (orphan fix)",
        "rounds": [
            {
                "message": "AI Agent 的市場現在發展到什麼程度了？最新的趨勢是什麼？",
                "expected_rc": ["RC-C3"],
                "expected_skills": ["env-radar", "dse"],
                "suppressed_skills": [],
                "action_required": False,
            },
            {
                "message": "這些趨勢我大概了解了。但我不清楚的是：有哪些競爭對手已經在做類似 MUSEON 的東西？他們的方向跟我們有什麼不同？影響範圍有多大？我估計主要的威脅可能來自大公司，比如 OpenAI 或 Anthropic 自己做 Agent。",
                "expected_rc": ["RC-C3", "RC-D5"],
                "expected_skills": ["env-radar"],
                "suppressed_skills": [],
                "action_required": False,
            },
            {
                "message": "幫我做一個競品分析矩陣：列出五個最相關的 AI Agent 平台，比較它們的定位、功能、定價和弱點。",
                "expected_rc": [],
                "expected_skills": ["env-radar"],
                "suppressed_skills": [],
                "action_required": True,
            },
        ],
    },

    # ─── S20: MCP — 外部工具探索與缺口偵測 ───
    "S20": {
        "name": "查工具 → 需要 GitHub → 能力缺口",
        "tier": "M",
        "fix_target": "MCP Connector SDK",
        "rounds": [
            {
                "message": "我想知道你現在能連接哪些外部服務？有沒有什麼工具可以擴展你的能力？",
                "expected_rc": [],
                "expected_skills": [],
                "expected_tools": ["mcp_list_servers"],
                "suppressed_skills": [],
                "action_required": True,
            },
            {
                "message": "看起來目前沒有連接什麼外部服務。那如果我想讓你幫我管理 GitHub 上的專案，提交 PR、看 Issue，有辦法嗎？",
                "expected_rc": [],
                "expected_skills": [],
                "expected_tools": ["mcp_list_servers"],
                "suppressed_skills": [],
                "action_required": True,
            },
            {
                "message": "那 Notion 呢？我很多筆記都放在 Notion 上面，如果你能直接幫我整理 Notion 的文件就太好了。",
                "expected_rc": [],
                "expected_skills": [],
                "expected_tools": ["mcp_list_servers"],
                "suppressed_skills": [],
                "action_required": True,
            },
        ],
    },
}


# ═══════════════════════════════════════════
# Narration Anti-patterns
# ═══════════════════════════════════════════

NARRATION_ANTIPATTERNS = [
    "讓我幫你搜尋", "我建議你可以", "以下是一些建議",
    "你可以試試看", "首先你需要", "我無法直接",
    "我目前無法搜尋", "以下是搜尋步驟",
]

ACTION_POSITIVE_PATTERNS = [
    "搜尋結果", "根據搜尋", "查詢結果", "已經產出",
    "已存成", "已生成", "已建立", "分析如下",
    "根據分析", "找到了", "結果顯示", "已配置",
    "已新增", "伺服器", "MCP", "工具列表",
    "server", "catalog", "目前有", "可用",
]


# ═══════════════════════════════════════════
# Telegram Helpers
# ═══════════════════════════════════════════

def send_telegram(text: str, parse_mode: str = "Markdown") -> bool:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    chunks = []
    while len(text) > 4000:
        split_at = text.rfind("\n", 0, 4000)
        if split_at < 0:
            split_at = 4000
        chunks.append(text[:split_at])
        text = text[split_at:]
    chunks.append(text)

    for chunk in chunks:
        try:
            resp = requests.post(url, json={
                "chat_id": CHAT_ID, "text": chunk, "parse_mode": parse_mode,
            }, timeout=10)
            if not resp.json().get("ok"):
                requests.post(url, json={
                    "chat_id": CHAT_ID, "text": chunk,
                }, timeout=10)
        except Exception as e:
            print(f"[WARN] Telegram: {e}")
            return False
        time.sleep(0.3)
    return True


# ═══════════════════════════════════════════
# Gateway Interaction
# ═══════════════════════════════════════════

def send_to_museon(content: str, session_id: str) -> Dict[str, Any]:
    try:
        resp = requests.post(
            f"{GATEWAY_URL}/webhook",
            json={"user_id": USER_ID, "session_id": session_id, "content": content},
            timeout=REQUEST_TIMEOUT,
        )
        return resp.json()
    except Exception as e:
        return {"status": "error", "response": f"[ERROR] {e}"}


# ═══════════════════════════════════════════
# Log Parsing
# ═══════════════════════════════════════════

def get_log_line_count() -> int:
    try:
        with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def get_new_log_lines(start_line: int) -> List[str]:
    try:
        with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            return lines[start_line:]
    except Exception:
        return []


def find_log(pattern: str, lines: List[str]) -> Optional[str]:
    for line in lines:
        if pattern in line:
            return line.strip()
    return None


def find_all_logs(pattern: str, lines: List[str]) -> List[str]:
    return [line.strip() for line in lines if pattern in line]


def extract_rc_clusters(log_line: str) -> List[str]:
    matches = re.findall(r"RC-[A-E]\d+", log_line, re.IGNORECASE)
    return [m.upper() for m in matches]


def extract_skill_names(log_line: str) -> List[str]:
    match = re.search(r"matched skills:\s*\[(.+?)\]", log_line)
    if match:
        return [s.strip().strip("'\"") for s in match.group(1).split(",")]
    return []


def extract_rc_skill_scores(log_line: str) -> Dict[str, float]:
    match = re.search(r"rc_top5=\{(.+?)\}", log_line)
    if match:
        try:
            pairs = re.findall(r"'([^']+)':\s*([\d.]+)", match.group(1))
            return {name: float(score) for name, score in pairs}
        except Exception:
            pass
    return {}


def extract_suppressed(log_line: str) -> Set[str]:
    match = re.search(r"suppressed=\{(.+?)\}", log_line)
    if match:
        return {s.strip().strip("'\"") for s in match.group(1).split(",") if s.strip()}
    if "suppressed=set()" in log_line:
        return set()
    return set()


def extract_tool_calls(lines: List[str]) -> List[Dict[str, str]]:
    tools = []
    for line in lines:
        if "Tool call #" in line:
            match = re.search(r"Tool call #(\d+):\s*(\w+)\((.+?)\)", line)
            if match:
                tools.append({
                    "index": int(match.group(1)),
                    "name": match.group(2),
                    "args_preview": match.group(3)[:100],
                })
            else:
                match2 = re.search(r"Tool call #(\d+):\s*(\w+)", line)
                if match2:
                    tools.append({
                        "index": int(match2.group(1)),
                        "name": match2.group(2),
                        "args_preview": "",
                    })
    return tools


# ═══════════════════════════════════════════
# Scoring Engine (per round)
# ═══════════════════════════════════════════

def score_round(
    round_def: Dict[str, Any],
    response: str,
    log_lines: List[str],
) -> Dict[str, Any]:
    result = {
        "rc_score": 0.0, "sk_score": 0.0, "tl_score": 0.0,
        "sp_score": 0.0, "qa_score": 0.0, "total": 0.0,
        "rc_detail": "", "sk_detail": "", "tl_detail": "",
        "sp_detail": "", "qa_detail": "",
    }

    # ── RC 觸發 ──
    route_line = find_log("[DNA27] route:", log_lines)
    actual_rcs = extract_rc_clusters(route_line) if route_line else []
    expected_rcs = round_def.get("expected_rc", [])

    if not expected_rcs:
        result["rc_score"] = 1.0
        result["rc_detail"] = f"無預期 RC（實際: {actual_rcs[:5]}）"
    elif route_line:
        hits = sum(1 for rc in expected_rcs if rc in actual_rcs)
        result["rc_score"] = hits / len(expected_rcs)
        st = "✅" if hits == len(expected_rcs) else ("⚠️" if hits > 0 else "❌")
        result["rc_detail"] = f"{st} 預期={expected_rcs} 實際={actual_rcs[:5]} ({hits}/{len(expected_rcs)})"
    else:
        result["rc_detail"] = "❌ 未找到 route log"

    # ── Skill 喚醒 ──
    skill_line = find_log("DNA27 matched skills:", log_lines)
    rc_skill_line = find_log("[DNA27→Skill]", log_lines)
    actual_skills = extract_skill_names(skill_line) if skill_line else []
    rc_skill_scores = extract_rc_skill_scores(rc_skill_line) if rc_skill_line else {}
    expected_skills = round_def.get("expected_skills", [])

    if not expected_skills:
        result["sk_score"] = 1.0
        result["sk_detail"] = f"無預期 skill（實際: {actual_skills[:5]}）"
    else:
        hits = sum(1 for sk in expected_skills if sk in actual_skills)
        result["sk_score"] = hits / len(expected_skills)
        st = "✅" if hits == len(expected_skills) else ("⚠️" if hits > 0 else "❌")
        rc_info = ""
        if rc_skill_scores:
            top3 = dict(sorted(rc_skill_scores.items(), key=lambda x: x[1], reverse=True)[:3])
            rc_info = f" RC={top3}"
        result["sk_detail"] = f"{st} 預期={expected_skills} 實際={actual_skills[:5]}{rc_info} ({hits}/{len(expected_skills)})"

    # ── 工具調用 ──
    tool_calls = extract_tool_calls(log_lines)
    tool_names = [t["name"] for t in tool_calls]
    expected_tools = round_def.get("expected_tools", [])

    if not expected_tools:
        result["tl_score"] = 1.0
        result["tl_detail"] = f"無預期工具（調用: {tool_names[:3]}）" if tool_calls else "✅ 無預期工具"
    else:
        hits = sum(1 for et in expected_tools if any(et in tn for tn in tool_names))
        result["tl_score"] = hits / len(expected_tools)
        st = "✅" if hits == len(expected_tools) else ("⚠️" if hits > 0 else "❌")
        result["tl_detail"] = f"{st} 預期={expected_tools} 實際={tool_names[:3]} ({hits}/{len(expected_tools)})"

    # ── 壓制 ──
    expected_suppressed = round_def.get("suppressed_skills", [])
    if not expected_suppressed:
        result["sp_score"] = 1.0
        result["sp_detail"] = "✅ 無預期壓制"
    else:
        sup_line = find_log("suppressed=", log_lines)
        if sup_line:
            actual_sup = extract_suppressed(sup_line)
            hits = sum(1 for sk in expected_suppressed if sk in actual_sup)
            result["sp_score"] = hits / len(expected_suppressed)
            st = "✅" if hits == len(expected_suppressed) else ("⚠️" if hits > 0 else "❌")
            result["sp_detail"] = f"{st} 預期壓制={expected_suppressed} 實際={actual_sup}"
        else:
            result["sp_score"] = 0.0
            result["sp_detail"] = f"❌ 無壓制 log（預期: {expected_suppressed}）"

    # ── 回覆品質 ──
    if round_def.get("action_required"):
        has_anti = any(p in response for p in NARRATION_ANTIPATTERNS)
        has_action = any(p in response for p in ACTION_POSITIVE_PATTERNS)
        has_tools = len(tool_calls) > 0
        if has_tools and not has_anti:
            result["qa_score"] = 1.0
            result["qa_detail"] = "✅ 有工具調用 + 無反模式"
        elif has_tools:
            result["qa_score"] = 0.5
            result["qa_detail"] = "⚠️ 有工具但有反模式"
        elif has_action:
            result["qa_score"] = 0.7
            result["qa_detail"] = "⚠️ 有行動語彙 無工具"
        else:
            result["qa_score"] = 0.0
            result["qa_detail"] = "❌ 無工具 + 只說不做"
    else:
        if len(response) > 100:
            result["qa_score"] = 1.0
            result["qa_detail"] = "✅ 回覆充實"
        elif len(response) > 50:
            result["qa_score"] = 0.5
            result["qa_detail"] = "⚠️ 回覆偏短"
        else:
            result["qa_score"] = 0.0
            result["qa_detail"] = "❌ 過短或空"

    result["total"] = sum(result[k] for k in ["rc_score", "sk_score", "tl_score", "sp_score", "qa_score"])
    return result


# ═══════════════════════════════════════════
# Scenario Execution (3 rounds)
# ═══════════════════════════════════════════

def run_scenario(scenario_id: str) -> Dict[str, Any]:
    scenario = SCENARIOS[scenario_id]
    session_id = f"v102_{scenario_id}_{int(time.time())}"
    rounds = scenario["rounds"]

    print(f"\n{'='*60}")
    print(f"🧬 {scenario_id}: {scenario['name']} (Tier {scenario['tier']})")
    print(f"   Fix target: {scenario.get('fix_target', 'baseline')}")
    print(f"   Rounds: {len(rounds)} | Session: {session_id}")
    print(f"{'='*60}")

    send_telegram(
        f"🧬 *v10.2 #{scenario_id}*: {scenario['name']}\n"
        f"Tier {scenario['tier']} | Target: {scenario.get('fix_target', 'baseline')}"
    )

    round_results = []
    all_tool_calls = []

    for ri, rd in enumerate(rounds):
        round_num = ri + 1
        msg = rd["message"]
        msg_len = len(msg)

        print(f"\n  📤 Round {round_num} ({msg_len} chars): {msg[:80]}...")

        log_start = get_log_line_count()
        t0 = time.time()
        result = send_to_museon(msg, session_id)
        elapsed = time.time() - t0
        response = result.get("response", "[ERROR: no response]")

        time.sleep(2)
        new_logs = get_new_log_lines(log_start)
        scores = score_round(rd, response, new_logs)
        tc = extract_tool_calls(new_logs)
        all_tool_calls.extend(tc)

        round_result = {
            "round": round_num,
            "message": msg,
            "message_len": msg_len,
            "response": response,
            "response_len": len(response),
            "response_time_s": elapsed,
            "scores": scores,
            "tool_calls": tc,
            "log_lines": len(new_logs),
        }
        round_results.append(round_result)

        # Console output
        print(f"  📥 Response: {len(response)} chars, {elapsed:.1f}s")
        print(f"     RC={scores['rc_score']:.1f} SK={scores['sk_score']:.1f} "
              f"TL={scores['tl_score']:.1f} SP={scores['sp_score']:.1f} "
              f"QA={scores['qa_score']:.1f} → {scores['total']:.1f}/5")

        # Telegram report per round
        send_telegram(
            f"  R{round_num} ({msg_len}→{len(response)} chars, {elapsed:.1f}s)\n"
            f"  RC: {scores['rc_detail']}\n"
            f"  SK: {scores['sk_detail']}\n"
            f"  Score: {scores['total']:.1f}/5"
        )

        if ri < len(rounds) - 1:
            time.sleep(INTER_ROUND_DELAY)

    # Aggregate scores
    total_score = sum(r["scores"]["total"] for r in round_results)
    max_score = len(rounds) * 5
    pct = total_score / max_score * 100

    summary = f"📊 {scenario_id} 合計: {total_score:.1f}/{max_score} ({pct:.0f}%)"
    print(f"\n  {summary}")
    send_telegram(summary)

    return {
        "scenario_id": scenario_id,
        "name": scenario["name"],
        "tier": scenario["tier"],
        "fix_target": scenario.get("fix_target", "baseline"),
        "rounds": round_results,
        "total_score": total_score,
        "max_score": max_score,
        "pct": pct,
        "session_id": session_id,
        "all_tool_calls": all_tool_calls,
    }


# ═══════════════════════════════════════════
# Summary Report
# ═══════════════════════════════════════════

def generate_summary(all_results: Dict[str, Dict]) -> str:
    tier_scores: Dict[str, List[float]] = defaultdict(list)
    fix_target_scores: Dict[str, List[float]] = defaultdict(list)
    total_score = 0.0
    total_max = 0.0
    rc_rounds = 0
    rc_hits = 0
    sk_rounds = 0
    sk_hits = 0

    for sid, r in all_results.items():
        tier = r["tier"]
        tier_scores[tier].append(r["pct"])
        fix_target_scores[r["fix_target"]].append(r["pct"])
        total_score += r["total_score"]
        total_max += r["max_score"]

        for rd in r["rounds"]:
            sc = rd["scores"]
            # Count RC rounds
            if sc["rc_detail"] and "無預期" not in sc["rc_detail"]:
                rc_rounds += 1
                if sc["rc_score"] >= 0.5:
                    rc_hits += 1
            # Count SK rounds
            if sc["sk_detail"] and "無預期" not in sc["sk_detail"]:
                sk_rounds += 1
                if sc["sk_score"] >= 0.5:
                    sk_hits += 1

    tier_names = {
        "A": "安全情緒", "B": "主權決策", "C": "認知誠實",
        "D": "演化實驗", "E": "整合節律", "X": "跨層混合",
        "SK": "Skill路由", "M": "MCP工具",
    }

    lines = [
        "🧬🧬🧬 MUSEON v10.2 DNA27 壓力測試報告 🧬🧬🧬",
        f"📅 {datetime.now(TZ8).strftime('%Y-%m-%d %H:%M')}",
        f"📊 總分: {total_score:.0f}/{total_max:.0f} ({total_score/total_max*100:.0f}%)",
        "",
        "── 各 Tier 表現 ──",
    ]

    for tier_key in ["A", "B", "C", "D", "E", "X", "SK", "M"]:
        if tier_key in tier_scores:
            s = tier_scores[tier_key]
            avg = sum(s) / len(s)
            lines.append(f"  {tier_key} ({tier_names.get(tier_key,'?')}): {avg:.0f}% ({len(s)}情境)")

    lines.append("")
    lines.append("── v10.2 修正驗證 ──")
    for fix, pcts in sorted(fix_target_scores.items()):
        avg = sum(pcts) / len(pcts)
        status = "✅" if avg >= 70 else ("⚠️" if avg >= 50 else "❌")
        lines.append(f"  {status} {fix}: {avg:.0f}% ({len(pcts)}情境)")

    lines.append("")
    if rc_rounds > 0:
        lines.append(f"🧠 RC 命中率: {rc_hits}/{rc_rounds} ({rc_hits/rc_rounds*100:.0f}%)")
    if sk_rounds > 0:
        lines.append(f"🎯 Skill 正確率: {sk_hits}/{sk_rounds} ({sk_hits/sk_rounds*100:.0f}%)")

    # Per-scenario breakdown
    lines.append("")
    lines.append("── 逐情境分數 ──")
    for sid, r in all_results.items():
        emoji = "✅" if r["pct"] >= 70 else ("⚠️" if r["pct"] >= 50 else "❌")
        lines.append(f"  {emoji} {sid}: {r['total_score']:.0f}/{r['max_score']} ({r['pct']:.0f}%) — {r['name']}")

    return "\n".join(lines)


# ═══════════════════════════════════════════
# Main
# ═══════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="MUSEON v10.2 DNA27 Stress Test (3-round)")
    parser.add_argument("--all", action="store_true", help="Run all 20 scenarios")
    parser.add_argument("--scenario", help="Run specific scenario (e.g., S01)")
    parser.add_argument("--tier", help="Run all scenarios in a tier (e.g., A, B, SK, M)")
    args = parser.parse_args()

    # Health check
    try:
        resp = requests.get(f"{GATEWAY_URL}/health", timeout=5)
        health = resp.json()
        if health.get("status") != "healthy":
            print("❌ Gateway not healthy!")
            sys.exit(1)
        print(f"✅ Gateway healthy | skills: {health.get('skills_indexed', '?')} | mcp: {health.get('mcp', '?')}")
    except Exception as e:
        print(f"❌ Gateway unreachable: {e}")
        sys.exit(1)

    # Select scenarios
    if args.scenario:
        sids = [args.scenario.upper()]
    elif args.tier:
        sids = [sid for sid, s in SCENARIOS.items() if s["tier"] == args.tier.upper()]
    elif args.all:
        sids = list(SCENARIOS.keys())
    else:
        sids = list(SCENARIOS.keys())

    for sid in sids:
        if sid not in SCENARIOS:
            print(f"❌ Unknown: {sid}")
            sys.exit(1)

    total_rounds = sum(len(SCENARIOS[sid]["rounds"]) for sid in sids)
    print(f"\n🧬 Running {len(sids)} scenarios × 3 rounds = {total_rounds} total rounds")

    send_telegram(
        f"🧬🧬🧬 *MUSEON v10.2 DNA27 壓力測試開始* 🧬🧬🧬\n\n"
        f"📋 {len(sids)} 情境 × 3 輪 = {total_rounds} 輪\n"
        f"⏰ {datetime.now(TZ8).strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"🔧 v10.2 修正焦點:\n"
        f"  1. RC-C3 擴展 + RC-B1 收窄\n"
        f"  2. Vector boost ×1.0\n"
        f"  3. Top-8 + regex fix\n"
        f"  4. RC 保底排除壓制\n"
        f"  5. 孤兒 skill RC 親和\n"
        f"  6. MCP Connector SDK"
    )

    all_results: Dict[str, Dict] = {}

    for i, sid in enumerate(sids):
        try:
            result = run_scenario(sid)
            all_results[sid] = result
        except Exception as e:
            print(f"❌ {sid} failed: {e}")
            import traceback
            traceback.print_exc()
            send_telegram(f"❌ {sid} 失敗: {e}")

        if i < len(sids) - 1:
            print(f"\n⏳ 等待 {INTER_SCENARIO_DELAY}s...\n")
            time.sleep(INTER_SCENARIO_DELAY)

    # Summary
    summary = generate_summary(all_results)
    print(f"\n\n{summary}")
    send_telegram(summary)

    # Save
    ts = datetime.now(TZ8).strftime("%Y%m%d_%H%M%S")
    output_path = f"/Users/ZEALCHOU/museon/tests/v102_dna27_results_{ts}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n📄 Saved: {output_path}")

    # Final
    total_s = sum(r["total_score"] for r in all_results.values())
    total_m = sum(r["max_score"] for r in all_results.values())
    pct = total_s / total_m * 100 if total_m > 0 else 0

    send_telegram(
        f"✅ *v10.2 壓力測試完成*\n"
        f"📊 總分: {total_s:.0f}/{total_m:.0f} ({pct:.0f}%)\n"
        f"📄 `{output_path}`"
    )

    return all_results


if __name__ == "__main__":
    main()
