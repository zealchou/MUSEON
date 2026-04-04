# 施工後強制檢查協議（Post-Build Checklist）

> **任何新增功能/模組/Skill 完成後，必須依序完成。缺少此步驟是「漏膠水層」的根因。**

## 核心清單

1. □ 新模組/Skill 有沒有 Manifest？（`io` / `connects_to` / `memory` 欄位）
2. □ 跑 `scripts/validate_connections.py`：有沒有孤立輸出或缺失輸入？
3. □ 新 Skill 的輸出流向哪個記憶系統？（查 `docs/memory-router.md`）
4. □ 如果記憶路由表沒有涵蓋，新增一行到 `docs/memory-router.md`
5. □ 如果新增了 Skill，同步更新 `data/skills/native/plugin-registry/SKILL.md`
6. □ 如果新增了 Skill，同步 `~/.claude/skills/` 鏡像
7. □ **拓撲↔心智圖同步檢查**：改了節點/連線 → 跑 `scripts/sync_topology_to_3d.py --apply` 確保 HTML 與拓撲一致
8. □ **Hub 歸位檢查**：新 Skill 的 `hub` 欄位是否為 9 種合法值之一？歸位是否合理？（參照 `docs/skill-routing-governance.md`）
9. □ **Workflow stages 檢查**：若 `type: workflow`，是否有結構化 `stages` + `speed_paths`？（參照 `docs/skill-manifest-spec.md`）
10. □ **發送路徑零直送檢查**：`grep 'bot.send_message' src/` 確認只有 `_safe_send()` 內部那一處；新增的對外發送必須走 `adapter._safe_send()`
