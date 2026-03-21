#!/usr/bin/env python3
"""
validate_connections.py — Skill 連線驗證器
掃描所有 Skill 的 Manifest（YAML frontmatter），檢查：
1. 孤立輸出：output.trigger == "always" 但無人接收
2. 斷裂輸入：input.required == true 但無人提供
3. 孤立 Skill：零 input + 零 output（非 reference/workflow）
4. 幽靈連線：connects_to 中的名稱不存在
5. 記憶無家：memory.writes.target 不在已知記憶系統列表

用法:
    .venv/bin/python scripts/validate_connections.py
"""

import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "data" / "skills" / "native"

# 已知的記憶系統（對應 memory-router.md）
KNOWN_MEMORY_TARGETS = {
    "knowledge-lattice", "user-model", "wee", "eval-engine",
    "session-log", "auto-memory", "morphenix", "diary",
}


def parse_yaml_frontmatter(text: str) -> dict[str, Any]:
    """簡易 YAML 解析（只處理 Skill Manifest 的結構）"""
    if not text.startswith("---"):
        return {}

    try:
        end = text.index("---", 3)
    except ValueError:
        return {}

    yaml_text = text[3:end].strip()
    result: dict[str, Any] = {}

    # 解析頂層欄位
    current_key = None
    current_section = None
    current_subsection = None
    current_item: dict[str, str] | None = None
    items_list: list[dict] = []

    for line in yaml_text.split("\n"):
        stripped = line.rstrip()

        # 頂層 key（不縮排）
        if stripped and not stripped.startswith(" ") and not stripped.startswith("-"):
            if ":" in stripped:
                # flush 上一個 key 的未完成 item
                if current_key == "io" and current_section and current_item:
                    result.setdefault("io", {}).setdefault(current_section, [])
                    result["io"][current_section].append(current_item)
                if current_key == "memory" and current_subsection and current_item:
                    result.setdefault("memory", {}).setdefault(current_subsection, [])
                    result["memory"][current_subsection].append(current_item)
                key, _, val = stripped.partition(":")
                key = key.strip()
                val = val.strip()
                if val and val != ">":
                    result[key] = val
                current_key = key
                current_section = None
                current_subsection = None
                current_item = None
                continue

        # 頂層 key 切換時，先 flush 上一個 section 的未完成 item
        if current_key == "connects_to" and stripped.strip().startswith("- "):
            result.setdefault("connects_to", [])
            result["connects_to"].append(stripped.strip()[2:].strip())
            continue

        # io 區段
        if current_key == "io":
            s = stripped.strip()
            if s in ("inputs:", "outputs:"):
                # flush 上一個 sub-section 的最後一個 item
                if current_item and current_section:
                    result["io"][current_section].append(current_item)
                current_section = s[:-1]
                result.setdefault("io", {}).setdefault(current_section, [])
                current_item = None
                continue
            if s.startswith("- ") and current_section:
                # 新項目
                if current_item:
                    result["io"][current_section].append(current_item)
                kv = s[2:]
                k, _, v = kv.partition(":")
                current_item = {k.strip(): v.strip()}
                continue
            if s and ":" in s and current_item is not None:
                k, _, v = s.partition(":")
                current_item[k.strip()] = v.strip()
                continue
            if current_item and (not s or s.startswith("connects_to") or s.startswith("memory")):
                result["io"][current_section].append(current_item)
                current_item = None

        # memory 區段
        if current_key == "memory":
            s = stripped.strip()
            if s in ("writes:", "reads:"):
                # flush 上一個 sub-section 的最後一個 item
                if current_item and current_subsection:
                    result["memory"][current_subsection].append(current_item)
                current_subsection = s[:-1]
                result.setdefault("memory", {}).setdefault(current_subsection, [])
                current_item = None
                continue
            if s.startswith("- ") and current_subsection:
                if current_item:
                    result["memory"][current_subsection].append(current_item)
                kv = s[2:]
                k, _, v = kv.partition(":")
                current_item = {k.strip(): v.strip().strip('"')}
                continue
            if s and ":" in s and current_item is not None:
                k, _, v = s.partition(":")
                current_item[k.strip()] = v.strip().strip('"')
                continue

    # 收尾
    if current_key == "io" and current_section and current_item:
        result["io"][current_section].append(current_item)
    if current_key == "memory" and current_subsection and current_item:
        result["memory"][current_subsection].append(current_item)

    return result


def load_all_manifests() -> dict[str, dict]:
    """載入所有 Skill 的 Manifest"""
    manifests = {}
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue
        content = skill_file.read_text(encoding="utf-8")
        manifest = parse_yaml_frontmatter(content)
        if manifest.get("name"):
            manifests[manifest["name"]] = manifest
    return manifests


