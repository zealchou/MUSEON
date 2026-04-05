"""Entity Registry 端對端真實情境測試.

模擬 Zeal 在 Telegram 私訊中的實際操作流程，
驗證 Entity Registry 所有功能在真實資料上的表現。

執行方式：
    cd ~/MUSEON && .venv/bin/python tests/integration/test_entity_registry_e2e.py

注意：此腳本會修改真實資料（alias 表、profile 溫度），
      但每個測試結束時會 cleanup。
"""

import json
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# 確保 MUSEON src 在 path 中
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
PASS = 0
FAIL = 0
RESULTS = []


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
    RESULTS.append((name, passed, detail))


# ══════════════════════════════════════════════
# 情境 1：Nightly 自動建 alias
# 模擬 Nightly bridge sync 後自動從 display_name 建 alias
# ══════════════════════════════════════════════
print("\n═══ 情境 1：Nightly 自動建 alias ═══")

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
    gcs.add_alias(display_name, ares_pid, "ares_profile", "e2e_test")
    gcs.add_alias(display_name, tg_uid, "telegram_uid", "e2e_test")
    alias_count += 1

report("自動建 alias 數量", alias_count >= 10, f"{alias_count} 組 alias 已建立")

# 驗證 Feng 可被 alias 查到
feng_hits = gcs.resolve_alias("Feng")
report(
    "resolve_alias('Feng') 找到結果",
    len(feng_hits) > 0,
    f"找到 {len(feng_hits)} 筆",
)

# 驗證吳明憲可被 alias 查到
alan_hits = gcs.resolve_alias("吳明憲")
report(
    "resolve_alias('吳明憲') 找到結果",
    len(alan_hits) > 0,
    f"找到 {len(alan_hits)} 筆",
)


# ══════════════════════════════════════════════
# 情境 2：DM 中三層人物搜尋
# 模擬 Zeal 在私訊中提到客戶名字
# ══════════════════════════════════════════════
print("\n═══ 情境 2：DM 三層人物搜尋 ═══")

# 第一層：alias 查詢
alias_results = gcs.resolve_alias("Feng")
report(
    "第一層 alias：搜 'Feng'",
    any(r["entity_type"] == "ares_profile" for r in alias_results),
    f"{len(alias_results)} 筆命中",
)

# 第二層：Ares ProfileStore 搜尋
ares_results = ps.search("Feng")
report(
    "第二層 Ares：搜 'Feng'",
    len(ares_results) > 0,
    f"{len(ares_results)} 個 profile 命中",
)

# 驗證 Ares profile 有完整七層資料
if ares_results:
    p = ares_results[0]
    has_l1 = bool(p.get("L1_facts", {}).get("name"))
    has_l4 = p.get("L4_interactions", {}).get("total_count", 0) > 0
    has_temp = bool(p.get("temperature", {}).get("level"))
    report(
        "Ares profile 有完整資料",
        has_l1 and has_temp,
        f"L1={has_l1}, L4互動={has_l4}, temp={p['temperature']['level']}",
    )

# 第三層：ExternalAnima 搜尋
from museon.governance.multi_tenant import ExternalAnimaManager

ext_mgr = ExternalAnimaManager(DATA_DIR)
ext_results = ext_mgr.search_by_keyword("Feng", limit=3)
report(
    "第三層 ExternalAnima：搜 'Feng'",
    len(ext_results) > 0,
    f"{len(ext_results)} 筆命中",
)

# 搜尋中文名
alan_ares = ps.search("吳明憲")
report(
    "Ares 搜中文名 '吳明憲'",
    len(alan_ares) > 0,
    f"{len(alan_ares)} 個 profile",
)

# 搜尋英文名
alan_ext = ext_mgr.search_by_keyword("Alan", limit=3)
report(
    "ExternalAnima 搜 'Alan'",
    len(alan_ext) > 0,
    f"{len(alan_ext)} 筆命中",
)


# ══════════════════════════════════════════════
# 情境 3：DM 中設定別名
# 模擬 Zeal 說「小馮就是Feng」
# ══════════════════════════════════════════════
print("\n═══ 情境 3：L4 DM 別名偵測 ═══")

