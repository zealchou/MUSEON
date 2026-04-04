# 可執行工作流協議（Executable Workflow Protocol）

> **原則**：涉及外部操作的 Workflow 必須有 `scripts/workflows/<name>.sh`，執行腳本而非即興。

---

## Tier 0：可執行性檢查

1. □ 此 Workflow 涉及外部操作嗎？
2. □ `scripts/workflows/<name>.sh` 存在嗎？
3. □ 腳本有驗證步驟嗎？
4. □ 驗證失敗有 `exit 1` 嗎？
5. □ 腳本是 idempotent 的嗎？

---

## 鐵律：驗證通過前不可推播

1. 外部操作完成後，必須驗證結果
2. 驗證失敗 → 不發送連結、不通知使用者

---

## GitHub Pages 發佈規則

禁止即興操作——必須用：

```bash
bash scripts/publish-report.sh <file>
```

從輸出中提取 `VERIFIED_URL=` 行作為使用者連結。

- 禁止自己構造 URL
- 禁止自己做 git push 到 gh-pages
- 檔名不一致 = 404
