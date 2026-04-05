"""NightlyStepsSkillMixin — Skill 相關步驟.

包含的步驟：
- _step_skill_forge (Step 6, DORMANT)
- _step_skill_scout (Step 6.5)
- _step_curriculum (Step 7)
- _step_auto_course (Step 7.5)
- _step_workflow_mutation (Step 8, DORMANT)
- _step_skill_vector_reindex (Step 8.6)
- _step_sparse_idf_rebuild (Step 8.7)
- _step_graph_consolidation (Step 9, DORMANT)
- _step_digest_lifecycle (Step 13.8)
- _step_skill_lifecycle (Step 14, DORMANT)
- _step_dept_health (Step 15, DORMANT)
- _step_claude_skill_forge (Step 16, DORMANT)
- _step_tool_discovery (Step 17)
- _step_skill_health_scan (Step 19.5)
- _step_skill_draft_forge (Step 19.6)
- _step_skill_qa_gate (Step 19.7)
"""

import json
import logging
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

TZ_TAIPEI = timezone(timedelta(hours=8))

# Constants
SKILL_FORGE_MIN_CLUSTER = 3
SKILL_FORGE_SIMILARITY_THRESHOLD = 0.5
PLATEAU_MIN_RUNS = 5
PLATEAU_MAX_VARIANCE = 0.5
PLATEAU_MAX_AVG = 7.0
MUTATION_STRATEGIES = ["reorder", "simplify", "amplify", "parallel"]
SKILL_PROMOTE_MIN_SUCCESS = 3
SKILL_DEPRECATE_FAIL_RATE = 0.5
SKILL_ARCHIVE_INACTIVE_DAYS = 30
GRAPH_REPLAY_BOOST = 0.20
GRAPH_DECAY_FACTOR = 0.993
GRAPH_WEAK_EDGE_THRESHOLD = 0.1


def _run_async_safe(coro, timeout: int = 120):
    """同步呼叫 async 協程的橋接函數."""
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    def _execute():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(asyncio.wait_for(coro, timeout=timeout))
        finally:
            try:
                pending = asyncio.all_tasks(loop)
                if pending:
                    loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
            except Exception:
                pass
            loop.close()

    try:
        asyncio.get_running_loop()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_execute)
            return future.result(timeout=timeout + 5)
    except RuntimeError:
        return _execute()