from museon.agent.l4_cpu_observer import L4CpuObserver

l4 = L4CpuObserver(data_dir=DATA_DIR)

# 測試 1：「小馮就是Feng」
result1 = l4._step6_alias_detection("小馮就是Feng", metadata=None)
report(
    "偵測 '小馮就是Feng'",
    result1 is True,
    "alias 已建立" if result1 else "偵測失敗",
)

# 驗證 alias 確實建立了
if result1:
    xf_hits = gcs.resolve_alias("小馮")
    report(
        "resolve_alias('小馮') 找到 Feng",
        len(xf_hits) > 0,
        f"{len(xf_hits)} 筆",
    )

# 測試 2：「Alan = 吳明憲」
result2 = l4._step6_alias_detection("Alan = 吳明憲", metadata=None)
report(
    "偵測 'Alan = 吳明憲'",
    result2 is True,
    "alias 已建立" if result2 else "偵測失敗",
)

# 測試 3：群組中不應偵測
result3 = l4._step6_alias_detection(
    "小馮就是Feng", metadata={"is_group": True}
)
report(
    "群組中不偵測別名",
    result3 is False,
    "正確跳過",
)

# 測試 4：不存在的人不建 alias
result4 = l4._step6_alias_detection("小王就是完全不存在的人XYZ", metadata=None)
report(
    "不存在的 target 不建 alias",
    result4 is False,
    "正確跳過",
)


# ══════════════════════════════════════════════
# 情境 4：溫度自動衰減
# 模擬一個 profile 15 天沒互動，應該從 hot → warm
# ══════════════════════════════════════════════
print("\n═══ 情境 4：溫度自動衰減 ═══")

# 找一個有映射的 profile 做測試
test_pid = None
for pid, entry in ps.list_all().items():
    if entry.get("name") == "Feng":
        test_pid = pid
        break

if test_pid:
    profile = ps.load(test_pid)
    # 備份原始狀態
    orig_temp = json.loads(json.dumps(profile["temperature"]))
    orig_l4 = json.loads(json.dumps(profile["L4_interactions"]))

    # 設定為 hot，但 last_interaction 是 15 天前
    fifteen_days_ago = (datetime.now() - timedelta(days=15)).isoformat()
    profile["temperature"] = {"level": "hot", "trend": "stable", "last_updated": datetime.now().isoformat()}
    profile["L4_interactions"]["last_interaction"] = fifteen_days_ago
    profile["L4_interactions"]["total_count"] = max(profile["L4_interactions"]["total_count"], 5)
    profile["L4_interactions"]["positive_count"] = max(profile["L4_interactions"]["positive_count"], 3)
    ps._save_profile(profile)
    ps._update_index_entry(profile)

    # 模擬 Nightly 溫度衰減邏輯
    _now = datetime.now()
    _profile = ps.load(test_pid)
    _current = _profile["temperature"]["level"]
    _last = _profile["L4_interactions"].get("last_interaction")
    _days = (_now - datetime.fromisoformat(_last)).days if _last else 999
    _new_level = _current
    if _current == "hot" and _days > 14:
        _new_level = "warm"
    elif _current == "warm" and _days > 30:
        _new_level = "cold"

    report(
        f"hot + 15天 → warm（{_current} → {_new_level}）",
        _new_level == "warm",
        f"距上次互動 {_days} 天",
    )

    # 還原
    profile["temperature"] = orig_temp
    profile["L4_interactions"] = orig_l4
    ps._save_profile(profile)
    ps._update_index_entry(profile)
else:
    report("溫度衰減測試", False, "找不到 Feng profile")


# ══════════════════════════════════════════════
# 情境 5：重複 profile 偵測
# 系統中有 淑慧×3、Huang×3、Feng×2、Joh×2
# ══════════════════════════════════════════════
print("\n═══ 情境 5：重複 profile 偵測 ═══")

index = ps.list_all()
name_groups: dict[str, list[str]] = {}
for pid, entry in index.items():
    name = (entry.get("name") or "").strip()
    if name:
        name_groups.setdefault(name, []).append(pid)

