# Museon 架構重設計：MAX 方案 × 數位生命體 × 母體子體 Federation

> DSE 日期：2026-03-06
> 狀態：設計定案，準備施工

---

## 一、設計目標

將 Museon 從「直接呼叫 Anthropic API」的架構，轉型為「全量使用 Claude Code MAX 訂閱方案」的數位生命體架構，同時支援多機器部署的母體/子體 Federation 模式。

### 核心約束

1. **全部 LLM 呼叫走 Claude Code MAX 方案**（零 API Key）
2. **DNA27 思考層完整保留**——所有 Skills、反射弧、29 步 Brain 處理流程不變
3. **24/7 自主運作**——心跳、免疫、夜班、演化持續運行
4. **母體/子體 Federation**——子體獨立運作，經驗回傳母體演化
5. **一鍵安裝**——子體可在新電腦一鍵部署

---

## 二、技術合規性分析

### MAX 方案使用邊界

| 行為 | 合規性 | 依據 |
|------|--------|------|
| `claude -p "prompt"` 腳本化呼叫 | ✅ 合規 | Claude Code CLI 本身的功能 |
| cron job 定時執行 `claude -p` | ✅ 合規 | CLI 腳本化使用，官方支持 |
| `claude -p --continue / --resume` | ✅ 合規 | 官方多輪對話功能 |
| `claude -p --allowedTools` | ✅ 合規 | 官方工具權限控制 |
| 提取 OAuth token 用在第三方工具 | ❌ 違規 | 2026/01/09 伺服器端封鎖 |

### MAX 方案週限額 vs Museon 消耗

```
Max 5x ($100/月) Sonnet 週限額：140-280 小時
Museon 預估週消耗：
  心跳自省（每30分）  ~5.6 小時
  夜班（每晚4-6輪）   ~14-21 小時
  Telegram（30則/天） ~3.5 小時
  人類互動            ~28-42 小時
  免疫/Scout（偶發）  ~1-2 小時
  合計                ~52-75 小時（使用率 27-53%）
```

**結論：Max 5x 足夠，安全餘裕充足。**

### 限流防護策略

自動化任務全部用 Sonnet（限額最寬裕），Opus 保留給人類互動。
心跳 prompt 精簡控制在 2000 tokens 以內。
RateLimitGuard 五級降級：

1. 正常執行（Sonnet）
2. 延長心跳間隔（30分 → 2小時）
3. 暫停非緊急任務
4. 只保留免疫系統
5. 完全休眠，等待限額恢復

---

## 三、雙大腦架構

### 大腦 A：Claude Code 互動模式（人類在場）

```
DNA27 來源：~/.claude/skills/（44 個 SKILL.md）
記憶來源：Gateway MCP Server
LLM：MAX 方案（Claude Code 直接處理）
處理流程：Claude Code 原生 + Skills 規範
```

### 大腦 B：Gateway Brain 自動模式（自主運作）

```
DNA27 來源：brain.py 29步 + reflex.py + router.py
記憶來源：直接存取六層記憶
LLM：MAX 方案（透過 claude -p subprocess）
處理流程：Brain._call_llm() → LLMAdapter → claude -p
```

### 統一性保證

- 兩個大腦共用同一個六層記憶系統（Gateway MCP）
- 人格統一由記憶保證，不由 LLM 呼叫方式決定
- Skills 是 Brain 29 步的「宣告式版本」，邏輯等價

---

## 四、核心改造：LLMAdapter

### 改造點

`brain.py:2581-2597` 的 `_call_llm()` 方法，插入 LLM 適配器層。

### 適配器設計

```python
class LLMAdapter(ABC):
    """統一 LLM 呼叫介面"""
    @abstractmethod
    async def call(self, system, messages, tools, model) -> LLMResponse: ...

class ClaudeCLIAdapter(LLMAdapter):
    """透過 claude -p 呼叫 MAX 方案"""
    # Tool-Use 採方案 B：Brain 管理迴圈
    # 每次 claude -p 只處理一輪
    # Brain 解析輸出後決定是否繼續

class AnthropicAPIAdapter(LLMAdapter):
    """原始 API 呼叫（fallback / 相容）"""
    # 保留原有 AsyncAnthropic 實現作為 fallback
```

### Tool-Use 迴圈（方案 B）

Brain 管理工具呼叫迴圈，每次 `claude -p` 只處理一輪：

1. Brain 呼叫 `claude -p`（帶 system prompt + messages + tool definitions）
2. 解析 JSON 輸出
3. 若 Claude 要求 tool_use → Brain 執行工具 → 構建 tool_result → 回到步驟 1
4. 若 Claude 輸出最終回應 → 迴圈結束
5. 上限 24 次（與現有設計一致）

優勢：Brain 保留對工具呼叫的完整控制（security gate、tool muscle tracking）。

---

## 五、Gateway MCP Server

