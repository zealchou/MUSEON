---
name: onemuse-personal-report
description: >
  One Muse 個人盤能量解讀報告書生成模組。用於將解盤諮詢逐字稿轉換為專業 PDF 報告書。
  包含：八方位雷達圖繪製（內在紅線／外在藍線）、能量週期波動圖、八方位能量表格、
  四軸人格傾向、卡點定位與逆時針回推、行動方案、自我總結區塊。
  觸發時機：(1) 使用者輸入 /report 或 /個人盤報告 指令；
  (2) 使用者提供解盤逐字稿並要求生成報告書；
  (3) 使用者提供八方位能量數據並要求視覺化輸出。
  依賴：OM-Brand-Visual 品牌規範、OM-Report-Template-Spec-v2 報告結構。
---

# One Muse 個人盤報告書生成模組

## 使命

將解盤諮詢的豐富敘事轉化為專業、可追溯、溫暖的書面報告，讓個案能在諮詢後持續回顧與行動。

## 報告生成流程

```
1. 讀取逐字稿 / 盤面資料
2. 萃取八方位能量數據（inner/outer）
3. 計算統計指標（總和、落差、卡點、起點）
4. 生成雷達圖（內在紅線、外在藍線）
5. 套入 HTML 模板 + CSS（依 OM-Brand-Visual 規範）
6. 用 playwright 轉 PDF（A4, print_background=True）
7. 輸出 PDF 檔案
```

## 雷達圖規範（核心視覺）

### 圖表結構

雷達圖是諮詢表的核心視覺，呈現八方位能量的內外對比。

```
八方位順序（順時針，從上方 12 點鐘開始）：
  ☰ 天（目標）    — 12 點鐘位置
  ☴ 風（適應）    — 1:30 位置
  ☵ 水（關係）    — 3 點鐘位置
  ☶ 山（累積）    — 4:30 位置
  ☷ 地（成就）    — 6 點鐘位置
  ☳ 雷（察覺）    — 7:30 位置
  ☲ 火（點燃）    — 9 點鐘位置
  ☱ 澤（機會）    — 10:30 位置
```

### 雷達圖規格

| 屬性 | 值 |
|-----|-----|
| 刻度範圍 | -4 到 +4（0 不存在） |
| 同心圓 | 9 圈（-4, -3, -2, -1, 中心, +1, +2, +3, +4） |
| 中心點 | 代表刻度 0（無能量偏移） |
| 內在線 | 紅色 #c43e2a，線寬 2px，填充 20% 透明 |
| 外在線 | 藍色 #2e6b4f，線寬 2px，填充 20% 透明 |
| 方位軸線 | 淡灰 #e0e0e0，從中心延伸到邊緣 |
| 刻度標籤 | 深灰 #666666，小字 10px |
| 方位標籤 | 深靛藍 #181737，粗體 12px |

### 雷達圖座標轉換

由於刻度包含負數，需要做座標轉換：

```python
def energy_to_radius(energy_value, max_radius):
    """
    將能量值（-4 到 +4）轉換為雷達圖半徑
    energy_value: -4 到 +4（不含 0）
    max_radius: 雷達圖最大半徑（像素）
    """
    # 將 -4~+4 映射到 0~8，再正規化到 0~max_radius
    normalized = (energy_value + 4) / 8
    return normalized * max_radius
```

### 八方位角度對應

```python
DIRECTION_ANGLES = {
    "天": 90,    # 12 點鐘（向上）
    "風": 45,    # 1:30
    "水": 0,     # 3 點鐘（向右）
    "山": 315,   # 4:30
    "地": 270,   # 6 點鐘（向下）
    "雷": 225,   # 7:30
    "火": 180,   # 9 點鐘（向左）
    "澤": 135,   # 10:30
}

# 八方位固定順序（順時針）
DIRECTION_ORDER = ["天", "風", "水", "山", "地", "雷", "火", "澤"]
```

### 雷達圖 SVG 生成範例