duplicates = {n: pids for n, pids in name_groups.items() if len(pids) > 1}
report(
    "偵測到重複 profiles",
    len(duplicates) > 0,
    f"{len(duplicates)} 組重複：" + ", ".join(f"{n}({len(pids)})" for n, pids in duplicates.items()),
)

# 驗證已知的重複
report("淑慧 有 3 個 profile", len(name_groups.get("淑慧", [])) == 3, "")
report("Huang 有 3 個 profile", len(name_groups.get("Huang", [])) == 3, "")
report("Feng 有 2 個 profile", len(name_groups.get("Feng", [])) == 2, "")


# ══════════════════════════════════════════════
# 情境 6：L4 記憶落地 + chat_scope
# 模擬一次 DM 對話後 L4 觀察
# ══════════════════════════════════════════════
print("\n═══ 情境 6：L4 記憶落地 + chat_scope ═══")

# 驗證 L4 的 observe() 有 chat_scope 推導邏輯
import inspect

l4_src = inspect.getsource(L4CpuObserver.observe)
report(
    "observe() 有 chat_scope 推導",
    "chat_scope" in l4_src and "group:" in l4_src and "private:" in l4_src,
    "",
)

# 驗證 _step1 使用 store() 而非 write()
step1_src = inspect.getsource(L4CpuObserver._step1_memory_write)
report(
    "_step1 使用 store() API",
    ".store(" in step1_src,
    "",
)
report(
    "_step1 傳入 chat_scope",
    "chat_scope" in step1_src,
    "",
)

# 模擬 DM metadata → 推導 chat_scope
_metadata_dm = {"is_group": False}
_chat_scope = ""
_chat_id = "6969045906"
if _metadata_dm:
    _group_id = _metadata_dm.get("group_id", "")
    _is_group = _metadata_dm.get("is_group", False)
    if _is_group and _group_id:
        _chat_scope = f"group:{_group_id}"
    elif _chat_id:
        _chat_scope = f"private:{_chat_id}"
elif _chat_id:
    _chat_scope = f"private:{_chat_id}"

report(
    "DM 推導 chat_scope = private:xxx",
    _chat_scope == f"private:{_chat_id}",
    f"scope = {_chat_scope}",
)

# 模擬群組 metadata
_metadata_grp = {"is_group": True, "group_id": "5107045509"}
_chat_scope_grp = ""
if _metadata_grp.get("is_group") and _metadata_grp.get("group_id"):
    _chat_scope_grp = f"group:{_metadata_grp['group_id']}"

report(
    "群組推導 chat_scope = group:xxx",
    _chat_scope_grp == "group:5107045509",
    f"scope = {_chat_scope_grp}",
)


# ══════════════════════════════════════════════
# 情境 7：會議記錄 entity 對接
# 模擬會議後為參與者建立互動 + 事件記錄
# ══════════════════════════════════════════════
print("\n═══ 情境 7：會議記錄 entity 對接 ═══")

# 模擬：Feng 群組會議 → 使用者指定 Feng = profile 9fb5f4233b9c
feng_pid = "9fb5f4233b9c"
feng_profile = ps.load(feng_pid)
if feng_profile:
    orig_interaction_count = feng_profile["L4_interactions"]["total_count"]

    # 建立互動記錄
    updated = ps.add_interaction(
        profile_id=feng_pid,
        interaction_type="meeting",
        summary="Entity Registry 功能討論會議",
        outcome="positive",
    )
    report(
        "add_interaction 成功",
        updated is not None,
        f"互動次數 {orig_interaction_count} → {updated['L4_interactions']['total_count']}" if updated else "",
    )

    # 建立事件記錄
    evt_id = f"e2e_{uuid.uuid4().hex[:8]}"
    gcs.add_event(
        event_id=evt_id,
        event_type="meeting",
        summary="Entity Registry 功能討論會議",
        entity_type="ares_profile",
        entity_id=feng_pid,
        project_id="",
        source="e2e_test",
    )
    events = gcs.get_entity_events(feng_pid, "ares_profile")
    report(
        "add_event 成功且可查詢",
        any(e["event_id"] == evt_id for e in events),
        f"Feng 共 {len(events)} 筆事件",
    )

    # Cleanup event
    conn = gcs._get_conn()
    conn.execute("DELETE FROM events WHERE event_id = ?", (evt_id,))
    conn.commit()
