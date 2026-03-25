# ScreenplayForge 快速開始指南

**工具名稱**：ScreenplayForge（劇本鍛造局）
**版本**：1.0
**上次更新**：2026-03-25

---

## 一句話描述

為劇本創意生成提供「結構化 Prompt + 自動驗收 + 製作清單」的 AI 工作流。

---

## 30 秒快速開始

### 1. 執行工作流

```bash
~/MUSEON/scripts/workflows/screenplay-gen.sh \
  --project "品牌微劇本 #咖啡日常" \
  --genre "廣告" \
  --duration "30秒" \
  --theme "一個媽媽的晨間寧靜" \
  --characters 2 \
  --tone "溫馨"
```

### 2. 取得輸入 JSON

腳本會在 `~/MUSEON/outputs/screenplay/[時間戳]/screenplay_input.json` 生成參數文件。

### 3. 在 Claude 中生成劇本

1. 複製 `screenplay_input.json` 的內容
2. 在 Claude 中貼入以下 Prompt：

```
你是資深劇本編劇。根據以下 JSON 需求生成劇本：

【需求】
[貼入 screenplay_input.json]

【任務】
1. 生成三幕劇結構的完整劇本（Fountain 格式）
2. 為每場景設計視覺敘事與道具
3. 生成情緒線表（含場景目的與預期觀眾情感）
4. 確保情緒線有 ≥2 處內在衝突
5. 生成製作清單（場景、道具、成本估算）

【輸出格式】
JSON 格式，包含以下欄位：
{
  "screenplay_markdown": "...",
  "emotional_arc_table": [...],
  "production_brief": {...},
  "qa_report": {...},
  "improvement_notes": [...]
}
```

### 4. 更新輸出文件

Claude 生成後，複製 JSON 並更新：
- `[project_name]_screenplay.md` — 劇本文本
- `[project_name]_production_brief.json` — 製作清單
- `[project_name]_qa_report.json` — 驗收報告

### 5. 驗收

檢查 `qa_report.json` 中 `status` 欄位：
- ✅ `PASS` → 劇本已驗收，可提交製片團隊
- ⚠️ `PENDING_REVIEW` → 按改進建議修改

---

## 完整使用說明

### 必填參數

| 參數 | 說明 | 範例 |
|------|------|------|
| `--project` | 專案名稱 | `"品牌微劇本 #咖啡日常"` |
| `--genre` | 劇本類型 | `短篇`, `廣告`, `微劇本`, `話劇` |
| `--duration` | 目標時長 | `30秒`, `1分鐘`, `3分鐘`, `5分鐘`, `10分鐘` |
| `--theme` | 核心主題 | `"一個媽媽的晨間寧靜"` |
| `--characters` | 角色數 | `2`, `3`, `5` |
| `--tone` | 情感基調 | `溫馨`, `懸疑`, `喜劇`, `激勵`, `感傷`, `驚悚` |

### 選填參數

| 參數 | 說明 | 預設值 |
|------|------|--------|
| `--audience` | 目標觀眾 | `"一般大眾"` |
| `--setting` | 佈景限制 | `"無限制"` |
| `--props` | 必須包含的道具 | `"[]"` |
| `--values` | 品牌價值觀 | `"[]"` |
| `--special` | 特殊要求 | `""` |
| `--budget` | 製作預算層級 | `"medium"` |

### 預算層級定義

| 層級 | 說明 | 道具成本 | 場景數 | 佈景複雜度 |
|------|------|---------|--------|-----------|
| **low** | 極簡製作 | < $50 | 3-5 | 現有場景 (家/辦公室) |
| **medium** | 標準製作 | $50-300 | 5-12 | 簡單搭建 |
| **high** | 專業製作 | > $300 | 8-15 | 複雜美術設計 |

---

## 工作流輸出

每次運行會在 `~/MUSEON/outputs/screenplay/[時間戳]/` 下生成：

```
.
├── screenplay_input.json                    # 輸入參數 (給 Claude)
├── [project_name]_screenplay.md             # 完整劇本文本
├── [project_name]_production_brief.json     # 製作清單 (場景、道具、成本)
├── [project_name]_emotional_arc.html        # 情緒線可視化圖表
├── [project_name]_qa_report.json            # 驗收報告
└── WORKFLOW_REPORT.md                       # 工作流總結報告
```

### 各檔案說明

| 檔案 | 格式 | 用途 | 使用者 |
|------|------|------|--------|
| screenplay_input.json | JSON | 提供給 Claude 的結構化輸入 | Claude |
| _screenplay.md | Markdown | 可讀的劇本文本（易於編輯） | 編劇、導演 |
| _production_brief.json | JSON | 製片人用的成本與資源估算 | 製片主任 |
| _emotional_arc.html | HTML | 互動式情緒線圖表 | 導演、製片人 |
| _qa_report.json | JSON | 自動驗收結果與改進建議 | 品質保證 |

