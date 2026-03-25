#!/bin/bash

################################################################################
# MUSEON 劇本生成工作流 (ScreenplayForge Workflow)
# 用途：將客户輸入轉化為結構化劇本 + 製作清單 + 驗收報告
# 使用方式：
#   ./screenplay-gen.sh --project "品牌微劇本 #咖啡日常" \
#                       --genre "廣告" \
#                       --duration "30秒" \
#                       --theme "一個媽媽的日常寧靜" \
#                       --characters 2 \
#                       --tone "溫馨"
#
# 輸出：
#   - {project_name}_screenplay.md
#   - {project_name}_production_brief.json
#   - {project_name}_emotional_arc.html
#   - {project_name}_qa_report.json
################################################################################

set -e  # Exit on error

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MUSEON_HOME="${MUSEON_HOME:-/Users/ZEALCHOU/MUSEON}"
WORKFLOW_NAME="ScreenplayForge"
VERSION="1.0"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# 邏輯：檢查是否有已打包的 Claude 執行環境
# 若無，則提示人工操作
CLAUDE_AVAILABLE=false
OUTPUT_DIR="${MUSEON_HOME}/outputs/screenplay/${TIMESTAMP}"

################################################################################
# 函數：打印日誌
################################################################################
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[⚠]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
}

################################################################################
# 函數：驗證輸入參數
################################################################################
validate_inputs() {
    log_info "驗證輸入參數..."

    # 必填項檢查
    if [[ -z "$PROJECT_NAME" ]]; then
        log_error "必須提供 --project 參數"
        exit 1
    fi

    if [[ -z "$GENRE" ]]; then
        log_error "必須提供 --genre 參數（短篇|廣告|微劇本|話劇）"
        exit 1
    fi

    if [[ -z "$TARGET_DURATION" ]]; then
        log_error "必須提供 --duration 參數（30秒|1分鐘|3分鐘|5分鐘|10分鐘）"
        exit 1
    fi

    if [[ -z "$THEME" ]]; then
        log_error "必須提供 --theme 參數"
        exit 1
    fi

    if [[ -z "$NUM_CHARACTERS" ]]; then
        log_error "必須提供 --characters 參數（整數）"
        exit 1
    fi

    if [[ -z "$EMOTIONAL_TONE" ]]; then
        log_error "必須提供 --tone 參數（溫馨|懸疑|喜劇|激勵|感傷|驚悚）"
        exit 1
    fi

    # 驗證 genre
    case "$GENRE" in
        短篇|廣告|微劇本|話劇) ;;
        *) log_error "無效的 genre: $GENRE"; exit 1 ;;
    esac

    # 驗證 duration
    case "$TARGET_DURATION" in
        30秒|1分鐘|3分鐘|5分鐘|10分鐘) ;;
        *) log_error "無效的 duration: $TARGET_DURATION"; exit 1 ;;
    esac

    # 驗證 tone
    case "$EMOTIONAL_TONE" in
        溫馨|懸疑|喜劇|激勵|感傷|驚悚) ;;
        *) log_error "無效的 tone: $EMOTIONAL_TONE"; exit 1 ;;
    esac

    # 驗證角色數
    if ! [[ "$NUM_CHARACTERS" =~ ^[0-9]+$ ]] || [[ "$NUM_CHARACTERS" -lt 1 ]] || [[ "$NUM_CHARACTERS" -gt 20 ]]; then
        log_error "characters 必須是 1-20 之間的整數"
        exit 1
    fi

    # 若角色 > 8，提示
    if [[ "$NUM_CHARACTERS" -gt 8 ]]; then
        log_warning "角色數 > 8，建議加入群演設定"
    fi

    log_success "輸入驗證通過"
}

################################################################################
# 函數：根據時長推薦場景數
################################################################################
recommend_scene_count() {
    case "$TARGET_DURATION" in
        30秒) echo 4 ;;    # 30秒 = 4-5 場景，平均 7-8 秒/場景
        1分鐘) echo 5 ;;   # 1分鐘 = 5-7 場景
        3分鐘) echo 8 ;;   # 3分鐘 = 7-10 場景
        5分鐘) echo 10 ;;  # 5分鐘 = 10-12 場景
        10分鐘) echo 15 ;; # 10分鐘 = 12-18 場景
    esac
}

################################################################################
# 函數：建立輸出目錄
################################################################################
setup_output_dir() {
    log_info "建立輸出目錄..."
    mkdir -p "$OUTPUT_DIR"
    log_success "輸出目錄: $OUTPUT_DIR"
}

