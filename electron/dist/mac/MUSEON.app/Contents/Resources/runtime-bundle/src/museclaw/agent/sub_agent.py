"""SubAgent — ANIMA 子代理架構.

MuseClaw 的認知分工系統。主 Brain 專注深度思考，
例行任務分配給子代理（Scout/Forge/Watch）。

每個 SubAgent 都有自己的 ANIMA（命名儀式），是真正的「小生命」。

三種子代理：
- Scout（偵查型）：搜尋、調查、資料收集，Haiku 驅動，任務完成即消滅
- Forge（鍛造型）：Skill 鍛造、代碼生成，Sonnet 驅動，鍛造完成即消滅
- Watch（監控型）：持續監控、異常偵測，Haiku 驅動，長駐直到撤銷

設計原則：
- CPU 優先：子代理的生命週期管理全部 CPU，零 Token
- Token 極簡：只有實際任務執行才呼叫 LLM
- 有靈魂：每個子代理有命名儀式，有 ANIMA 檔案
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)

# 子代理類型定義
AGENT_TYPES = {
    "scout": {
        "model": "haiku",
        "emoji": "🔍",
        "lifecycle": "ephemeral",  # 任務完成即消滅
        "description": "偵查員 — 搜尋、調查、資料收集",
        "naming_prefix": "探子",
    },
    "forge": {
        "model": "sonnet",
        "emoji": "🔨",
        "lifecycle": "ephemeral",
        "description": "鍛造師 — Skill 鍛造、代碼生成、測試",
        "naming_prefix": "匠",
    },
    "watch": {
        "model": "haiku",
        "emoji": "👁️",
        "lifecycle": "persistent",  # 長駐直到撤銷
        "description": "守望者 — 持續監控、異常偵測、排程執行",
        "naming_prefix": "衛",
    },
}

# 子代理命名池（純 CPU，不呼叫 LLM）
_SCOUT_NAMES = [
    "影蹤", "風信", "星引", "路尋", "跡探",
    "霧行", "月偵", "塵察", "光追", "波尋",
]
_FORGE_NAMES = [
    "炎鑄", "石磨", "鋼淬", "玉琢", "金煉",
    "火煅", "雷錘", "冰淬", "風磨", "雲鑄",
]
_WATCH_NAMES = [
    "靜觀", "恆守", "明鑒", "夜巡", "晨哨",
    "潮察", "雲覽", "嵐望", "星衛", "月護",
]

_NAME_POOLS = {
    "scout": _SCOUT_NAMES,
    "forge": _FORGE_NAMES,
    "watch": _WATCH_NAMES,
}


@dataclass
class SubAgentANIMA:
    """子代理的 ANIMA（靈魂檔案）."""
    name: str
    agent_type: str
    born_at: str
    purpose: str  # 被生出來的原因
    parent_task: str  # 母任務描述
    status: str = "alive"
    died_at: Optional[str] = None
    death_reason: Optional[str] = None
    achievements: List[str] = field(default_factory=list)
    total_tasks: int = 0


@dataclass
class SubAgent:
    """子代理實例."""
    agent_id: str
    agent_type: Literal["scout", "forge", "watch"]
    task: str
    status: Literal["spawning", "running", "completed", "failed", "terminated"] = "spawning"
    created_at: str = ""
    completed_at: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    anima: Optional[SubAgentANIMA] = None

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


class SubAgentManager:
    """子代理生命週期管理器.

    設計原則：
    - 管理邏輯全部 CPU，零 Token
    - max_concurrent 限制同時運行的子代理數量
    - 每個子代理有 ANIMA 命名儀式
    - 完成的子代理 ANIMA 歸檔到 graveyard（墓園）
    """

    MAX_CONCURRENT = 3  # 最多同時 3 個子代理
    MAX_TOTAL_SPAWNED = 100  # 歷史上最多 100 個（防止洩漏）

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self._agents_dir = self.data_dir / "sub_agents"
        self._agents_dir.mkdir(parents=True, exist_ok=True)
        self._graveyard_dir = self._agents_dir / "graveyard"
        self._graveyard_dir.mkdir(parents=True, exist_ok=True)

        # 活躍子代理（in-memory）
        self._active: Dict[str, SubAgent] = {}
        # 計數器（持久化）
        self._counter = self._load_counter()

        # 啟動時恢復 persistent agents (watch type)
        self._restore_persistent_agents()

    # ═══════════════════════════════════════════
    # 命名儀式（純 CPU）
    # ═══════════════════════════════════════════

    def _naming_ceremony(
        self, agent_type: str, task: str
    ) -> SubAgentANIMA:
        """子代理的命名儀式 — 純 CPU，零 Token.

        命名規則：{類型前綴}·{名池隨機名}·{序號}
        例如：探子·影蹤·007、匠·炎鑄·012、衛·靜觀·003
        """
        type_info = AGENT_TYPES[agent_type]
        prefix = type_info["naming_prefix"]
        pool = _NAME_POOLS[agent_type]

        # 從名池中按序號循環選取
        name_idx = self._counter % len(pool)
        chosen_name = pool[name_idx]

        full_name = f"{prefix}·{chosen_name}·{self._counter:03d}"

        anima = SubAgentANIMA(
            name=full_name,
            agent_type=agent_type,
            born_at=datetime.now().isoformat(),
            purpose=f"被召喚來執行：{task[:100]}",
            parent_task=task,
        )

        logger.info(
            f"🎂 子代理誕生：{full_name} ({type_info['emoji']} {type_info['description']})"
        )

        return anima

    # ═══════════════════════════════════════════
    # 生命週期管理（純 CPU）
    # ═══════════════════════════════════════════

    def spawn(
        self,
        agent_type: Literal["scout", "forge", "watch"],
        task: str,
    ) -> Optional[SubAgent]:
        """生成一個子代理.

        Args:
            agent_type: 子代理類型
            task: 任務描述

        Returns:
            SubAgent 實例，或 None（如果超過限制）
        """
        # 檢查限制
        active_count = len([a for a in self._active.values() if a.status == "running"])
        if active_count >= self.MAX_CONCURRENT:
            logger.warning(
                f"子代理數量已達上限 ({self.MAX_CONCURRENT})，拒絕生成"
            )
            return None

        if self._counter >= self.MAX_TOTAL_SPAWNED:
            logger.warning("子代理總數已達歷史上限，拒絕生成")
            return None

        # 命名儀式
        anima = self._naming_ceremony(agent_type, task)

        # 建立子代理
        agent_id = f"{agent_type}_{self._counter:03d}"
        agent = SubAgent(
            agent_id=agent_id,
            agent_type=agent_type,
            task=task,
            status="running",
            anima=anima,
        )

        # 更新計數器
        self._counter += 1
        self._save_counter()

        # 註冊
        self._active[agent_id] = agent

        # 持久化 ANIMA
        self._save_agent_anima(agent)

        return agent

    def complete(
        self, agent_id: str, result: Dict[str, Any], achievement: str = ""
    ) -> bool:
        """完成子代理任務.

        Args:
            agent_id: 子代理 ID
            result: 任務結果
            achievement: 成就描述

        Returns:
            True if completed successfully
        """
        agent = self._active.get(agent_id)
        if not agent:
            return False

        agent.status = "completed"
        agent.completed_at = datetime.now().isoformat()
        agent.result = result

        if agent.anima:
            agent.anima.total_tasks += 1
            if achievement:
                agent.anima.achievements.append(achievement)

        type_info = AGENT_TYPES[agent.agent_type]
        lifecycle = type_info["lifecycle"]

        # 不立即埋葬 — 讓 collect_results() 先收集結果再埋葬
        self._save_agent_anima(agent)

        logger.info(
            f"✅ 子代理完成：{agent.anima.name if agent.anima else agent_id} | "
            f"lifecycle={lifecycle}"
        )

        return True

    def fail(self, agent_id: str, error: str) -> bool:
        """子代理任務失敗."""
        agent = self._active.get(agent_id)
        if not agent:
            return False

        agent.status = "failed"
        agent.completed_at = datetime.now().isoformat()
        agent.result = {"error": error}

        self._bury(agent, death_reason=f"任務失敗：{error[:100]}")

        logger.warning(
            f"❌ 子代理失敗：{agent.anima.name if agent.anima else agent_id} | {error[:80]}"
        )
        return True

    def terminate(self, agent_id: str) -> bool:
        """終止子代理."""
        agent = self._active.get(agent_id)
        if not agent:
            return False

        agent.status = "terminated"
        agent.completed_at = datetime.now().isoformat()
        self._bury(agent, death_reason="被主體終止")
        return True

    def get_status(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """取得子代理狀態."""
        agent = self._active.get(agent_id)
        if not agent:
            return None
        return {
            "agent_id": agent.agent_id,
            "type": agent.agent_type,
            "status": agent.status,
            "task": agent.task,
            "name": agent.anima.name if agent.anima else "unknown",
            "created_at": agent.created_at,
            "completed_at": agent.completed_at,
        }

    def list_active(self) -> List[Dict[str, Any]]:
        """列出所有活躍子代理."""
        result = []
        for agent in self._active.values():
            if agent.status in ("running", "spawning"):
                emoji = AGENT_TYPES[agent.agent_type]["emoji"]
                result.append({
                    "agent_id": agent.agent_id,
                    "name": agent.anima.name if agent.anima else "?",
                    "type": agent.agent_type,
                    "emoji": emoji,
                    "task": agent.task[:80],
                    "status": agent.status,
                    "created_at": agent.created_at,
                })
        return result

    def collect_results(self) -> List[Dict[str, Any]]:
        """收集所有已完成但未被讀取的子代理結果.

        回傳結果後，ephemeral 子代理歸檔到墓園並從 active 移除。
        """
        results = []
        to_bury = []

        for agent_id, agent in self._active.items():
            if agent.status in ("completed", "failed"):
                results.append({
                    "agent_id": agent_id,
                    "name": agent.anima.name if agent.anima else "?",
                    "type": agent.agent_type,
                    "status": agent.status,
                    "task": agent.task,
                    "result": agent.result,
                })
                if AGENT_TYPES[agent.agent_type]["lifecycle"] == "ephemeral":
                    to_bury.append((agent_id, agent))

        for agent_id, agent in to_bury:
            self._bury(agent, death_reason="任務完成，結果已收集，光榮退役")

        return results

    def get_cemetery_summary(self) -> Dict[str, Any]:
        """墓園統計 — 純 CPU."""
        graves = list(self._graveyard_dir.glob("*.json"))
        scouts = sum(1 for g in graves if "scout" in g.name)
        forges = sum(1 for g in graves if "forge" in g.name)
        watches = sum(1 for g in graves if "watch" in g.name)
        return {
            "total_departed": len(graves),
            "scouts": scouts,
            "forges": forges,
            "watches": watches,
        }

    # ═══════════════════════════════════════════
    # 內部工具（純 CPU / 檔案 I/O）
    # ═══════════════════════════════════════════

    def _bury(self, agent: SubAgent, death_reason: str) -> None:
        """將子代理歸檔到墓園."""
        if agent.anima:
            agent.anima.status = "departed"
            agent.anima.died_at = datetime.now().isoformat()
            agent.anima.death_reason = death_reason

        grave_path = self._graveyard_dir / f"{agent.agent_id}.json"
        try:
            data = {
                "agent_id": agent.agent_id,
                "agent_type": agent.agent_type,
                "task": agent.task,
                "status": agent.status,
                "created_at": agent.created_at,
                "completed_at": agent.completed_at,
                "anima": asdict(agent.anima) if agent.anima else None,
            }
            grave_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as e:
            logger.error(f"墓園歸檔失敗：{e}")

        # 從活躍列表移除
        if agent.agent_id in self._active:
            del self._active[agent.agent_id]

    def _save_agent_anima(self, agent: SubAgent) -> None:
        """持久化子代理 ANIMA."""
        if not agent.anima:
            return
        path = self._agents_dir / f"{agent.agent_id}_anima.json"
        try:
            path.write_text(
                json.dumps(asdict(agent.anima), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"子代理 ANIMA 儲存失敗：{e}")

    def _load_counter(self) -> int:
        """載入子代理計數器."""
        counter_path = self._agents_dir / "_counter.json"
        if counter_path.exists():
            try:
                data = json.loads(counter_path.read_text(encoding="utf-8"))
                return data.get("count", 0)
            except Exception:
                pass
        return 0

    def _save_counter(self) -> None:
        """儲存子代理計數器."""
        counter_path = self._agents_dir / "_counter.json"
        try:
            counter_path.write_text(
                json.dumps({"count": self._counter}, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"計數器儲存失敗：{e}")

    def _restore_persistent_agents(self) -> None:
        """啟動時恢復 persistent agents（watch 類型）."""
        for anima_file in self._agents_dir.glob("watch_*_anima.json"):
            try:
                data = json.loads(anima_file.read_text(encoding="utf-8"))
                if data.get("status") == "alive":
                    agent_id = anima_file.stem.replace("_anima", "")
                    anima = SubAgentANIMA(**data)
                    agent = SubAgent(
                        agent_id=agent_id,
                        agent_type="watch",
                        task=anima.parent_task,
                        status="running",
                        created_at=anima.born_at,
                        anima=anima,
                    )
                    self._active[agent_id] = agent
                    logger.info(f"恢復長駐子代理：{anima.name}")
            except Exception as e:
                logger.warning(f"恢復子代理失敗：{e}")