def validate(manifests: dict[str, dict]) -> tuple[list[str], list[str], list[str]]:
    """執行全部驗證規則，返回 (errors, warnings, info)"""
    errors: list[str] = []
    warnings: list[str] = []
    info: list[str] = []

    all_names = set(manifests.keys())

    # 建立輸出索引：(skill_name, field) → trigger
    output_index: dict[tuple[str, str], str] = {}
    for name, m in manifests.items():
        for out in m.get("io", {}).get("outputs", []):
            to_skill = out.get("to", "")
            field = out.get("field", "")
            trigger = out.get("trigger", "on-request")
            if to_skill and field:
                output_index[(name, field)] = trigger

    # 建立輸入索引：(skill_name) 需要哪些 (from_skill, field, required)
    input_index: dict[str, list[tuple[str, str, bool]]] = {}
    for name, m in manifests.items():
        for inp in m.get("io", {}).get("inputs", []):
            from_skill = inp.get("from", "")
            field = inp.get("field", "")
            required = inp.get("required", "false") == "true"
            input_index.setdefault(name, []).append((from_skill, field, required))

    # 規則 1：孤立輸出（always trigger 但沒有任何 Skill 接收）
    for name, m in manifests.items():
        for out in m.get("io", {}).get("outputs", []):
            to_skill = out.get("to", "")
            field = out.get("field", "")
            trigger = out.get("trigger", "on-request")

            if to_skill == "user":
                continue  # 輸出給使用者不需要接收方

            if trigger == "always":
                # 檢查 to_skill 是否有對應的 input
                has_receiver = False
                for inp_list in input_index.values():
                    for from_s, from_f, _ in inp_list:
                        if from_s == name and from_f == field:
                            has_receiver = True
                            break
                    if has_receiver:
                        break
                # 也檢查 to_skill 是否在其 inputs 中有 from: name
                if not has_receiver:
                    target_inputs = input_index.get(to_skill, [])
                    for from_s, _, _ in target_inputs:
                        if from_s == name:
                            has_receiver = True
                            break

                if not has_receiver:
                    warnings.append(
                        f"⚠️  孤立輸出: {name} → {to_skill}.{field} (trigger=always 但 {to_skill} 的 inputs 未接收)"
                    )

    # 規則 2：斷裂輸入（required=true 但沒有 Skill 提供）
    for name, inputs in input_index.items():
        for from_skill, field, required in inputs:
            if from_skill == "user":
                continue  # 來自使用者不需要 Skill 提供
            if required:
                has_provider = False
                target_outputs = manifests.get(from_skill, {}).get("io", {}).get("outputs", [])
                for out in target_outputs:
                    if out.get("to") == name:
                        has_provider = True
                        break
                if not has_provider:
                    # 也檢查是否有任何輸出的 field 匹配
                    for out in target_outputs:
                        if out.get("field") == field:
                            has_provider = True
                            break
                if not has_provider and from_skill in all_names:
                    warnings.append(
                        f"⚠️  斷裂輸入: {name} 需要 {from_skill}.{field} (required=true) 但 {from_skill} 未宣告對應輸出"
                    )

    # 規則 3：孤立 Skill（零 I/O）
    for name, m in manifests.items():
        skill_type = m.get("type", "on-demand")
        if skill_type in ("reference", "workflow"):
            continue
        inputs = m.get("io", {}).get("inputs", [])
        outputs = m.get("io", {}).get("outputs", [])
        if not inputs and not outputs:
            warnings.append(f"⚠️  孤立 Skill: {name} 無 inputs 也無 outputs")

    # 規則 4：幽靈連線
    for name, m in manifests.items():
        for ct in m.get("connects_to", []):
            if ct not in all_names:
                errors.append(f"❌ 幽靈連線: {name} connects_to '{ct}' 但此 Skill 不存在")

    # 規則 5：記憶無家
    for name, m in manifests.items():
        for write in m.get("memory", {}).get("writes", []):
            target = write.get("target", "")
            if target and target not in KNOWN_MEMORY_TARGETS:
                warnings.append(
                    f"⚠️  記憶無家: {name} 寫入 '{target}' 但此目標不在 memory-router.md 中"
                )

    # 統計資訊
    info.append(f"📊 Skill 總數: {len(manifests)}")
    types = {}
    for m in manifests.values():
        t = m.get("type", "unknown")
        types[t] = types.get(t, 0) + 1
    for t, c in sorted(types.items()):
        info.append(f"   {t}: {c}")

    total_connections = sum(
        len(m.get("io", {}).get("outputs", []))
        for m in manifests.values()
    )
    info.append(f"📊 總連線數: {total_connections}")

    memory_writes = sum(
        len(m.get("memory", {}).get("writes", []))
        for m in manifests.values()
    )
    info.append(f"📊 記憶寫入點: {memory_writes}")

    return errors, warnings, info


def main():
    print("=" * 60)
    print("MUSEON Skill 連線驗證器 v1.0")
    print("=" * 60)

    manifests = load_all_manifests()

    if not manifests:
        print("❌ 未找到任何 Skill Manifest")
        sys.exit(1)

    errors, warnings, info = validate(manifests)

    print("\n--- 統計 ---")
    for i in info:
        print(f"  {i}")

    if warnings:
        print(f"\n--- 警告 ({len(warnings)}) ---")
        for w in warnings:
            print(f"  {w}")

    if errors:
        print(f"\n--- 錯誤 ({len(errors)}) ---")
        for e in errors:
            print(f"  {e}")

    print(f"\n{'=' * 60}")
    if errors:
        print(f"結果: ❌ {len(errors)} 錯誤, {len(warnings)} 警告")
        sys.exit(1)
    elif warnings:
        print(f"結果: ⚠️  {len(warnings)} 警告, 0 錯誤")
        sys.exit(0)
    else:
        print("結果: ✅ 所有連線驗證通過")
        sys.exit(0)


if __name__ == "__main__":
    main()