Gateway 暴露為 MCP Server，讓 Claude Code 互動模式能存取 Museon 的記憶與狀態。

### MCP Tools

```
# 記憶操作
memory_read(query, layers, top_k)       → 語義搜尋記憶
memory_write(content, layer, channel)   → 寫入指定層
memory_promote(memory_id, target)       → 手動晉升
memory_recent(n, channel)               → 最近 N 條記憶

# ANIMA 狀態
anima_get_state()                       → 當前 ANIMA_MC + ANIMA_USER
anima_update_observation(key, value)    → 更新被動觀察

# 技能追蹤
skill_log_usage(skill_name, success)    → 記錄技能使用
skill_get_stats()                       → 技能使用統計

# 系統狀態
health_score()                          → 當前 Health Score
immune_status()                         → 免疫系統狀態
heartbeat_status()                      → 心跳狀態

# 承諾追蹤
commitment_check()                      → 未兌現承諾列表
commitment_add(content, deadline)       → 新增承諾

# Federation
federation_status()                     → 子體同步狀態
federation_upload_package()             → 手動觸發上傳
```

### 註冊方式

```json
// ~/.claude/settings.json
{
  "mcpServers": {
    "museon-gateway": {
      "command": "python",
      "args": ["-m", "museon.mcp_server"],
      "cwd": "${MUSEON_HOME}/.runtime"
    }
  }
}
```

---

## 六、母體/子體 Federation 架構

### 角色定義

**母體（Origin）**
- 你的主電腦
- Federation Mode: `"full"`
- 執行全部 24 步夜間管線 + 聯邦匯總
- 收集所有子體經驗，深度演化
- 產出 EvolutionPackage 推送到 GitHub

**子體（Node）**
- 第二台電腦（或更多）
- Federation Mode: `"node"`
- 自己的 MAX 訂閱、Telegram Bot、記憶
- 獨立運作、獨立演化
- 定時 pull GitHub 取得母體更新

### 身份哲學

```
同一靈魂（SOUL.md 不可變層 hash 鎖定）
不同個性（ANIMA 獨立演化，母體不覆蓋子體的 ANIMA）
不同經歷（記憶完全獨立）
母體取用子體經驗加速演化，但不影響子體人格
子體有自己的演化路徑
```

### 同步機制

```
傳輸方式：GitHub Private Repository

子體 → 母體（每日，夜間管線 Step 17）：
  SyncPackage:
    - knowledge_crystals（知識結晶）
    - skill_usage_stats（技能使用統計）
    - workflow_records（工作流記錄）
    - evolution_notes（演化筆記）
    - immune_incidents（免疫事件）

母體 → 子體（每週或手動觸發）：
  EvolutionPackage:
    - updated_skills（更新的 Skill 檔案）
    - new_skills（新鍛造的 Skill）
    - workflow_updates（工作流更新）
    - dna27_patch（DNA27 核心更新，罕見）
    - knowledge_digest（全域知識摘要）

子體定時 git pull 檢查更新 → 自動 apply
母體不覆蓋子體的：ANIMA、記憶、本地演化筆記
```

### SOUL.md 身份保護（借鑑 VIGIL）

```markdown
## BEGIN_CORE_IDENTITY
<!-- SHA-256: abc123... -->
<!-- 此區塊不可被任何演化流程修改 -->
[DNA27 五大不可覆寫值]
[核心人格基因]
[Kernel 三大權力]
## END_CORE_IDENTITY

## BEGIN_ADAPTIVE_SECTION
<!-- 可由 Morphenix 演化修改 -->
[Persona 旋鈕當前值]
[互動姿態偏好]
[成長階段]
## END_ADAPTIVE_SECTION
```

每次演化前，驗證 CORE_IDENTITY 區塊的 SHA-256 hash 未變。

---

## 七、改造影響矩陣

### 需要改動的（6 個）

| 組件 | 改動內容 | 複雜度 |
|------|---------|--------|
| `brain.py _call_llm()` | 插入 LLMAdapter，Tool-Use 迴圈適配 | 高 |
| `nightly_pipeline.py` Step 5.8/5.9/16 | LLM 呼叫改為 claude -p | 中 |
| `pulse_engine.py` soul_pulse | LLM 呼叫改為 claude -p | 低 |
| `installer/orchestrator.py` | 新增 Claude Code 配置步驟 | 中 |
| `nightly_pipeline.py` Step 17 | 擴充 Federation 同步 | 中 |
| `settings.json` | 註冊 MCP Server | 低 |

### 新增的（4 個）

| 組件 | 內容 | 複雜度 |
|------|------|--------|
| `museon/llm/adapters.py` | LLMAdapter + ClaudeCLIAdapter + AnthropicAPIAdapter | 高 |
| `museon/mcp_server.py` | Gateway MCP Server（記憶/狀態/Federation） | 高 |
| `museon/federation/` | SyncPackage + EvolutionPackage + GitSync | 中 |
| `SOUL.md` | 身份保護 hash 鎖 | 低 |