################################################################################
# 函數：生成輸入 JSON（給 Claude）
################################################################################
generate_input_json() {
    local input_file="${OUTPUT_DIR}/screenplay_input.json"
    local scene_count=$(recommend_scene_count)

    log_info "生成輸入 JSON..."

    cat > "$input_file" << EOF
{
  "project_name": "$PROJECT_NAME",
  "genre": "$GENRE",
  "target_duration": "$TARGET_DURATION",
  "theme": "$THEME",
  "num_characters": $NUM_CHARACTERS,
  "emotional_tone": "$EMOTIONAL_TONE",
  "target_audience": "$TARGET_AUDIENCE",
  "setting": "$SETTING",
  "key_props": $KEY_PROPS,
  "brand_values": $BRAND_VALUES,
  "special_requirements": "$SPECIAL_REQUIREMENTS",
  "budget_tier": "$BUDGET_TIER",
  "recommended_scene_count": $scene_count
}
EOF

    log_success "輸入 JSON 已生成: $input_file"
}

################################################################################
# 函數：檢查 Claude 可用性
################################################################################
check_claude_availability() {
    log_info "檢查 Claude 可用性..."

    # 檢查是否有 python 與必要的模組
    if command -v python3 &> /dev/null; then
        if python3 -c "import anthropic" 2>/dev/null; then
            CLAUDE_AVAILABLE=true
            log_success "Claude 可用（via Anthropic Python SDK）"
        fi
    fi

    if ! $CLAUDE_AVAILABLE; then
        log_warning "Claude 不可用 - 將進入手動模式"
        log_info "提示：需要人工操作 Claude 完成劇本生成"
    fi
}

################################################################################
# 函數：調用 Claude 生成劇本
################################################################################
generate_screenplay() {
    log_info "開始生成劇本 (會耗時 10-30 秒)..."

    if ! $CLAUDE_AVAILABLE; then
        log_warning "=== 手動模式 ==="
        log_info "1. 開啟 Claude (https://claude.ai 或 Claude App)"
        log_info "2. 複製以下提示，貼入 Claude："
        log_info ""

        # 列出 Prompt（簡化版）
        cat << 'EOF'
---
你是資深劇本編劇。根據以下需求生成劇本：

【基本資訊】
EOF
        cat "${OUTPUT_DIR}/screenplay_input.json"

        cat << 'EOF'

【任務】
1. 生成三幕劇結構的完整劇本（Fountain 格式）
2. 為每場景設計視覺敘事意圖
3. 生成道具清單（含象徵意義）
4. 確保情緒線呈波浪狀，有≥2處內在衝突
5. 驗收清單全部通過

【輸出格式】
```json
{
  "screenplay_markdown": "...",
  "production_brief_json": {...},
  "qa_report_json": {...},
  "improvement_suggestions": [...]
}
```

生成完成後，複製 JSON 並貼進終端：
EOF

        log_info ""
        return 1
    else
        log_info "（此功能需要實現 Anthropic API 整合，目前為測試模式）"
        return 1
    fi
}

################################################################################
# 函數：生成默認樣本輸出（測試用）
################################################################################
generate_sample_outputs() {
    log_info "生成樣本輸出（測試用）..."

    # 樣本劇本
    local screenplay_file="${OUTPUT_DIR}/${PROJECT_NAME}_screenplay.md"
    cat > "$screenplay_file" << 'EOF'
# 劇本標題

## 基本資訊
- 時長：待更新
- 場景數：待更新
- 角色數：待更新

## 角色檔案
### 主角
待 Claude 生成

## 完整劇本
待 Claude 生成

## 製作清單
待 Claude 生成
EOF

    # 樣本製作清單
    local prod_file="${OUTPUT_DIR}/${PROJECT_NAME}_production_brief.json"
    cat > "$prod_file" << 'EOF'
{
  "project": "待更新",
  "scenes": [],
  "props_summary": {
    "total_unique_props": 0,
    "estimated_prop_cost": "$0"
  },
  "crew_requirements": {},
  "production_timeline": "待 Claude 確認"
}
EOF

    # 樣本驗收報告
    local qa_file="${OUTPUT_DIR}/${PROJECT_NAME}_qa_report.json"
    cat > "$qa_file" << 'EOF'
{
  "timestamp": "'$(date -Iseconds)'",
  "project_name": "待更新",
  "qa_checks": {
    "structure_integrity": {"score": "待更新"},
    "emotional_arc": {"score": "待更新"},
    "character_development": {"score": "待更新"},
    "production_feasibility": {"score": "待更新"}
  },
  "overall_score": "待更新",
  "status": "PENDING_CLAUDE_INPUT"
}
EOF

    log_success "樣本輸出已生成（等待 Claude 內容填充）"
}

