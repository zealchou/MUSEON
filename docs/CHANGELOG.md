# MUSEON CHANGELOG

> 每次迭代/修復/功能新增的變更紀錄。新的在最上面。
> 迭代前必讀最近 5 筆，避免重蹈覆轍或重複修改。

---

## [v9.3] 2026-03-24 — GitHub Pages DSE 根因修復 + 可執行工作流架構

### DSE 根因分析（4 個系統性根因）
| # | 根因 | 嚴重度 | 修復 |
|---|------|--------|------|
| RC-1 | 意圖與實作斷裂（Skill 只有描述沒有可執行代碼） | 💀致命 | 建立 `scripts/workflows/` 架構 |
| RC-2 | 指令來源衝突（3 份互相矛盾的文件） | 🔴嚴重 | 刪除矛盾文件，統一為單一腳本 |
| RC-3 | gh-pages 分支狀態損壞（src/tests 被推進） | 🔴嚴重 | 切換為 GitHub Actions 部署 |
| RC-4 | Claude git 分支切換脆弱（5 個失敗點） | 🟠中高 | 不再切換分支，只推 main |

### 修改清單
| # | 修改 | 檔案 | 行為變化 |
|---|------|------|---------|
| 1 | GitHub Actions 自動部署 | `.github/workflows/deploy-pages.yml`（新建） | 推送 `docs/_reports/` 到 main 自動部署到 Pages |
| 2 | 發布腳本 v3.0 | `scripts/publish-report.sh` | 不切換分支、不 stash、只推 main |
| 3 | 可執行工作流架構 | `scripts/workflows/`（新建目錄） | Skill/Workflow 的外部操作有可執行腳本 |
| 4 | 刪除矛盾文件 | `docs/REPORT_PUBLISHING_CHECKLIST.md` | 已刪除 |
| 5 | 刪除矛盾文件 | `docs/PUBLISH-SYSTEM-SETUP.md` | 已刪除 |
| 6 | GitHub Pages 來源切換 | GitHub repo 設定 | `legacy/gh-pages` → `workflow/Actions` |
| 7 | 清理殘留 stash | git stash | 4 個殘留 stash 清除 |

**影響範圍**：CI/CD 層、文件層。不影響 Brain/Gateway 運行時。

---

## [v9.2] 2026-03-24 — 軍師認知升級 + 跨群組洩漏防禦 + CLI OAuth 統一

### 軍師認知升級（5 項修改）

| # | 修改 | 檔案（.runtime/src/museon/agent/） | 行為變化 |
|---|------|----------------------------------|---------|
| 1 | 群組迴圈路由升級 | `reflex_router.py` | select_loop/route 新增 `is_group`；群組 A<0.8 → EXPLORATION；C+D/E → SLOW |
| 2 | 認知 DNA 化 | `brain_prompt_builder.py` | system prompt 注入「軍師認知框架」（~150 tokens）：多路徑+終局反推+SMART |
| 3 | 群組禁止確認詞 | `brain_prompt_builder.py` | 群組模式禁止以「收到」「了解」「好的」開頭 |
| 4 | SMART 回答門檻 | `brain.py` | 新增 `_check_smart_completeness()`；計畫類缺 T+M → 強制追問 |
| 5 | Roundtable ≥3 Skill | `brain_p3_fusion.py` | 3+ 任意 Skill 命中 → 自動觸發多角度融合（roundtable-auto） |

**DSE 根據**：群組自評 3.2/10，七道防線只啟動兩道半。外部 DSE 驗證 DeepMind Talker-Reasoner 架構。
**影響範圍**：純內部邏輯，向後相容（is_group 預設 False）。
**注意**：修改在 `.runtime/src/` 中（gitignored），`src/` 合併版未同步。

### 跨群組訊息洩漏防禦（commit 89dbf5d9）

| # | 修改 | 檔案 | 行為變化 |
|---|------|------|---------|
| 1 | ResponseGuard 閘門 | `src/museon/governance/response_guard.py`（新建） | 所有回覆發送前 chat_id 二次驗證 |
| 2 | Escalation 精確匹配 | `src/museon/governance/multi_tenant.py` | 新增 `resolve_by_id()`；DM 通知加 `#eid` |
| 3 | Brain ctx 清空 | `src/museon/agent/brain.py` | process() finally 清空 self._ctx 和 6 個 alias |
| 4 | Session lock 守衛 | `src/museon/gateway/server.py` | 改用 `wait_and_acquire(30s)`，超時回覆忙碌 |

**事件**：Amber 群組訊息洩漏到士維群組（第二次發生）。
**DSE 根因**：Escalation 全域 FIFO + Brain instance 變數殘留 + Session lock 無守衛。

### CLI OAuth 統一通道（commit 8b299572）

| # | 修改 | 檔案 | 行為變化 |
|---|------|------|---------|
| 1 | 移除 ANTHROPIC_API_KEY | `.env` + `.runtime/.env` | 註解化，不再使用 API 通道 |
| 2 | 純 CLI adapter | `src/museon/llm/adapters.py` | 移除 FallbackAdapter/--bare；注入 USER env var |
| 3 | 健康檢查更新 | preflight/vital_signs/health_check/daemon | 不再檢查 API key |

**事件**：API 餘額耗盡 + `--bare` 禁止 OAuth + daemon 缺 USER = 三重故障。
**根因**：昨晚的 hack（OAuth token 塞 ANTHROPIC_API_KEY）不穩定。

### E2E timeout（commit 2dcdaaf3）

- `vital_signs.py`：E2E flow timeout 60s → 180s（移除 --bare 後 CLI 啟動較慢）

---

## [v9.1] 2026-03-23 — Brain 思考品質 5 項修復

**commit**: 1128c984

| # | 問題 | 檔案 | 修復 |
|---|------|------|------|
| 1 | SLOW_LOOP 不觸發 | reflex_router.py | 移除 RC-D1 從 EXPLORATION 攔截 |
| 2 | 強反射清空 matched_skills | brain.py | action_verbs 加 8 個動作詞 |
| 3 | Skill 過度壓制 | rc_affinity_loader.py | 只在 RC ≥ 0.5 時壓制 |
| 4 | P3 confidence 恆定 | brain_p3_fusion.py | EXPLORATION + matched ≥ 2 → 0.70 |
| 5 | deep-think P0 零觸發 | brain.py | P0 戰略分類 → 強制注入策略 Skill |

**DSE 根因**：一個架構缺陷的五種症狀——DNA27 路由與 Deliberate 間缺少信號強度 vs 行為意圖的博弈層。

---

## 讀法指南

- **迭代前**：讀最近 3-5 筆，了解什麼剛改過、什麼還沒穩定
- **Debug 時**：搜尋相關模組名稱，看最近是否有人改過
- **新功能前**：搜尋影響範圍，避免改到剛修好的地方
- **`.runtime/` vs `src/`**：`.runtime/src/` 是 Gateway 實際執行的程式碼（gitignored）；`src/` 是 git 追蹤的合併版。兩者可能不同步。
