# Decision Atlas — 創造者決策圖譜

> MUSEON 最重要的資產之一。記錄的不是 Zeal 說了什麼，是他怎麼想、怎麼選、為什麼。

## 資料結構

每個結晶一個 JSON 檔案，格式：
```json
{
  "id": "da-YYYYMMDD-NNN",
  "date": "2026-04-05",
  "source": "claude_code | museon_bot | manual",
  "category": "taste | priority | boundary | strategy | value",
  "absurdity_dimension": "self_awareness | direction | gap | accumulation | leverage | integration",
  "context": "當時的情境描述",
  "options": ["選項A", "選項B", ...],
  "chosen": "他選了什麼",
  "why": "他為什麼這樣選（推理過程）",
  "conditions_to_change": "什麼條件下他會改變這個決定",
  "confidence": 0.0-1.0,
  "tags": ["keyword1", "keyword2"]
}
```

## 覆蓋度矩陣

| 維度 \ 類型 | taste | priority | boundary | strategy | value |
|-------------|-------|----------|----------|----------|-------|
| self_awareness | | | | | |
| direction | | | | | |
| gap | | | | | |
| accumulation | | | | | |
| leverage | | | | | |
| integration | | | | | |

每格目標 ≥ 2 個結晶。覆蓋度 ≥ 80%（24/30 格有結晶）→ 通知 Zeal。

## 來源

- **claude_code**: 從 Claude Code session 中觀察萃取
- **museon_bot**: 從 MUSEON Bot 的 L4 觀察者萃取
- **manual**: Zeal 主動做的結晶對話
