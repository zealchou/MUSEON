"""DARWIN — 事件偵測器

從 52 週模擬快照中偵測重大事件並生成因果敘事。
每個事件包含：type / severity / icon / title / narrative / data / impact / action
"""

from __future__ import annotations

import logging
from typing import Any

from museon.darwin.simulation.product_profile import get_product_profile

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 公用小工具
# ─────────────────────────────────────────────────────────────────────────────

def _get_metrics(snapshot) -> dict:
    """從 WeeklySnapshot（dataclass 或 dict）取出 business_metrics。"""
    if isinstance(snapshot, dict):
        return snapshot.get("business_metrics", {})
    return getattr(snapshot, "business_metrics", {})


def _get_week(snapshot) -> int:
    if isinstance(snapshot, dict):
        return snapshot.get("week", 0)
    return getattr(snapshot, "week", 0)


def _dist(metrics: dict) -> dict:
    """取出 state_distribution，預設全 0。"""
    return metrics.get("state_distribution", {})


def _pen(metrics: dict) -> float:
    """採用率（penetration_rate）。"""
    return metrics.get("penetration_rate", 0.0)


def _energy_val(energy: dict | None, side: str, primal: str) -> float:
    """安全取 energy[side][primal]。"""
    if not energy:
        return 0.0
    return energy.get(side, {}).get(primal, 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# 因果敘事生成器
# ─────────────────────────────────────────────────────────────────────────────

def _narrate_milestone(
    key: str, week: int, label: str, dist: dict, energy: dict | None,
    product_type: str, tam: int
) -> dict:
    """里程碑事件敘事。"""
    pen_pct = (dist.get("decided", 0) + dist.get("loyal", 0)) * 100
    aware_pct = (1 - dist.get("unaware", 1)) * 100
    considering_count = int(dist.get("considering", 0) * tam)
    adopted_count = int((dist.get("decided", 0) + dist.get("loyal", 0)) * tam)

    # penetration 里程碑
    if key.startswith("penetration_"):
        if _energy_val(energy, "inner", "澤") > 2.0:
            driver = "口碑飛輪在地下悶燒多週後，終於引燃社群共識"
        elif _energy_val(energy, "inner", "山") > 2.0:
            driver = "累積的品質口碑讓觀望者陸續越過信任門檻"
        else:
            driver = "持續曝光的量變終於引發採用率的質變"

        return {
            "narrative": f"第 {week} 週，你的採用率突破 {pen_pct:.0f}%，"
                         f"共有 {adopted_count} 位客戶已採用。{driver}。",
            "impact": f"目前還有 {considering_count} 位客戶在觀望——"
                      f"他們看到了這批採用者，決策速度正在加快。",
            "action": f"立刻啟動「社會證據收割」：向這 {adopted_count} 位採用者"
                      f"索取評價截圖，在下週投放前部署完成。",
        }

    # awareness 里程碑
    if key.startswith("awareness_"):
        product_label = {"cafe": "咖啡廳", "beauty": "美業", "b2b_saas": "SaaS",
                         "education": "課程", "consulting": "顧問服務"}.get(product_type, "服務")
        return {
            "narrative": f"第 {week} 週，{aware_pct:.0f}% 的目標客群已認知你的{product_label}。"
                         f"這意味著 {int(aware_pct / 100 * tam)} 人知道你的存在，"
                         f"但大多數還在觀望。",
            "impact": f"認知覆蓋是後續所有轉化的上限。"
                      f"現在有 {considering_count} 人在考慮——這批人是最近的果實。",
            "action": "把下週預算從「提升認知」移轉 30% 到「促進決策」，"
                      "針對已認知族群投放更具體的轉化訴求。",
        }

    # 首次類里程碑
    if key == "first_loyal":
        loyal_count = int(dist.get("loyal", 0) * tam)
        return {
            "narrative": f"第 {week} 週，{loyal_count} 位客戶從「決定購買」晉升為「忠實擁護者」。"
                         f"他們不只是回頭客——他們會主動推薦你。",
            "impact": "忠實客戶的口碑價值是付費廣告的 3-5 倍。"
                      "他們的每一則正評，都在幫你說服還在觀望的潛在客戶。",
            "action": f"在 48 小時內，私訊感謝這 {loyal_count} 位忠實客戶，"
                      "給他們一個「老朋友專屬」的驚喜，強化這段關係。",
        }

    if key == "first_decided":
        return _narrate_first_decided(week, dist, energy, product_type, tam)

    if key == "first_considering":
        cons_count = int(dist.get("considering", 0) * tam)
        return {
            "narrative": f"第 {week} 週，{cons_count} 位潛在客戶開始認真評估你的產品。"
                         f"他們不再只是「知道你」——他們在比較、在想要不要試。",
            "impact": "考慮期是客戶最容易被競爭者截走的階段。"
                      "你需要在未來 2 週內給他們一個「現在就決定」的理由。",
            "action": "部署一個限時優惠或試用方案，針對「已認知但未決策」的族群，"
                      "給他們一個低門檻的第一步。",
        }

    # first_aware
    aware_count = int((1 - dist.get("unaware", 1)) * tam)
    return {
        "narrative": f"第 {week} 週，{aware_count} 位潛在客戶首次注意到你。"
                     f"種子已種下——接下來是耐心培育的開始。",
        "impact": "認知的種子需要反覆觸點才能生根。"
                  "單次曝光的轉化率不到 2%，需要至少 5-7 次觸點才能進入考慮。",
        "action": "確保這批剛接觸的潛在客戶，在未來 2 週內"
                  "至少再收到 3 次不同形式的品牌訊息（內容、社群、口碑）。",
    }


def _narrate_first_decided(
    week: int, dist: dict, energy: dict | None, product_type: str, tam: int
) -> dict:
    decided_count = int(dist.get("decided", 0) * tam)
    considering_pct = dist.get("considering", 0) * 100

    if _energy_val(energy, "inner", "澤") > 2.0:
        driver = "社群口碑累積到臨界點，同儕效應開始發酵"
    elif _energy_val(energy, "inner", "山") > 2.0:
        driver = "品質證據足夠說服觀望者，信任門檻被跨越"
    else:
        driver = "策略持續曝光開始收割，量變引發質變"

    return {
        "narrative": f"第 {week} 週，{decided_count} 位客戶跨過「考慮」進入「決定購買」。"
                     f"{driver}，目前仍有 {considering_pct:.0f}% 在觀望。",
        "impact": "轉化飛輪啟動——每個新客戶都是社會證據，"
                  "會加速後續觀望者的決策。",
        "action": f"立刻收集這 {decided_count} 位客戶的使用心得，"
                  "作為下一波社會證據策略的彈藥。",
    }


def _narrate_momentum(
    mtype: str, week: int, dist: dict, pen_pct: float, tam: int,
    growth: float, avg_growth: float
) -> dict:
    """動能事件敘事。"""
    adopted = int((dist.get("decided", 0) + dist.get("loyal", 0)) * tam)
    considering = int(dist.get("considering", 0) * tam)

    if mtype == "burst":
        return {
            "narrative": f"第 {week} 週，採用率單週暴增 {growth * 100:.1f}%（是前四週均速的"
                         f" {growth / max(avg_growth, 0.001):.1f} 倍）。"
                         f"目前 {adopted} 人已採用，{considering} 人在觀望。",
            "impact": "爆發式增長通常伴隨某個觸媒——可能是一篇爆紅貼文、一個意見領袖的轉發，"
                      "或者節慶節點疊加。這個觸媒必須被識別並複製。",
            "action": "在 24 小時內，追查這週流量來源的構成比例，"
                      "找出貢獻最大的單一觸媒，準備在下週加碼複製。",
        }

    if mtype == "acceleration":
        return {
            "narrative": f"第 {week} 週，連續 2 週週增量超過前期均速的 1.5 倍。"
                         f"採用率 {pen_pct:.1f}%，成長動能正在加速。",
            "impact": "加速期是投入產出比最高的視窗。"
                      "此刻每 1 元廣告費的效益，是停滯期的 3-5 倍。",
            "action": "在加速期結束前，把行銷預算提高 50%，"
                      "趁動能高峰最大化滲透速度。",
        }

    if mtype == "deceleration":
        return {
            "narrative": f"第 {week} 週，週增量連續 3 週低於均速的 50%。"
                         f"成長放緩至 {growth * 100:.1f}%/週，動能正在流失。",
            "impact": "減速往往是某個渠道飽和的信號，或者初期嘗鮮族群已耗盡。"
                      "繼續用同樣方法只會得到邊際遞減的結果。",
            "action": "停止追加現有渠道的預算，轉而測試 1 個新觸點策略——"
                      "例如從線上轉到線下體驗活動，或從陌生客轉向口碑轉介。",
        }

    # stagnation
    return {
        "narrative": f"第 {week} 週，採用率連續 4 週週增量低於 0.5%，"
                     f"現在停在 {pen_pct:.1f}%。成長實質停止。",
        "impact": "停滯是系統警訊。可能是認知已觸及天花板、"
                  "觀望者卡在某個未被解決的疑慮，或競爭者的干擾。",
        "action": "立即訪談 5 位「已知道但沒決定」的潛在客戶，"
                  "找出讓他們停住的真實原因，而不是繼續猜測。",
    }


def _narrate_chasm(
    ctype: str, week: int, dist: dict, pen_pct: float, tam: int,
    threshold: float
) -> dict:
    """鴻溝事件敘事。"""
    considering_pct = dist.get("considering", 0) * 100
    considering_count = int(dist.get("considering", 0) * tam)

    if ctype == "enter":
        return {
            "narrative": f"第 {week} 週，採用率 {pen_pct:.1f}% 進入鴻溝區（門檻：{threshold * 100:.0f}%）。"
                         f"鴻溝是「早期嘗鮮者」與「主流市場」之間的信任斷層——"
                         f"很多品牌在此消失。",
            "impact": f"目前有 {considering_count} 人（{considering_pct:.0f}%）在觀望。"
                      f"他們不是不感興趣，而是在等「有沒有人跟我一樣在用」的社會證據。",
            "action": "立刻打造一個「主流客戶的成功案例」，"
                      "聚焦在「像他們一樣的人也在用」的敘事，而不是產品功能。",
        }

    if ctype == "pressure":
        return {
            "narrative": f"第 {week} 週，觀望比例達到峰值（{considering_pct:.0f}%）。"
                         f"鴻溝壓力最大——大量潛在客戶在邊緣猶豫不決。",
            "impact": "這是關鍵轉折點。如果你在這 2 週內無法提供足夠的社會證據，"
                      "這批觀望者很可能流向競爭者或直接放棄。",
            "action": "本週聚焦單一訴求：找到你最有說服力的 1-2 個客戶故事，"
                      "集中所有渠道反覆傳播，不要分散在多個訊息上。",
        }

    # crossed
    crossed_count = int((dist.get("decided", 0) + dist.get("loyal", 0)) * tam)
    return {
        "narrative": f"第 {week} 週，採用率 {pen_pct:.1f}% 突破鴻溝上界！"
                     f"你成功跨越了「早期市場」與「主流市場」的斷層，"
                     f"目前 {crossed_count} 人已採用。",
        "impact": "跨越鴻溝後，口碑傳播會進入自我增強的正循環。"
                  "成長動能將從「策略驅動」轉型為「口碑驅動」。",
        "action": "重新審視你的運營規模——主流市場的客戶服務需求與早期客戶不同，"
                  "現在是建立標準化服務流程的最後視窗。",
    }


def _narrate_social(
    stype: str, week: int, dist: dict, tam: int
) -> dict:
    """社群事件敘事。"""
    loyal_count = int(dist.get("loyal", 0) * tam)
    decided_count = int(dist.get("decided", 0) * tam)

    if stype == "wom_engine":
        return {
            "narrative": f"第 {week} 週，口碑貢獻開始超越策略直接投放。"
                         f"你的 {loyal_count} 位忠實客戶 + {decided_count} 位採用者，"
                         f"正在形成自發性的推薦網絡。",
            "impact": "口碑引擎一旦啟動，每位客戶的獲客成本（CAC）會開始下降。"
                      "接下來的成長不需要等比例增加廣告預算。",
            "action": "建立一個正式的轉介系統（推薦獎勵或專屬連結），"
                      "把自然發生的口碑行為制度化，讓它可預測、可擴大。",
        }

    # loyal_reversal
    return {
        "narrative": f"第 {week} 週，忠實客戶數（{loyal_count} 人）首次超越「已購買但普通」的客戶數。"
                     f"你的品牌已從「選擇」變成了部分人的「習慣」。",
        "impact": "忠實客戶是你對抗競爭者最堅固的護城河。"
                  "他們不只是重購客，更是主動替你排除競爭者的外部銷售力量。",
        "action": f"設計一個「忠實會員」的身份認同機制，"
                  f"讓這 {loyal_count} 人感到自己是特殊群體的一份子，強化歸屬感。",
    }


def _narrate_risk(
    rtype: str, week: int, dist: dict, tam: int
) -> dict:
    """風險事件敘事。"""
    resistant_pct = dist.get("resistant", 0) * 100
    resistant_count = int(dist.get("resistant", 0) * tam)
    aware_count = int(dist.get("aware", 0) * tam)
    considering_count = int(dist.get("considering", 0) * tam)

    if rtype == "first_resistant":
        return {
            "narrative": f"第 {week} 週，首批 {resistant_count} 位潛在客戶出現排斥信號——"
                         f"他們不是「還沒決定」，而是「已決定不要」。",
            "impact": "排斥訊號是早期警告。如果不找出根本原因，"
                      "排斥比例會隨著認知擴散而等比例放大。",
            "action": "立刻訪談 3-5 位排斥者，用「你會推薦我們給朋友嗎？為什麼不會？」"
                      "這個問題挖出真實的反對理由，而不是用問卷猜測。",
        }

    if rtype == "resistant_high":
        return {
            "narrative": f"第 {week} 週，排斥率達 {resistant_pct:.1f}%（{resistant_count} 人）。"
                         f"這是一個需要正視的系統性問題，不是個別案例。",
            "impact": "高排斥率會透過社群網絡擴散負面口碑，"
                      "抵銷你在正面認知上的所有投資。",
            "action": "暫停擴大觸及的行銷行動，先做 10 人深度訪談，"
                      "找出最頻繁出現的 1-2 個排斥原因，直接在產品或溝通訊息上修正。",
        }

    if rtype == "resistant_critical":
        return {
            "narrative": f"第 {week} 週，排斥率突破警戒線 5%（目前 {resistant_pct:.1f}%）。"
                         f"這意味著每 20 個知道你的人，就有 1 個以上在主動抵制。",
            "impact": "超過 5% 的排斥率通常代表有結構性問題——"
                      "可能是定價、信任、品質或溝通訊息的根本誤差。",
            "action": "本週停止所有新渠道投放，把資源 100% 轉向「根因分析」。"
                      "用 DSE 框架拆解：是哪個觸點製造了排斥？可以被根除而非只是掩蓋？",
        }

    if rtype == "awareness_ceiling":
        return {
            "narrative": f"第 {week} 週，認知率連續 6 週停滯。"
                         f"你已觸達 {aware_count} 人，但成長通道似乎關閉了。",
            "impact": "認知天花板意味著你的現有渠道已到達飽和邊界，"
                      "繼續加碼只是在重複觸及相同的人。",
            "action": "分析現有認知客群的來源分布，找出最大的「未觸及的潛在族群」，"
                      "測試一個全新的曝光渠道（換平台、換格式、換代言人）。",
        }

    # considering_stagnation
    return {
        "narrative": f"第 {week} 週，{considering_count} 位考慮中的客戶連續 4 週既不前進也不退出。"
                     f"他們卡住了。",
        "impact": "觀望堆積是轉化漏斗的最大殺手。這批人的決策成本已經付過了，"
                  "但沒有足夠的推力讓他們跨出最後一步。",
        "action": "針對「考慮中」族群設計一個「零風險試用」觸點——"
                  "降低第一次決定的心理成本，例如免費體驗、分期付款、或退款保證。",
    }


def _narrate_energy(
    etype: str, week: int, energy: dict | None, dist: dict, tam: int
) -> dict:
    """能量事件敘事。"""
    inner = energy.get("inner", {}) if energy else {}
    outer = energy.get("outer", {}) if energy else {}

    if etype == "ze_resonance":
        ze_val = inner.get("澤", 0)
        return {
            "narrative": f"第 {week} 週，你的「澤」能量達到 {ze_val:.1f}（共鳴高峰）。"
                         f"澤代表社群、快樂與連結——此刻是啟動社群口碑的最佳時機。",
            "impact": "澤能量高峰期，你的品牌在目標社群中的情緒共鳴最強，"
                      "口碑傳播的自然速度是平時的 2 倍以上。",
            "action": "在這個視窗內（1-2 週）投放社群互動型內容，"
                      "鼓勵分享、評論、標記朋友，趁共鳴高點最大化自然傳播。",
        }

    if etype == "shan_resonance":
        shan_val = inner.get("山", 0)
        return {
            "narrative": f"第 {week} 週，「山」能量強勢（{shan_val:.1f}）。"
                         f"山代表品質、耐力與可信度——此刻你的品牌形象最具說服力。",
            "impact": "山能量高峰期，理性訴求的轉化率最高，"
                      "客戶比較容易接受數據、測試結果、品質認證等硬性證據。",
            "action": "本週主打「品質證明型」內容——案例研究、第三方評測、"
                      "原物料溯源故事——趁信任窗口轉化觀望者。",
        }

    # low_energy_warning
    low_dims = [k for k, v in inner.items() if v < -1.5]
    dims_str = "、".join(low_dims) if low_dims else "多個方位"
    return {
        "narrative": f"第 {week} 週，{dims_str}能量偏低，"
                     f"系統整體動能處於低潮。",
        "impact": "低能量期間，相同的行銷投入會得到更少的共鳴回應。"
                  "這不是策略問題，而是時機問題。",
        "action": "這週降低外部推廣強度，轉而做內部優化——"
                  "改善服務品質、整理客戶資料、訓練團隊，"
                  "讓自己在下次高峰時以更強狀態出發。",
    }


# ─────────────────────────────────────────────────────────────────────────────
# 主偵測函數
# ─────────────────────────────────────────────────────────────────────────────

def detect_events(
    snapshots: list,
    product_type: str = "cafe",
    district: str = "",
    strategy_name: str = "",
    energy: dict | None = None,
    tam: int = 100,
) -> list[dict]:
    """
    從快照偵測重大事件，回傳按週排序的事件列表。

    每個事件：
    {
        "week": int,
        "type": str,          # milestone / momentum / chasm / social / risk / energy
        "severity": str,      # critical / high / medium / low
        "icon": str,
        "title": str,
        "narrative": str,
        "data": dict,
        "impact": str,
        "action": str,
    }
    """
    if not snapshots:
        return []

    profile = get_product_profile(product_type)
    events: list[dict] = []

    # ── 預計算時間序列 ──
    weeks = [_get_week(s) for s in snapshots]
    metrics_list = [_get_metrics(s) for s in snapshots]
    pen_series = [_pen(m) for m in metrics_list]
    dist_series = [_dist(m) for m in metrics_list]

    # ── 1. 里程碑偵測 ──
    milestones_triggered: set[str] = set()

    MILESTONE_DEFS: list[tuple[str, str, str, str, Any]] = [
        # (key, title, severity, icon, check_fn)
        # check_fn signature: (dist, pen) -> bool
        ("first_aware",      "首位潛在客戶注意到你",    "low",      "👁️",  lambda d, p: (1 - d.get("unaware", 1)) > 0.01),
        ("awareness_10pct",  "10% 認知覆蓋",            "medium",   "📢",  lambda d, p: (1 - d.get("unaware", 1)) >= 0.10),
        ("awareness_30pct",  "30% 認知覆蓋",            "medium",   "📣",  lambda d, p: (1 - d.get("unaware", 1)) >= 0.30),
        ("awareness_50pct",  "過半客群已認知",           "high",     "🔔",  lambda d, p: (1 - d.get("unaware", 1)) >= 0.50),
        ("first_considering","首批客戶開始認真考慮",     "medium",   "🤔",  lambda d, p: d.get("considering", 0) > 0.01),
        ("first_decided",    "首批客戶決定購買",         "high",     "🎯",  lambda d, p: d.get("decided", 0) > 0.01),
        ("first_loyal",      "首批忠實客戶誕生",         "high",     "❤️",  lambda d, p: d.get("loyal", 0) > 0.01),
        ("penetration_5pct", "5% 採用率",               "medium",   "🌱",  lambda d, p: p >= 0.05),
        ("penetration_10pct","10% 採用率",               "high",     "🌿",  lambda d, p: p >= 0.10),
        ("penetration_20pct","20% 採用率突破",           "high",     "🌳",  lambda d, p: p >= 0.20),
        ("penetration_30pct","30% 採用率突破",           "critical", "🏆",  lambda d, p: p >= 0.30),
        ("penetration_50pct","過半採用",                 "critical", "🎉",  lambda d, p: p >= 0.50),
    ]

    for week_idx, (week, dist, metrics) in enumerate(zip(weeks, dist_series, metrics_list)):
        pen = pen_series[week_idx]
        for key, title, severity, icon, check_fn in MILESTONE_DEFS:
            if key in milestones_triggered:
                continue
            if check_fn(dist, pen):
                milestones_triggered.add(key)
                narr = _narrate_milestone(key, week, title, dist, energy, product_type, tam)
                events.append({
                    "week": week,
                    "type": "milestone",
                    "severity": severity,
                    "icon": icon,
                    "title": title,
                    "narrative": narr["narrative"],
                    "data": {
                        "penetration_rate": round(pen, 4),
                        "state_distribution": dist,
                        "adopted_count": metrics.get("adopted_count", int(pen * tam)),
                    },
                    "impact": narr["impact"],
                    "action": narr["action"],
                })

    # ── 2. 動能偵測 ──
    # 需要至少 5 週的數據才開始計算
    momentum_triggered: dict[str, int] = {}  # mtype -> last triggered week

    for i in range(4, len(pen_series)):
        week = weeks[i]
        dist = dist_series[i]
        pen = pen_series[i]
        prev_pen = pen_series[i - 1]
        growth = pen - prev_pen

        # 前 4 週平均增量
        prev_growths = [pen_series[j] - pen_series[j - 1] for j in range(max(1, i - 4), i)]
        avg_growth = sum(prev_growths) / max(len(prev_growths), 1)

        # 爆發
        if avg_growth > 0.001 and growth > avg_growth * 3.0:
            last = momentum_triggered.get("burst", -99)
            if week - last >= 4:
                momentum_triggered["burst"] = week
                narr = _narrate_momentum("burst", week, dist, pen * 100, tam, growth, avg_growth)
                events.append({
                    "week": week,
                    "type": "momentum",
                    "severity": "critical",
                    "icon": "🚀",
                    "title": "爆發式成長",
                    "narrative": narr["narrative"],
                    "data": {"growth": round(growth, 4), "avg_growth": round(avg_growth, 4), "penetration_rate": round(pen, 4)},
                    "impact": narr["impact"],
                    "action": narr["action"],
                })
            continue

        # 加速：連續 2 週高於均速 1.5x
        if i >= 5:
            prev_growth = pen_series[i - 1] - pen_series[i - 2]
            if avg_growth > 0.001 and growth > avg_growth * 1.5 and prev_growth > avg_growth * 1.5:
                last = momentum_triggered.get("acceleration", -99)
                if week - last >= 6:
                    momentum_triggered["acceleration"] = week
                    narr = _narrate_momentum("acceleration", week, dist, pen * 100, tam, growth, avg_growth)
                    events.append({
                        "week": week,
                        "type": "momentum",
                        "severity": "high",
                        "icon": "⬆️",
                        "title": "成長加速",
                        "narrative": narr["narrative"],
                        "data": {"growth": round(growth, 4), "avg_growth": round(avg_growth, 4), "penetration_rate": round(pen, 4)},
                        "impact": narr["impact"],
                        "action": narr["action"],
                    })
                continue

        # 減速：連續 3 週低於均速 0.5x
        if i >= 6:
            recent_3 = [pen_series[j] - pen_series[j - 1] for j in range(i - 2, i + 1)]
            if avg_growth > 0.001 and all(g < avg_growth * 0.5 for g in recent_3):
                last = momentum_triggered.get("deceleration", -99)
                if week - last >= 8:
                    momentum_triggered["deceleration"] = week
                    narr = _narrate_momentum("deceleration", week, dist, pen * 100, tam, growth, avg_growth)
                    events.append({
                        "week": week,
                        "type": "momentum",
                        "severity": "medium",
                        "icon": "⬇️",
                        "title": "成長減速",
                        "narrative": narr["narrative"],
                        "data": {"growth": round(growth, 4), "avg_growth": round(avg_growth, 4), "penetration_rate": round(pen, 4)},
                        "impact": narr["impact"],
                        "action": narr["action"],
                    })
                continue

        # 停滯：連續 4 週 < 0.5%
        if i >= 7:
            recent_4 = [pen_series[j] - pen_series[j - 1] for j in range(i - 3, i + 1)]
            if all(abs(g) < 0.005 for g in recent_4):
                last = momentum_triggered.get("stagnation", -99)
                if week - last >= 10:
                    momentum_triggered["stagnation"] = week
                    narr = _narrate_momentum("stagnation", week, dist, pen * 100, tam, growth, avg_growth)
                    events.append({
                        "week": week,
                        "type": "momentum",
                        "severity": "high",
                        "icon": "⏸️",
                        "title": "成長停滯",
                        "narrative": narr["narrative"],
                        "data": {"growth": round(growth, 4), "avg_growth": round(avg_growth, 4), "penetration_rate": round(pen, 4)},
                        "impact": narr["impact"],
                        "action": narr["action"],
                    })

    # ── 3. 鴻溝偵測 ──
    chasm_lo = profile.chasm_threshold - 0.05
    chasm_hi = profile.chasm_threshold + 0.15
    chasm_entered = False
    chasm_crossed = False
    chasm_peak_triggered = False
    max_considering = 0.0
    max_considering_week = 0

    for i, (week, dist, pen) in enumerate(zip(weeks, dist_series, pen_series)):
        considering = dist.get("considering", 0)

        if not chasm_entered and chasm_lo <= pen <= chasm_hi:
            chasm_entered = True
            narr = _narrate_chasm("enter", week, dist, pen * 100, tam, profile.chasm_threshold)
            events.append({
                "week": week,
                "type": "chasm",
                "severity": "critical",
                "icon": "🕳️",
                "title": "進入鴻溝區",
                "narrative": narr["narrative"],
                "data": {"penetration_rate": round(pen, 4), "chasm_threshold": profile.chasm_threshold, "considering": round(considering, 4)},
                "impact": narr["impact"],
                "action": narr["action"],
            })

        if chasm_entered and not chasm_crossed:
            if considering > max_considering:
                max_considering = considering
                max_considering_week = week

            # 鴻溝壓力最大（考慮率峰值後開始下降）
            if (not chasm_peak_triggered and i > 0
                    and considering < dist_series[i - 1].get("considering", 0)
                    and max_considering > 0.05):
                chasm_peak_triggered = True
                narr = _narrate_chasm("pressure", max_considering_week, dist_series[i - 1], pen * 100, tam, profile.chasm_threshold)
                events.append({
                    "week": max_considering_week,
                    "type": "chasm",
                    "severity": "critical",
                    "icon": "⚠️",
                    "title": "鴻溝壓力最大",
                    "narrative": narr["narrative"],
                    "data": {"penetration_rate": round(pen, 4), "max_considering": round(max_considering, 4)},
                    "impact": narr["impact"],
                    "action": narr["action"],
                })

            # 跨越鴻溝
            if pen > chasm_hi:
                chasm_crossed = True
                narr = _narrate_chasm("crossed", week, dist, pen * 100, tam, profile.chasm_threshold)
                events.append({
                    "week": week,
                    "type": "chasm",
                    "severity": "critical",
                    "icon": "🌉",
                    "title": "跨越鴻溝",
                    "narrative": narr["narrative"],
                    "data": {"penetration_rate": round(pen, 4), "chasm_hi": chasm_hi},
                    "impact": narr["impact"],
                    "action": narr["action"],
                })

    # ── 4. 社群事件 ──
    wom_triggered = False
    loyal_reversal_triggered = False

    for i, (week, dist, pen, metrics) in enumerate(zip(weeks, dist_series, pen_series, metrics_list)):
        decided = dist.get("decided", 0)
        loyal = dist.get("loyal", 0)

        # 口碑引擎：penetration > 10% 且週增量加速
        if not wom_triggered and pen > 0.10 and i >= 2:
            growth = pen_series[i] - pen_series[i - 1]
            prev_growth = pen_series[i - 1] - pen_series[i - 2]
            if growth > prev_growth * 1.3:
                wom_triggered = True
                narr = _narrate_social("wom_engine", week, dist, tam)
                events.append({
                    "week": week,
                    "type": "social",
                    "severity": "high",
                    "icon": "💬",
                    "title": "口碑引擎啟動",
                    "narrative": narr["narrative"],
                    "data": {"penetration_rate": round(pen, 4), "loyal": round(loyal, 4), "decided": round(decided, 4)},
                    "impact": narr["impact"],
                    "action": narr["action"],
                })

        # 忠實客戶反向輸出
        if not loyal_reversal_triggered and loyal > decided and loyal > 0.01:
            loyal_reversal_triggered = True
            narr = _narrate_social("loyal_reversal", week, dist, tam)
            events.append({
                "week": week,
                "type": "social",
                "severity": "medium",
                "icon": "🔄",
                "title": "忠實客戶開始反向輸出",
                "narrative": narr["narrative"],
                "data": {"loyal": round(loyal, 4), "decided": round(decided, 4)},
                "impact": narr["impact"],
                "action": narr["action"],
            })

    # ── 5. 風險事件 ──
    first_resistant_triggered = False
    resistant_high_triggered = False
    resistant_critical_triggered = False
    awareness_ceiling_triggered = False
    considering_stagnation_triggered = False

    for i, (week, dist) in enumerate(zip(weeks, dist_series)):
        resistant = dist.get("resistant", 0)
        aware = dist.get("aware", 0)
        considering = dist.get("considering", 0)

        # 首次排斥
        if not first_resistant_triggered and resistant > 0:
            first_resistant_triggered = True
            narr = _narrate_risk("first_resistant", week, dist, tam)
            events.append({
                "week": week,
                "type": "risk",
                "severity": "medium",
                "icon": "🚫",
                "title": "市場出現排斥信號",
                "narrative": narr["narrative"],
                "data": {"resistant": round(resistant, 4), "resistant_count": int(resistant * tam)},
                "impact": narr["impact"],
                "action": narr["action"],
            })

        # 排斥率偏高 (>3%)
        if not resistant_high_triggered and resistant > 0.03:
            resistant_high_triggered = True
            narr = _narrate_risk("resistant_high", week, dist, tam)
            events.append({
                "week": week,
                "type": "risk",
                "severity": "high",
                "icon": "🔴",
                "title": "排斥率偏高",
                "narrative": narr["narrative"],
                "data": {"resistant": round(resistant, 4), "resistant_pct": round(resistant * 100, 1)},
                "impact": narr["impact"],
                "action": narr["action"],
            })

        # 排斥率警戒 (>5%)
        if not resistant_critical_triggered and resistant > 0.05:
            resistant_critical_triggered = True
            narr = _narrate_risk("resistant_critical", week, dist, tam)
            events.append({
                "week": week,
                "type": "risk",
                "severity": "critical",
                "icon": "🆘",
                "title": "排斥率警戒",
                "narrative": narr["narrative"],
                "data": {"resistant": round(resistant, 4), "resistant_pct": round(resistant * 100, 1)},
                "impact": narr["impact"],
                "action": narr["action"],
            })

        # 認知天花板：連續 6 週 aware 不增長
        if not awareness_ceiling_triggered and i >= 6:
            aware_vals = [dist_series[j].get("aware", 0) for j in range(i - 5, i + 1)]
            if max(aware_vals) - min(aware_vals) < 0.01 and max(aware_vals) > 0.05:
                awareness_ceiling_triggered = True
                narr = _narrate_risk("awareness_ceiling", week, dist, tam)
                events.append({
                    "week": week,
                    "type": "risk",
                    "severity": "medium",
                    "icon": "🪟",
                    "title": "認知天花板",
                    "narrative": narr["narrative"],
                    "data": {"aware": round(aware, 4), "aware_count": int(aware * tam)},
                    "impact": narr["impact"],
                    "action": narr["action"],
                })

        # 觀望堆積：considering 連續 4 週不動
        if not considering_stagnation_triggered and i >= 4 and considering > 0.03:
            cons_vals = [dist_series[j].get("considering", 0) for j in range(i - 3, i + 1)]
            if max(cons_vals) - min(cons_vals) < 0.01:
                considering_stagnation_triggered = True
                narr = _narrate_risk("considering_stagnation", week, dist, tam)
                events.append({
                    "week": week,
                    "type": "risk",
                    "severity": "medium",
                    "icon": "🧊",
                    "title": "觀望堆積",
                    "narrative": narr["narrative"],
                    "data": {"considering": round(considering, 4), "considering_count": int(considering * tam)},
                    "impact": narr["impact"],
                    "action": narr["action"],
                })

    # ── 6. 能量事件（如果提供）──
    if energy:
        inner = energy.get("inner", {})
        ze = inner.get("澤", 0)
        shan = inner.get("山", 0)

        # 高澤能量共鳴
        if ze > 2.0:
            # 找第一個 aware > 5% 的週（即開始需要推廣的時機）
            for i, (week, dist, pen) in enumerate(zip(weeks, dist_series, pen_series)):
                if pen > 0.05:
                    narr = _narrate_energy("ze_resonance", week, energy, dist, tam)
                    events.append({
                        "week": week,
                        "type": "energy",
                        "severity": "medium",
                        "icon": "💧",
                        "title": "澤能量共鳴高峰",
                        "narrative": narr["narrative"],
                        "data": {"澤": ze, "penetration_rate": round(pen, 4)},
                        "impact": narr["impact"],
                        "action": narr["action"],
                    })
                    break

        # 高山能量共鳴
        if shan > 2.0:
            for i, (week, dist, pen) in enumerate(zip(weeks, dist_series, pen_series)):
                if pen > 0.05:
                    narr = _narrate_energy("shan_resonance", week, energy, dist, tam)
                    events.append({
                        "week": week,
                        "type": "energy",
                        "severity": "medium",
                        "icon": "🏔️",
                        "title": "山能量共鳴高峰",
                        "narrative": narr["narrative"],
                        "data": {"山": shan, "penetration_rate": round(pen, 4)},
                        "impact": narr["impact"],
                        "action": narr["action"],
                    })
                    break

        # 低能量警告
        low_count = sum(1 for v in inner.values() if v < -1.5)
        if low_count >= 2:
            first_week = weeks[0] if weeks else 1
            narr = _narrate_energy("low_energy_warning", first_week, energy, dist_series[0] if dist_series else {}, tam)
            events.append({
                "week": first_week,
                "type": "energy",
                "severity": "low",
                "icon": "🌑",
                "title": "多方位能量低潮",
                "narrative": narr["narrative"],
                "data": {"low_dims": [k for k, v in inner.items() if v < -1.5]},
                "impact": narr["impact"],
                "action": narr["action"],
            })

    # ── 排序（按週，同週按嚴重度）──
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    events.sort(key=lambda e: (e["week"], severity_order.get(e["severity"], 9)))

    logger.info(
        f"event_detector | product={product_type} district={district} "
        f"strategy={strategy_name} events={len(events)}"
    )
    return events
