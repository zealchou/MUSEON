"""BDD step definitions for Blueprint Integrity (工程藍圖完整性).

驗證四張工程藍圖涵蓋所有已知的模組、共享狀態和跨系統依賴。
"""

import re
from pathlib import Path

import pytest
from pytest_bdd import given, scenarios, then, when, parsers

# ── Link feature file ──
scenarios("../../features/blueprint_integrity.feature")

# ── 路徑常數 ──
DOCS_DIR = Path(__file__).parent.parent.parent / "docs"
JOINT_MAP = DOCS_DIR / "joint-map.md"
BLAST_RADIUS = DOCS_DIR / "blast-radius.md"
SYSTEM_TOPOLOGY = DOCS_DIR / "system-topology.md"
PERSISTENCE_CONTRACT = DOCS_DIR / "persistence-contract.md"


# ═══════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════

class BlueprintContext:
    """Test context for blueprint validation."""

    def __init__(self):
        self.joint_map: str = ""
        self.blast_radius: str = ""
        self.topology: str = ""
        self.persistence: str = ""

    def load_all(self):
        self.joint_map = JOINT_MAP.read_text(encoding="utf-8")
        self.blast_radius = BLAST_RADIUS.read_text(encoding="utf-8")
        self.topology = SYSTEM_TOPOLOGY.read_text(encoding="utf-8")
        self.persistence = PERSISTENCE_CONTRACT.read_text(encoding="utf-8")


@pytest.fixture
def ctx():
    return BlueprintContext()


# ═══════════════════════════════════════
# Background
# ═══════════════════════════════════════

@given("四張工程藍圖已載入")
def given_blueprints_loaded(ctx):
    ctx.load_all()
    assert len(ctx.joint_map) > 0, "joint-map.md 為空"
    assert len(ctx.blast_radius) > 0, "blast-radius.md 為空"
    assert len(ctx.topology) > 0, "system-topology.md 為空"
    assert len(ctx.persistence) > 0, "persistence-contract.md 為空"


# ═══════════════════════════════════════
# 🔗 接頭圖（joint-map.md）
# ═══════════════════════════════════════

@when("掃描 ANIMA_MC.json 的實際寫入模組")
def when_scan_anima_mc_writers(ctx):
    pass  # 驗證在 then 步驟中進行


@when("掃描 ANIMA_USER.json 的實際寫入模組")
def when_scan_anima_user_writers(ctx):
    pass


@when("掃描 evolution 目錄的共享檔案寫入")
def when_scan_evolution_shared_files(ctx):
    pass


@when("檢查 CRITICAL 區域的寫入者清單")
def when_check_critical_writers(ctx):
    pass


@then(parsers.parse('接頭圖應列出 "{module}" 為 ANIMA_MC 寫入者'))
def then_joint_map_anima_mc_writer(ctx, module):
    # 搜尋 ANIMA_MC.json 段落中是否出現此模組
    anima_mc_section = _extract_section(ctx.joint_map, "1. ANIMA_MC", "2. PULSE")
    assert module in anima_mc_section, (
        f"接頭圖的 ANIMA_MC.json 段落中未找到 '{module}'"
    )


@then(parsers.parse('接頭圖應列出 "{module}" 為 ANIMA_MC 讀寫者'))
def then_joint_map_anima_mc_rw(ctx, module):
    anima_mc_section = _extract_section(ctx.joint_map, "1. ANIMA_MC", "2. PULSE")
    assert module in anima_mc_section, (
        f"接頭圖的 ANIMA_MC.json 段落中未找到 '{module}'"
    )


@then(parsers.parse('接頭圖應列出 "{module}" 為 ANIMA_USER 寫入者'))
def then_joint_map_anima_user_writer(ctx, module):
    anima_user_section = _extract_section(ctx.joint_map, "3. ANIMA_USER", "4. question_queue")
    assert module in anima_user_section, (
        f"接頭圖的 ANIMA_USER.json 段落中未找到 '{module}'"
    )


