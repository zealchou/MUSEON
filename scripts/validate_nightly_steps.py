#!/usr/bin/env python3
"""validate_nightly_steps.py — Nightly Pipeline 步驟完整性檢查工具.

用途：
  - 比對 _FULL_STEPS、_step_map、_step_* 方法，找出不一致
  - 強制執行步驟數量上限（硬上限 55 步）
  - 在 CI / 施工後執行，防止「步驟宣告了但不會跑」的靜默失敗

執行方式：
  python scripts/validate_nightly_steps.py

回傳值：
  0 — 全部通過
  1 — 有問題（詳見 stdout）
"""

import sys
import inspect
import importlib
from pathlib import Path
from typing import Set, List

# 確保可以 import museon
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

MAX_FULL_STEPS = 55  # 硬上限


def main() -> int:
    """執行驗證，回傳 exit code（0=OK, 1=FAIL）."""
    issues: List[str] = []

    # ── 載入模組 ──────────────────────────────────────
    try:
        from museon.nightly.nightly_pipeline import NightlyPipeline, _FULL_STEPS
    except ImportError as e:
        print(f"[FAIL] 無法 import nightly_pipeline: {e}")
        return 1

    # ── 1. 提取 _FULL_STEPS ──────────────────────────
    full_steps_set: Set[str] = set(_FULL_STEPS)
    print(f"[INFO] _FULL_STEPS: {len(_FULL_STEPS)} 步驟")
    print(f"       {_FULL_STEPS}")

    # ── 2. 提取 _step_map ────────────────────────────
    # 需要實例化（需要假 workspace）
    dummy_workspace = Path("data")
    try:
        pipeline = NightlyPipeline(workspace=dummy_workspace)
        step_map = pipeline._step_map
    except Exception as e:
        print(f"[FAIL] 無法實例化 NightlyPipeline: {e}")
        return 1

    step_map_keys: Set[str] = set(step_map.keys())
    print(f"[INFO] _step_map: {len(step_map_keys)} 步驟")

    # ── 3. 提取所有 _step_* 方法 ─────────────────────
    all_step_methods: Set[str] = set()
    for name, _ in inspect.getmembers(pipeline, predicate=inspect.ismethod):
        if name.startswith("_step_"):
            all_step_methods.add(name)
    print(f"[INFO] _step_* 方法: {len(all_step_methods)} 個")

    # ── 4. 取得 _step_map 中對應的方法名稱 ───────────
    step_map_method_names: Set[str] = set()
    step_map_step_names: Set[str] = set()
    for step_id, (step_name, func) in step_map.items():
        step_map_step_names.add(step_name)
        # 取方法名稱（去掉 bound method 的 self）
        method_name = getattr(func, "__name__", None) or getattr(func, "__func__", None).__name__
        step_map_method_names.add(method_name)

    # ── 5. 檢查 _FULL_STEPS 中但不在 _step_map 的步驟 ──
    in_full_not_in_map = full_steps_set - step_map_keys
    if in_full_not_in_map:
        issues.append(
            f"Steps in _FULL_STEPS but NOT in _step_map (will CRASH at runtime): "
            f"{sorted(in_full_not_in_map)}"
        )

    # ── 6. 檢查 _step_map 中但不在 _FULL_STEPS 的步驟 ──
    in_map_not_in_full = step_map_keys - full_steps_set
    if in_map_not_in_full:
        print(
            f"[WARN] Steps in _step_map but NOT in _FULL_STEPS (orphaned/dormant, never run): "
            f"{sorted(in_map_not_in_full)}"
        )
        # 這只是警告，不是 issue（可能是 DORMANT 步驟）

    # ── 7. 檢查 _step_* 方法但不在 _step_map 的 ─────
    methods_not_in_map = all_step_methods - step_map_method_names
    if methods_not_in_map:
        print(
            f"[WARN] _step_* methods not referenced in _step_map (dead code): "
            f"{sorted(methods_not_in_map)}"
        )
        # 也只是警告

    # ── 8. 硬上限檢查 ─────────────────────────────────
    if len(_FULL_STEPS) > MAX_FULL_STEPS:
        issues.append(
            f"_FULL_STEPS has {len(_FULL_STEPS)} steps, exceeds hard cap of {MAX_FULL_STEPS}. "
            f"Remove ghost/dormant steps before adding new ones."
        )

    # ── 9. 重複步驟 ID 檢查 ───────────────────────────
    if len(_FULL_STEPS) != len(full_steps_set):
        dupes = [s for s in _FULL_STEPS if _FULL_STEPS.count(s) > 1]
        issues.append(f"Duplicate step IDs in _FULL_STEPS: {sorted(set(dupes))}")

    # ── 輸出結果 ──────────────────────────────────────
    print()
    print("=" * 60)

    if issues:
        print("[FAIL] 發現以下問題：")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
        print("=" * 60)
        print(f"[FAIL] {len(issues)} 個問題，請修復後再執行。")
        return 1
    else:
        print("[PASS] 所有檢查通過！")
        print(f"  _FULL_STEPS: {len(_FULL_STEPS)} 步驟（上限 {MAX_FULL_STEPS}）")
        print(f"  _step_map: {len(step_map_keys)} 步驟")
        print(f"  _step_* 方法: {len(all_step_methods)} 個")
        in_map_not_in_full_count = len(in_map_not_in_full)
        if in_map_not_in_full_count > 0:
            print(f"  DORMANT 步驟（在 _step_map 但不在 _FULL_STEPS）: {in_map_not_in_full_count} 個")
        print("=" * 60)
        return 0


if __name__ == "__main__":
    sys.exit(main())
