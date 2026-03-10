"""Federated Learning — 差分隱私聯邦學習引擎.

支援多節點協同學習：
- 差分隱私梯度聚合（Laplacian noise）
- 隱私邊界驗證
- 聯邦學習輪次管理
- 本地模型更新貢獻

設計原則：
- 隱私優先：所有梯度加入 Laplacian noise
- 驗證邊界：確保資料不洩露隱私
- 離線優先：可在無網路環境運作
- 所有外部呼叫 try/except 包裹
- 聯邦狀態持久化到 _system/federation/
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import random
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

# ═══════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════

DEFAULT_EPSILON = 1.0           # 差分隱私 epsilon（越小越隱私）
DEFAULT_DELTA = 1e-5            # 差分隱私 delta
MAX_GRADIENT_NORM = 1.0         # 梯度裁剪上限
MIN_NODES_FOR_ROUND = 2         # 最少參與節點數
ROUND_TIMEOUT_SECONDS = 3600    # 單輪超時
MAX_FEDERATION_HISTORY = 100    # 歷史輪次上限

# 隱私邊界檢查閾值
PRIVACY_SENSITIVITY_THRESHOLD = 0.01  # 敏感度閾值
PRIVACY_MAX_CONTRIBUTION = 10.0       # 單次貢獻上限


class FederatedLearning:
    """差分隱私聯邦學習引擎."""

    def __init__(
        self,
        workspace: Optional[str] = None,
        event_bus: Any = None,
    ) -> None:
        ws = workspace or os.getenv("MUSEON_WORKSPACE", str(Path.home() / "MUSEON"))
        self._workspace = Path(ws)
        self._event_bus = event_bus
        self._node_id = os.getenv("MUSEON_NODE_ID", f"node-{uuid.uuid4().hex[:8]}")

        # Federation 狀態目錄
        self._fed_dir = self._workspace / "_system" / "federation"
        self._fed_dir.mkdir(parents=True, exist_ok=True)

        # 狀態檔案
        self._state_path = self._fed_dir / "federated_state.json"
        self._rounds_dir = self._fed_dir / "rounds"
        self._rounds_dir.mkdir(parents=True, exist_ok=True)

        # 載入狀態
        self._state: Dict = self._load_state()

    # ── State Persistence ───────────────────────────────

    def _load_state(self) -> Dict:
        """載入聯邦學習狀態."""
        if self._state_path.exists():
            try:
                return json.loads(self._state_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"Failed to load federation state: {e}")
        return {
            "node_id": self._node_id,
            "current_round": 0,
            "total_contributions": 0,
            "total_aggregations": 0,
            "last_round_at": None,
            "global_model_version": 0,
            "participating_nodes": [],
            "status": "idle",
        }

    def _save_state(self) -> None:
        """持久化聯邦學習狀態."""
        try:
            self._state_path.write_text(
                json.dumps(self._state, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"Failed to save federation state: {e}")

    # ── Gradient Aggregation ────────────────────────────

    async def aggregate_gradients(self, node_gradients: List[Dict]) -> Dict:
        """差分隱私梯度聚合.

        對多個節點提交的梯度進行加權平均，並加入差分隱私噪音。

        Args:
            node_gradients: 各節點梯度列表
                [{node_id, gradients: {param_name: value}, weight}]

        Returns:
            聚合後的全域梯度 Dict
        """
        if not node_gradients:
            return {"error": "No gradients to aggregate", "aggregated": {}}

        if len(node_gradients) < MIN_NODES_FOR_ROUND:
            logger.warning(f"Insufficient nodes: {len(node_gradients)} < {MIN_NODES_FOR_ROUND}")
            return {
                "error": f"Need at least {MIN_NODES_FOR_ROUND} nodes",
                "aggregated": {},
            }

        logger.info(f"Aggregating gradients from {len(node_gradients)} nodes")

        # 1. 驗證隱私邊界
        valid_gradients: List[Dict] = []
        for ng in node_gradients:
            if self._validate_privacy_boundary(ng):
                valid_gradients.append(ng)
            else:
                logger.warning(f"Node {ng.get('node_id', '?')} failed privacy validation, excluded")

        if not valid_gradients:
            return {"error": "All gradients failed privacy validation", "aggregated": {}}

        # 2. 梯度裁剪
        clipped = [self._clip_gradients(ng) for ng in valid_gradients]

        # 3. 加權平均
        aggregated = self._weighted_average(clipped)

        # 4. 差分隱私噪音注入
        noisy_aggregated = self._apply_differential_privacy(aggregated)

        # 5. 更新狀態
        self._state["current_round"] += 1
        self._state["total_aggregations"] += 1
        self._state["last_round_at"] = datetime.now(TZ8).isoformat()
        self._state["global_model_version"] += 1
        self._state["participating_nodes"] = [
            ng.get("node_id", "unknown") for ng in valid_gradients
        ]
        self._state["status"] = "aggregated"
        self._save_state()

        # 6. 保存輪次結果
        round_id = self._state["current_round"]
        self._save_round_result(round_id, noisy_aggregated, valid_gradients)

        # 7. 發布事件
        try:
            if self._event_bus is not None:
                from museon.core.event_bus import SHARED_ASSET_PUBLISHED
                self._event_bus.publish(SHARED_ASSET_PUBLISHED, {
                    "asset_type": "federated_model",
                    "round": round_id,
                    "node_count": len(valid_gradients),
                    "timestamp": datetime.now(TZ8).isoformat(),
                })
        except Exception as e:
            logger.warning(f"Failed to publish aggregation event: {e}")

        logger.info(f"Federation round {round_id}: aggregated from {len(valid_gradients)} nodes")
        return {
            "round": round_id,
            "aggregated": noisy_aggregated,
            "node_count": len(valid_gradients),
            "model_version": self._state["global_model_version"],
        }

    def _apply_differential_privacy(
        self, gradient: Dict, epsilon: float = DEFAULT_EPSILON
    ) -> Dict:
        """對梯度加入 Laplacian noise 實現差分隱私.

        Laplace mechanism: noise ~ Lap(sensitivity / epsilon)

        Args:
            gradient: 梯度 dict {param_name: value}
            epsilon: 隱私預算（越小越隱私，噪音越大）

        Returns:
            加噪後的梯度 dict
        """
        noisy = {}
        sensitivity = MAX_GRADIENT_NORM  # L1 sensitivity bound

        for param, value in gradient.items():
            if isinstance(value, (int, float)):
                # Laplacian noise
                scale = sensitivity / max(epsilon, 1e-10)
                noise = self._laplace_noise(scale)
                noisy[param] = value + noise
            elif isinstance(value, list):
                scale = sensitivity / max(epsilon, 1e-10)
                noisy[param] = [
                    v + self._laplace_noise(scale)
                    if isinstance(v, (int, float)) else v
                    for v in value
                ]
            else:
                noisy[param] = value

        return noisy

    @staticmethod
    def _laplace_noise(scale: float) -> float:
        """產生 Laplace 分佈噪音.

        Laplace(0, scale) = -scale * sign(u) * ln(1 - 2|u|) where u ~ Uniform(-0.5, 0.5)
        """
        u = random.random() - 0.5
        if abs(u) < 1e-10:
            return 0.0
        return -scale * (1 if u >= 0 else -1) * math.log(1 - 2 * abs(u))

    def _validate_privacy_boundary(self, data: Dict) -> bool:
        """驗證資料是否在隱私邊界內.

        檢查：
        1. 梯度值不超過上限
        2. 不包含原始資料（只允許梯度/增量）
        3. 貢獻量在合理範圍

        Args:
            data: 節點提交的梯度資料

        Returns:
            True if data is within privacy envelope
        """
        gradients = data.get("gradients", {})

        # 檢查是否有禁止欄位（可能洩露原始資料）
        forbidden_fields = {"raw_data", "user_data", "personal_info", "messages", "conversations"}
        if forbidden_fields & set(data.keys()):
            logger.warning(f"Privacy boundary violation: forbidden fields detected")
            return False

        # 檢查梯度範圍
        for param, value in gradients.items():
            if isinstance(value, (int, float)):
                if abs(value) > PRIVACY_MAX_CONTRIBUTION:
                    logger.warning(f"Gradient {param} exceeds max contribution: {abs(value)}")
                    return False
            elif isinstance(value, list):
                for v in value:
                    if isinstance(v, (int, float)) and abs(v) > PRIVACY_MAX_CONTRIBUTION:
                        logger.warning(f"Gradient {param} element exceeds max: {abs(v)}")
                        return False

        return True

    def _clip_gradients(self, node_gradient: Dict) -> Dict:
        """梯度裁剪（限制 L2 norm）.

        Args:
            node_gradient: 單節點梯度

        Returns:
            裁剪後的梯度
        """
        gradients = node_gradient.get("gradients", {})
        clipped = dict(node_gradient)

        # 計算 L2 norm
        l2_norm = 0.0
        values: List[float] = []
        for param, value in gradients.items():
            if isinstance(value, (int, float)):
                values.append(float(value))
            elif isinstance(value, list):
                values.extend(float(v) for v in value if isinstance(v, (int, float)))

        l2_norm = math.sqrt(sum(v ** 2 for v in values)) if values else 0.0

        # 裁剪
        if l2_norm > MAX_GRADIENT_NORM and l2_norm > 0:
            scale = MAX_GRADIENT_NORM / l2_norm
            new_grads = {}
            for param, value in gradients.items():
                if isinstance(value, (int, float)):
                    new_grads[param] = value * scale
                elif isinstance(value, list):
                    new_grads[param] = [
                        v * scale if isinstance(v, (int, float)) else v
                        for v in value
                    ]
                else:
                    new_grads[param] = value
            clipped["gradients"] = new_grads
            logger.debug(f"Clipped gradients: L2 {l2_norm:.4f} -> {MAX_GRADIENT_NORM}")

        return clipped

    @staticmethod
    def _weighted_average(node_gradients: List[Dict]) -> Dict:
        """對多節點梯度做加權平均.

        Args:
            node_gradients: 裁剪後的各節點梯度

        Returns:
            加權平均的梯度 dict
        """
        if not node_gradients:
            return {}

        # 收集所有參數名
        all_params: set = set()
        for ng in node_gradients:
            all_params.update(ng.get("gradients", {}).keys())

        total_weight = sum(ng.get("weight", 1.0) for ng in node_gradients)
        if total_weight == 0:
            total_weight = len(node_gradients)

        aggregated: Dict[str, Any] = {}
        for param in all_params:
            weighted_sum = 0.0
            is_list = False
            list_sums: List[float] = []

            for ng in node_gradients:
                value = ng.get("gradients", {}).get(param)
                weight = ng.get("weight", 1.0)

                if value is None:
                    continue
                if isinstance(value, (int, float)):
                    weighted_sum += float(value) * weight
                elif isinstance(value, list):
                    is_list = True
                    if not list_sums:
                        list_sums = [0.0] * len(value)
                    for i, v in enumerate(value):
                        if i < len(list_sums) and isinstance(v, (int, float)):
                            list_sums[i] += float(v) * weight

            if is_list:
                aggregated[param] = [s / total_weight for s in list_sums]
            else:
                aggregated[param] = weighted_sum / total_weight

        return aggregated

    # ── Federation Rounds ───────────────────────────────

    async def request_federation_round(self) -> Dict:
        """發起聯邦學習輪次.

        Returns:
            輪次請求結果
        """
        round_id = self._state["current_round"] + 1
        request = {
            "round_id": round_id,
            "requester": self._node_id,
            "requested_at": datetime.now(TZ8).isoformat(),
            "status": "requested",
            "min_nodes": MIN_NODES_FOR_ROUND,
            "timeout_seconds": ROUND_TIMEOUT_SECONDS,
            "global_model_version": self._state["global_model_version"],
        }

        # 保存輪次請求
        round_path = self._rounds_dir / f"round_{round_id}_request.json"
        try:
            round_path.write_text(
                json.dumps(request, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"Failed to save round request: {e}")

        self._state["status"] = "waiting_for_contributions"
        self._save_state()

        # 發布事件
        try:
            if self._event_bus is not None:
                from museon.core.event_bus import SHARED_ASSET_PUBLISHED
                self._event_bus.publish(SHARED_ASSET_PUBLISHED, {
                    "asset_type": "federation_round_request",
                    "round_id": round_id,
                    "timestamp": datetime.now(TZ8).isoformat(),
                })
        except Exception as e:
            logger.warning(f"Failed to publish round request event: {e}")

        logger.info(f"Federation round {round_id} requested by {self._node_id}")
        return request

    async def contribute_update(self, local_model_delta: Dict) -> Dict:
        """貢獻本地模型更新.

        Args:
            local_model_delta: 本地模型增量
                {gradients: {param: value}, metadata: {...}}

        Returns:
            貢獻確認結果
        """
        # 驗證隱私
        if not self._validate_privacy_boundary(local_model_delta):
            return {"error": "Contribution rejected: privacy boundary violation"}

        # 加入差分隱私噪音（本地端先加一層）
        gradients = local_model_delta.get("gradients", {})
        noisy_gradients = self._apply_differential_privacy(gradients, epsilon=DEFAULT_EPSILON * 2)

        contribution = {
            "node_id": self._node_id,
            "round_id": self._state["current_round"] + 1,
            "gradients": noisy_gradients,
            "weight": local_model_delta.get("weight", 1.0),
            "contributed_at": datetime.now(TZ8).isoformat(),
            "model_version": self._state["global_model_version"],
        }

        # 保存貢獻
        contrib_path = (
            self._rounds_dir
            / f"round_{contribution['round_id']}_contrib_{self._node_id}.json"
        )
        try:
            contrib_path.write_text(
                json.dumps(contribution, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"Failed to save contribution: {e}")

        self._state["total_contributions"] += 1
        self._save_state()

        logger.info(f"Contributed to round {contribution['round_id']}")
        return {
            "status": "contributed",
            "round_id": contribution["round_id"],
            "node_id": self._node_id,
        }

    # ── Status ──────────────────────────────────────────

    def get_federation_status(self) -> Dict:
        """回傳當前聯邦學習狀態."""
        return {
            "node_id": self._state.get("node_id", self._node_id),
            "current_round": self._state.get("current_round", 0),
            "total_contributions": self._state.get("total_contributions", 0),
            "total_aggregations": self._state.get("total_aggregations", 0),
            "global_model_version": self._state.get("global_model_version", 0),
            "last_round_at": self._state.get("last_round_at"),
            "status": self._state.get("status", "idle"),
            "participating_nodes": self._state.get("participating_nodes", []),
        }

    # ── Helpers ──────────────────────────────────────────

    def _save_round_result(
        self, round_id: int, aggregated: Dict, participants: List[Dict]
    ) -> None:
        """保存輪次結果."""
        result = {
            "round_id": round_id,
            "aggregated_at": datetime.now(TZ8).isoformat(),
            "participant_count": len(participants),
            "participants": [p.get("node_id", "unknown") for p in participants],
            "aggregated_gradient_keys": list(aggregated.keys()),
            "model_version": self._state["global_model_version"],
        }
        result_path = self._rounds_dir / f"round_{round_id}_result.json"
        try:
            result_path.write_text(
                json.dumps(result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"Failed to save round result: {e}")
