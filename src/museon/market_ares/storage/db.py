"""Market Ares — SQLite 儲存層"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from museon.market_ares.config import MARKET_ARES_DATA, MARKET_ARES_DB


def _ensure_dir():
    MARKET_ARES_DATA.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    _ensure_dir()
    conn = sqlite3.connect(str(MARKET_ARES_DB), timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=60000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection | None = None):
    """初始化 Market Ares 資料庫 Schema"""
    close_after = conn is None
    if conn is None:
        conn = get_connection()

    conn.executescript("""
        -- 地區數據
        CREATE TABLE IF NOT EXISTS regions (
            id TEXT PRIMARY KEY,
            country TEXT NOT NULL DEFAULT '台灣',
            city TEXT NOT NULL,
            district TEXT,
            l1_geography TEXT,        -- JSON: 地理基底
            l2_demographics TEXT,     -- JSON: 人口結構
            l3_lifestyle TEXT,        -- JSON: 生活型態
            l4_events TEXT,           -- JSON: 最近事件
            l5_topology TEXT,         -- JSON: 關係拓樸
            energy_inner TEXT,        -- JSON: 內在八方位基底能量
            energy_outer TEXT,        -- JSON: 外在八方位基底能量
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- 原型定義
        CREATE TABLE IF NOT EXISTS archetypes (
            id INTEGER PRIMARY KEY,
            region_id TEXT NOT NULL REFERENCES regions(id),
            name TEXT NOT NULL,
            description TEXT,
            weight REAL NOT NULL DEFAULT 0.0,
            inner_energy TEXT NOT NULL,   -- JSON: {天: 2.1, 風: -0.5, ...}
            outer_energy TEXT NOT NULL,   -- JSON
            adoption_stage TEXT NOT NULL DEFAULT 'early_majority',
            purchase_triggers TEXT,       -- JSON array
            resistance_triggers TEXT,     -- JSON array
            influence_targets TEXT,       -- JSON array of archetype IDs
            influenced_by TEXT,           -- JSON array of archetype IDs
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- 模擬設定
        CREATE TABLE IF NOT EXISTS simulations (
            id TEXT PRIMARY KEY,
            region_id TEXT NOT NULL REFERENCES regions(id),
            strategy TEXT NOT NULL,        -- JSON: StrategyVector
            mode TEXT NOT NULL DEFAULT 'self_drive',
            round_number INTEGER DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        );

        -- 模擬快照（每週一筆）
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            simulation_id TEXT NOT NULL REFERENCES simulations(id),
            week INTEGER NOT NULL,
            archetype_states TEXT NOT NULL, -- JSON
            business_metrics TEXT NOT NULL, -- JSON
            competitor_actions TEXT,        -- JSON
            partner_attitudes TEXT,         -- JSON
            events TEXT,                    -- JSON
            insight TEXT,
            is_turning_point INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(simulation_id, week)
        );

        -- 競爭者 Agent
        CREATE TABLE IF NOT EXISTS competitors (
            id TEXT PRIMARY KEY,
            simulation_id TEXT NOT NULL REFERENCES simulations(id),
            name TEXT NOT NULL,
            market_share REAL DEFAULT 0.0,
            energy_profile TEXT,    -- JSON
            reaction_style TEXT DEFAULT 'analytical',
            reaction_threshold REAL DEFAULT 0.05
        );

        -- 生態夥伴 Agent
        CREATE TABLE IF NOT EXISTS partners (
            id TEXT PRIMARY KEY,
            simulation_id TEXT NOT NULL REFERENCES simulations(id),
            name TEXT NOT NULL,
            role TEXT DEFAULT 'supplier',
            cooperation_score REAL DEFAULT 0.7,
            energy_profile TEXT,    -- JSON
            interest_alignment REAL DEFAULT 0.5
        );

        -- 索引
        CREATE INDEX IF NOT EXISTS idx_archetypes_region ON archetypes(region_id);
        CREATE INDEX IF NOT EXISTS idx_snapshots_sim ON snapshots(simulation_id);
        CREATE INDEX IF NOT EXISTS idx_snapshots_week ON snapshots(simulation_id, week);
        CREATE INDEX IF NOT EXISTS idx_competitors_sim ON competitors(simulation_id);
        CREATE INDEX IF NOT EXISTS idx_partners_sim ON partners(simulation_id);
    """)

    conn.commit()
    if close_after:
        conn.close()


def save_region(conn: sqlite3.Connection, region_id: str, country: str, city: str,
                district: str | None = None, **layer_data) -> None:
    conn.execute("""
        INSERT OR REPLACE INTO regions (id, country, city, district,
            l1_geography, l2_demographics, l3_lifestyle, l4_events, l5_topology,
            energy_inner, energy_outer, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (
        region_id, country, city, district,
        json.dumps(layer_data.get("l1"), ensure_ascii=False) if layer_data.get("l1") else None,
        json.dumps(layer_data.get("l2"), ensure_ascii=False) if layer_data.get("l2") else None,
        json.dumps(layer_data.get("l3"), ensure_ascii=False) if layer_data.get("l3") else None,
        json.dumps(layer_data.get("l4"), ensure_ascii=False) if layer_data.get("l4") else None,
        json.dumps(layer_data.get("l5"), ensure_ascii=False) if layer_data.get("l5") else None,
        json.dumps(layer_data.get("energy_inner"), ensure_ascii=False) if layer_data.get("energy_inner") else None,
        json.dumps(layer_data.get("energy_outer"), ensure_ascii=False) if layer_data.get("energy_outer") else None,
    ))
    conn.commit()


def save_snapshot(conn: sqlite3.Connection, simulation_id: str, snapshot: dict) -> None:
    conn.execute("""
        INSERT OR REPLACE INTO snapshots
            (simulation_id, week, archetype_states, business_metrics,
             competitor_actions, partner_attitudes, events, insight, is_turning_point)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        simulation_id,
        snapshot["week"],
        json.dumps(snapshot.get("archetype_states", {}), ensure_ascii=False),
        json.dumps(snapshot.get("business_metrics", {}), ensure_ascii=False),
        json.dumps(snapshot.get("competitor_actions", []), ensure_ascii=False),
        json.dumps(snapshot.get("partner_attitudes", []), ensure_ascii=False),
        json.dumps(snapshot.get("events", []), ensure_ascii=False),
        snapshot.get("insight", ""),
        1 if snapshot.get("is_turning_point") else 0,
    ))
    conn.commit()