---

## 驗收清單

劇本完成後，應檢查以下項目：

### 結構檢查
- [ ] 有明確的「第一幕 - 衝突引爆」(Setup + Inciting Incident)
- [ ] 有「中點轉折」(Midpoint) 改變劇情方向
- [ ] 有「高潮」(Climax) 在第三幕 85-95% 位置
- [ ] 有「解決方案」(Resolution) 不超過 3 場景

### 情感檢查
- [ ] 情緒曲線呈波浪狀（至少 3 個小高潮）
- [ ] 有 ≥2 處「內在衝突」(主角 vs 自己)
- [ ] 有「轉折發現」(主角發現自己錯了/遺漏了什麼)
- [ ] 結尾有「情感釋放」（滿足感或警醒感）

### 效率檢查
- [ ] 無「無故場景」(每場景都推動情節或暴露角色)
- [ ] 對白無冗長獨白 (單句最多 4 行)
- [ ] 無重複訊息 (同一情感不重複表達)

### 製作檢查
- [ ] 場景數與時長匹配（時長 min = 場景 count / 2）
- [ ] 道具清單成本在預算內
- [ ] 角色數可實際招募
- [ ] 佈景設計可執行

---

## 常見用法

### 場景 1：30 秒廣告短片

```bash
./screenplay-gen.sh \
  --project "咖啡品牌廣告" \
  --genre "廣告" \
  --duration "30秒" \
  --theme "晨間的一刻寧靜" \
  --characters 2 \
  --tone "溫馨" \
  --audience "25-45 歲女性" \
  --budget "low"
```

**預期**：4-5 場景、極簡佈景、明確情緒釋放、3-5 天製作。

### 場景 2：3 分鐘品牌故事

```bash
./screenplay-gen.sh \
  --project "品牌故事 #堅持" \
  --genre "短篇" \
  --duration "3分鐘" \
  --theme "創業者在失敗後的蛻變" \
  --characters 4 \
  --tone "激勵" \
  --audience "年輕創業者" \
  --budget "medium" \
  --values '["創新","堅持","人文"]'
```

**預期**：7-10 場景、多層衝突、強烈情感弧線、5-7 天製作。

### 場景 3：教育微劇本

```bash
./screenplay-gen.sh \
  --project "校園劇本 #勇氣" \
  --genre "短篇" \
  --duration "5分鐘" \
  --theme "少女在朋友壓力中堅持自我" \
  --characters 5 \
  --tone "激勵" \
  --audience "國中生" \
  --budget "low" \
  --setting "學校"
```

**預期**：8-12 場景、貼近校園現實、有教育意義、適合校園演出。

---

## 失敗排查

### Q: 腳本提示「Claude 不可用」

**A**: 工作流支援「手動模式」。將 `screenplay_input.json` 複製到 Claude，按上述 Prompt 生成，再手動更新輸出檔案。

### Q: 輸出檔案名有特殊字符（例如 `#`）

**A**: 這是正常的。Shell 會自動轉義，檔案系統支援。若編輯器打不開，用 Terminal 或 VS Code。

### Q: 驗收報告顯示 PENDING_REVIEW

**A**: 按 `improvement_suggestions` 列表修改劇本，重新提交驗收。

### Q: 想修改已生成的劇本

**A**: 直接編輯 `.md` 檔案，再用 Claude 驗證是否仍通過驗收清單。

---

## 下一步

### 短期
1. ✅ 完成羅臻的第一個劇本生成
2. ✅ 收集他的反饋（結構、情感、製作可行性）
3. 調整 Prompt 和驗收標準

### 中期
1. 錄製「ScreenplayForge 教學影片」（10 分鐘）
2. 建立「劇本案例庫」（3-5 個優秀範例）
3. 整合到 MUSEON 官網作為「Skill 展示」

### 長期
1. 加入「AI 分鏡參考」（自動生成視覺參考圖）
2. 支援「版本管理」（Git 追蹤每次修改）
3. 建立「客户反饋循環」優化生成品質

---

## 聯絡與支援

- **專案負責人**：MUSEON L2 思考者
- **文件位置**：`~/MUSEON/docs/screenplay-*.md`
- **工作流腳本**：`~/MUSEON/scripts/workflows/screenplay-gen.sh`
- **輸出目錄**：`~/MUSEON/outputs/screenplay/`

有任何問題，請參照 `screenplay-skill-spec.md` 的完整技術規格。

---

**Version**: 1.0
**Last Updated**: 2026-03-25
**Status**: Production Ready ✅
