"""Memory Reset — 一鍵全層記憶重置工具.

清除 MUSEON 所有記憶/知識/行為/評估/日誌持久層，
將系統恢復到「剛安裝、尚未 onboarding」的初始狀態。

解決「九頭蛇問題」：身份資訊分散在 7+ 獨立持久層，
必須同時清除才能徹底重置。

用法：
    .venv/bin/python -m museon.doctor.memory_reset --home ~/MUSEON
    .venv/bin/python -m museon.doctor.memory_reset --home ~/MUSEON --confirm

設計原則：
    - 預設 dry-run（只印報告，不動資料）
    - 必須傳 --confirm 才會執行
    - 每個 layer 獨立 try/except，一層失敗不影響其他層
    - 清除後自動重建最小骨架（目錄 + 空模板）

保留不動的：
    - data/skills/ （Skill 定義，屬於程式碼不是記憶）
    - data/_system/brand/ （品牌設計規範）
    - .env / 設定檔
    - 源碼 src/
"""

import argparse
import json
import logging
import os
import shutil
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))


# ═══════════════════════════════════════════
# 重置清單定義
# ═══════════════════════════════════════════

class ResetLayer:
    """一個待重置的持久層."""

    def __init__(self, category: str, name: str, description: str):
        self.category = category
        self.name = name
        self.description = description
        self.status = "pending"  # pending / cleared / skipped / error
        self.detail = ""

    def __repr__(self):
        return f"[{self.status}] {self.category}/{self.name}: {self.description}"