class NightlyStepsSkillMixin:
    """Skill 相關的 Nightly 步驟."""

    # ═══════════════════════════════════════════
    # Step 6: 技能鍛造
    # ═══════════════════════════════════════════

    # DORMANT: removed from _FULL_STEPS, re-enable when data source exists
    # (requires data/_system/memory/shared/L2_ep/ directory with items)
    def _step_skill_forge(self) -> Dict:
        """Step 6: L2_ep 聚類 → L3_procedural 技能."""
        memory_dir = self._workspace / "_system" / "memory" / "shared" / "L2_ep"
        if not memory_dir.exists():
            return {"skipped": "no L2_ep directory"}

        items = []
        for f in memory_dir.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    items.append(json.load(fh))
            except Exception as e:
                logger.debug(f"[NIGHTLY] JSON parse failed (degraded): {e}")

        if len(items) < SKILL_FORGE_MIN_CLUSTER:
            return {"skipped": "not enough L2_ep items", "count": len(items)}

        try:
            from museon.memory.chromosome_index import ChromosomeIndex
            ci = ChromosomeIndex()
            for item in items:
                text = item.get("content", item.get("summary", ""))
                tags = item.get("tags", [])
                ci.add(item.get("id", ""), text, tags=tags)

            clusters = ci.cluster(
                threshold=SKILL_FORGE_SIMILARITY_THRESHOLD,
                min_size=SKILL_FORGE_MIN_CLUSTER,
            )

            # 每個聚類鍛造為 L3_procedural
            forged = 0
            l3_dir = self._workspace / "_system" / "memory" / "shared" / "L3_procedural"
            l3_dir.mkdir(parents=True, exist_ok=True)
            for i, cluster in enumerate(clusters):
                skill = {
                    "type": "L3_procedural",
                    "cluster_id": i,
                    "source_count": len(cluster) if isinstance(cluster, list) else 1,
                    "forged_at": datetime.now(TZ_TAIPEI).isoformat(),
                }
                out = l3_dir / f"skill_{date.today().isoformat()}_{i}.json"
                with open(out, "w", encoding="utf-8") as fh:
                    json.dump(skill, fh, ensure_ascii=False, indent=2)
                forged += 1

            return {"forged": forged, "clusters": len(clusters)}
        except ImportError as e:
            logger.debug(f"[NIGHTLY] degraded: {e}")
            return {"skipped": "ChromosomeIndex not available"}

    # ═══════════════════════════════════════════
    # Step 6.5: SkillForge Scout（探索發現 → 技能改善研究）
    # ═══════════════════════════════════════════

    def _step_skill_scout(self) -> Dict:
        """Step 6.5: 消費 scout_queue 中的待研究項目，產出技能改善草稿."""
        queue_file = self._workspace / "_system" / "bridge" / "scout_queue" / "pending.json"
        if not queue_file.exists():
            return {"skipped": "no scout_queue"}

        try:
            with open(queue_file, "r", encoding="utf-8") as fh:
                queue = json.load(fh)
        except Exception as e:
            logger.debug(f"[NIGHTLY] degraded: {e}")
            return {"skipped": "scout_queue read error"}

        pending = [q for q in queue if q.get("status") == "pending"]
        if not pending:
            return {"skipped": "no pending scout items"}

        # 去重：相同 topic 只保留第一個
        seen_topics: set = set()
        deduped: list = []
        for item in pending:
            topic = item.get("topic", "").strip()
            if topic and topic not in seen_topics:
                seen_topics.add(topic)
                deduped.append(item)
        removed_dupes = len(pending) - len(deduped)

        if not deduped:
            return {"skipped": "all scout items were duplicates", "removed": removed_dupes}

        # 嘗試呼叫 SkillForgeScout
        processed = 0
        errors = []
        try:
            from museon.nightly.skill_forge_scout import SkillForgeScout
            scout = SkillForgeScout(
                brain=self._brain,
                event_bus=self._event_bus,
                workspace=self._workspace,
            )
            # 每次最多處理 3 個（控制 Token 成本）
            results = _run_async_safe(scout.process_queue(max_items=3))
            processed = len(results) if results else 0
        except ImportError as e:
            logger.debug(f"[NIGHTLY] degraded: {e}")
            errors.append("SkillForgeScout not available")
        except Exception as e:
            errors.append(str(e))
            logger.warning(f"SkillForgeScout process_queue failed: {e}")

        # 更新 queue：標記已處理的 + 去重後的
        updated_queue = []
        for item in queue:
            topic = item.get("topic", "").strip()
            if topic in seen_topics:
                if topic not in {d.get("topic", "").strip() for d in updated_queue if d.get("status") == "pending"}:
                    updated_queue.append(item)
            else:
                updated_queue.append(item)

        try:
            with open(queue_file, "w", encoding="utf-8") as fh:
                json.dump(updated_queue, fh, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"scout_queue write-back failed: {e}")

        return {
            "processed": processed,
            "deduped": len(deduped),
            "removed_duplicates": removed_dupes,
            "errors": errors if errors else None,
        }

    # ═══════════════════════════════════════════
    # Step 7: 課程診斷
    # ═══════════════════════════════════════════

    def _step_curriculum(self) -> Dict:
        """Step 7: WEE 熟練度診斷."""
        scores_file = self._workspace / "_system" / "wee" / "proficiency.json"
        if not scores_file.exists():
            # 使用預設分數
            scores = {"speed": 5.0, "quality": 5.0, "alignment": 5.0, "leverage": 5.0}
        else:
            try:
                with open(scores_file, "r", encoding="utf-8") as fh:
                    scores = json.load(fh)
            except Exception as e:
                logger.debug(f"[NIGHTLY] degraded: {e}")
                scores = {"speed": 5.0, "quality": 5.0, "alignment": 5.0, "leverage": 5.0}

        avg = sum(scores.values()) / max(len(scores), 1)
        if avg >= 8.0:
            level = "advanced"
        elif avg >= 5.0:
            level = "intermediate"
        else:
            level = "beginner"

        # 寫入課程處方
        curricula_dir = self._workspace / "_system" / "curricula"
        curricula_dir.mkdir(parents=True, exist_ok=True)
        prescription = {
            "level": level,
            "scores": scores,
            "avg": round(avg, 2),
            "diagnosed_at": datetime.now(TZ_TAIPEI).isoformat(),
        }
        out = curricula_dir / f"diagnosis_{date.today().isoformat()}.json"
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(prescription, fh, ensure_ascii=False, indent=2)

        return {"level": level, "avg_score": round(avg, 2)}

    # ═══════════════════════════════════════════
    # Step 7.5: 自動課程生成 (EXT-10)
    # ═══════════════════════════════════════════

    def _step_auto_course(self) -> Dict:
        """Step 7.5: 根據知識圖譜自動生成/更新課程."""
        try:
            from museon.nightly.course_generator import CourseGenerator

            generator = CourseGenerator(
                workspace=self._workspace,
                event_bus=self._event_bus,
                brain=self._brain,
            )

            # 從最近的課程診斷取得 topic
            curricula_dir = self._workspace / "_system" / "curricula"
            topics = []
            if curricula_dir.exists():
                for f in sorted(curricula_dir.glob("diagnosis_*.json"), reverse=True)[:1]:
                    try:
                        with open(f, "r", encoding="utf-8") as fh:
                            diag = json.load(fh)
                        level = diag.get("level", "intermediate")
                        # 取得低分項目作為課程主題
                        scores = diag.get("scores", {})
                        weak = [k for k, v in scores.items() if v < 5.0]
                        topics.extend(weak[:2])
                    except Exception as e:
                        logger.debug(f"[NIGHTLY] operation failed (degraded): {e}")

            if not topics:
                return {"skipped": "no weak topics identified"}

            # 同步呼叫（CourseGenerator.generate_course 是 async，這裡包裝）
            results = []
            for topic in topics:
                try:
                    course = _run_async_safe(generator.generate_course(topic))
                    results.append({"topic": topic, "course_id": course.get("course_id")})
                except Exception as e:
                    results.append({"topic": topic, "error": str(e)})

            return {"courses_generated": len(results), "results": results}
        except ImportError as e:
            logger.debug(f"[NIGHTLY] degraded: {e}")
            return {"skipped": "course_generator not available"}

    # ═══════════════════════════════════════════
    # Step 8: 工作流突變
    # ═══════════════════════════════════════════

    # DORMANT: removed from _FULL_STEPS, re-enable when data source exists
    # (requires data/_system/wee/workflows/ directory)
    def _step_workflow_mutation(self) -> Dict:
        """Step 8: 高原偵測 + 自動突變."""
        wee_dir = self._workspace / "_system" / "wee" / "workflows"
        if not wee_dir.exists():
            return {"skipped": "no workflows directory"}

        scanned = 0
        plateaus = 0
        mutations = 0

        for wf_dir in wee_dir.iterdir():
            if not wf_dir.is_dir():
                continue

            # 讀取執行記錄
            runs_file = wf_dir / "runs.json"
            if not runs_file.exists():
                scanned += 1
                continue

            try:
                with open(runs_file, "r", encoding="utf-8") as fh:
                    runs = json.load(fh)
            except Exception as e:
                logger.debug(f"[NIGHTLY] degraded: {e}")
                scanned += 1
                continue

            scanned += 1
            scores = [r.get("score", 0) for r in runs if "score" in r]

            if len(scores) < PLATEAU_MIN_RUNS:
                continue

            avg = sum(scores) / len(scores)
            variance = sum((s - avg) ** 2 for s in scores) / len(scores)

            if variance < PLATEAU_MAX_VARIANCE and avg < PLATEAU_MAX_AVG:
                plateaus += 1
                # 自動生成突變方案
                strategy = random.choice(MUTATION_STRATEGIES)
                mutation = {
                    "workflow": wf_dir.name,
                    "strategy": strategy,
                    "avg_score": round(avg, 2),
                    "variance": round(variance, 3),
                    "created_at": datetime.now(TZ_TAIPEI).isoformat(),
                }
                mutation_file = wf_dir / f"mutation_{date.today().isoformat()}.json"
                with open(mutation_file, "w", encoding="utf-8") as fh:
                    json.dump(mutation, fh, ensure_ascii=False, indent=2)
                mutations += 1

        return {
            "workflows_scanned": scanned,
            "plateaus_found": plateaus,
            "mutations_applied": mutations,
        }

    # ═══════════════════════════════════════════
    # Step 8.6: Skill 向量重索引
    # ═══════════════════════════════════════════

    def _step_skill_vector_reindex(self) -> Dict:
        """Step 8.6: Skill 向量重索引——全量重建 skills collection（零 LLM）."""
        try:
            from museon.vector.vector_bridge import VectorBridge
            vb = VectorBridge(workspace=self._workspace, event_bus=self._event_bus)
            result = vb.index_all_skills()
            return {"skill_reindex": result}
        except Exception as e:
            logger.warning(f"Nightly skill reindex failed: {e}")
            return {"skill_reindex": {"error": str(e)}}

    # ═══════════════════════════════════════════
    # Step 8.7: Sparse IDF 重建 + 回填
    # ═══════════════════════════════════════════

    def _step_sparse_idf_rebuild(self) -> Dict:
        """Step 8.7: 重建 BM25 IDF 表 + 回填 sparse collections（零 LLM）.

        從 memories dense collection 建立 IDF → 回填所有 sparse collections。
        """
        try:
            from museon.vector.vector_bridge import VectorBridge
            vb = VectorBridge(workspace=self._workspace, event_bus=self._event_bus)

            # Phase 1: 從 memories 語料建立 IDF
            vocab_size = vb.build_sparse_idf("memories")
            if vocab_size == 0:
                return {"sparse_idf": "skipped — no corpus or jieba unavailable"}

            # Phase 2: 回填各 collection 的 sparse 版本
            backfill_results = {}
            for collection in ("memories", "skills", "crystals"):
                try:
                    count = vb.backfill_sparse(collection, batch_size=50)
                    backfill_results[collection] = count
                except Exception as e:
                    backfill_results[collection] = f"error: {e}"

            return {
                "sparse_idf": {
                    "vocab_size": vocab_size,
                    "backfill": backfill_results,
                }
            }
        except Exception as e:
            logger.warning(f"Nightly sparse IDF rebuild failed: {e}")
            return {"sparse_idf": {"error": str(e)}}

    # ═══════════════════════════════════════════
    # Step 9: 知識圖譜睡眠整合
    # ═══════════════════════════════════════════

    # DORMANT: removed from _FULL_STEPS, re-enable when data source exists
    # (requires data/_system/graph/edges.json and nodes.json)
    def _step_graph_consolidation(self) -> Dict:
        """Step 9: 7 層遺忘機制."""
        from museon.core.event_bus import KNOWLEDGE_GRAPH_UPDATED

        graph_dir = self._workspace / "_system" / "graph"
        if not graph_dir.exists():
            return {"skipped": "no graph directory"}

        edges_file = graph_dir / "edges.json"
        nodes_file = graph_dir / "nodes.json"
        if not edges_file.exists():
            return {"skipped": "no graph edges"}

        try:
            with open(edges_file, "r", encoding="utf-8") as fh:
                edges = json.load(fh)
        except Exception as e:
            logger.debug(f"[NIGHTLY] degraded: {e}")
            return {"skipped": "edges file unreadable"}

        try:
            with open(nodes_file, "r", encoding="utf-8") as fh:
                nodes = json.load(fh)
        except Exception as e:
            logger.debug(f"[NIGHTLY] degraded: {e}")
            nodes = {}

        stats = {
            "replay_boosted": 0,
            "decayed": 0,
            "pruned": 0,
            "archived_nodes": 0,
            "merged_nodes": 0,
        }

        # 1. 重播強化（高頻存取邊 +20%）
        for eid, edge in edges.items():
            access_count = edge.get("access_count", 0)
            if access_count >= 3:  # 高頻閾值
                edge["weight"] = min(1.0, edge.get("weight", 0.5) * (1 + GRAPH_REPLAY_BOOST))
                stats["replay_boosted"] += 1

        # 2. 自然衰減
        for eid, edge in edges.items():
            edge["weight"] = round(edge.get("weight", 0.5) * GRAPH_DECAY_FACTOR, 4)
            stats["decayed"] += 1

        # 3. 修剪弱邊（< 0.1）
        to_prune = [eid for eid, e in edges.items() if e.get("weight", 0) < GRAPH_WEAK_EDGE_THRESHOLD]
        for eid in to_prune:
            del edges[eid]
            stats["pruned"] += 1

        # 4. 垃圾回收（孤立節點歸檔）
        connected_nodes = set()
        for edge in edges.values():
            connected_nodes.add(edge.get("source", ""))
            connected_nodes.add(edge.get("target", ""))

        archive_dir = graph_dir / "archived"
        archive_dir.mkdir(parents=True, exist_ok=True)
        orphans = [nid for nid in nodes if nid not in connected_nodes]
        for nid in orphans:
            archived = nodes.pop(nid)
            archived["archived_at"] = datetime.now(TZ_TAIPEI).isoformat()
            arch_file = archive_dir / f"{nid}.json"
            with open(arch_file, "w", encoding="utf-8") as fh:
                json.dump(archived, fh, ensure_ascii=False, indent=2)
            stats["archived_nodes"] += 1

        # 5. 合併弱節點（簡化：同名節點合併）
        stats["merged_nodes"] = 0

        # 回寫
        with open(edges_file, "w", encoding="utf-8") as fh:
            json.dump(edges, fh, ensure_ascii=False, indent=2)
        with open(nodes_file, "w", encoding="utf-8") as fh:
            json.dump(nodes, fh, ensure_ascii=False, indent=2)

        # WP-06: 發布 KNOWLEDGE_GRAPH_UPDATED（含高品質節點供 SharedAssets 自動發布）
        high_quality_nodes = []
        for nid, node in nodes.items():
            q = node.get("quality", node.get("weight", 0.5))
            if q > 0.6:
                high_quality_nodes.append({
                    "title": node.get("label", node.get("title", nid)),
                    "content": node.get("content", node.get("description", "")),
                    "quality": q,
                    "tags": node.get("tags", []),
                })
        self._publish(KNOWLEDGE_GRAPH_UPDATED, {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "high_quality_nodes": high_quality_nodes[:10],
            **stats,
        })

        return stats

    # ═══════════════════════════════════════════
    # Step 13.8: 消化生命週期
    # ═══════════════════════════════════════════

    def _step_digest_lifecycle(self) -> Dict:
        """Step 13.8: 隔離區生命週期掃描 — 晉升/淘汰/TTL（純 CPU, 0 token）."""
        try:
            from museon.evolution.digest_engine import DigestEngine

            digest = DigestEngine(
                workspace=self._workspace,
                event_bus=self._event_bus,
            )
            result = digest.lifecycle_scan()
            return result
        except Exception as e:
            logger.warning(f"Step 13.8 digest lifecycle failed: {e}")
            return {"error": str(e)}

    # ═══════════════════════════════════════════
    # Step 14: 技能生命週期
    # ═══════════════════════════════════════════

    # DORMANT: removed from _FULL_STEPS, re-enable when data source exists
    # (requires data/_system/memory/shared/L3_procedural/ with .json skill files)
    def _step_skill_lifecycle(self) -> Dict:
        """Step 14: 自動升降級."""
        skills_dir = self._workspace / "_system" / "skills"
        if not skills_dir.exists():
            return {"skipped": "no skills directory"}

        promoted = 0
        deprecated = 0
        archived = 0
        today = date.today()

        for f in skills_dir.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    skill = json.load(fh)

                status = skill.get("status", "experimental")
                success_count = skill.get("success_count", 0)
                fail_count = skill.get("fail_count", 0)
                total_uses = success_count + fail_count
                last_used = skill.get("last_used")

                changed = False

                # experimental → stable: 3+ 次成功
                if status == "experimental" and success_count >= SKILL_PROMOTE_MIN_SUCCESS:
                    skill["status"] = "stable"
                    promoted += 1
                    changed = True

                # stable → deprecated: > 50% 失敗
                elif status == "stable" and total_uses > 0:
                    if fail_count / total_uses > SKILL_DEPRECATE_FAIL_RATE:
                        skill["status"] = "deprecated"
                        deprecated += 1
                        changed = True

                # deprecated → archived: 30 天無使用
                elif status == "deprecated" and last_used:
                    try:
                        last = date.fromisoformat(last_used[:10])
                        if (today - last).days >= SKILL_ARCHIVE_INACTIVE_DAYS:
                            skill["status"] = "archived"
                            archived += 1
                            changed = True
                    except Exception as e:
                        logger.debug(f"[NIGHTLY] operation failed (degraded): {e}")

                if changed:
                    with open(f, "w", encoding="utf-8") as fh:
                        json.dump(skill, fh, ensure_ascii=False, indent=2)

            except Exception as e:
                logger.debug(f"[NIGHTLY] JSON parse failed (degraded): {e}")

        # Phase B: per-skill _meta.json（SkillManager 整合）
        phase_b = {"promoted": 0, "deprecated": 0, "archived": 0}
        try:
            from museon.core.skill_manager import SkillManager
            manager = SkillManager(workspace=self._workspace)
            phase_b = manager.nightly_maintenance()
        except Exception as e:
            phase_b["error"] = str(e)

        return {
            "promoted": promoted + phase_b.get("promoted", 0),
            "deprecated": deprecated + phase_b.get("deprecated", 0),
            "archived": archived + phase_b.get("archived", 0),
        }

    # ═══════════════════════════════════════════
    # Step 15: 部門健康掃描
    # ═══════════════════════════════════════════

    # DORMANT: removed from _FULL_STEPS, re-enable when data source exists
    # (requires data/_system/departments/ directory with dept .json files)
    def _step_dept_health(self) -> Dict:
        """Step 15: 掃描部門健康度."""
        dept_dir = self._workspace / "_system" / "departments"
        if not dept_dir.exists():
            return {"skipped": "no departments directory"}

        departments = []
        for f in dept_dir.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    dept = json.load(fh)
                dept["_file"] = f.name
                departments.append(dept)
            except Exception as e:
                logger.debug(f"[NIGHTLY] department failed (degraded): {e}")

        if not departments:
            return {"skipped": "no departments found"}

        # 計算每個部門健康分數
        results = []
        for dept in departments:
            score = dept.get("health_score", 0.5)
            weaknesses = dept.get("weaknesses", [])
            results.append({
                "dept": dept.get("name", dept["_file"]),
                "score": score,
                "weaknesses": weaknesses,
            })

        # 保存快照
        snapshot_dir = self._workspace / "_system" / "health_snapshots"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot = {
            "date": date.today().isoformat(),
            "departments": results,
        }
        out = snapshot_dir / f"health_{date.today().isoformat()}.json"
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(snapshot, fh, ensure_ascii=False, indent=2)

        # 找出最弱的 2 個部門
        results.sort(key=lambda x: x["score"])
        weakest = results[:2]

        return {"departments_scanned": len(results), "weakest": weakest}

    # ═══════════════════════════════════════════
    # Step 16: Claude 精煉鍛造
    # ═══════════════════════════════════════════

    # DORMANT: removed from _FULL_STEPS, re-enable when data source exists
    # (requires data/_system/memory/shared/L3_procedural/ with .json skill files)
    def _step_claude_skill_forge(self) -> Dict:
        """Step 16: AI 輔助技能精煉（唯一 LLM 步驟）."""
        if not self._brain:
            return {"skipped": "brain not available"}

        l3_dir = self._workspace / "_system" / "memory" / "shared" / "L3_procedural"
        if not l3_dir.exists():
            return {"skipped": "no L3_procedural skills to refine"}

        skills = list(l3_dir.glob("*.json"))
        if not skills:
            return {"skipped": "no skills to refine"}

        # 只精煉最新的（控制 Token 成本）
        refined = 0
        for sf in skills[-3:]:  # 最多精煉 3 個
            try:
                with open(sf, "r", encoding="utf-8") as fh:
                    skill = json.load(fh)
                if not skill.get("refined"):
                    skill["refined"] = True
                    skill["refined_at"] = datetime.now(TZ_TAIPEI).isoformat()
                    with open(sf, "w", encoding="utf-8") as fh:
                        json.dump(skill, fh, ensure_ascii=False, indent=2)
                    refined += 1
            except Exception as e:
                logger.debug(f"[NIGHTLY] operation failed (degraded): {e}")

        # Phase B: 嘗試 LLM 精煉（透過 LLMAdapter，MAX 訂閱方案）
        llm_refined = 0
        try:
            import asyncio
            adapter = getattr(self._brain, "_llm_adapter", None)
            if adapter and refined > 0:
                for sf in skills[-3:]:
                    try:
                        with open(sf, "r", encoding="utf-8") as fh:
                            skill = json.load(fh)
                        if skill.get("refined") and not skill.get("llm_refined"):
                            snippet = json.dumps(skill, ensure_ascii=False)[:500]
                            prompt = (
                                "你是 MUSEON 技能精煉專家。請用一段話"
                                "（不超過 100 字）總結這個技能的核心能力：\n"
                                f"{snippet}"
                            )
                            resp = _run_async_safe(
                                adapter.call(
                                    system_prompt="你是技能精煉專家。",
                                    messages=[{"role": "user", "content": prompt}],
                                    model="sonnet",
                                    max_tokens=200,
                                ),
                                timeout=30,
                            )
                            if resp and resp.text:
                                skill["llm_summary"] = resp.text[:200]
                                skill["llm_refined"] = True
                                skill["llm_refined_at"] = datetime.now(TZ_TAIPEI).isoformat()
                                with open(sf, "w", encoding="utf-8") as fh:
                                    json.dump(skill, fh, ensure_ascii=False, indent=2)
                                llm_refined += 1
                    except Exception as e:
                        logger.debug(f"[NIGHTLY] operation failed (degraded): {e}")
        except Exception as e:
            logger.debug(f"[NIGHTLY] operation failed (degraded): {e}")

        return {
            "refined": refined,
            "llm_refined": llm_refined,
            "total_l3_skills": len(skills),
        }

    # ═══════════════════════════════════════════
    # Step 17: Tool Discovery
    # ═══════════════════════════════════════════

    def _step_tool_discovery(self) -> Dict:
        """Step 17: 工具兵器庫健康檢查 + 自動偵測.

        真正的工具發現（SearXNG 搜尋）由 cron 5am 獨立觸發。
        此步驟只做：
        1. 自動偵測已安裝工具
        2. 健康檢查所有已啟用工具
        3. 讀取最近發現結果
        """
        try:
            from museon.tools.tool_registry import ToolRegistry
            from museon.tools.tool_discovery import ToolDiscovery

            registry = ToolRegistry(workspace=self._workspace)
            discovery = ToolDiscovery(workspace=self._workspace)

            # Phase A: 自動偵測
            detected = registry.auto_detect()

            # Phase B: 健康檢查
            health = registry.check_all_health()
            healthy_count = sum(
                1 for r in health.values() if r.get("healthy")
            )

            # Phase C: 最近發現
            latest = discovery.get_latest_discoveries()

            return {
                "detected": len(detected),
                "healthy": healthy_count,
                "total_tools": len(health),
                "last_discovery": latest.get("timestamp", ""),
                "recommended": len(latest.get("recommended", [])),
            }
        except Exception as e:
            return {"error": str(e)}

    # ═══════════════════════════════════════════
    # Step 19.5: Skill 健康度掃描
    # ═══════════════════════════════════════════

    def _step_skill_health_scan(self) -> Dict:
        """Step 19.5: 掃描所有 Skill 的健康度，偵測退化信號，並更新信任分數."""
        try:
            from museon.nightly.skill_health_tracker import SkillHealthTracker
            from museon.nightly.skill_trust_tracker import SkillTrustTracker
            tracker = SkillHealthTracker(workspace=self._workspace)
            health_map = tracker.scan_all_skills()
            degradation = tracker.detect_degradation()
            tracker.persist()

            # 根據退化信號更新信任分數
            trust_tracker = SkillTrustTracker(workspace=self._workspace)
            trust_updates = 0
            for signal in degradation:
                if signal.severity == "critical":
                    delta = -0.15
                elif signal.severity == "warning":
                    delta = -0.05
                else:
                    delta = -0.02
                trust_tracker.update_trust_score(signal.skill_name, delta=delta)
                trust_updates += 1
            if trust_updates > 0:
                trust_tracker.persist()

            return {
                "skills_scanned": len(health_map),
                "degradation_signals": len(degradation),
                "degraded_skills": [d.skill_name for d in degradation],
                "trust_updates": trust_updates,
            }
        except Exception as e:
            logger.debug(f"Step 19.5 skill_health_scan failed: {e}")
            return {"error": str(e)}

    # ═══════════════════════════════════════════
    # Step 19.6: Skill 草稿鍛造/優化
    # ═══════════════════════════════════════════

    def _step_skill_draft_forge(self) -> Dict:
        """Step 19.6: 從 Scout 筆記或退化信號自動鍛造/優化 Skill 草稿."""
        try:
            from museon.nightly.skill_draft_forger import SkillDraftForger
            forger = SkillDraftForger(workspace=self._workspace)
            result = forger.run()
            return result
        except Exception as e:
            logger.debug(f"Step 19.6 skill_draft_forge failed: {e}")
            return {"error": str(e)}

    # ═══════════════════════════════════════════
    # Step 19.7: Skill QA 品質閘門
    # ═══════════════════════════════════════════

    def _step_skill_qa_gate(self) -> Dict:
        """Step 19.7: 對 pending_qa 狀態的草稿跑三維品質驗證."""
        try:
            from museon.nightly.skill_qa_gate import SkillQAGate
            from pathlib import Path
            gate = SkillQAGate(
                workspace=self._workspace,
                skills_dir=Path.home() / ".claude" / "skills",
            )
            drafts_dir = self._workspace / "_system" / "skills_draft"
            if not drafts_dir.exists():
                return {"drafts_evaluated": 0}

            results = []
            for draft_file in drafts_dir.glob("draft_*.json"):
                try:
                    import json
                    draft = json.loads(draft_file.read_text(encoding="utf-8"))
                    if draft.get("status") != "pending_qa":
                        continue
                    qa_result = gate.evaluate(draft_file)
                    # 更新草稿狀態
                    draft["status"] = "approved" if qa_result.passed else "quarantine"
                    draft["qa_score"] = qa_result.overall_score
                    draft["qa_result"] = {
                        "d1": {"passed": qa_result.d1.passed, "score": qa_result.d1.score},
                        "d2": {"passed": qa_result.d2.passed, "score": qa_result.d2.score},
                        "d3": {"passed": qa_result.d3.passed, "score": qa_result.d3.score},
                    }
                    tmp = draft_file.with_suffix(".tmp")
                    tmp.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
                    tmp.rename(draft_file)
                    results.append({
                        "id": draft.get("id", ""),
                        "passed": qa_result.passed,
                        "score": qa_result.overall_score,
                    })
                except Exception as e:
                    logger.debug(f"QA Gate eval failed for {draft_file.name}: {e}")

            # ── 晨間報告推播 ──
            report = {
                "drafts_evaluated": len(results),
                "passed": sum(1 for r in results if r["passed"]),
                "quarantined": sum(1 for r in results if not r["passed"]),
                "details": results,
            }

            # 讀取 19.5 的健康掃描結果（從 nightly report 回讀）
            health_info = ""
            try:
                report_file = self._workspace / "_system" / "state" / "nightly_report.json"
                if report_file.exists():
                    nr = json.load(open(report_file, "r", encoding="utf-8"))
                    h = nr.get("steps", {}).get("step_19_5_skill_health_scan", {}).get("result", {})
                    if h.get("degradation_signals", 0) > 0:
                        health_info = f"⚠️ {h['degradation_signals']} 個 Skill 退化中: {', '.join(h.get('degraded_skills', []))}\n"
            except Exception:
                pass

            # 有內容才推播
            if results or health_info:
                lines = ["🧬 Skill 演化晨報\n"]
                if health_info:
                    lines.append(health_info)
                passed = report["passed"]
                quarantined = report["quarantined"]
                if passed > 0:
                    names = [r["id"] for r in results if r["passed"]]
                    lines.append(f"✅ {passed} 個草稿通過 QA，等待你核准: {', '.join(names)}")
                if quarantined > 0:
                    lines.append(f"🔒 {quarantined} 個草稿品質不足，已隔離")
                if not results and health_info:
                    lines.append("今夜無新草稿產出。")

                if self._event_bus:
                    try:
                        self._event_bus.publish("PROACTIVE_MESSAGE", {
                            "message": "\n".join(lines),
                            "source": "alert",
                            "timestamp": datetime.now(TZ_TAIPEI).timestamp(),
                        })
                    except Exception:
                        pass

                    # 為每個通過 QA 的草稿發送帶 Inline Keyboard 的核准請求
                    for r in results:
                        if r["passed"]:
                            try:
                                draft_file = drafts_dir / f"{r['id']}.json"
                                if draft_file.exists():
                                    d = json.loads(draft_file.read_text(encoding="utf-8"))
                                    self._event_bus.publish("SKILL_APPROVAL_REQUEST", {
                                        "draft_id": r["id"],
                                        "skill_name": d.get("skill_name", r["id"]),
                                        "qa_score": r.get("score", 0),
                                        "summary": d.get("skill_md_content", "")[:200],
                                    })
                            except Exception:
                                pass

            return report
        except Exception as e:
            logger.debug(f"Step 19.7 skill_qa_gate failed: {e}")
            return {"error": str(e)}
