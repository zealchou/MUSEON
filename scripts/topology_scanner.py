#!/usr/bin/env python3
"""
MUSEON Topology Scanner
Phase 1: Full static analysis of all Python files
- Maps all imports (who depends on whom)
- Maps all class/function definitions
- Maps all usages (who calls/references what)
- Detects orphans (forward + reverse)
"""

import ast
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

ROOT = Path("/Users/ZEALCHOU/MUSEON/src/museon")
PACKAGE = "museon"


# ─────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────

@dataclass
class Symbol:
    name: str
    kind: str  # "class" | "function" | "method"
    module: str  # e.g. museon.agent.brain
    file: str
    line: int
    parent_class: Optional[str] = None  # for methods

@dataclass
class ModuleInfo:
    module_path: str   # e.g. museon.agent.brain
    file: str
    imports: list = field(default_factory=list)         # (source_module, symbol_or_None)
    definitions: list = field(default_factory=list)     # Symbol objects
    references: list = field(default_factory=list)      # raw name references made in this file


# ─────────────────────────────────────────────
# Scanner
# ─────────────────────────────────────────────

class MuseonScanner:
    def __init__(self):
        self.modules: dict[str, ModuleInfo] = {}
        self.all_symbols: dict[str, list[Symbol]] = defaultdict(list)  # qualified_name -> [Symbol]
        self.errors: list[str] = []

    def file_to_module(self, filepath: str) -> str:
        p = Path(filepath)
        rel = p.relative_to(ROOT.parent)  # relative to src/
        parts = rel.with_suffix("").parts
        return ".".join(parts)

    def scan_all(self):
        py_files = sorted(ROOT.rglob("*.py"))
        for f in py_files:
            self._scan_file(str(f))
        print(f"[scanner] Scanned {len(self.modules)} modules, "
              f"{sum(len(m.definitions) for m in self.modules.values())} symbols, "
              f"{len(self.errors)} parse errors")

    def _scan_file(self, filepath: str):
        module_path = self.file_to_module(filepath)
        info = ModuleInfo(module_path=module_path, file=filepath)

        try:
            source = Path(filepath).read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=filepath)
        except SyntaxError as e:
            self.errors.append(f"SyntaxError in {filepath}: {e}")
            self.modules[module_path] = info
            return

        # Collect imports
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    info.imports.append((alias.name, None))
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level > 0:
                    # relative import → resolve to absolute
                    parts = module_path.split(".")
                    base_parts = parts[:-(node.level)]
                    if base:
                        base_parts.append(base)
                    base = ".".join(base_parts)
                for alias in node.names:
                    info.imports.append((base, alias.name))

        # Collect definitions
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                sym = Symbol(
                    name=node.name,
                    kind="class",
                    module=module_path,
                    file=filepath,
                    line=node.lineno,
                )
                info.definitions.append(sym)
                self.all_symbols[f"{module_path}.{node.name}"].append(sym)
                # Methods
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        msym = Symbol(
                            name=item.name,
                            kind="method",
                            module=module_path,
                            file=filepath,
                            line=item.lineno,
                            parent_class=node.name,
                        )
                        info.definitions.append(msym)
                        self.all_symbols[f"{module_path}.{node.name}.{item.name}"].append(msym)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Top-level functions only (not inside a class)
                if not any(
                    isinstance(p, ast.ClassDef)
                    for p in ast.walk(tree)
                    if any(
                        isinstance(child, type(node)) and child is node
                        for child in ast.walk(p)
                        if isinstance(p, ast.ClassDef)
                    )
                ):
                    pass  # will handle below

        # Re-collect top-level functions more carefully
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                sym = Symbol(
                    name=node.name,
                    kind="function",
                    module=module_path,
                    file=filepath,
                    line=node.lineno,
                )
                info.definitions.append(sym)
                self.all_symbols[f"{module_path}.{node.name}"].append(sym)

        # Collect raw Name/Attribute references (rough usage map)
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                info.references.append(node.id)
            elif isinstance(node, ast.Attribute):
                info.references.append(node.attr)

        self.modules[module_path] = info


# ─────────────────────────────────────────────
# Analysis
# ─────────────────────────────────────────────