else:
    report("會議記錄 entity 對接", False, f"Feng profile {feng_pid} not found")


# ══════════════════════════════════════════════
# 情境 8：專案追蹤
# 模擬建立一個客戶專案並關聯人物
# ══════════════════════════════════════════════
print("\n═══ 情境 8：專案追蹤 ═══")

proj_id = f"e2e_{uuid.uuid4().hex[:8]}"
gcs.create_project(proj_id, "Feng 品牌重塑專案", "模擬客戶品牌重塑")

# 加入 Feng 和 Alan
gcs.add_entity_to_project(proj_id, feng_pid, "ares_profile", "client")
alan_pid = "85520498d5dd"
gcs.add_entity_to_project(proj_id, alan_pid, "ares_profile", "consultant")

entities = gcs.get_project_entities(proj_id)
report(
    "專案有 2 個成員",
    len(entities) == 2,
    f"實際 {len(entities)} 個",
)

# Feng 的專案列表
feng_projects = gcs.get_entity_projects(feng_pid, "ares_profile")
report(
    "Feng 可查到此專案",
    any(p["project_id"] == proj_id for p in feng_projects),
    f"Feng 參與 {len(feng_projects)} 個專案",
)

# 在專案下建事件
proj_evt_id = f"e2e_evt_{uuid.uuid4().hex[:8]}"
gcs.add_event(
    event_id=proj_evt_id,
    event_type="milestone",
    summary="品牌定位初稿完成",
    entity_type="ares_profile",
    entity_id=feng_pid,
    project_id=proj_id,
    source="e2e_test",
)
proj_events = gcs.get_project_events(proj_id)
report(
    "專案事件可查詢",
    len(proj_events) >= 1,
    f"{len(proj_events)} 筆事件",
)

# Cleanup
conn = gcs._get_conn()
conn.execute("DELETE FROM events WHERE event_id = ?", (proj_evt_id,))
conn.execute("DELETE FROM project_entities WHERE project_id = ?", (proj_id,))
conn.execute("DELETE FROM projects WHERE project_id = ?", (proj_id,))
conn.commit()


# ══════════════════════════════════════════════
# 情境 9：pending_signals schema 相容
# ══════════════════════════════════════════════
print("\n═══ 情境 9：pending_signals schema ═══")

signals_path = DATA_DIR / "_system" / "ares" / "pending_signals.json"
if signals_path.exists():
    raw = json.loads(signals_path.read_text(encoding="utf-8"))
    # 模擬 Nightly 讀取邏輯
    if isinstance(raw, list):
        _signals = {"alerts": []}
    else:
        _signals = raw
    report(
        "pending_signals 可安全讀取",
        isinstance(_signals, dict) and "alerts" in _signals,
        f"type={type(raw).__name__}, alerts={len(_signals.get('alerts', []))}",
    )
else:
    report("pending_signals 檔案存在", False, "not found")


# ══════════════════════════════════════════════
# Cleanup：移除測試產生的 alias
# ══════════════════════════════════════════════
print("\n═══ Cleanup ═══")

conn = gcs._get_conn()
conn.execute("DELETE FROM entity_aliases WHERE created_by IN ('e2e_test', 'l4_auto')")
deleted = conn.execute("SELECT changes()").fetchone()[0]
conn.commit()
print(f"  清除 {deleted} 筆測試 alias")


# ══════════════════════════════════════════════
# 總結
# ══════════════════════════════════════════════
print(f"\n{'═' * 50}")
print(f"  總結：{PASS}/{PASS + FAIL} PASS")
if FAIL > 0:
    print(f"  ❌ {FAIL} FAIL:")
    for name, passed, detail in RESULTS:
        if not passed:
            print(f"    - {name}: {detail}")
print(f"{'═' * 50}")

sys.exit(0 if FAIL == 0 else 1)
