"""NightlyStepsEcosystemMixin — 生態系與每日摘要相關步驟.

包含的步驟：
- _step_ecosystem_radar (Step 17.5)
- _ecosystem_search_one (helper)
- _step_daily_summary (Step 18)
- _generate_narrative (helper)
- _step_federation_upload (node 模式)
- _step_budget_settlement (Step 0)
- _step_client_profile_update (Step 18.5)
- _step_system_health_audit (Step 18.7)
- _step_ares_bridge_sync (Step 18.6)
- _step_footprint_cleanup (Step 0.1)
"""

import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

TZ_TAIPEI = timezone(timedelta(hours=8))


class NightlyStepsEcosystemMixin:
    """生態系雷達、每日摘要與外部整合相關的 Nightly 步驟."""

    # ═══════════════════════════════════════════
    # Step 17.5: 生態系雷達
    # ═══════════════════════════════════════════

    def _step_ecosystem_radar(self) -> Dict:
        """Step 17.5: 生態系雷達 — 每週一掃描外部工具/Skill 趨勢.

        設計原則：
        - 僅在週一執行（其他日 skip，節省 API 成本）
        - 使用 ResearchEngine 搜尋 3 個外部生態系查詢
        - 每個有價值的結果寫入 morphenix/notes/scout_ecosystem_{ts}.json
        - 餵給 Step 19.6 (skill_draft_forge) 消費

        每週掃描的 3 個查詢：
          1. "Claude skills new popular 2026"
          2. "MCP server trending useful"
          3. "AI agent tools best practices latest"
        """
        from datetime import date as _date

        # 僅週一執行（weekday() == 0）
        today = _date.today()
        if today.weekday() != 0:
            return {
                "skipped": True,
                "reason": f"not_monday (weekday={today.weekday()})",
                "next_run": "next Monday",
            }

        ECOSYSTEM_QUERIES = [
            "Claude skills new popular 2026",
            "MCP server trending useful",
            "AI agent tools best practices latest",
        ]

        notes_dir = self._workspace / "_system" / "morphenix" / "notes"
        notes_dir.mkdir(parents=True, exist_ok=True)

        results = []
        for query in ECOSYSTEM_QUERIES:
            try:
                result = self._ecosystem_search_one(query, notes_dir)
                results.append(result)
            except Exception as e:
                logger.debug(f"Step 17.5 ecosystem_radar query failed ({query!r}): {e}")
                results.append({"query": query, "status": "error", "error": str(e)})

        written = sum(1 for r in results if r.get("status") == "written")
        return {
            "queries_run": len(ECOSYSTEM_QUERIES),
            "notes_written": written,
            "results": [
                {"query": r["query"], "status": r.get("status", "unknown")}
                for r in results
            ],
        }

    def _ecosystem_search_one(self, query: str, notes_dir: Path) -> Dict:
        """對單一查詢執行生態系雷達搜尋，有結果時寫入 scout note.

        Args:
            query: 搜尋查詢字串
            notes_dir: morphenix/notes/ 目錄路徑

        Returns:
            {"query": str, "status": "written"|"no_value"|"error", ...}
        """
        import json
        from datetime import datetime, timezone, timedelta

        TZ8 = timezone(timedelta(hours=8))
        now = datetime.now(TZ8)
        ts = now.strftime("%Y%m%d_%H%M%S")

        try:
            from museon.research.research_engine import ResearchEngine

            engine = ResearchEngine(
                brain=self._brain,
                searxng_url=getattr(self, "_searxng_url", "http://127.0.0.1:8888"),
            )

            import asyncio
            loop = asyncio.new_event_loop()
            try:
                research_result = loop.run_until_complete(
                    engine.research(
                        query=query,
                        context_type="skill",
                        max_rounds=2,
                        language="zh-TW",
                    )
                )
            finally:
                loop.close()

            if not research_result.is_valuable or not research_result.filtered_summary:
                return {"query": query, "status": "no_value"}

            summary_snippet = research_result.filtered_summary[:500]

        except Exception as e:
            # SearXNG 不可用時，寫入基本 note（仍記錄查詢意圖）
            logger.debug(f"Ecosystem radar ResearchEngine failed for {query!r}: {e}")
            summary_snippet = f"(搜尋暫不可用: {e!s:.100})"

        # 寫入 morphenix/notes/scout_ecosystem_{ts}.json
        note_path = notes_dir / f"scout_ecosystem_{ts}.json"
        note = {
            "type": "scout_ecosystem_scan",
            "topic": f"External ecosystem scan: {query}",
            "gap_identified": "External tool/skill discovery",
            "sample_queries": [query],
            "suggested_skill": "external-discovery",
            "source": "ecosystem_radar",
            "created_at": now.isoformat(),
            "auto_propose": True,
            "search_results_summary": summary_snippet,
        }

        try:
            note_path.write_text(
                json.dumps(note, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info(f"EcosystemRadar: wrote note → {note_path.name}")
            return {"query": query, "status": "written", "note": str(note_path.name)}
        except Exception as e:
            logger.error(f"EcosystemRadar: note write failed: {e}")
            return {"query": query, "status": "error", "error": str(e)}

    # ═══════════════════════════════════════════
    # Step 18: 每日摘要生成
    # ═══════════════════════════════════════════

    def _step_daily_summary(self) -> Dict:
        """Step 18: 每日摘要生成 — 從 activity log + memory 頻道產生一則快照.

        產出儲存到 data/daily_summaries/YYYY-MM-DD.json
        """
        try:
            from datetime import date as _date
            from museon.core.activity_logger import ActivityLogger

            today = _date.today().isoformat()
            summary_dir = self._workspace / "daily_summaries"
            summary_dir.mkdir(parents=True, exist_ok=True)
            summary_path = summary_dir / f"{today}.json"

            # 如果今天已經有摘要就跳過
            if summary_path.exists():
                return {"skipped": True, "date": today, "reason": "already_exists"}

            # 收集活動日誌
            al = ActivityLogger(data_dir=str(self._workspace))
            today_events = al.today_events()

            # 收集記憶頻道內容
            memory_dir = self._workspace / "memory"
            now = _date.today()
            date_path = memory_dir / str(now.year) / f"{now.month:02d}" / f"{now.day:02d}"
            channels = {}
            if date_path.exists():
                for md_file in date_path.glob("*.md"):
                    channel = md_file.stem
                    content = md_file.read_text(encoding="utf-8").strip()
                    if content:
                        channels[channel] = content[:2000]  # 截取前 2000 字

            # 組裝摘要
            event_summary = []
            for evt in today_events[:50]:
                event_summary.append({
                    "ts": evt.get("ts", ""),
                    "event": evt.get("event", ""),
                    "source": evt.get("source", ""),
                })

            summary = {
                "date": today,
                "generated_at": datetime.now().isoformat(),
                "event_count": len(today_events),
                "events_digest": event_summary,
                "memory_channels": list(channels.keys()),
                "memory_excerpts": channels,
                "narrative": self._generate_narrative(today_events, channels),
            }

            summary_path.write_text(
                json.dumps(summary, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return {"date": today, "event_count": len(today_events), "channels": len(channels)}

        except Exception as e:
            return {"error": str(e)}

    def _generate_narrative(self, events: list, channels: dict) -> str:
        """Generate a brief narrative summary from events + memory channels.

        For now uses a simple template. Can be upgraded to LLM later.
        """
        lines = []
        if events:
            event_types = {}
            for evt in events:
                etype = evt.get("event", "unknown")
                event_types[etype] = event_types.get(etype, 0) + 1
            top = sorted(event_types.items(), key=lambda x: -x[1])[:5]
            lines.append(f"今日共 {len(events)} 個活動事件。")
            for etype, count in top:
                lines.append(f"  - {etype}: {count} 次")

        if channels:
            lines.append(f"記錄了 {len(channels)} 個記憶頻道。")
            for ch in channels:
                excerpt = channels[ch][:80].replace("\n", " ")
                lines.append(f"  - {ch}: {excerpt}...")

        if not lines:
            lines.append("今日尚無顯著活動。")

        return "\n".join(lines)

    def _step_federation_upload(self) -> Dict:
        """Federation 未實作，保留 node 模式進入點供未來擴充."""
        return {"skipped": "federation not implemented"}

    # ═══════════════════════════════════════════
    # Step 0: Token 預算日結算
    # ═══════════════════════════════════════════

    def _step_budget_settlement(self) -> Dict:
        """Step 0: 每日呼叫統計摘要（MAX 訂閱方案 — 無 per-token 計費）.

        v3: 改為記錄每日呼叫次數、模型分布，不再做 token 預算結算。
        """
        # 嘗試從 BudgetMonitor 取得統計（僅記錄用途）
        try:
            if hasattr(self, '_brain') and self._brain and hasattr(self._brain, 'budget_monitor'):
                bm = self._brain.budget_monitor
                if bm:
                    stats = bm.get_usage_stats()
                    return {
                        "mode": "max_subscription",
                        "daily_calls": sum(
                            stats.get("models", {}).get(m, {}).get("calls", 0)
                            for m in ("sonnet", "haiku")
                        ),
                        "model_distribution": {
                            m: stats.get("models", {}).get(m, {}).get("calls", 0)
                            for m in ("sonnet", "haiku")
                        },
                        "daily_tokens": stats.get("used", 0),
                    }
        except Exception as e:
            logger.warning(f"Budget stats read failed: {e}")

        return {"mode": "max_subscription", "skipped": "no_budget_monitor"}

    # ═══════════════════════════════════════════
    # Step 18.5: 客戶互動萃取
    # ═══════════════════════════════════════════

    def _step_client_profile_update(self) -> Dict:
        """Step 18.5: 從 dispatch/completed 萃取客戶互動摘要.

        管線接通：
        - dispatch/completed/*.json（最完整的對話紀錄）→ 讀取
        - external_users/{user_id}.json → 更新 context_summary
        - group_context.db clients 表 → 更新 personality_notes
        """
        import json
        import glob
        from datetime import datetime, timedelta

        stats = {"dispatches_scanned": 0, "profiles_updated": 0, "clients_updated": 0}

        dispatch_dir = self._workspace / "dispatch" / "completed"
        if not dispatch_dir.exists():
            return {"skipped": "no dispatch/completed directory"}

        # 只掃最近 3 天
        cutoff = datetime.now() - timedelta(days=3)

        # 收集每個 session 的互動摘要
        session_interactions: dict = {}  # session_id → [user_request snippets]

        for dfile in sorted(dispatch_dir.glob("*.json")):
            stats["dispatches_scanned"] += 1
            try:
                data = json.loads(dfile.read_text(encoding="utf-8"))
                created = data.get("created_at", "")
                if created:
                    try:
                        dt = datetime.fromisoformat(created)
                        if dt < cutoff:
                            continue
                    except Exception:
                        pass

                session_id = data.get("session_id", "")
                user_req = data.get("user_request", "")[:500]
                if session_id and user_req:
                    session_interactions.setdefault(session_id, []).append(user_req)

            except Exception:
                continue

        # 從 group_context.db 的 clients 表讀取現有用戶
        # 用 dispatch 中的 session_id 反查 group_id → 找到互動的用戶
        try:
            from museon.governance.group_context import get_group_context_store
            gc_store = get_group_context_store()
            conn = gc_store._get_conn()

            # 取最近 3 天活躍的 clients
            active_clients = conn.execute("""
                SELECT DISTINCT c.user_id, c.display_name, c.personality_notes
                FROM clients c
                JOIN messages m ON c.user_id = m.user_id
                WHERE m.created_at > datetime('now', '-3 days')
                  AND c.user_id != 'bot'
                ORDER BY c.last_seen DESC
                LIMIT 20
            """).fetchall()

            for client in active_clients:
                user_id = client[0]
                display_name = client[1] or ""
                existing_notes = client[2] or ""

                # 取此用戶最近的訊息做互動摘要
                recent_msgs = conn.execute("""
                    SELECT text FROM messages
                    WHERE user_id = ? AND created_at > datetime('now', '-7 days')
                    ORDER BY created_at DESC LIMIT 20
                """, (user_id,)).fetchall()

                if not recent_msgs:
                    continue

                # 簡單摘要：取最近訊息的關鍵詞
                msg_texts = [m[0] for m in recent_msgs if m[0]]
                topics = set()
                for t in msg_texts[:10]:
                    # 取每則訊息的前 30 字作為話題
                    snippet = t[:30].strip()
                    if snippet and len(snippet) > 3:
                        topics.add(snippet)

                if topics:
                    topic_summary = "、".join(list(topics)[:5])
                    new_notes = f"[{datetime.now().strftime('%m/%d')}] 近期話題：{topic_summary}"

                    # 追加而非覆蓋（保留歷史，最多 500 字）
                    if existing_notes:
                        combined = f"{new_notes}\n{existing_notes}"[:500]
                    else:
                        combined = new_notes[:500]

                    conn.execute(
                        "UPDATE clients SET personality_notes = ? WHERE user_id = ?",
                        (combined, user_id),
                    )
                    stats["clients_updated"] += 1

            conn.commit()
        except Exception as e:
            logger.warning(f"[NIGHTLY] Client profile update failed: {e}")

        # 更新 external_users 的 context_summary（如果是空的）
        try:
            from museon.governance.multi_tenant import ExternalAnimaManager
            ext_mgr = ExternalAnimaManager(self._workspace)
            for p in ext_mgr.users_dir.glob("*.json"):
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    if data.get("context_summary"):
                        continue  # 已有摘要，跳過
                    user_id = data.get("user_id", p.stem)
                    display_name = data.get("display_name", "")
                    if not display_name:
                        continue

                    # 從 group_context.db 取此用戶的訊息
                    recent = gc_store._get_conn().execute("""
                        SELECT text FROM messages
                        WHERE user_id = ? ORDER BY created_at DESC LIMIT 10
                    """, (user_id,)).fetchall()

                    if recent:
                        snippets = [r[0][:50] for r in recent if r[0]][:5]
                        if snippets:
                            data["context_summary"] = f"{display_name} 的近期話題：{'；'.join(snippets)}"
                            ext_mgr.save(user_id, data)
                            stats["profiles_updated"] += 1
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"[NIGHTLY] External user update failed: {e}")

        if stats["clients_updated"] > 0 or stats["profiles_updated"] > 0:
            logger.info(
                f"[NIGHTLY] Client profile update: clients={stats['clients_updated']}, "
                f"external_users={stats['profiles_updated']}"
            )

        return stats

    # ═══════════════════════════════════════════
    # Step 18.7: 六層系統健康檢查
    # ═══════════════════════════════════════════

    def _step_system_health_audit(self) -> Dict:
        """Step 18.7: 全系統六層健康檢查.

        先嘗試讀取快取（< 2 小時內的 shared_board.json），避免重複 subprocess。
        快取不新鮮或不存在時，fallback 重跑 full_system_audit。
        如果有 CRITICAL/HIGH 問題，記錄到 shared_board 供 MuseDoctor 巡邏時處理。
        """
        import time

        # ── 嘗試讀取快取 ──
        cache_dir = self._workspace / "_system" / "doctor"
        shared_board_path = cache_dir / "shared_board.json"
        _CACHE_TTL = 2 * 3600  # 2 小時

        if shared_board_path.exists():
            try:
                cache_mtime = shared_board_path.stat().st_mtime
                if (time.time() - cache_mtime) < _CACHE_TTL:
                    with open(shared_board_path, encoding="utf-8") as f:
                        board = json.load(f)
                    nightly_entry = board.get("nightly") or {}
                    summary = nightly_entry.get("summary", "")
                    # 快取有效：直接返回摘要，跳過重跑
                    logger.info(f"[NIGHTLY 18.7] Using cached audit (age < 2h): {summary}")
                    return {"cached": True, "summary": summary}
            except Exception as cache_err:
                logger.debug(f"[NIGHTLY 18.7] Cache read failed, will re-run audit: {cache_err}")

        # ── Fallback：重跑 full_system_audit ──
        try:
            import subprocess
            import sys
            script = self._workspace.parent / "scripts" / "full_system_audit.py"
            if not script.exists():
                # 嘗試相對路徑
                script = Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "full_system_audit.py"
            if not script.exists():
                return {"skipped": "full_system_audit.py not found"}

            r = subprocess.run(
                [sys.executable, str(script)],
                capture_output=True, text=True, timeout=60,
                cwd=str(script.parent.parent),
            )
            output = r.stdout

            # 解析結果
            import re
            health_match = re.search(r"系統狀態:\s*\x1b\[\d+m(\w+)", output)
            health = health_match.group(1) if health_match else "UNKNOWN"

            pass_match = re.search(r"通過:\s*\x1b\[\d+m(\d+)", output)
            fail_match = re.search(r"失敗:\s*\x1b\[\d+m(\d+)", output)
            warn_match = re.search(r"警告:\s*\x1b\[\d+m(\d+)", output)

            stats = {
                "health": health,
                "pass": int(pass_match.group(1)) if pass_match else 0,
                "fail": int(fail_match.group(1)) if fail_match else 0,
                "warn": int(warn_match.group(1)) if warn_match else 0,
            }

            if health not in ("HEALTHY",):
                logger.warning(f"[NIGHTLY] System health: {health} (fail={stats['fail']}, warn={stats['warn']})")

            return stats
        except Exception as e:
            logger.warning(f"[NIGHTLY] System health audit failed: {e}")
            return {"skipped": str(e)}

    # ═══════════════════════════════════════════
    # Step 18.6: Ares 橋接同步
    # ═══════════════════════════════════════════

    def _step_ares_bridge_sync(self) -> Dict:
        """Step 18.6: 將 external_users 同步到 Ares ProfileStore.

        接在 Step 18.5 之後——18.5 更新 external_users，18.6 橋接到 Ares。
        """
        try:
            from museon.athena.profile_store import ProfileStore
            from museon.athena.external_bridge import ExternalBridge

            store = ProfileStore(self._workspace)
            ext_dir = self._workspace / "_system" / "external_users"
            if not ext_dir.exists():
                ext_dir = self._workspace / "data" / "_system" / "external_users"
            if not ext_dir.exists():
                return {"skipped": "external_users directory not found"}

            bridge = ExternalBridge(store, ext_dir)
            stats = bridge.sync_all()
            if stats["created"] > 0 or stats["updated"] > 0:
                logger.info(
                    f"[NIGHTLY] Ares bridge sync: created={stats['created']}, "
                    f"updated={stats['updated']}, errors={stats['errors']}"
                )

            # ── 溫度自動衰減 ──
            try:
                _ps = ProfileStore(self._workspace)
                _index = _ps.list_all()
                _decay_count = 0
                _now = datetime.now()
                for _pid, _entry in _index.items():
                    _profile = _ps.load(_pid)
                    if not _profile:
                        continue
                    _temp = _profile.get("temperature", {})
                    _current = _temp.get("level", "new")
                    # 只衰減 hot 和 warm，cold 和 new 不動
                    if _current not in ("hot", "warm"):
                        continue
                    _last = _profile.get("L4_interactions", {}).get("last_interaction")
                    if not _last:
                        continue
                    try:
                        _days = (_now - datetime.fromisoformat(_last)).days
                    except Exception:
                        continue
                    # 衰減規則：hot → warm (14天), warm → cold (30天)
                    _new_level = _current
                    if _current == "hot" and _days > 14:
                        _new_level = "warm"
                    elif _current == "warm" and _days > 30:
                        _new_level = "cold"
                    if _new_level != _current:
                        _profile["temperature"] = {
                            "level": _new_level,
                            "trend": "falling",
                            "last_updated": _now.isoformat(),
                        }
                        _ps._save_profile(_profile)
                        _ps._update_index_entry(_profile)
                        _decay_count += 1
                        logger.info(
                            f"[NIGHTLY] Temperature decay: {_entry.get('name', _pid)} "
                            f"{_current} → {_new_level}"
                        )
                if _decay_count > 0:
                    logger.info(f"[NIGHTLY] Temperature decay: {_decay_count} profiles updated")
                stats["temperature_decay"] = _decay_count
            except Exception as e:
                logger.warning(f"[NIGHTLY] Temperature decay failed: {e}")

            # ── 自動建立 alias（從 ExternalAnima display_name）──
            try:
                from museon.governance.group_context import GroupContextStore
                _gcs = GroupContextStore(self.data_dir)
                _ext_map = bridge._load_map()  # {telegram_uid: ares_profile_id}
                _alias_count = 0
                for _tg_uid, _ares_pid in _ext_map.items():
                    # 讀 ExternalAnima 取 display_name
                    _ext_path = bridge.ext_dir / f"{_tg_uid}.json"
                    if not _ext_path.exists():
                        continue
                    try:
                        _ext_data = json.loads(_ext_path.read_text(encoding="utf-8"))
                        _display_name = _ext_data.get("display_name", "")
                        if not _display_name or _display_name.startswith("User_"):
                            continue
                        # 建 display_name → ares_profile alias
                        _gcs.add_alias(_display_name, _ares_pid, "ares_profile", "nightly_auto")
                        # 建 display_name → telegram_uid alias
                        _gcs.add_alias(_display_name, _tg_uid, "telegram_uid", "nightly_auto")
                        _alias_count += 1
                    except Exception:
                        continue
                if _alias_count > 0:
                    logger.info(f"[NIGHTLY] Auto-alias: {_alias_count} names synced")
                stats["auto_aliases"] = _alias_count
            except Exception as e:
                logger.warning(f"[NIGHTLY] Auto-alias failed: {e}")

            # ── 從群組名稱建立 alias ──
            try:
                _group_alias_count = 0
                _owner_ids = {"6969045906", "boss", "bot"}  # Owner + Bot 的 UID
                conn = _gcs._get_conn()
                groups = conn.execute("SELECT group_id, title FROM groups").fetchall()
                for _grp in groups:
                    _title = _grp[1] or ""
                    # 解析 "Museon x 客戶名" 或 "MUSEON 測試 x 客戶名" pattern
                    import re as _re
                    _match = _re.search(r'museon\s*(?:測試\s*)?x\s+(.+)', _title, _re.IGNORECASE)
                    if not _match:
                        continue
                    _client_name = _match.group(1).strip()
                    if not _client_name:
                        continue
                    # 找該群組的非 Owner 成員
                    _members = conn.execute(
                        "SELECT user_id FROM group_members WHERE group_id = ?",
                        (_grp[0],),
                    ).fetchall()
                    for _mem in _members:
                        _uid = str(_mem[0])
                        if _uid in _owner_ids:
                            continue
                        # 建 alias: 群組名中的客戶名 → 該成員
                        _gcs.add_alias(_client_name, _uid, "telegram_uid", "nightly_group_name")
                        # 如果有 ares profile 映射，也建
                        _ares_pid = _ext_map.get(_uid)
                        if _ares_pid:
                            _gcs.add_alias(_client_name, _ares_pid, "ares_profile", "nightly_group_name")
                        _group_alias_count += 1
                if _group_alias_count > 0:
                    logger.info(f"[NIGHTLY] Group-name alias: {_group_alias_count} names synced")
                stats["group_name_aliases"] = _group_alias_count
            except Exception as e:
                logger.warning(f"[NIGHTLY] Group-name alias failed: {e}")

            # ── 重複 profile 偵測 ──
            try:
                _index = _ps.list_all() if '_ps' in dir() else ProfileStore(self._workspace).list_all()
                _name_groups: dict = {}
                for _pid, _entry in _index.items():
                    _name = (_entry.get("name") or "").strip()
                    if _name:
                        _name_groups.setdefault(_name, []).append(_pid)
                _duplicates = {n: pids for n, pids in _name_groups.items() if len(pids) > 1}
                if _duplicates:
                    _dup_summary = "; ".join(f"{n}({len(pids)})" for n, pids in _duplicates.items())
                    logger.warning(f"[NIGHTLY] Duplicate profiles detected: {_dup_summary}")
                    # 寫入 pending_signals 供推播
                    try:
                        _signals_path = self.data_dir / "_system" / "ares" / "pending_signals.json"
                        _signals = json.loads(_signals_path.read_text(encoding="utf-8")) if _signals_path.exists() else {"alerts": []}
                        if isinstance(_signals, list):
                            _signals = {"alerts": []}  # 舊格式相容：捨棄 list 重建 dict
                        # 避免重複 alert（每天只發一次）
                        _today = datetime.now().strftime("%Y-%m-%d")
                        _existing_dup_alerts = [a for a in _signals.get("alerts", []) if a.get("type") == "duplicate_profiles" and a.get("date") == _today]
                        if not _existing_dup_alerts:
                            _signals.setdefault("alerts", []).append({
                                "type": "duplicate_profiles",
                                "date": _today,
                                "summary": f"偵測到重複人物檔案：{_dup_summary}",
                                "details": {n: pids for n, pids in _duplicates.items()},
                                "action": "建議使用者確認是否為同一人並合併",
                            })
                            _signals_path.parent.mkdir(parents=True, exist_ok=True)
                            _tmp = _signals_path.with_suffix(".tmp")
                            _tmp.write_text(json.dumps(_signals, ensure_ascii=False, indent=2), encoding="utf-8")
                            _tmp.rename(_signals_path)
                    except Exception as _se:
                        logger.debug(f"[NIGHTLY] Duplicate alert write failed: {_se}")
                stats["duplicate_profiles"] = len(_duplicates) if '_duplicates' in dir() else 0
            except Exception as e:
                logger.warning(f"[NIGHTLY] Duplicate detection failed: {e}")

            return stats
        except Exception as e:
            logger.warning(f"[NIGHTLY] Ares bridge sync failed: {e}")
            return {"skipped": str(e)}

    # ═══════════════════════════════════════════
    # Step 0.1: 足跡清理
    # ═══════════════════════════════════════════

    def _step_footprint_cleanup(self) -> Dict:
        """Step 0.1: 足跡清理 — L1 30天 / L2 90天."""
        try:
            from museon.governance.footprint import FootprintStore
            store = FootprintStore(data_dir=self._workspace)
        except Exception as e:
            return {"skipped": f"FootprintStore not available: {e}"}

        result = store.cleanup()
        stats = store.get_stats()

        return {
            "l1_removed": result.get("l1_removed", 0),
            "l2_removed": result.get("l2_removed", 0),
            "remaining": stats,
        }
