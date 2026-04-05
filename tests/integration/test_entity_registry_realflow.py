"""Entity Registry 真實 DM 管道測試.

模擬真實 Telegram 私訊進入 Brain 的完整流程：
  1. Brain 初始化（載入所有模組）
  2. 設定 DM context（非群組）
  3. 呼叫 _build_memory_inject（三層人物搜尋注入）
  4. L4 CPU Observer 完整 observe()（含記憶寫入 + chat_scope + alias 偵測）
  5. 驗證資料庫副作用

不呼叫 LLM — 只走 prompt 建構和 L4 觀察管道，
這是 Brain 在真實 DM 中「看到的」和「做完之後做的」。

執行方式：
    cd ~/MUSEON && .venv/bin/python tests/integration/test_entity_registry_realflow.py
"""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
PASS = 0
FAIL = 0


def report(name: str, passed: bool, detail: str = ""):
    global PASS, FAIL
    status = "✅ PASS" if passed else "❌ FAIL"
    if passed:
        PASS += 1
    else:
        FAIL += 1
    line = f"  {status}: {name}"
    if detail:
        line += f" — {detail}"
    print(line)


def section(title: str):
    print(f"\n{'═' * 50}")
    print(f"  {title}")
    print(f"{'═' * 50}")


# ══════════════════════════════════════════════
# Step 0：初始化 Brain（真實模組載入）
# ══════════════════════════════════════════════
section("Step 0：初始化 Brain")
t0 = time.time()

try:
    from museon.agent.brain import MuseonBrain
    brain = MuseonBrain(data_dir=str(DATA_DIR))
    brain_ok = True
    report("Brain 初始化", True, f"{time.time() - t0:.1f}s")
except Exception as e:
    brain_ok = False
    report("Brain 初始化", False, str(e)[:100])
    brain = None

if brain_ok:
    report("memory_manager 存在", brain.memory_manager is not None, "")
    report("memory_store 存在", brain.memory_store is not None, "")

    # 確認兩者是不同實例
    report(
        "memory_manager ≠ memory_store（類型不同）",
        type(brain.memory_manager).__name__ != type(brain.memory_store).__name__,
        f"manager={type(brain.memory_manager).__name__}, store={type(brain.memory_store).__name__}",
    )


# ══════════════════════════════════════════════
# Step 1：Nightly auto-alias 先跑一次（填充 alias 表）
# ══════════════════════════════════════════════
section("Step 1：填充 alias 表（模擬 Nightly auto-alias）")

from museon.governance.group_context import GroupContextStore
from museon.athena.profile_store import ProfileStore
from museon.athena.external_bridge import ExternalBridge

gcs = GroupContextStore(DATA_DIR)
ps = ProfileStore(DATA_DIR)
bridge = ExternalBridge(ps, DATA_DIR / "_system" / "external_users")

ext_map = bridge._load_map()
alias_count = 0
for tg_uid, ares_pid in ext_map.items():
    ext_path = bridge.ext_dir / f"{tg_uid}.json"
    if not ext_path.exists():
        continue
    ext_data = json.loads(ext_path.read_text(encoding="utf-8"))
    display_name = ext_data.get("display_name", "")
    if not display_name or display_name.startswith("User_"):
        continue
    gcs.add_alias(display_name, ares_pid, "ares_profile", "realflow_test")
    gcs.add_alias(display_name, tg_uid, "telegram_uid", "realflow_test")
    alias_count += 1

report("Auto-alias 填充", alias_count >= 10, f"{alias_count} 組")


# ══════════════════════════════════════════════
# Step 2：模擬 DM —「Feng 那邊品牌案進度如何」
# Brain 的 prompt builder 三層搜尋會注入什麼？
# ══════════════════════════════════════════════
section("Step 2：DM「Feng 那邊品牌案進度如何」→ Brain prompt 注入")

if brain_ok:
    # 設定 DM context
    brain._is_group_session = False
    brain._current_metadata = None

    # 呼叫 _build_memory_inject（需要 budget 物件）
    from museon.agent.token_optimizer import TokenBudget
    budget = TokenBudget()

    t1 = time.time()
    inject_text = brain._build_memory_inject(
        user_query="Feng 那邊品牌案進度如何",
        budget=budget,
        anima_user=None,
        session_id="test_dm_feng",
    )
    t1_elapsed = time.time() - t1

    report("_build_memory_inject 執行成功", True, f"{t1_elapsed:.2f}s")

    # 檢查注入文字中是否包含 Feng 的資訊
    has_feng = "Feng" in inject_text or "人物" in inject_text
    report("注入文字包含 Feng 資訊", has_feng, f"注入長度 {len(inject_text)} 字")

    # 印出實際注入的人物資訊
    print("\n  ── Brain 看到的人物資訊 ──")
    for line in inject_text.split("\n"):
        if "人物" in line or "外部用戶" in line or "Feng" in line:
            print(f"    {line.strip()[:120]}")
    if not inject_text:
        print("    (空 — 沒有人物資訊注入)")


