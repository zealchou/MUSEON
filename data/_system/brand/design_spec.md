# MUSEON 設計規範 v1.0

> 所有視覺產出（HTML 報告、儀表板、卡片、對外文件）必須遵循此規範。

---

## 設計哲學

**核心命題：溫暖的精密感**

MUSEON 不是冷酷的科技工具，也不是輕浮的 SaaS dashboard。它是**壁爐旁的精密儀器**——溫暖到你願意靠近，精密到你信任它的判斷。

參考來源：Apple HIG（清晰/留白/層次）、Stripe（B2B 資訊密度）、Notion（暖色中性）、Linear（深色 premium）、Figma（組件系統化）

---

## 色彩系統

### 品牌主色
```
Ember        #C4502A   主 CTA、強調文字、品牌識別
Ember Light  #E0714D   Hover 狀態、漸層高光
Ember Dark   #9A3A1C   深色背景強調、按鈕按下態
```

### 輔助色
```
Teal         #2A7A6E   信任感、成功狀態、連結色
Gold         #B8923A   智慧/洞見標記、Premium 標籤
```

### 中性色
```
Ink          #12121A   主要文字
Slate        #5A5A6E   次要文字、說明文字
Mist         #9898A8   禁用狀態、placeholder
Border       #E2E0DA   分隔線、輸入框邊框
Parchment    #F7F5F0   頁面背景（帶暖調，不純白）
Snow         #FDFCFA   卡片背景
```

### 深色模式
```
Deep Ink     #0E0E16   頁面背景
Surface      #16161F   卡片/面板
Raised       #1E1E2A   懸浮元素
Border Dark  #2A2A38   邊框
```

### 語義色
```
Success      #2D8A6E
Warning      #C9943A
Error        #C4402A
Info         #2A6A8A
```

### 禁止色
- 純 `#0000FF` 科技藍
- 紫色漸層（`#7c6aff` 系列）
- 螢光綠
- 純黑純白背景

---

## 字型系統

### 三層架構

**Display — Cormorant Garamond**（品牌大標題、英雄區塊）
```
H1 Display   56px / weight 600 / italic optional / line-height 1.15
H2 Display   40px / weight 600 / line-height 1.2
H3 Title     28px / weight 600 / line-height 1.3
```

**Body — Outfit（英文）+ Noto Sans TC（中文）**（正文、說明、UI）
```
Body Large   18px / weight 400 / line-height 1.8
Body         16px / weight 400 / line-height 1.75
Body Small   14px / weight 400 / line-height 1.7
Caption      12px / weight 500 / line-height 1.6
```

**Mono — IBM Plex Mono**（系統標籤、版本號、代碼）
```
Code Block   14px / weight 400
Inline Code  13px / weight 500 / 背景 #F0EDE8
Tag / Badge  11px / weight 600 / letter-spacing 0.08em / uppercase
```

### 排版原則
- 每頁最多使用 3 個字重
- 長文閱讀最大寬度：65ch（約 650px）
- 標題下方留 0.75em，段落間 1.25em

---

## 間距系統（8px 基準）

```
2px   細節對齊
4px   緊密元素內部
8px   按鈕 padding、tag 間距
16px  組件內部間距
24px  卡片 padding
32px  區塊間距
48px  Section 分隔
64px  頁面大節間距
96px  Hero 區塊垂直留白
```

---

## 組件規範

### 按鈕
```
Primary：背景 #C4502A / 文字 #FFF / padding 12px 24px / 圓角 6px / 15px weight 600
Secondary：透明背景 / 邊框 1.5px #E2E0DA / 文字 #12121A
Ghost：無背景邊框 / 文字 Ember / Hover 背景 rgba(196,80,42,0.08)
```

### 卡片
```
背景：#FDFCFA
邊框：1px solid #E2E0DA
圓角：10px
Padding：24px
Shadow：0 1px 3px rgba(18,18,26,0.06), 0 4px 12px rgba(18,18,26,0.04)
```

### 標籤 / Badge
```
背景：rgba(196,80,42,0.1)
文字：Ember Dark #9A3A1C
圓角：100px / Padding 3px 10px
字型：IBM Plex Mono 11px / 600 / uppercase / letter-spacing 0.08em
```

### 輸入框
```
高度：44px / 邊框 1.5px solid #E2E0DA / 圓角 6px
Focus：border-color #C4502A / outline 3px rgba(196,80,42,0.2)
```

---

## 動效規範

```
頁面載入淡入     opacity 0→1 + translateY(12px→0) / 400ms / ease-out
卡片 Hover      translateY(-2px) + shadow 加深 / 200ms / ease
按鈕互動        120ms / ease
Modal 進入      opacity + scale(0.96→1) / 220ms / ease-out
```

禁止：bounce 動畫、旋轉裝飾、超過 500ms 過場效果。

---

## 版面系統

```
最大寬度：1200px（儀表板）/ 820px（長文/報告）
欄數：12 欄 / 欄距 24px
邊距：40px（≥1024px）/ 24px（≥768px）/ 16px（<768px）
```

### 響應式斷點
```
Mobile    <640px
Tablet    640–1024px
Desktop   ≥1024px
Wide      ≥1440px（版面居中不再擴展）
```

---

## 圖像方向

**採用**：暖色調光影（琥珀/陶土/深靛）、抽象神經脈絡晶格、帶噪點深色漸層、細線條架構圖

**禁止**：科技藍紫漸層、機器人3D渲染、商務握手照、無意義儀表板截圖拼貼

---

## 生成視覺產出前必做清單

- [ ] 背景用 Parchment `#F7F5F0`，不用純白
- [ ] 主標題用 Cormorant Garamond（H1/H2），H3 以下用 Outfit
- [ ] 強調色用 Ember `#C4502A`，不用藍紫
- [ ] 最大寬度設定正確（820 or 1200px）
- [ ] 動效不超過 400ms
- [ ] 深色區塊用 Deep Ink `#0E0E16`，不用純黑
- [ ] Badge/Tag 用全圓角 + Mono 字型
- [ ] Google Fonts 引入：Cormorant Garamond + Outfit + IBM Plex Mono + Noto Sans TC