class TopologyAnalyzer:
    def __init__(self, scanner: MuseonScanner):
        self.s = scanner
        self.report = {}

    # ── 1. Module dependency graph ──
    def build_module_graph(self) -> dict:
        """Returns: {module: {"imports": [...], "imported_by": [...]}}"""
        graph = {m: {"imports": [], "imported_by": []} for m in self.s.modules}
        for mod, info in self.s.modules.items():
            for src, sym in info.imports:
                if src in self.s.modules:
                    if src not in graph[mod]["imports"]:
                        graph[mod]["imports"].append(src)
                    if mod not in graph[src]["imported_by"]:
                        graph[src]["imported_by"].append(mod)
        return graph

    # ── 2. Orphan modules (no one imports them) ──
    def find_orphan_modules(self, graph: dict) -> list:
        """Modules with zero imported_by (and not an entrypoint)"""
        entrypoints = {
            "museon.gateway.server",
            "museon.mcp_server",
            "museon.doctor.museworker",
            "museon.doctor.museoff",
            "museon.doctor.museqa",
            "museon.doctor.musedoc",
            "museon.nightly.nightly_pipeline",
            "museon.doctor.system_audit",
            "museon.__init__",
        }
        orphans = []
        for mod, data in graph.items():
            if not data["imported_by"] and mod not in entrypoints:
                orphans.append(mod)
        return sorted(orphans)

    # ── 3. Broken imports (import target doesn't exist in codebase) ──
    def find_broken_imports(self) -> list:
        broken = []
        for mod, info in self.s.modules.items():
            for src, sym in info.imports:
                if src.startswith("museon"):
                    if src not in self.s.modules:
                        broken.append({
                            "in_module": mod,
                            "missing_import": src,
                            "symbol": sym,
                        })
        return broken

    # ── 4. Symbols defined but never referenced ──
    def find_unused_symbols(self, graph: dict) -> list:
        # Build a set of all names referenced anywhere
        all_refs = set()
        for info in self.s.modules.values():
            all_refs.update(info.references)

        unused = []
        for qname, syms in self.s.all_symbols.items():
            for sym in syms:
                if sym.kind in ("class", "function"):
                    if sym.name not in all_refs and not sym.name.startswith("_"):
                        unused.append({
                            "qualified_name": qname,
                            "kind": sym.kind,
                            "module": sym.module,
                            "file": sym.file,
                            "line": sym.line,
                        })
        return unused

    # ── 5. Fan-in count per module ──
    def fan_in_table(self, graph: dict) -> list:
        rows = []
        for mod, data in graph.items():
            rows.append({
                "module": mod,
                "fan_in": len(data["imported_by"]),
                "fan_out": len(data["imports"]),
                "imported_by": data["imported_by"],
            })
        return sorted(rows, key=lambda r: r["fan_in"], reverse=True)

    # ── 6. Run all ──
    def run(self) -> dict:
        graph = self.build_module_graph()
        orphan_mods = self.find_orphan_modules(graph)
        broken = self.find_broken_imports()
        unused_syms = self.find_unused_symbols(graph)
        fan_in = self.fan_in_table(graph)

        self.report = {
            "summary": {
                "total_modules": len(self.s.modules),
                "total_symbols": sum(len(v) for v in self.s.all_symbols.values()),
                "orphan_modules": len(orphan_mods),
                "broken_imports": len(broken),
                "parse_errors": len(self.s.errors),
            },
            "orphan_modules": orphan_mods,
            "broken_imports": broken,
            "unused_symbols_sample": unused_syms[:100],  # top 100
            "fan_in_table": fan_in[:40],  # top 40 by fan-in
            "parse_errors": self.s.errors,
        }
        return self.report


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    print("[museon-topology-scanner] Starting full static analysis...")
    scanner = MuseonScanner()
    scanner.scan_all()

    analyzer = TopologyAnalyzer(scanner)
    report = analyzer.run()

    out_path = Path("/Users/ZEALCHOU/MUSEON/scripts/topology_report.json")
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"[scanner] Report written to {out_path}")

    # Print summary to stdout
    s = report["summary"]
    print(f"\n{'='*60}")
    print(f"  MUSEON Topology Scan Summary")
    print(f"{'='*60}")
    print(f"  Total modules     : {s['total_modules']}")
    print(f"  Total symbols     : {s['total_symbols']}")
    print(f"  Orphan modules    : {s['orphan_modules']}")
    print(f"  Broken imports    : {s['broken_imports']}")
    print(f"  Parse errors      : {s['parse_errors']}")
    print(f"{'='*60}")

    print(f"\n── Orphan Modules (no one imports them) ──")
    for m in report["orphan_modules"]:
        print(f"  🔴 {m}")

    print(f"\n── Broken Imports (target missing) ──")
    for b in report["broken_imports"][:30]:
        sym = f":{b['symbol']}" if b['symbol'] else ""
        print(f"  ⚡ {b['in_module']} → {b['missing_import']}{sym}")

    print(f"\n── Top Fan-In Modules (扇入最高 = 最危險改動) ──")
    for r in report["fan_in_table"][:20]:
        bar = "█" * min(r["fan_in"], 30)
        print(f"  {r['fan_in']:3d} {bar}  {r['module']}")

    print(f"\nFull report: {out_path}")


if __name__ == "__main__":
    main()