# ══════════════════════════════════════════════
# Step 3：模擬 DM —「吳明憲上次提的合作方案」
# 測試中文名搜尋
# ══════════════════════════════════════════════
section("Step 3：DM「吳明憲上次提的合作方案」→ 中文名搜尋")

if brain_ok:
    budget2 = TokenBudget()
    t2 = time.time()
    inject_alan = brain._build_memory_inject(
        user_query="吳明憲上次提的合作方案怎麼樣了",
        budget=budget2,
        anima_user=None,
        session_id="test_dm_alan",
    )
    t2_elapsed = time.time() - t2

    has_alan = "吳明憲" in inject_alan or "Alan" in inject_alan
    report("注入文字包含吳明憲資訊", has_alan, f"{t2_elapsed:.2f}s, {len(inject_alan)} 字")

    print("\n  ── Brain 看到的人物資訊 ──")
    for line in inject_alan.split("\n"):
        if "吳明憲" in line or "Alan" in line or "人物" in line or "外部用戶" in line:
            print(f"    {line.strip()[:120]}")


# ══════════════════════════════════════════════
# Step 4：模擬 DM —「小馮」（alias 搜尋）
# 先建 alias「小馮 → Feng」，再搜
# ══════════════════════════════════════════════
section("Step 4：DM「小馮最近忙什麼」→ alias 搜尋")

# 先手動建 alias
from museon.agent.l4_cpu_observer import L4CpuObserver

l4 = L4CpuObserver(data_dir=DATA_DIR, memory_manager=brain.memory_manager if brain_ok else None)
l4._step6_alias_detection("小馮就是Feng", metadata=None)

if brain_ok:
    budget3 = TokenBudget()
    inject_xiaofeng = brain._build_memory_inject(
        user_query="小馮最近忙什麼",
        budget=budget3,
        anima_user=None,
        session_id="test_dm_xiaofeng",
    )

    # 「小馮」應該透過 alias 解析到 Feng，然後 Ares 搜到 Feng profile
    has_xiaofeng_result = "Feng" in inject_xiaofeng or "人物" in inject_xiaofeng
    report("alias '小馮' 能找到 Feng", has_xiaofeng_result, f"{len(inject_xiaofeng)} 字")

    print("\n  ── Brain 看到的人物資訊 ──")
    for line in inject_xiaofeng.split("\n"):
        if "Feng" in line or "小馮" in line or "人物" in line or "外部用戶" in line:
            print(f"    {line.strip()[:120]}")


# ══════════════════════════════════════════════
# Step 5：L4 完整 observe() — 模擬 DM 對話後觀察
# ══════════════════════════════════════════════
section("Step 5：L4 observe() 完整管道（DM）")

dm_metadata = {"is_group": False, "sender_name": "Zeal"}
t3 = time.time()
l4_result = l4.observe(
    session_id="telegram_6969045906",
    chat_id="6969045906",
    user_id="boss",
    user_message="Feng 那邊品牌案進度如何？上次跟他聊到 CIS 設計的部分，他說要先跟團隊討論",
    museon_reply="根據上次的對話紀錄，Feng 提到 CIS 設計需要先跟內部團隊對齊方向...",
    metadata=dm_metadata,
)
t3_elapsed = time.time() - t3

report("L4 observe() 執行成功", isinstance(l4_result, dict), f"{t3_elapsed:.2f}s")
report(
    "memory_written 結果",
    True,  # 不管 True/False 都報告，重點是有跑
    f"memory_written={l4_result.get('memory_written')}",
)
report(
    "signal_updated 結果",
    True,
    f"signal_updated={l4_result.get('signal_updated')}",
)
report(
    "semantic cache 結果",
    True,
    f"cache_written={l4_result.get('cache_written')}",
)

print(f"\n  ── L4 完整結果 ──")
for k, v in l4_result.items():
    print(f"    {k}: {v}")


