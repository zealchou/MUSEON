"""
AST-based import scanner — 計算 src/museon/ 下所有模組的實際扇入扇出。

用 AST 靜態解析 import 語句，不執行任何程式碼。
MuseWorker 的核心計算引擎，也供 MuseOff / MuseDoc 查詢。

設計參考：
- Google presubmit 的依賴圖分析
- Datadog Watchdog 的 baseline 建立
"""

from __future__ import annotations

import ast
import logging
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 安全分級常數（與 blast-radius.md v1.62 一致）
# ---------------------------------------------------------------------------
ZONE_FORBIDDEN = "FORBIDDEN"  # 扇入 >= 40
ZONE_RED = "RED"              # 扇入 10-39 或系統核心
ZONE_YELLOW = "YELLOW"        # 扇入 2-9
ZONE_GREEN = "GREEN"          # 扇入 0-1

# 特殊模組：扇入低但因扇出/關鍵度列為紅區
_FORCE_RED = frozenset({
    "gateway/server.py",   # 入口點，扇出 50+
    "agent/brain.py",      # 系統核心，扇出 32+
})


class ModuleInfo(NamedTuple):
    """單一模組的掃描結果"""
    relative_path: str       # e.g. "agent/brain.py"
    fan_in: int              # 被多少個不同模組 import
    fan_out: int             # import 了多少個不同模組
    zone: str                # FORBIDDEN / RED / YELLOW / GREEN
    importers: list[str]     # 誰 import 了它
    imports: list[str]       # 它 import 了誰


def classify_zone(fan_in: int, relative_path: str) -> str:
    """根據扇入數和特殊規則分類安全等級"""
    if relative_path in _FORCE_RED:
        return ZONE_RED
    if fan_in >= 40:
        return ZONE_FORBIDDEN
    if fan_in >= 10:
        return ZONE_RED
    if fan_in >= 2:
        return ZONE_YELLOW
    return ZONE_GREEN