################################################################################
# 函數：驗證輸出完整性
################################################################################
verify_outputs() {
    log_info "驗證輸出完整性..."

    local required_files=(
        "${OUTPUT_DIR}/${PROJECT_NAME}_screenplay.md"
        "${OUTPUT_DIR}/${PROJECT_NAME}_production_brief.json"
        "${OUTPUT_DIR}/${PROJECT_NAME}_qa_report.json"
    )

    local missing=0
    for file in "${required_files[@]}"; do
        if [[ ! -f "$file" ]]; then
            log_error "缺失文件: $file"
            ((missing++))
        else
            log_success "✓ $(basename $file)"
        fi
    done

    if [[ $missing -eq 0 ]]; then
        log_success "所有必要輸出文件已生成"
        return 0
    else
        log_error "有 $missing 個文件缺失"
        return 1
    fi
}

################################################################################
# 函數：生成情緒線 HTML（可視化）
################################################################################
generate_emotional_arc_html() {
    log_info "生成情緒線可視化..."

    local html_file="${OUTPUT_DIR}/${PROJECT_NAME}_emotional_arc.html"

    cat > "$html_file" << 'EOF'
<!DOCTYPE html>
<html lang="zh-Hant">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>情緒線圖表</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body {
            font-family: 'Cormorant Garamond', serif;
            max-width: 900px;
            margin: 40px auto;
            background: #FEFAF4;
            padding: 20px;
        }
        #chart {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(196, 80, 42, 0.1);
        }
        h1 {
            color: #C4502A;
            text-align: center;
        }
    </style>
</head>
<body>
    <h1>情緒線圖表 (待 Claude 更新)</h1>
    <div id="chart"></div>
    <script>
        // Plotly 圖表將由 Claude 自動生成
        // 此為預設空圖表
        var layout = {
            title: '情感曲線',
            xaxis: { title: '場景序號' },
            yaxis: { title: '情感強度' },
            plot_bgcolor: '#FEFAF4',
            paper_bgcolor: '#FEFAF4'
        };
        Plotly.newPlot('chart', [], layout);
    </script>
</body>
</html>
EOF

    log_success "情緒線 HTML 已生成: $html_file"
}