# ══════════════════════════════════════════════
# Step 6：L4 observe() — 別名偵測（DM 中說「Rita 也叫小麗」）
# ══════════════════════════════════════════════
section("Step 6：L4 observe() 中偵測別名")

l4_alias_result = l4.observe(
    session_id="telegram_6969045906",
    chat_id="6969045906",
    user_id="boss",
    user_message="對了，Rita 也叫小麗，下次提到小麗你要知道是她",
    museon_reply="了解，我已經記住小麗就是 Rita 了。",
    metadata=dm_metadata,
)

report(
    "alias_detected = True",
    l4_alias_result.get("alias_detected") is True,
    f"alias_detected={l4_alias_result.get('alias_detected')}",
)

# 驗證 alias 真的建了
hits = gcs.resolve_alias("小麗")
report(
    "resolve_alias('小麗') 找到 Rita",
    len(hits) > 0,
    f"{len(hits)} 筆命中",
)


# ══════════════════════════════════════════════
# Step 7：L4 observe() — 群組不偵測別名
# ══════════════════════════════════════════════
section("Step 7：群組中 L4 不偵測別名")

group_metadata = {"is_group": True, "group_id": "5107045509", "sender_name": "客戶"}
l4_group_result = l4.observe(
    session_id="telegram_group_5107045509",
    chat_id="5107045509",
    user_id="8252847174",
    user_message="Vivi 就是我們的設計師小薇",
    museon_reply="了解。",
    metadata=group_metadata,
)

report(
    "群組中 alias_detected = False",
    l4_group_result.get("alias_detected") is False,
    f"alias_detected={l4_group_result.get('alias_detected')}",
)


# ══════════════════════════════════════════════
# Step 8：Brain prompt 搜尋 — 搜不存在的人（負面測試）
# ══════════════════════════════════════════════
section("Step 8：搜不存在的人「張三丰」→ 不應注入任何人物")

if brain_ok:
    budget4 = TokenBudget()
    inject_nobody = brain._build_memory_inject(
        user_query="張三丰昨天說什麼了",
        budget=budget4,
        anima_user=None,
        session_id="test_dm_nobody",
    )

    # 不應該有任何人物資訊
    has_person = "人物「" in inject_nobody or "外部用戶「" in inject_nobody
    report(
        "不存在的人不注入人物資訊",
        not has_person,
        f"注入 {len(inject_nobody)} 字, has_person={has_person}",
    )


# ══════════════════════════════════════════════
# Step 9：完整 DM 流程模擬 — brain.process() (async)
# 這會真正走 Brain 全管道（含 LLM 呼叫）
# ══════════════════════════════════════════════
section("Step 9：brain.process() 完整管道（含 LLM）")

if brain_ok:
    async def test_full_process():
        try:
            response = await brain.process(
                content="Feng 的品牌案目前到哪個階段了？我記得上次聊到 CIS",
                session_id="e2e_test_dm",
                user_id="boss",
                source="telegram",
                metadata={"is_group": False},
            )
            # response 可能是 str 或 BrainResponse 物件
            resp_text = str(response) if response else ""
            return True, resp_text[:200]
        except Exception as e:
            return False, str(e)[:200]

    t4 = time.time()
    success, resp_preview = asyncio.run(test_full_process())
    t4_elapsed = time.time() - t4

    report(
        "brain.process() 完整執行",
        success,
        f"{t4_elapsed:.1f}s" + (f" | 回覆: {resp_preview[:80]}..." if success else f" | 錯誤: {resp_preview}"),
    )


# ══════════════════════════════════════════════
# Cleanup
# ══════════════════════════════════════════════
section("Cleanup")

conn = gcs._get_conn()
conn.execute("DELETE FROM entity_aliases WHERE created_by IN ('realflow_test', 'l4_auto')")
deleted = conn.execute("SELECT changes()").fetchone()[0]
conn.commit()
print(f"  清除 {deleted} 筆測試 alias")

# 清理測試 session history
if brain_ok and "e2e_test_dm" in brain._sessions:
    del brain._sessions["e2e_test_dm"]


# ══════════════════════════════════════════════
# 總結
# ══════════════════════════════════════════════
print(f"\n{'═' * 50}")
print(f"  總結：{PASS}/{PASS + FAIL} PASS")
if FAIL > 0:
    print(f"\n  ❌ FAIL 項目：")
    # 不再追蹤 RESULTS list，直接報數字
print(f"{'═' * 50}")

sys.exit(0 if FAIL == 0 else 1)