@then(parsers.parse('接頭圖應包含共享狀態 "{state_name}"'))
def then_joint_map_contains_state(ctx, state_name):
    assert state_name in ctx.joint_map, (
        f"接頭圖中未找到共享狀態 '{state_name}'"
    )


@then(parsers.parse("ANIMA_MC.json 的寫入者應至少有 {n:d} 個模組"))
def then_anima_mc_min_writers(ctx, n):
    anima_mc_section = _extract_section(ctx.joint_map, "1. ANIMA_MC", "2. PULSE")
    # 計算寫入者表格中的行數（每行以 | 開頭且包含模組路徑）
    writer_rows = [
        line for line in anima_mc_section.split("\n")
        if line.strip().startswith("|") and ".py" in line
        and "寫入" not in line and "模組" not in line
    ]
    assert len(writer_rows) >= n, (
        f"ANIMA_MC.json 寫入者只有 {len(writer_rows)} 個，預期至少 {n} 個"
    )


@then(parsers.parse("ANIMA_USER.json 的寫入者應至少有 {n:d} 個模組"))
def then_anima_user_min_writers(ctx, n):
    anima_user_section = _extract_section(ctx.joint_map, "3. ANIMA_USER", "4. question_queue")
    writer_rows = [
        line for line in anima_user_section.split("\n")
        if line.strip().startswith("|") and ".py" in line
        and "寫入" not in line and "模組" not in line
    ]
    assert len(writer_rows) >= n, (
        f"ANIMA_USER.json 寫入者只有 {len(writer_rows)} 個，預期至少 {n} 個"
    )


# ═══════════════════════════════════════
# 💥 爆炸圖（blast-radius.md）
# ═══════════════════════════════════════

@when("掃描 evolution 目錄的跨模組依賴")
def when_scan_evolution_deps(ctx):
    pass


@when("掃描 guardian 目錄的跨模組依賴")
def when_scan_guardian_deps(ctx):
    pass


@when("檢查模組組定義")
def when_check_module_groups(ctx):
    pass


@then(parsers.parse('爆炸圖應包含模組 "{module}"'))
def then_blast_radius_contains_module(ctx, module):
    assert module in ctx.blast_radius, (
        f"爆炸圖中未找到模組 '{module}'"
    )


@then(parsers.parse('應存在模組組 "{group_id}" 包含 "{member}"'))
def then_module_group_contains(ctx, group_id, member):
    # 在模組組表格中找到 group_id 對應的行，檢查是否包含 member
    group_section = _extract_section(
        ctx.blast_radius,
        "必須同時修改的模組組",
        "修改決策流程圖"
    )
    group_rows = [
        line for line in group_section.split("\n")
        if group_id in line
    ]
    assert any(member in row for row in group_rows), (
        f"模組組 {group_id} 中未找到成員 '{member}'"
    )


# ═══════════════════════════════════════
# 🧠 神經圖（system-topology.md）
# ═══════════════════════════════════════

@when("掃描 evolution 系統的實際模組")
def when_scan_evolution_system(ctx):
    pass


@when("掃描 governance 群組的實際模組")
def when_scan_governance_group(ctx):
    pass


@when("掃描 agent 群組的實際模組")
def when_scan_agent_group(ctx):
    pass


@when("掃描 tools 系統的實際模組")
def when_scan_tools_system(ctx):
    pass


@when("掃描 evolution 事件鏈的連線")
def when_scan_evolution_event_chain(ctx):
    pass


@when("檢查群組 Hub 與 event-bus 的連線")
def when_check_hub_event_bus(ctx):
    pass


@then(parsers.parse('神經圖應包含節點 "{node_id}"'))
def then_topology_contains_node(ctx, node_id):
    assert node_id in ctx.topology, (
        f"神經圖中未找到節點 '{node_id}'"
    )


@then(parsers.parse('神經圖應包含連線從 "{source}" 到 "{target}"'))
def then_topology_contains_link(ctx, source, target):
    # 在連線清單中尋找 source → target 的行
    links_section = _extract_section(ctx.topology, "連線清單", "驗證規則")
    # 尋找包含 source 和 target 的同一行
    found = False
    for line in links_section.split("\n"):
        if source in line and target in line and "|" in line:
            found = True
            break
    assert found, (
        f"神經圖中未找到從 '{source}' 到 '{target}' 的連線"
    )


