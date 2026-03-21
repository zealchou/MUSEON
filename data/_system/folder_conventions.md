# MUSEON 資料夾規範（Folder Convention）

> 此文件是 MUSEON 系統自身的資料夾結構規範。
> Brain、Nightly Pipeline、info-architect Skill 在規劃檔案結構時應參照此規範。
> 最後更新：2026-03-06

---

## 根目錄配置

```
~/MUSEON/        ← 唯一正式專案根目錄（開發 + 運行）
~/.museon/       ← Gateway daemon 運行狀態（immunity, locks, refractory）
~/MUSEON_archive/ ← 舊版資料封存（唯讀）
```

**規則**：不可在家目錄下建立其他 museon 相關資料夾。

---

## ~/MUSEON/ 內部結構

```
MUSEON/
├── src/museon/         ← Python 源碼（所有模組）
├── data/               ← 運行時資料
├── tests/              ← 測試（unit/, integration/, e2e/, fixtures/）
├── electron/           ← Dashboard 前端（Electron）
├── scripts/            ← 建置與部署腳本
├── features/           ← BDD 測試（.feature 檔）
├── docs/               ← 文件
├── bin/                ← CLI 工具腳本
├── dist/               ← 打包產物（安裝檔）
├── logs/               ← 執行日誌
├── .runtime/           ← 正式運行環境（src/ 的打包鏡像）
├── .venv/              ← 開發用 Python 虛擬環境
├── .env                ← 環境變數（不入 Git）
├── pyproject.toml      ← 專案配置
└── README.md
```

---

## 命名規範

| 規則 | 範例 |
|------|------|
| 全小寫 + 底線分隔 | `memory_v3/`, `pulse_engine.py` |
| 系統內部目錄加底線前綴 | `_system/`, `_tools/` |
| Python 模組遵循 PEP 8 | `rate_limit_guard.py` |
| 不混用中英文 | 避免「開發殘餘（即時可刪除）」這種命名 |

---

## data/ 子目錄職責

| 目錄 | 職責 | 備註 |
|------|------|------|
| `skills/` | 44 個 Skill 定義（.md） | 唯讀參考，Nightly 可更新 |
| `memory_v3/` | 六層記憶系統 | 唯一記憶版本 |
| `_system/` | 系統內部狀態 | budget, state, federation, mcp 等 |
| `_tools/` | 外部工具 | whisper.cpp 等大型二進位 |
| `anima/` | ANIMA 人格備份 | |
| `eval/` | 評估報告 | daily/, weekly/ |
| `guardian/` | 守護系統校準 | rc_calibration/ |
| `lattice/` | 知識晶格 | |
| `morphenix/` | 自我演化資料 | |
| `plans/` | 計畫引擎 | |
| `pulse/` | 心跳資料 | |
| `workspace/` | 工作區 | 各種子空間 |
| `vector/` | 向量索引 | |

**規則**：不隨意在 `data/` 下新增頂層子目錄。新功能的資料優先歸入現有目錄（如 `_system/` 或 `workspace/`）。

---

## 層級限制

- 資料夾最深 **3 層**（不含 `src/museon/` 模組層）
- 3 次點擊（操作）可達任何檔案
- 超過 3 層時重新檢視分類邏輯

---

## 不入 Git 的項目

以下項目由 `.gitignore` 控制，不應提交到版本庫：

- `__pycache__/`, `*.pyc`
- `.DS_Store`
- `htmlcov/`, `.coverage`, `.pytest_cache/`
- `.env`
- `.venv/`, `.runtime/.venv/`
- `logs/`
- `data/_tools/`（大型二進位）
- `*.bak`

---

## .runtime/ 同步規則

- 開發時修改 `src/`，**不直接修改** `.runtime/src/`
- 打包前執行：`rsync -av --delete --exclude='__pycache__' src/ .runtime/src/`
- `.runtime/` 是 Gateway daemon 載入程式碼的來源

---

## 相關 Skill

- **info-architect**：資訊架構與整理引擎，先定義美感再定義結構
- **aesthetic-sense**：美感審計，確保結構的視覺整齊和邏輯清晰
