# Project Epigenesis — DNA 式記憶系統重構

> 設計哲學：DNA 3.2GB — 不存所有蛋白質，存調控規則
> 目標：讓 MUSEON 從「被動快照」進化為「主動預判」

## 迭代進度

| # | 迭代 | 狀態 | Commit | 說明 |
|---|------|------|--------|------|
| 1 | ANIMA_USER Changelog | ✅ 完成 | `f3374f89` | 差分版本追蹤，讓使用者變化可回溯 |
| 2 | PulseDB Anima History API | ✅ 完成 | `cbcfbece` | 暴露八元素變化歷史查詢（by_days + trend） |
| 3 | Soul Ring → Qdrant 索引 | ✅ 完成 | `3b9f7139` | 年輪語義搜索 + 回填腳本（第 9 個 collection） |
| 4 | Adaptive Decay Engine | ✅ 完成 | `46bb4dfc` | ACT-R 式統一衰減引擎（B_i = ln(Σt^{-d}) + β） |
| 5 | Memory Reflector | ✅ 完成 | `f9646876` | Hindsight 式 Retain→Recall→Reflect |
| 6 | Epigenetic Router | ✅ 完成 | `f9646876` | MAGMA 式多圖遍歷（semantic/temporal/causal/entity） |
| 7 | Proactive Predictor | ✅ 完成 | `74024786` | 四維需求預判（序列/情緒/決策循環） |
| 8 | 藍圖全面同步 + brain.py 接線 | ✅ 完成 | (pending) | brain.py 接入 EpigeneticRouter；brain_prompt_builder 反思摘要注入；blast-radius v1.55 + joint-map v1.40 + memory-router v1.6 + persistence-contract v1.32；system-topology v1.45 已有節點定義 |

## 架構總覽

```
Layer 3: 表觀遺傳層 — EpigeneticRouter（迭代 6）
    ↑ 觸發
Layer 2: 編碼層 — Soul Ring 索引（迭代 3）+ Reflector（迭代 5）
    ↑ 來源
Layer 1: 調控層 — Changelog（迭代 1）+ History API（迭代 2）+ Decay（迭代 4）
```

## 設計約束

### 絕對不能變的
- Soul Ring Hash Chain 完整性（append-only + SHA-256）
- KernelGuard 五大不可覆寫值
- AnimaMCStore Lock + 原子寫入
- 現有 8 個 Qdrant collection 結構
- 六層記憶 TTL + 升降級邏輯
- Crystal RI 衰減公式
- Memory Gate 糾正/否認機制
- WriteQueue 序列化保證

### 新增檔案（預計）
- `src/museon/pulse/anima_changelog.py`
- `src/museon/memory/adaptive_decay.py`
- `src/museon/memory/epigenetic_router.py`
- `src/museon/memory/memory_reflector.py`
- `scripts/backfill_soul_rings_to_qdrant.py`
- 對應 5 個 test 檔案

---

## 迭代 1 詳細規格：ANIMA_USER Changelog

### 目的
讓 ANIMA_USER 的每次變化可追溯——「什麼時候開始偏好簡潔風格」「信任等級何時升級」

### 新增檔案
`src/museon/pulse/anima_changelog.py`

### 設計
```python
class AnimaChangelog:
    """ANIMA_USER 差分日誌 — append-only JSONL。

    每次 _save_anima_user() 時，計算 old vs new 的 diff 並追加。
    不改變 ANIMA_USER 本身的讀寫機制——純 hook。

    儲存：data/anima/anima_user_changelog.jsonl
    格式：{"ts": ISO8601, "diffs": [{"path": "...", "old": ..., "new": ...}], "trigger": "observe_user"}

    查詢 API：
    - get_changes(field_path, days=30) → 特定欄位的變化歷史
    - get_evolution_summary(months=3) → 演化摘要
    - get_snapshot_at(date) → 從 changelog 反推某日的 ANIMA_USER 近似狀態
    """
```

### 改動現有檔案
`brain.py` `_save_anima_user()` — 加 2 行：
```python
# 在寫入前，取 old_data 與 new_data 的 diff
if hasattr(self, '_anima_changelog') and self._anima_changelog:
    self._anima_changelog.record(old_data, anima, trigger="observe_user")
```

`brain.py` `__init__()` — 加 1 行初始化

### 測試
`tests/unit/test_anima_changelog.py`
- test_record_diff_basic
- test_record_no_change
- test_get_changes_by_field
- test_get_evolution_summary
- test_changelog_rotation（超過 90 天自動壓縮）

### Pre-Flight
- joint-map：ANIMA_USER.json 新增一個讀取者（changelog）
- blast-radius：brain.py 新增一個 import（anima_changelog），扇出 +1
- 安全等級：🟢 綠區（純新增，不改現有讀寫邏輯）

---

## 迭代 2 詳細規格：PulseDB Anima History API

### 目的
八元素變化歷史已經在 PulseDB `log_anima_change()` 記了——沒人讀。暴露查詢。

### 改動檔案
`src/museon/pulse/pulse_db.py` — 新增 1 個方法（~40 行）

### 設計
```python
def get_anima_history(
    self,
    element: Optional[str] = None,
    days: int = 30,
    granularity: str = "daily",  # daily / weekly / raw
) -> List[Dict]:
    """查詢八元素變化歷史。

    Returns:
        [{"date": "2026-03-20", "element": "kun", "total_delta": 5, "reasons": [...]}]
    """
```

### Pre-Flight
- 安全等級：🟢 綠區（純新增查詢方法，不碰寫入邏輯）

---

## 迭代 3-8 規格（待迭代 1-2 完成後展開）
