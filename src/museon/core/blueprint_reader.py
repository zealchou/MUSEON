"""blueprint_reader — 工程藍圖程式化解析器.

解析 docs/ 目錄下的 Markdown 藍圖文件，提供程式化 API，
讓 Doctor / Surgeon / Morphenix / Nightly 能動態查詢：
  - 模組扇入數和安全分級（blast-radius.md）
  - 共享狀態的讀寫者（joint-map.md）

設計原則：
  - 純正則表達式解析，零依賴（不引入 Markdown 解析庫）
  - 唯讀——只讀取文件，不修改任何東西
  - 容錯——檔案不存在或格式異常時回傳安全預設值
  - 快取——同一 process 週期內只解析一次

DSE 參考：P4 Doctor 藍圖感知——讓機器也能讀人類的架構圖。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class BlastRadiusReader:
    """解析 blast-radius.md，提供模組扇入和安全分級查詢.

    使用方式::

        reader = BlastRadiusReader(Path("docs"))
        zone = reader.get_safety_zone("core/event_bus.py")
        # → "forbidden"
        fan_in = reader.get_fan_in("gateway/server.py")
        # → 0
        forbidden = reader.get_forbidden_modules()
        # → ["core/event_bus.py"]
    """

    def __init__(self, docs_dir: Path) -> None:
        self._path = docs_dir / "blast-radius.md"
        self._parsed = False
        # module_name → {"fan_in": int, "zone": str}
        self._modules: Dict[str, Dict] = {}
        self._forbidden: List[str] = []
        self._red_zone: List[str] = []

    def _ensure_parsed(self) -> None:
        """惰性解析（第一次查詢時才解析）."""
        if self._parsed:
            return
        self._parsed = True

        if not self._path.exists():
            logger.warning(
                f"BlastRadiusReader: {self._path} not found"
            )
            return

        try:
            content = self._path.read_text(encoding="utf-8")
            self._parse(content)
        except Exception as e:
            logger.warning(f"BlastRadiusReader parse failed: {e}")

    def _parse(self, content: str) -> None:
        """解析 blast-radius.md 的區段結構."""
        current_zone = "green"  # 預設綠區
        current_module = ""

        for line in content.splitlines():
            stripped = line.strip()

            # 偵測安全區段標題
            if "禁區" in stripped and stripped.startswith("##"):
                current_zone = "forbidden"
            elif "紅區" in stripped and stripped.startswith("##"):
                current_zone = "red"
            elif "黃區" in stripped and stripped.startswith("##"):
                current_zone = "yellow"
            elif "綠區" in stripped and stripped.startswith("##"):
                current_zone = "green"
            # 偵測模組標題（### xxx/yyy.py）
            elif stripped.startswith("### ") and (
                "/" in stripped or ".py" in stripped
            ):
                module_name = stripped[4:].strip()
                current_module = module_name
                self._modules[module_name] = {
                    "fan_in": 0,
                    "zone": current_zone,
                }
                if current_zone == "forbidden":
                    self._forbidden.append(module_name)
                elif current_zone == "red":
                    self._red_zone.append(module_name)
            # 偵測扇入數（| **扇入** | N... |）
            elif current_module and "扇入" in stripped:
                match = re.search(r"\|\s*\*?\*?扇入\*?\*?\s*\|\s*(\d+)", stripped)
                if match:
                    fan_in = int(match.group(1))
                    if current_module in self._modules:
                        self._modules[current_module]["fan_in"] = fan_in

    def get_fan_in(self, module_name: str) -> int:
        """查詢模組扇入數.

        Args:
            module_name: 模組路徑（如 "core/event_bus.py"）

        Returns:
            扇入數，未找到回傳 -1
        """
        self._ensure_parsed()
        info = self._modules.get(module_name)
        return info["fan_in"] if info else -1

    def get_safety_zone(self, module_name: str) -> str:
        """回傳安全分級.

        Args:
            module_name: 模組路徑

        Returns:
            "forbidden" / "red" / "yellow" / "green" / "unknown"
        """
        self._ensure_parsed()
        info = self._modules.get(module_name)
        return info["zone"] if info else "unknown"

    def get_forbidden_modules(self) -> List[str]:
        """回傳所有禁區模組路徑."""
        self._ensure_parsed()
        return list(self._forbidden)

    def get_red_zone_modules(self) -> List[str]:
        """回傳所有紅區模組路徑."""
        self._ensure_parsed()
        return list(self._red_zone)

    def get_all_modules(self) -> Dict[str, Dict]:
        """回傳所有解析到的模組及其資訊."""
        self._ensure_parsed()
        return dict(self._modules)


class JointMapReader:
    """解析 joint-map.md，提供共享狀態查詢.

    使用方式::

        reader = JointMapReader(Path("docs"))
        writers = reader.get_writers("PulseDB")
        # → ["pulse/pulse_db.py", "nightly/nightly_pipeline.py", ...]
    """

    def __init__(self, docs_dir: Path) -> None:
        self._path = docs_dir / "joint-map.md"
        self._parsed = False
        # state_name → {"writers": [...], "readers": [...]}
        self._states: Dict[str, Dict[str, List[str]]] = {}

    def _ensure_parsed(self) -> None:
        """惰性解析."""
        if self._parsed:
            return
        self._parsed = True

        if not self._path.exists():
            logger.warning(
                f"JointMapReader: {self._path} not found"
            )
            return

        try:
            content = self._path.read_text(encoding="utf-8")
            self._parse(content)
        except Exception as e:
            logger.warning(f"JointMapReader parse failed: {e}")

    def _parse(self, content: str) -> None:
        """解析 joint-map.md 的共享狀態區段."""
        current_state = ""
        current_section = ""  # "writers" or "readers"

        for line in content.splitlines():
            stripped = line.strip()

            # 偵測共享狀態標題（### N. name）
            if stripped.startswith("### ") and re.match(
                r"### \d+\.", stripped
            ):
                # 例如 "### 8. PulseDB (pulse.db)"
                match = re.match(r"### \d+\.\s+(.+)", stripped)
                if match:
                    current_state = match.group(1).strip()
                    self._states[current_state] = {
                        "writers": [],
                        "readers": [],
                    }
                    current_section = ""

            # 偵測寫入者/讀取者區段
            elif "寫入者" in stripped and stripped.startswith("####"):
                current_section = "writers"
            elif "讀取者" in stripped and stripped.startswith("####"):
                current_section = "readers"
            elif stripped.startswith("####"):
                current_section = ""  # 其他子區段
            elif stripped.startswith("---"):
                current_section = ""

            # 解析表格行中的模組名（| `xxx/yyy.py` | ... |）
            elif (
                current_state
                and current_section
                and stripped.startswith("|")
                and "`" in stripped
            ):
                match = re.search(r"`([^`]+\.py)`", stripped)
                if match and current_state in self._states:
                    module = match.group(1)
                    self._states[current_state][current_section].append(
                        module
                    )

    def get_writers(self, state_name: str) -> List[str]:
        """查詢共享狀態的寫入者.

        Args:
            state_name: 狀態名稱（部分匹配）

        Returns:
            寫入者模組列表
        """
        self._ensure_parsed()
        # 支援部分匹配
        for key, info in self._states.items():
            if state_name.lower() in key.lower():
                return list(info["writers"])
        return []

    def get_readers(self, state_name: str) -> List[str]:
        """查詢共享狀態的讀取者.

        Args:
            state_name: 狀態名稱（部分匹配）

        Returns:
            讀取者模組列表
        """
        self._ensure_parsed()
        for key, info in self._states.items():
            if state_name.lower() in key.lower():
                return list(info["readers"])
        return []

    def get_all_states(self) -> Dict[str, Dict[str, List[str]]]:
        """回傳所有解析到的共享狀態."""
        self._ensure_parsed()
        return dict(self._states)