```python
import math

def generate_radar_svg(inner_data: dict, outer_data: dict, 
                        size: int = 400, max_energy: int = 4) -> str:
    """
    生成八方位能量雷達圖 SVG
    
    Args:
        inner_data: {"天": 3, "風": -2, "水": 1, ...}  內在能量
        outer_data: {"天": 2, "風": 1, "水": -3, ...}  外在能量
        size: SVG 尺寸（正方形）
        max_energy: 最大刻度值（預設 4）
    
    Returns:
        SVG 字串
    """
    center = size / 2
    max_radius = size / 2 - 50  # 留邊距給標籤
    
    # 品牌色彩
    INNER_COLOR = "#c43e2a"  # 負分紅
    OUTER_COLOR = "#2e6b4f"  # 正分綠
    GRID_COLOR = "#e0e0e0"
    LABEL_COLOR = "#181737"
    
    # 八方位配置
    directions = ["天", "風", "水", "山", "地", "雷", "火", "澤"]
    themes = {
        "天": "目標",
        "風": "適應", 
        "水": "關係",
        "山": "累積",
        "地": "成就",
        "雷": "察覺",
        "火": "點燃",
        "澤": "機會"
    }
    
    def get_angle(direction):
        """取得方位對應的角度（度）"""
        idx = directions.index(direction)
        return 90 - (idx * 45)  # 從 12 點鐘開始順時針
    
    def energy_to_point(direction, energy):
        """將能量值轉換為 SVG 座標點"""
        angle_deg = get_angle(direction)
        angle_rad = math.radians(angle_deg)
        
        # 將 -4~+4 映射到 0~max_radius
        # 0 在中心，+4 在外圈，-4 在內圈最裡面
        normalized_radius = ((energy + max_energy) / (2 * max_energy)) * max_radius
        
        x = center + normalized_radius * math.cos(angle_rad)
        y = center - normalized_radius * math.sin(angle_rad)
        return x, y
    
    svg_parts = []
    
    # SVG 開頭
    svg_parts.append(f'''<svg viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg">
      <style>
        .label {{ font-family: 'Noto Sans TC', sans-serif; font-size: 12px; font-weight: 700; fill: {LABEL_COLOR}; }}
        .theme {{ font-family: 'Noto Sans TC', sans-serif; font-size: 10px; fill: #666; }}
        .scale {{ font-family: 'Outfit', sans-serif; font-size: 9px; fill: #999; }}
      </style>''')
    
    # 繪製同心圓（9 圈：-4 到 +4）
    for i in range(-max_energy, max_energy + 1):
        if i == 0:
            continue  # 跳過 0（中心點）
        radius = ((i + max_energy) / (2 * max_energy)) * max_radius
        opacity = 0.3 if i in [-4, 4] else 0.15
        svg_parts.append(f'  <circle cx="{center}" cy="{center}" r="{radius}" fill="none" stroke="{GRID_COLOR}" stroke-width="1" opacity="{opacity}"/>')
    
    # 繪製方位軸線
    for direction in directions:
        angle_deg = get_angle(direction)
        angle_rad = math.radians(angle_deg)
        x2 = center + max_radius * math.cos(angle_rad)
        y2 = center - max_radius * math.sin(angle_rad)
        svg_parts.append(f'  <line x1="{center}" y1="{center}" x2="{x2}" y2="{y2}" stroke="{GRID_COLOR}" stroke-width="1"/>')
    
    # 生成內在能量多邊形路徑
    inner_points = []
    for direction in directions:
        energy = inner_data.get(direction, 0)
        x, y = energy_to_point(direction, energy)
        inner_points.append(f"{x},{y}")
    inner_path = " ".join(inner_points)
    
    # 生成外在能量多邊形路徑
    outer_points = []
    for direction in directions:
        energy = outer_data.get(direction, 0)
        x, y = energy_to_point(direction, energy)
        outer_points.append(f"{x},{y}")
    outer_path = " ".join(outer_points)
    
    # 繪製外在能量區域（藍色，先繪製在下層）
    svg_parts.append(f'  <polygon points="{outer_path}" fill="{OUTER_COLOR}" fill-opacity="0.2" stroke="{OUTER_COLOR}" stroke-width="2"/>')
    
    # 繪製內在能量區域（紅色，繪製在上層）
    svg_parts.append(f'  <polygon points="{inner_path}" fill="{INNER_COLOR}" fill-opacity="0.2" stroke="{INNER_COLOR}" stroke-width="2"/>')
    
    # 繪製方位標籤
    for direction in directions:
        angle_deg = get_angle(direction)
        angle_rad = math.radians(angle_deg)
        label_radius = max_radius + 30
        x = center + label_radius * math.cos(angle_rad)
        y = center - label_radius * math.sin(angle_rad)
        
        theme = themes[direction]
        svg_parts.append(f'  <text x="{x}" y="{y}" text-anchor="middle" dominant-baseline="middle" class="label">{direction}</text>')
        svg_parts.append(f'  <text x="{x}" y="{y + 14}" text-anchor="middle" dominant-baseline="middle" class="theme">{theme}</text>')
    
    # 繪製刻度標籤（在天方位軸線上）
    for i in [-4, -2, 2, 4]:
        radius = ((i + max_energy) / (2 * max_energy)) * max_radius
        y = center - radius
        svg_parts.append(f'  <text x="{center + 8}" y="{y}" class="scale">{i:+d}</text>')
    
    # 繪製圖例
    legend_y = size - 30
    svg_parts.append(f'  <rect x="50" y="{legend_y}" width="20" height="3" fill="{INNER_COLOR}"/>')
    svg_parts.append(f'  <text x="75" y="{legend_y + 4}" class="theme">內在能量</text>')
    svg_parts.append(f'  <rect x="150" y="{legend_y}" width="20" height="3" fill="{OUTER_COLOR}"/>')
    svg_parts.append(f'  <text x="175" y="{legend_y + 4}" class="theme">外在能量</text>')
    
    svg_parts.append('</svg>')
    
    return '\n'.join(svg_parts)
```