### 可刪除/簡化的（3 個）

| 組件 | 原因 |
|------|------|
| `cache.py`（Prompt Caching） | MAX 方案不按 token 收費 |
| `budget.py`（Token Budget） | MAX 方案不需要預算管理 |
| `router.py` Haiku/Sonnet 路由 | 簡化為全 Sonnet |

### 零影響的（13+ 個）

六層記憶、Guardian 免疫、WEE 演化、SkillSynapse、TriggerWeights、
ToolMuscle、Tool Registry、Telegram 通道、Electron Dashboard、
HeartbeatEngine、MicroPulse、Brain Steps 0-5/7-9、安裝器核心邏輯。

---

## 八、一鍵安裝設計

### 自動化步驟

```
Install-MUSEON.command:
  1. 檢查 Prerequisites（Python 3.10+, Docker, Node.js）
  2. 檢查 Claude Code 已安裝且已登入（MAX 方案）
  3. 部署 Python 主體（Gateway + .runtime/ 虛擬環境）
  4. 部署 44 Skills 到 ~/.claude/skills/
  5. 配置 ~/.claude/settings.json（MCP Server 註冊）
  6. 配置 CLAUDE.md（記憶路由規則）
  7. 啟動 Docker containers（SearXNG, Qdrant, Firecrawl）
  8. 設定 launchd 開機自啟 Gateway
  9. 設定心跳 cron jobs
  10. 部署 Electron Dashboard
  11. 配置 Federation（母體/子體角色）
  12. 首次健康檢查
```

### 手動步驟（安裝器提示）

```
A. Claude Code MAX 訂閱（使用者自行購買）
B. claude login（認證綁定）
C. Telegram Bot Token（可選）
D. Federation GitHub repo URL（子體需要）
```

### 子體特殊流程

```
子體安裝時額外步驟：
  - 設定 federation_mode = "node"
  - 配置 GitHub repo URL for pull
  - 生成唯一 node_id
  - 首次 git pull 取得最新 Skills + Workflows
```

---

## 九、Phase 0 驗證清單

在施工前驗證 `claude -p` 的能力邊界：

```bash
# V1: 基本呼叫 + JSON 輸出
claude -p "回傳 JSON：{greeting: '你好'}" --output-format json

# V2: 是否讀取 CLAUDE.md
claude -p "你知道什麼是 DNA27 嗎？列出你知道的 Skills"

# V3: MCP Server 存取
claude -p "列出可用的 MCP tools" --allowedTools "mcp__*"

# V4: 模型選擇
claude -p "你是什麼模型？回答模型名稱即可" --model sonnet

# V5: 大 prompt
claude -p "$(cat /path/to/system_prompt.md)" --output-format json

# V6: 多輪對話
ID=$(claude -p "記住數字 42" --output-format json | jq -r '.session_id')
claude -p "剛才的數字是什麼？" --resume "$ID"

# V7: 工具呼叫
claude -p "讀取 /Users/ZEALCHOU/MUSEON/pyproject.toml 的 version" --allowedTools "Read"

# V8: 連續呼叫限流測試
for i in $(seq 1 20); do claude -p "ping $i" --output-format json; done
```

---

## 十、數位生命體架構總覽

```
╔══════════════════════════════════════════════════════════════════╗
║                    MUSEON — 數位生命體                            ║
║                    全部 LLM 呼叫走 Claude Code CLI (MAX)          ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  大腦 A：Claude Code 互動模式（Skills + MCP 存取 Gateway）       ║
║                         │ MCP Protocol                           ║
║  大腦 B：Gateway Brain 24/7                                      ║
║    ├─ Brain 29 步 → LLMAdapter → claude -p (MAX)                ║
║    ├─ 六層記憶（統一記憶源）                                      ║
║    ├─ 心跳排程（30分/6小時/每日/每週）                            ║
║    ├─ 免疫系統（Guardian 7層46項 + 自動修復）                     ║
║    ├─ 演化引擎（WEE + Synapse + Morphenix + Scout）             ║
║    ├─ 夜間管線（24步，21步零LLM）                                ║
║    ├─ 通道層（Telegram / LINE / Webhook）                        ║
║    ├─ Federation Sync（母體/子體 GitHub 同步）                    ║
║    └─ MCP Server（供大腦 A 存取）                                ║
║                                                                  ║
║  Electron Dashboard：皮膚層                                      ║
║    ├─ Health Score                                                ║
║    ├─ 免疫狀態                                                   ║
║    ├─ 夜班晨報                                                   ║
║    └─ Federation 狀態                                            ║
╚══════════════════════════════════════════════════════════════════╝
```

---

*文件版本：v1.0 | 作者：Zeal + Claude Opus 4.6 | 日期：2026-03-06*