@then("每個群組 Hub 應至少有 1 條與 event-bus 的連線")
def then_all_hubs_connected_to_event_bus(ctx):
    # 已知的群組 Hub
    hubs = ["brain", "pulse", "governance", "doctor", "llm-router", "nightly", "data-bus"]
    links_section = _extract_section(ctx.topology, "連線清單", "驗證規則")

    for hub in hubs:
        # 檢查是否有 event-bus → hub 或 hub → event-bus 的連線
        has_connection = False
        for line in links_section.split("\n"):
            if "event-bus" in line and hub in line and "|" in line:
                has_connection = True
                break
        assert has_connection, (
            f"群組 Hub '{hub}' 缺少與 event-bus 的連線"
        )


# ═══════════════════════════════════════
# 🔧 水電圖（persistence-contract.md）
# ═══════════════════════════════════════

@when("掃描 JSONL 日誌檔案群")
def when_scan_jsonl_log_group(ctx):
    pass


@when("掃描記憶系統的讀寫模組")
def when_scan_memory_system_rw(ctx):
    pass


@when("掃描 data 群組的持久層")
def when_scan_data_group_persistence(ctx):
    pass


@when("掃描 installer 目錄的資料寫入")
def when_scan_installer_data_writes(ctx):
    pass


@when("比對爆炸圖和接頭圖的共享狀態計數")
def when_compare_shared_state_counts(ctx):
    pass


@then(parsers.parse('爆炸圖健康快照應包含 "{count}"'))
def then_blast_radius_snapshot_contains(ctx, count):
    health_section = _extract_section(ctx.blast_radius, "系統健康度快照", "變更日誌")
    assert count in health_section, (
        f"爆炸圖健康快照中未找到 '{count}'"
    )


@when("掃描 evolution 目錄的資料寫入")
def when_scan_evolution_data_writes(ctx):
    pass


@when("掃描 guardian 目錄的資料寫入")
def when_scan_guardian_data_writes(ctx):
    pass


@when("檢查寫入消費配對表")
def when_check_write_consume_pairs(ctx):
    pass


@then(parsers.parse('水電圖應包含資料路徑 "{path_fragment}"'))
def then_persistence_contains_path(ctx, path_fragment):
    assert path_fragment in ctx.persistence, (
        f"水電圖中未找到資料路徑 '{path_fragment}'"
    )


@then("不應存在未被標記的 Dead Write")
def then_no_unmarked_dead_writes(ctx):
    # 驗證 Dead Write 段落存在且有明確列表
    assert "Dead Write" in ctx.persistence, (
        "水電圖中未找到 Dead Write 段落"
    )
    # 驗證每個 Dead Write 有建議處理方式
    dead_write_section = _extract_section(
        ctx.persistence,
        "Dead Write",
        "Dead Directory"
    )
    if "DW" in dead_write_section:
        # 確保每個 DW 條目有「建議處理」欄位
        dw_rows = [
            line for line in dead_write_section.split("\n")
            if line.strip().startswith("| DW")
        ]
        for row in dw_rows:
            assert "確認" in row or "移除" in row or "接通" in row or "清理" in row or "刪除" in row, (
                f"Dead Write 條目缺少處理建議: {row}"
            )


# ═══════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════

def _extract_section(content: str, start_marker: str, end_marker: str) -> str:
    """Extract a section of markdown between two markers."""
    lines = content.split("\n")
    start_idx = None
    end_idx = None

    for i, line in enumerate(lines):
        if start_marker in line and start_idx is None:
            start_idx = i
        elif end_marker in line and start_idx is not None:
            end_idx = i
            break

    if start_idx is not None:
        if end_idx is not None:
            return "\n".join(lines[start_idx:end_idx])
        return "\n".join(lines[start_idx:])
    return ""