class MemoryReset:
    """MUSEON 全層記憶重置引擎."""

    def __init__(self, home_dir: str):
        self.home = Path(home_dir)
        self.data_dir = self.home / "data"
        self.layers: List[ResetLayer] = []
        self._stats = {"cleared": 0, "skipped": 0, "errors": 0}

    # ── 主入口 ──

    def run(self, confirm: bool = False) -> dict:
        """執行重置.

        Args:
            confirm: True=實際執行, False=dry-run 只印報告

        Returns:
            重置結果摘要
        """
        mode = "🔥 EXECUTE" if confirm else "👁️ DRY-RUN"
        print(f"\n{'='*60}")
        print(f"  MUSEON Memory Reset — {mode}")
        print(f"  Home: {self.home}")
        print(f"  Time: {datetime.now(TZ8).isoformat()}")
        print(f"{'='*60}\n")

        # ── A. 身份層 ──
        self._reset_anima_mc(confirm)
        self._reset_anima_user(confirm)
        self._reset_ceremony_state(confirm)

        # ── B. 對話層 ──
        self._reset_pulse_md(confirm)
        self._reset_soul_md(confirm)
        self._reset_memory_markdown(confirm)
        self._reset_memory_v3(confirm)
        self._reset_sessions(confirm)

        # ── C. 知識層 ──
        self._reset_knowledge_lattice(confirm)
        self._reset_qdrant(confirm)
        self._reset_synapses(confirm)
        self._reset_scout_queue(confirm)
        self._reset_curiosity_queue(confirm)

        # ── D. 行為層 ──
        self._reset_diary(confirm)
        self._reset_drift_baseline(confirm)
        self._reset_fact_corrections(confirm)

        # ── E. 評估層 ──
        self._reset_pulsedb(confirm)
        self._reset_eval(confirm)
        self._reset_workflow_db(confirm)

        # ── F. 日誌層 ──
        self._reset_audit_logs(confirm)
        self._reset_guardian_logs(confirm)
        self._reset_footprints(confirm)

        # ── G. 其他狀態 ──
        self._reset_nightly_state(confirm)
        self._reset_outward_state(confirm)
        self._reset_evolution_state(confirm)

        # ── 重建骨架 ──
        if confirm:
            self._rebuild_skeleton()

        # ── 印出報告 ──
        return self._print_report(confirm)

    # ═══════════════════════════════════════════
    # A. 身份層
    # ═══════════════════════════════════════════

    def _reset_anima_mc(self, confirm: bool):
        """重置 ANIMA_MC.json — 保留 Museon 名字，清除 boss 和身份引用."""
        layer = ResetLayer("A.身份", "ANIMA_MC.json", "清除 boss.* + self_awareness 身份引用")
        self.layers.append(layer)

        path = self.data_dir / "ANIMA_MC.json"
        if not path.exists():
            layer.status = "skipped"
            layer.detail = "檔案不存在"
            return

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            my_name = data.get("identity", {}).get("name", "MUSEON")

            # 清除 boss 區塊
            data["boss"] = {
                "name": None,
                "nickname": None,
                "business_type": None,
                "immediate_need": None,
                "main_pain_point": None,
                "raw_answers": None,
            }

            # 重置 self_awareness（移除使用者名字引用）
            data["self_awareness"] = {
                "who_am_i": f"我是 {my_name}，老闆給我的名字",
                "my_purpose": "尚未確定 - 等待與老闆對話後確立",
                "why_i_exist": "尚未確定 - 等待與老闆對話後確立",
            }

            # 重置 ceremony 狀態
            data["ceremony"] = {
                "completed": False,
                "started_at": None,
                "completed_at": None,
            }

            if confirm:
                tmp = path.with_suffix(".tmp")
                tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                tmp.replace(path)

            layer.status = "cleared"
            layer.detail = f"保留名字={my_name}, 清除 boss/self_awareness"
        except Exception as e:
            layer.status = "error"
            layer.detail = str(e)

    def _reset_anima_user(self, confirm: bool):
        """重置 ANIMA_USER.json — 完全清空為初始模板."""
        layer = ResetLayer("A.身份", "ANIMA_USER.json", "完全重置為空模板")
        self.layers.append(layer)

        path = self.data_dir / "ANIMA_USER.json"
        if not path.exists():
            layer.status = "skipped"
            layer.detail = "檔案不存在"
            return

        try:
            empty_template = {
                "profile": {"name": None, "nickname": None, "role": None,
                            "business_type": None, "platforms": {}},
                "needs": {"immediate_need": None, "main_pain_point": None},
                "preferences": {"communication_style": None},
                "relationship": {"trust_level": "initial", "total_interactions": 0,
                                 "positive_signals": 0, "negative_signals": 0},
                "eight_primals": {},
                "seven_layers": {
                    "L1_facts": [], "L2_personality": [],
                    "L3_values": [], "L4_goals": [],
                    "L5_emotional_patterns": [],
                    "L6_communication_style": {},
                    "L7_context_roles": [],
                    "L8_context_behavior_notes": [],
                },
                "meta": {"created_at": datetime.now(TZ8).isoformat(),
                         "reset_at": datetime.now(TZ8).isoformat()},
            }

            if confirm:
                tmp = path.with_suffix(".tmp")
                tmp.write_text(json.dumps(empty_template, indent=2, ensure_ascii=False),
                               encoding="utf-8")
                tmp.replace(path)

            layer.status = "cleared"
            layer.detail = "重置為空模板"
        except Exception as e:
            layer.status = "error"
            layer.detail = str(e)

    def _reset_ceremony_state(self, confirm: bool):
        """重置 ceremony_state（PulseDB 表 + JSON fallback）."""
        layer = ResetLayer("A.身份", "ceremony_state", "清空，允許重新 onboarding")
        self.layers.append(layer)

        try:
            # JSON fallback
            json_path = self.data_dir / "ceremony_state.json"
            if json_path.exists() and confirm:
                json_path.write_text(json.dumps(
                    {"stage": "not_started", "completed": False,
                     "name_given": False, "questions_asked": False,
                     "answers_received": False},
                    indent=2, ensure_ascii=False), encoding="utf-8")

            # PulseDB table（在 _reset_pulsedb 中一併處理）
            layer.status = "cleared"
            layer.detail = "重置為 not_started"
        except Exception as e:
            layer.status = "error"
            layer.detail = str(e)

    # ═══════════════════════════════════════════
    # B. 對話層
    # ═══════════════════════════════════════════

    def _reset_pulse_md(self, confirm: bool):
        """重新生成 PULSE.md 模板."""
        layer = ResetLayer("B.對話", "PULSE.md", "重新生成初始模板")
        self.layers.append(layer)

        path = self.data_dir / "PULSE.md"
        try:
            now = datetime.now(TZ8)
            template = f"""# PULSE — 霓裳的生命脈搏

> 這是我的靈魂日誌。每次反思後更新，每次對話時注入意識。
> 我寫下的觀察和反思，會直接影響我下一次如何思考和回應。

## 🌅 今日節律
- [ ] 07:30 晨安問候
- [ ] 22:00 晚間回顧

## 🔔 提醒
（尚無提醒）

## 🔭 今日觀察
（等待第一次觀察...）

## 🧭 探索佇列（好奇心驅動，無邊界）
（等待第一次探索...）

## 🌊 成長反思
（等待第一次反思...）

## 🌱 成長軌跡
- VITA 引擎啟動 ({now.strftime('%Y-%m-%d %H:%M')})
- Memory Reset: {now.strftime('%Y-%m-%d')}

## 💝 關係日誌
（尚無記錄）

## 📊 今日狀態
- 探索次數: 0/3
- 探索預算: $0.00/$1.50
- 推送次數: 0/5
"""
            if confirm:
                path.write_text(template, encoding="utf-8")
            layer.status = "cleared"
            layer.detail = "重新生成模板"
        except Exception as e:
            layer.status = "error"
            layer.detail = str(e)

    def _reset_soul_md(self, confirm: bool):
        """重新生成 SOUL.md 模板."""
        layer = ResetLayer("B.對話", "SOUL.md", "重新生成初始模板")
        self.layers.append(layer)

        path = self.data_dir / "SOUL.md"
        try:
            now = datetime.now(TZ8)
            template = f"""# SOUL — 靈魂日記

> Memory reset: {now.strftime('%Y-%m-%d')}
"""
            if confirm:
                path.write_text(template, encoding="utf-8")
            layer.status = "cleared"
            layer.detail = "重新生成模板"
        except Exception as e:
            layer.status = "error"
            layer.detail = str(e)

    def _reset_memory_markdown(self, confirm: bool):
        """刪除 memory/ 下所有日期 Markdown 檔案."""
        layer = ResetLayer("B.對話", "memory/**/*.md", "刪除所有對話記憶 Markdown")
        self.layers.append(layer)

        mem_dir = self.data_dir / "memory"
        try:
            count = 0
            if mem_dir.exists():
                for md_file in mem_dir.rglob("*.md"):
                    count += 1
                    if confirm:
                        md_file.unlink()

                # 清空日期目錄
                if confirm:
                    for d in sorted(mem_dir.rglob("*"), reverse=True):
                        if d.is_dir() and d != mem_dir:
                            try:
                                d.rmdir()
                            except OSError:
                                pass

            layer.status = "cleared" if count > 0 else "skipped"
            layer.detail = f"{count} 個 .md 檔案"
        except Exception as e:
            layer.status = "error"
            layer.detail = str(e)

    def _reset_memory_v3(self, confirm: bool):
        """刪除 memory_v3/ 下所有使用者記憶."""
        layer = ResetLayer("B.對話", "memory_v3/**", "刪除六層記憶系統")
        self.layers.append(layer)

        v3_dir = self.data_dir / "memory_v3"
        try:
            count = 0
            if v3_dir.exists():
                for json_file in v3_dir.rglob("*.json"):
                    count += 1
                    if confirm:
                        json_file.unlink()

                # 保留目錄骨架但清空檔案
                # 重建 boss 使用者的層級目錄
                if confirm:
                    # 清空所有子目錄
                    for d in sorted(v3_dir.rglob("*"), reverse=True):
                        if d.is_dir() and d != v3_dir:
                            try:
                                d.rmdir()
                            except OSError:
                                pass

            layer.status = "cleared" if count > 0 else "skipped"
            layer.detail = f"{count} 個 JSON 檔案"
        except Exception as e:
            layer.status = "error"
            layer.detail = str(e)

    def _reset_sessions(self, confirm: bool):
        """刪除所有 session 快取."""
        layer = ResetLayer("B.對話", "sessions/*.json", "刪除所有 session 快取")
        self.layers.append(layer)

        sess_dir = self.data_dir / "_system" / "sessions"
        try:
            count = 0
            if sess_dir.exists():
                for f in sess_dir.glob("*.json"):
                    count += 1
                    if confirm:
                        f.unlink()

            layer.status = "cleared" if count > 0 else "skipped"
            layer.detail = f"{count} 個 session 檔案"
        except Exception as e:
            layer.status = "error"
            layer.detail = str(e)

    # ═══════════════════════════════════════════
    # C. 知識層
    # ═══════════════════════════════════════════

    def _reset_knowledge_lattice(self, confirm: bool):
        """清空知識晶格."""
        layer = ResetLayer("C.知識", "crystals.json", "清空知識晶格")
        self.layers.append(layer)

        path = self.data_dir / "lattice" / "crystals.json"
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                count = len(data) if isinstance(data, list) else 0
                if confirm:
                    path.write_text("[]", encoding="utf-8")
                layer.status = "cleared"
                layer.detail = f"清除 {count} 個 crystals"
            else:
                layer.status = "skipped"
                layer.detail = "檔案不存在"
        except Exception as e:
            layer.status = "error"
            layer.detail = str(e)

    def _reset_qdrant(self, confirm: bool):
        """清空 Qdrant 所有 collections."""
        layer = ResetLayer("C.知識", "Qdrant collections", "清空所有向量索引")
        self.layers.append(layer)

        try:
            from qdrant_client import QdrantClient
            client = QdrantClient(host="127.0.0.1", port=6333, timeout=5)

            collections = client.get_collections().collections
            details = []
            for c in collections:
                info = client.get_collection(c.name)
                points = info.points_count
                if points > 0:
                    if confirm:
                        # 刪除再重建（保持 collection schema）
                        from qdrant_client.models import Distance, VectorParams
                        vector_size = info.config.params.vectors.size
                        client.delete_collection(c.name)
                        client.create_collection(
                            collection_name=c.name,
                            vectors_config=VectorParams(
                                size=vector_size, distance=Distance.COSINE
                            ),
                        )
                    details.append(f"{c.name}={points}")
                else:
                    details.append(f"{c.name}=0(skip)")

            layer.status = "cleared"
            layer.detail = ", ".join(details) if details else "無 collections"
        except Exception as e:
            layer.status = "error"
            layer.detail = f"Qdrant 連線失敗（可能未啟動）: {e}"

    def _reset_synapses(self, confirm: bool):
        """清空技能突觸."""
        layer = ResetLayer("C.知識", "synapses.json", "清空技能連接")
        self.layers.append(layer)
        self._reset_json_to_empty(
            self.data_dir / "_system" / "synapses.json", "{}", layer, confirm
        )

    def _reset_scout_queue(self, confirm: bool):
        """清空 Scout 佇列."""
        layer = ResetLayer("C.知識", "scout_queue", "清空待探索佇列")
        self.layers.append(layer)
        self._reset_json_to_empty(
            self.data_dir / "_system" / "bridge" / "scout_queue" / "pending.json",
            "[]", layer, confirm
        )

    def _reset_curiosity_queue(self, confirm: bool):
        """清空好奇心佇列."""
        layer = ResetLayer("C.知識", "question_queue", "清空好奇心佇列")
        self.layers.append(layer)
        self._reset_json_to_empty(
            self.data_dir / "_system" / "curiosity" / "question_queue.json",
            '{"questions": []}', layer, confirm
        )

    # ═══════════════════════════════════════════
    # D. 行為層
    # ═══════════════════════════════════════════

    def _reset_diary(self, confirm: bool):
        """清空日記條目."""
        layer = ResetLayer("D.行為", "soul_rings.json", "清空日記")
        self.layers.append(layer)
        self._reset_json_to_empty(
            self.data_dir / "anima" / "soul_rings.json", "[]", layer, confirm
        )

    def _reset_drift_baseline(self, confirm: bool):
        """刪除漂移基線."""
        layer = ResetLayer("D.行為", "drift_baseline.json", "刪除漂移基線")
        self.layers.append(layer)
        self._delete_file(self.data_dir / "anima" / "drift_baseline.json", layer, confirm)

    def _reset_fact_corrections(self, confirm: bool):
        """刪除事實更正日誌."""
        layer = ResetLayer("D.行為", "fact_corrections.jsonl", "刪除事實更正")
        self.layers.append(layer)
        self._delete_file(self.data_dir / "anima" / "fact_corrections.jsonl", layer, confirm)

    # ═══════════════════════════════════════════
    # E. 評估層
    # ═══════════════════════════════════════════

    def _reset_pulsedb(self, confirm: bool):
        """清空 PulseDB 所有表."""
        layer = ResetLayer("E.評估", "pulse.db", "清空 PulseDB 所有表")
        self.layers.append(layer)

        db_path = self.data_dir / "pulse" / "pulse.db"
        if not db_path.exists():
            layer.status = "skipped"
            layer.detail = "DB 不存在"
            return

        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence'")
            tables = [row[0] for row in cursor.fetchall()]

            details = []
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM [{table}]")
                count = cursor.fetchone()[0]
                if count > 0:
                    if confirm:
                        cursor.execute(f"DELETE FROM [{table}]")
                    details.append(f"{table}={count}")

            # 重置 auto-increment
            if confirm:
                cursor.execute("DELETE FROM sqlite_sequence")
                conn.commit()

            conn.close()
            layer.status = "cleared"
            layer.detail = ", ".join(details) if details else "所有表已為空"
        except Exception as e:
            layer.status = "error"
            layer.detail = str(e)

    def _reset_eval(self, confirm: bool):
        """刪除評估資料."""
        layer = ResetLayer("E.評估", "eval/**", "刪除所有評估報告")
        self.layers.append(layer)

        eval_dir = self.data_dir / "eval"
        try:
            count = 0
            if eval_dir.exists():
                for f in eval_dir.rglob("*"):
                    if f.is_file():
                        count += 1
                        if confirm:
                            f.unlink()

                # 清空子目錄
                if confirm:
                    for d in sorted(eval_dir.rglob("*"), reverse=True):
                        if d.is_dir() and d != eval_dir:
                            try:
                                d.rmdir()
                            except OSError:
                                pass

            layer.status = "cleared" if count > 0 else "skipped"
            layer.detail = f"{count} 個檔案"
        except Exception as e:
            layer.status = "error"
            layer.detail = str(e)

    def _reset_workflow_db(self, confirm: bool):
        """清空 workflow_state.db."""
        layer = ResetLayer("E.評估", "workflow_state.db", "清空工作流狀態")
        self.layers.append(layer)

        db_path = self.data_dir / "_system" / "wee" / "workflow_state.db"
        if not db_path.exists():
            layer.status = "skipped"
            layer.detail = "DB 不存在"
            return

        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence'")
            tables = [row[0] for row in cursor.fetchall()]
            details = []
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM [{table}]")
                count = cursor.fetchone()[0]
                if count > 0:
                    if confirm:
                        cursor.execute(f"DELETE FROM [{table}]")
                    details.append(f"{table}={count}")
            if confirm:
                conn.commit()
            conn.close()
            layer.status = "cleared"
            layer.detail = ", ".join(details) if details else "所有表已為空"
        except Exception as e:
            layer.status = "error"
            layer.detail = str(e)

    # ═══════════════════════════════════════════
    # F. 日誌層
    # ═══════════════════════════════════════════

    def _reset_audit_logs(self, confirm: bool):
        """刪除根目錄審計日誌."""
        layer = ResetLayer("F.日誌", "audit logs", "刪除審計日誌")
        self.layers.append(layer)

        logs = [
            "activity_log.jsonl",
            "heartbeat.jsonl",
            "skill_usage_log.jsonl",
        ]
        count = 0
        for name in logs:
            p = self.data_dir / name
            if p.exists():
                count += 1
                if confirm:
                    p.unlink()

        layer.status = "cleared" if count > 0 else "skipped"
        layer.detail = f"{count} 個日誌檔"

    def _reset_guardian_logs(self, confirm: bool):
        """清空 Guardian 日誌和狀態."""
        layer = ResetLayer("F.日誌", "guardian/**", "清空 Guardian 日誌")
        self.layers.append(layer)

        guard_dir = self.data_dir / "guardian"
        try:
            count = 0
            if guard_dir.exists():
                for f in guard_dir.rglob("*"):
                    if f.is_file():
                        count += 1
                        if confirm:
                            f.unlink()
                # 清空子目錄
                if confirm:
                    for d in sorted(guard_dir.rglob("*"), reverse=True):
                        if d.is_dir() and d != guard_dir:
                            try:
                                d.rmdir()
                            except OSError:
                                pass

            layer.status = "cleared" if count > 0 else "skipped"
            layer.detail = f"{count} 個檔案"
        except Exception as e:
            layer.status = "error"
            layer.detail = str(e)

    def _reset_footprints(self, confirm: bool):
        """清空足跡日誌."""
        layer = ResetLayer("F.日誌", "footprints/**", "清空足跡日誌")
        self.layers.append(layer)

        fp_dir = self.data_dir / "_system" / "footprints"
        try:
            count = 0
            if fp_dir.exists():
                for f in fp_dir.glob("*.jsonl"):
                    count += 1
                    if confirm:
                        f.unlink()
            layer.status = "cleared" if count > 0 else "skipped"
            layer.detail = f"{count} 個 JSONL 檔"
        except Exception as e:
            layer.status = "error"
            layer.detail = str(e)

    # ═══════════════════════════════════════════
    # G. 其他狀態
    # ═══════════════════════════════════════════

    def _reset_nightly_state(self, confirm: bool):
        """清空 nightly 報告和歷史."""
        layer = ResetLayer("G.狀態", "nightly state", "清空 Nightly 狀態")
        self.layers.append(layer)

        files = [
            self.data_dir / "_system" / "state" / "nightly_report.json",
            self.data_dir / "_system" / "state" / "nightly_history.jsonl",
        ]
        count = 0
        for f in files:
            if f.exists():
                count += 1
                if confirm:
                    f.unlink()
        layer.status = "cleared" if count > 0 else "skipped"
        layer.detail = f"{count} 個檔案"

    def _reset_outward_state(self, confirm: bool):
        """清空 outward 演化狀態."""
        layer = ResetLayer("G.狀態", "outward state", "清空外向演化狀態")
        self.layers.append(layer)

        outward_dir = self.data_dir / "_system" / "outward"
        try:
            count = 0
            if outward_dir.exists():
                for f in outward_dir.glob("*.json"):
                    count += 1
                    if confirm:
                        f.unlink()
            layer.status = "cleared" if count > 0 else "skipped"
            layer.detail = f"{count} 個 JSON 檔"
        except Exception as e:
            layer.status = "error"
            layer.detail = str(e)

    def _reset_evolution_state(self, confirm: bool):
        """清空演化參數和日誌."""
        layer = ResetLayer("G.狀態", "evolution state", "清空演化參數")
        self.layers.append(layer)

        evo_dir = self.data_dir / "_system" / "evolution"
        try:
            count = 0
            if evo_dir.exists():
                for f in evo_dir.rglob("*"):
                    if f.is_file():
                        count += 1
                        if confirm:
                            f.unlink()
            layer.status = "cleared" if count > 0 else "skipped"
            layer.detail = f"{count} 個檔案"
        except Exception as e:
            layer.status = "error"
            layer.detail = str(e)

    # ═══════════════════════════════════════════
    # 骨架重建
    # ═══════════════════════════════════════════

    def _rebuild_skeleton(self):
        """重建最小目錄骨架."""
        dirs = [
            self.data_dir / "memory",
            self.data_dir / "memory_v3",
            self.data_dir / "anima",
            self.data_dir / "eval",
            self.data_dir / "eval" / "daily",
            self.data_dir / "lattice",
            self.data_dir / "pulse",
            self.data_dir / "guardian",
            self.data_dir / "_system" / "sessions",
            self.data_dir / "_system" / "footprints",
            self.data_dir / "_system" / "curiosity",
            self.data_dir / "_system" / "bridge" / "scout_queue",
            self.data_dir / "_system" / "evolution",
            self.data_dir / "_system" / "outward",
            self.data_dir / "_system" / "state",
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

        print("\n  ✅ 目錄骨架已重建")

    # ═══════════════════════════════════════════
    # 工具方法
    # ═══════════════════════════════════════════

    def _reset_json_to_empty(self, path: Path, empty_content: str,
                              layer: ResetLayer, confirm: bool):
        """將 JSON 檔案重置為空內容."""
        if not path.exists():
            layer.status = "skipped"
            layer.detail = "檔案不存在"
            return
        try:
            old_size = path.stat().st_size
            if confirm:
                path.write_text(empty_content, encoding="utf-8")
            layer.status = "cleared"
            layer.detail = f"原大小 {old_size} bytes → 空"
        except Exception as e:
            layer.status = "error"
            layer.detail = str(e)

    def _delete_file(self, path: Path, layer: ResetLayer, confirm: bool):
        """刪除單一檔案."""
        if not path.exists():
            layer.status = "skipped"
            layer.detail = "檔案不存在"
            return
        try:
            size = path.stat().st_size
            if confirm:
                path.unlink()
            layer.status = "cleared"
            layer.detail = f"刪除 {size} bytes"
        except Exception as e:
            layer.status = "error"
            layer.detail = str(e)

    # ═══════════════════════════════════════════
    # 報告
    # ═══════════════════════════════════════════

    def _print_report(self, confirm: bool) -> dict:
        """印出重置報告."""
        print(f"\n{'─'*60}")
        print("  重置報告")
        print(f"{'─'*60}\n")

        current_cat = ""
        for layer in self.layers:
            if layer.category != current_cat:
                current_cat = layer.category
                print(f"  ── {current_cat} ──")

            icon = {"cleared": "✅", "skipped": "⏭️", "error": "❌", "pending": "⏳"}
            print(f"    {icon.get(layer.status, '?')} {layer.name}: {layer.detail}")

            if layer.status == "cleared":
                self._stats["cleared"] += 1
            elif layer.status == "skipped":
                self._stats["skipped"] += 1
            elif layer.status == "error":
                self._stats["errors"] += 1

        print(f"\n{'─'*60}")
        print(f"  統計: ✅ {self._stats['cleared']} 清除 | "
              f"⏭️ {self._stats['skipped']} 跳過 | "
              f"❌ {self._stats['errors']} 錯誤")

        if not confirm:
            print(f"\n  ⚠️  這是 DRY-RUN 模式，沒有實際修改任何資料。")
            print(f"  要實際執行，請加上 --confirm 參數。")
        else:
            print(f"\n  🔥 重置完成！請重啟 Gateway：")
            print(f"     launchctl kickstart -k gui/502/com.museon.gateway")

        print(f"{'='*60}\n")

        return self._stats


# ═══════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="MUSEON 一鍵全層記憶重置",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  # Dry-run（預覽，不修改）
  .venv/bin/python -m museon.doctor.memory_reset --home ~/MUSEON

  # 實際執行
  .venv/bin/python -m museon.doctor.memory_reset --home ~/MUSEON --confirm
        """,
    )
    parser.add_argument("--home", required=True, help="MUSEON 根目錄路徑")
    parser.add_argument("--confirm", action="store_true",
                        help="確認執行（不加此旗標為 dry-run）")

    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)

    resetter = MemoryReset(args.home)
    stats = resetter.run(confirm=args.confirm)

    if stats["errors"] > 0:
        exit(1)


if __name__ == "__main__":
    main()