class FanInScanner:
    """AST-based import 掃描器"""

    def __init__(self, src_dir: Path | str):
        self.src_dir = Path(src_dir)
        if not self.src_dir.exists():
            raise FileNotFoundError(f"src_dir not found: {self.src_dir}")

    def scan_all(self) -> dict[str, ModuleInfo]:
        """全量掃描，返回 {relative_path: ModuleInfo}"""
        # Step 1: 收集所有 .py 檔案（排除 __init__.py 和 __pycache__）
        py_files = self._collect_py_files()

        # Step 2: 解析每個檔案的 import
        # module_imports[relative_path] = set of imported relative_paths
        module_imports: dict[str, set[str]] = {}
        for py_file in py_files:
            rel = self._to_relative(py_file)
            imports = self._extract_imports(py_file)
            module_imports[rel] = imports

        # Step 3: 計算扇入（反轉 import 關係）
        fan_in_map: dict[str, set[str]] = defaultdict(set)
        for importer, imported_set in module_imports.items():
            for imported in imported_set:
                if imported != importer:  # 排除自引用
                    fan_in_map[imported].add(importer)

        # Step 4: 組裝結果
        result: dict[str, ModuleInfo] = {}
        all_modules = set(module_imports.keys())
        for rel in sorted(all_modules):
            importers = sorted(fan_in_map.get(rel, set()))
            imports = sorted(module_imports.get(rel, set()))
            fan_in = len(importers)
            fan_out = len(imports)
            zone = classify_zone(fan_in, rel)
            result[rel] = ModuleInfo(
                relative_path=rel,
                fan_in=fan_in,
                fan_out=fan_out,
                zone=zone,
                importers=importers,
                imports=imports,
            )

        return result

    def scan_affected(self, changed_files: list[str]) -> dict[str, ModuleInfo]:
        """增量掃描：只重算受影響的模組（changed + 它們的直接依賴者）"""
        full = self.scan_all()  # TODO: 未來可優化為真正的增量
        changed_set = set(changed_files)
        affected = set()
        for rel in changed_set:
            if rel in full:
                affected.add(rel)
                affected.update(full[rel].importers)
        return {rel: full[rel] for rel in sorted(affected) if rel in full}

    def get_zone_summary(self) -> dict[str, list[str]]:
        """返回各安全等級的模組清單"""
        result = self.scan_all()
        summary: dict[str, list[str]] = {
            ZONE_FORBIDDEN: [],
            ZONE_RED: [],
            ZONE_YELLOW: [],
            ZONE_GREEN: [],
        }
        for info in result.values():
            summary[info.zone].append(info.relative_path)
        return summary

    # -----------------------------------------------------------------------
    # 內部方法
    # -----------------------------------------------------------------------

    def _collect_py_files(self) -> list[Path]:
        """收集所有 .py 檔案（排除 __init__.py 和測試）"""
        files = []
        for p in self.src_dir.rglob("*.py"):
            if p.name == "__init__.py":
                continue
            if "__pycache__" in str(p):
                continue
            if "_dead_code_archive" in str(p):
                continue
            files.append(p)
        return sorted(files)

    def _to_relative(self, path: Path) -> str:
        """轉為 src/museon/ 下的相對路徑，e.g. 'agent/brain.py'"""
        try:
            return str(path.relative_to(self.src_dir))
        except ValueError:
            return str(path)

    def _extract_imports(self, py_file: Path) -> set[str]:
        """用 AST 解析單一 .py 檔案的 museon 內部 import"""
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(py_file))
        except (SyntaxError, UnicodeDecodeError) as e:
            logger.warning("Failed to parse %s: %s", py_file, e)
            return set()

        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and node.module.startswith("museon."):
                    rel = self._module_to_relative(node.module)
                    if rel:
                        imports.add(rel)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("museon."):
                        rel = self._module_to_relative(alias.name)
                        if rel:
                            imports.add(rel)
        return imports

    def _module_to_relative(self, module_name: str) -> str | None:
        """
        將 'museon.agent.brain' 轉為 'agent/brain.py'
        如果對應檔案不存在，嘗試作為 package（__init__.py）
        """
        # 去掉 'museon.' 前綴
        parts = module_name.split(".")
        if len(parts) < 2 or parts[0] != "museon":
            return None
        sub_parts = parts[1:]

        # 嘗試直接對應 .py 檔案
        candidate = self.src_dir / "/".join(sub_parts)
        py_file = candidate.with_suffix(".py")
        if py_file.exists():
            return str(py_file.relative_to(self.src_dir))

        # 嘗試作為 package 目錄（import 到 __init__.py）
        # 但我們不追蹤 __init__.py，所以跳過
        return None


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import json
    import sys

    src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/Users/ZEALCHOU/MUSEON/src/museon")
    scanner = FanInScanner(src)
    result = scanner.scan_all()

    # 輸出統計
    zones = scanner.get_zone_summary()
    print(f"Total modules: {len(result)}")
    print(f"  FORBIDDEN: {len(zones[ZONE_FORBIDDEN])}")
    print(f"  RED:       {len(zones[ZONE_RED])}")
    print(f"  YELLOW:    {len(zones[ZONE_YELLOW])}")
    print(f"  GREEN:     {len(zones[ZONE_GREEN])}")

    # 輸出禁區和紅區細節
    for zone_name in (ZONE_FORBIDDEN, ZONE_RED):
        if zones[zone_name]:
            print(f"\n--- {zone_name} ---")
            for rel in zones[zone_name]:
                info = result[rel]
                print(f"  {rel}: fan_in={info.fan_in}, fan_out={info.fan_out}")

    # 如果帶 --json，輸出完整 JSON
    if "--json" in sys.argv:
        out = {}
        for rel, info in result.items():
            out[rel] = {
                "fan_in": info.fan_in,
                "fan_out": info.fan_out,
                "zone": info.zone,
                "importers": info.importers,
            }
        print(json.dumps(out, indent=2, ensure_ascii=False))