## 報告書區塊結構

### 封面（COVER）

| 欄位 | 說明 |
|-----|-----|
| CLIENT_NAME | 個案姓名 |
| CLIENT_IDENTITY | 身份/職業簡述 |
| GOAL_DESCRIPTION | 六個月目標描述 |
| DATE | 解盤日期 |
| CONSULTANT | 賦能師姓名（預設：周逸達） |

### 01 能量週期（選用）

條件：逐字稿中有提到能量波動/運勢週期才出此區塊。

### 02 八方位能量總覽（必出）

包含：
- 數字解讀說明框
- 八方位表格（含雷達圖）
- 統計欄位（落差項數、落差方位列表）

### 03 整體能量狀態（必出）

包含：
- 天氣卡（盤感天氣）
- 內在/外在能量總和
- 洞察區塊（2-3 個）

### 04 關鍵轉折點（必出）

包含：
- 卡點定位
- 保護假說
- 起點定位（逆時針回推）

### 05 八方位深度解讀（必出 ★ 報告主體）

每方位一張方位卡，包含：
- 三層解讀（事業/關係/內在）
- 原文揭露子區塊

### 06 四軸人格傾向（選用）

### 07 貴人與資源（選用）

### 08 你的下一步（必出）

### 09 你的自我整理（必出）

## 用語轉換表

報告書對外呈現時，內部術語必須轉換：

| 內部用語 | 對外呈現 |
|---------|---------|
| Knowledge Pack | 卡牌原文 |
| PDF 原文 | 卡牌原文 |
| AEO 行動卡 | 行動建議 |
| gap ≥ 3 | 內外落差 |
| +4/-4 臨界值 | 能量飽和點 |
| inner_sum | 內在能量總和 |
| outer_sum | 外在能量總和 |

## 品牌視覺規範速查

### 色彩系統

```css
:root {
  --navy: #181737;           /* 深靛藍 */
  --gold: #edd2a6;           /* 品牌金 */
  --gold-deep: #b6853d;      /* 深金 */
  --warm-white: #fdf9f4;     /* 暖米白 */
  --warm-red: #f15928;       /* 暖紅 */
  --positive: #2e6b4f;       /* 正分綠 */
  --negative: #c43e2a;       /* 負分紅 */
  --lavender: #8394c6;       /* 薰衣草藍 */
  --light-gold: #f5ead5;     /* 淺金 */
}
```

### 字體規範

| 用途 | 字體 |
|-----|-----|
| 中文標題 | Noto Serif TC Bold |
| 中文內文 | Noto Sans TC Regular |
| 英文標題 | Butler Stencil / Outfit Bold |
| 數字 | Outfit Bold + tabular-nums |

### 八卦符號對照

```
☰ 天（乾）　願景・主權・領導
☴ 風（巽）　敘事・成交・共識
☵ 水（坎）　親密關係・有效人脈
☶ 山（艮）　復盤・界線・覆盤
☷ 地（坤）　系統・感恩・愛自己
☳ 雷（震）　破框・止損・冒險
☲ 火（離）　研發・趨勢・新奇好玩
☱ 澤（兌）　品牌・社交・顯化
```

## PDF 生成指令

```python
import asyncio
from playwright.async_api import async_playwright

async def generate_pdf(html_path, pdf_path):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(f"file://{html_path}", wait_until="networkidle")
        await page.wait_for_timeout(3000)  # 等字體載入
        await page.pdf(
            path=pdf_path,
            format="A4",
            margin={"top":"1.5cm","bottom":"1.5cm","left":"2cm","right":"2cm"},
            print_background=True,
            prefer_css_page_size=False
        )
        await browser.close()

asyncio.run(generate_pdf("/home/claude/report.html", "/home/claude/report.pdf"))
```

## 排版規則

### 強制換頁規則

標題不可出現在頁面最後幾行而內容跑到下一頁。遇此情況強制換頁，確保標題與內容整段呈現。

```css
.section-title {
  page-break-after: avoid;
  break-after: avoid;
}

.section-content {
  page-break-inside: avoid;
  break-inside: avoid;
}

/* 區塊標題與內容綁定 */
.section {
  page-break-inside: avoid;
  break-inside: avoid;
}
```

## References 導覽

| 檔案 | 內容 | 何時讀取 |
|-----|-----|---------|
| `references/radar-chart.md` | 雷達圖詳細繪製規範與座標轉換 | 生成雷達圖時 |
| `references/energy-table.md` | 能量表格樣式與狀態標籤規則 | 生成表格時 |
| `templates/personal-report.html` | 個人盤報告 HTML 完整模板 | 生成報告時 |
| `assets/sample-data.json` | 範例盤面數據 | 測試模板時 |

## 角色稱呼提醒

報告書中顧問角色稱呼為「賦能師」，非「解盤師」。

報告書不顯示系統版本資訊。
