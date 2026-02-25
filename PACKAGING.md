# MuseClaw 打包與安裝指南

## 概述

MuseClaw 使用 **ad-hoc 簽名**，不需要 Apple Developer 帳號（$99/年）。

Ad-hoc 簽名滿足 Apple Silicon 的 code signing 要求，但需要在安裝時移除 quarantine 屬性。

## 打包流程

### 1. 打包 .dmg

在專案根目錄執行：

```bash
./scripts/build-dmg.sh
```

這會：
- 在 `electron/` 目錄執行 `electron-builder`
- 使用 ad-hoc 簽名（`identity: "-"`）
- 生成 `electron/dist/MuseClaw-{version}.dmg`

### 2. 驗證打包結果

```bash
# 檢查 .dmg 檔案
ls -lh electron/dist/*.dmg

# 掛載 .dmg 測試
open electron/dist/MuseClaw-*.dmg
```

### 3. 簽名狀態

Ad-hoc 簽名的應用會顯示：

```bash
codesign -dv /Applications/MuseClaw.app

# 輸出範例:
# Executable=/Applications/MuseClaw.app/Contents/MacOS/MuseClaw
# Identifier=com.museclaw.dashboard
# Format=app bundle with Mach-O thin (arm64)
# CodeDirectory v=20500 size=... flags=0x20002(adhoc,linker-signed) hashes=...
# Signature=adhoc  ← 這是 ad-hoc 簽名
```

## 安裝流程

### 方式一：自動安裝腳本（推薦）

```bash
./scripts/install-museclaw.sh [path/to/MuseClaw.app]
```

腳本會：
1. 複製 `.app` 到 `/Applications`
2. 移除 quarantine 屬性
3. 設定正確權限
4. 詢問是否立即啟動

### 方式二：手動安裝

1. 掛載 .dmg：
   ```bash
   open electron/dist/MuseClaw-*.dmg
   ```

2. 拖曳 `MuseClaw.app` 到 `/Applications`

3. 移除 quarantine 屬性：
   ```bash
   sudo xattr -r -d com.apple.quarantine /Applications/MuseClaw.app
   ```

4. 啟動：
   ```bash
   open /Applications/MuseClaw.app
   ```

## 首次啟動注意事項

### macOS Gatekeeper 警告

首次啟動時，macOS 可能顯示：

> "MuseClaw.app" 無法打開，因為它來自未識別的開發者。

**解決方法：**

1. 前往：**系統偏好設定 > 隱私權與安全性**
2. 在「安全性」區段，點擊 **「強制打開」**
3. 再次嘗試啟動 MuseClaw

這是因為我們使用 ad-hoc 簽名，而非經 Apple 公證的應用程式。

### macOS 15.1+ 的額外步驟

macOS Sequoia (15.1+) 的 Gatekeeper 更嚴格：

1. 如果「強制打開」不出現，使用：
   ```bash
   sudo spctl --master-disable  # 暫時關閉 Gatekeeper
   open /Applications/MuseClaw.app
   sudo spctl --master-enable   # 重新啟用 Gatekeeper
   ```

2. 或使用：
   ```bash
   sudo xattr -cr /Applications/MuseClaw.app
   ```

## 部署到客戶端

Zeal 到客戶現場安裝時的流程：

### 準備工作

1. 在 USB 隨身碟準備：
   - `MuseClaw-{version}.dmg`
   - `scripts/install-museclaw.sh`

2. 或使用雲端：
   - 上傳到 Google Drive / Dropbox
   - 提供下載連結給客戶

### 安裝步驟

1. 在客戶的 Mac 上：
   ```bash
   # 下載或從 USB 複製 .dmg 和腳本
   cd ~/Downloads

   # 掛載 .dmg
   open MuseClaw-*.dmg

   # 拖曳到 Applications（或讓腳本自動完成）

   # 執行安裝腳本
   chmod +x install-museclaw.sh
   ./install-museclaw.sh
   ```

2. 處理 Gatekeeper 警告（如上所述）

3. 啟動 MuseClaw 並執行命名儀式

## electron-builder 設定

`electron/package.json` 的關鍵設定：

```json
{
  "build": {
    "mac": {
      "identity": "-",              // Ad-hoc 簽名
      "signIgnore": ".*",           // 忽略簽名驗證
      "hardenedRuntime": false,     // 關閉 hardened runtime
      "gatekeeperAssess": false,    // 跳過 Gatekeeper 評估
      "entitlements": null,         // 不使用 entitlements
      "entitlementsInherit": null
    },
    "dmg": {
      "sign": false                 // .dmg 不簽名
    }
  }
}
```

## 常見問題

### Q1: 為什麼不使用 Apple Developer 簽名？

A:
- Ad-hoc 簽名免費且滿足 Apple Silicon 要求
- 因為 Zeal 親自到現場安裝，可以手動處理 quarantine
- 省下 $99/年 的 Apple Developer 費用

### Q2: Ad-hoc 簽名安全嗎？

A:
- Ad-hoc 簽名確保代碼完整性（防止竄改）
- 但不提供開發者身份驗證
- 適合內部部署或現場安裝的場景

### Q3: 可以遠端安裝嗎？

A:
- 可以，但需要客戶執行 `install-museclaw.sh` 腳本
- 或引導客戶手動移除 quarantine 屬性
- 建議提供詳細的圖文教學

### Q4: 未來要改用正式簽名嗎？

A:
- 如果規模擴大，需要遠端部署時，建議改用正式簽名
- 需要：
  - Apple Developer 帳號 ($99/年)
  - Developer ID Certificate
  - 公證 (Notarization)
- electron-builder 支援完整的簽名流程

## 開發流程

### 開發中測試

```bash
cd electron
npm run dev  # 開發模式啟動
```

### 打包測試

```bash
# 打包但不創建 .dmg（更快）
cd electron
npm run pack

# 測試打包的 .app
open dist/mac/MuseClaw.app
```

### 完整打包

```bash
./scripts/build-dmg.sh
```

## 自動化建議

### 未來可加入 GitHub Actions

```yaml
# .github/workflows/build.yml
name: Build MuseClaw

on:
  push:
    tags:
      - 'v*'

jobs:
  build:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
      - name: Build DMG
        run: ./scripts/build-dmg.sh
      - name: Upload artifacts
        uses: actions/upload-artifact@v3
        with:
          name: MuseClaw-dmg
          path: electron/dist/*.dmg
```

## 總結

MuseClaw 的打包策略：
- ✅ Ad-hoc 簽名（免 Apple Developer）
- ✅ 現場安裝（Zeal 親自處理）
- ✅ 一鍵安裝腳本（`install-museclaw.sh`）
- ✅ macOS 15.1+ 相容

未來擴展：
- 正式簽名 + 公證（遠端部署需要）
- 自動更新機制（electron-updater）
- CI/CD 自動打包