################################################################################
# 函數：生成最終報告
################################################################################
generate_final_report() {
    log_info "生成工作流完成報告..."

    local report_file="${OUTPUT_DIR}/WORKFLOW_REPORT.md"

    cat > "$report_file" << EOF
# ScreenplayForge 工作流報告

**時間戳記**: $(date -Iseconds)
**專案名稱**: $PROJECT_NAME
**工作流版本**: $VERSION
**狀態**: 待人工審核

---

## 輸入參數

| 參數 | 值 |
|------|-----|
| 專案名稱 | $PROJECT_NAME |
| 劇本類型 | $GENRE |
| 目標時長 | $TARGET_DURATION |
| 核心主題 | $THEME |
| 角色數 | $NUM_CHARACTERS |
| 情感基調 | $EMOTIONAL_TONE |
| 預算層級 | $BUDGET_TIER |
| 目標觀眾 | $TARGET_AUDIENCE |
| 佈景限制 | $SETTING |

---

## 推薦場景數

**推薦**: $(recommend_scene_count) 場景

---

## 輸出文件清單

- ✓ \`${PROJECT_NAME}_screenplay.md\` — 完整劇本文本
- ✓ \`${PROJECT_NAME}_production_brief.json\` — 製作清單
- ✓ \`${PROJECT_NAME}_emotional_arc.html\` — 情緒線可視化
- ✓ \`${PROJECT_NAME}_qa_report.json\` — 驗收報告

**路徑**: $OUTPUT_DIR

---

## 下一步

1. **填充內容**：用 Claude 根據上述輸入生成劇本
2. **驗收檢查**：確認 QA 報告中所有檢查項目通過
3. **修改迭代**：根據改進建議調整劇本
4. **提交發布**：將最終版本提交給製片團隊

---

## 工作流驗證

- [x] 輸入參數驗證完成
- [x] 輸出目錄已建立
- [x] 樣本文件已生成
- [ ] Claude 內容填充 (待人工操作)
- [ ] 所有驗收項目通過 (待檢查)
- [ ] 最終審核通過 (待決定)

---

**工作流啟動時間**: $(date)
**操作者**: $(whoami)
**工作目錄**: $(pwd)

EOF

    log_success "工作流報告已生成: $report_file"
}

################################################################################
# 函數：打印使用說明
################################################################################
print_usage() {
    cat << EOF
使用方式：
  $0 --project "項目名稱" \\
     --genre "廣告" \\
     --duration "30秒" \\
     --theme "主題說明" \\
     --characters 2 \\
     --tone "溫馨" \\
     [其他選填參數]

必填參數：
  --project NAME          專案名稱
  --genre TYPE            劇本類型（短篇|廣告|微劇本|話劇）
  --duration TIME         目標時長（30秒|1分鐘|3分鐘|5分鐘|10分鐘）
  --theme TEXT            核心主題
  --characters NUM        角色數
  --tone TONE             情感基調（溫馨|懸疑|喜劇|激勵|感傷|驚悚）

選填參數：
  --audience TEXT         目標觀眾（預設："一般大眾"）
  --setting TEXT          佈景限制（預設："無限制"）
  --props JSON            關鍵道具（JSON 陣列，預設："[]"）
  --values JSON           品牌價值觀（JSON 陣列，預設："[]"）
  --special TEXT          特殊要求（預設：""）
  --budget TIER           製作預算（low|medium|high，預設："medium"）
  --help                  顯示本說明

範例：
  $0 --project "咖啡品牌廣告" \\
     --genre "廣告" \\
     --duration "30秒" \\
     --theme "一個媽媽的晨間寧靜" \\
     --characters 2 \\
     --tone "溫馨" \\
     --audience "25-45 歲女性" \\
     --budget "low"

EOF
}

################################################################################
# MAIN 邏輯
################################################################################
main() {
    echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║           MUSEON ScreenplayForge 工作流 v${VERSION}          ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""

    # 解析命令行參數
    while [[ $# -gt 0 ]]; do
        case $1 in
            --project)      PROJECT_NAME="$2"; shift 2 ;;
            --genre)        GENRE="$2"; shift 2 ;;
            --duration)     TARGET_DURATION="$2"; shift 2 ;;
            --theme)        THEME="$2"; shift 2 ;;
            --characters)   NUM_CHARACTERS="$2"; shift 2 ;;
            --tone)         EMOTIONAL_TONE="$2"; shift 2 ;;
            --audience)     TARGET_AUDIENCE="$2"; shift 2 ;;
            --setting)      SETTING="$2"; shift 2 ;;
            --props)        KEY_PROPS="$2"; shift 2 ;;
            --values)       BRAND_VALUES="$2"; shift 2 ;;
            --special)      SPECIAL_REQUIREMENTS="$2"; shift 2 ;;
            --budget)       BUDGET_TIER="$2"; shift 2 ;;
            --help)         print_usage; exit 0 ;;
            *)              log_error "未知參數: $1"; print_usage; exit 1 ;;
        esac
    done

    # 設置預設值
    TARGET_AUDIENCE="${TARGET_AUDIENCE:-一般大眾}"
    SETTING="${SETTING:-無限制}"
    KEY_PROPS="${KEY_PROPS:-[]}"
    BRAND_VALUES="${BRAND_VALUES:-[]}"
    SPECIAL_REQUIREMENTS="${SPECIAL_REQUIREMENTS:- }"
    BUDGET_TIER="${BUDGET_TIER:-medium}"

    # 執行工作流
    validate_inputs
    setup_output_dir
    generate_input_json
    check_claude_availability
    generate_sample_outputs
    generate_emotional_arc_html
    generate_final_report

    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║                    工作流啟動成功！                        ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    log_success "輸出目錄: $OUTPUT_DIR"
    echo ""
    echo -e "${YELLOW}【下一步】${NC}"
    echo "1. 用 Claude 根據以下文件生成劇本:"
    echo "   → $OUTPUT_DIR/screenplay_input.json"
    echo ""
    echo "2. 更新輸出文件:"
    echo "   → ${PROJECT_NAME}_screenplay.md"
    echo "   → ${PROJECT_NAME}_production_brief.json"
    echo "   → ${PROJECT_NAME}_qa_report.json"
    echo ""
    echo "3. 驗收檢查:"
    echo "   → 查看 ${PROJECT_NAME}_qa_report.json 確認 status = PASS"
    echo ""
    echo "4. （可選）提交到 Git:"
    echo "   → git add $OUTPUT_DIR"
    echo "   → git commit -m \"feat: 劇本生成 - $PROJECT_NAME\""
    echo ""
}

# 執行主函數
main "$@"
