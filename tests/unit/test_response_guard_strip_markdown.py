"""Tests for ResponseGuard.strip_markdown and sanitize_for_group markdown cleaning."""

import pytest
from museon.governance.response_guard import ResponseGuard


class TestStripMarkdownHeaders:
    def test_h2_header(self):
        assert ResponseGuard.strip_markdown("## 七個問題") == "七個問題"

    def test_h3_bold_header(self):
        assert ResponseGuard.strip_markdown("### **第一類**") == "第一類"

    def test_h1_header(self):
        assert ResponseGuard.strip_markdown("# 標題") == "標題"

    def test_h4_header(self):
        assert ResponseGuard.strip_markdown("#### 小標") == "小標"

    def test_header_in_multiline(self):
        text = "開頭\n\n## 分析結果\n\n內容"
        result = ResponseGuard.strip_markdown(text)
        assert "##" not in result
        assert "分析結果" in result
        assert "內容" in result


class TestStripMarkdownTables:
    def test_table_no_separator_in_output(self):
        table = "| 問題 | 核心 |\n|---|---|\n| Q1 | 回覆慢 |"
        result = ResponseGuard.strip_markdown(table)
        assert "##" not in result
        assert "|---" not in result
        assert "Q1" in result
        assert "回覆慢" in result

    def test_table_row_converted_to_slash(self):
        row = "| 欄位A | 欄位B |"
        result = ResponseGuard.strip_markdown(row)
        assert "|" not in result
        assert "欄位A" in result
        assert "欄位B" in result
        assert "/" in result


class TestStripMarkdownBold:
    def test_bold_text(self):
        assert ResponseGuard.strip_markdown("**重要**的事") == "重要的事"

    def test_italic_text(self):
        assert ResponseGuard.strip_markdown("*斜體*文字") == "斜體文字"

    def test_underscore_bold(self):
        assert ResponseGuard.strip_markdown("__粗體__") == "粗體"

    def test_underscore_italic(self):
        assert ResponseGuard.strip_markdown("_斜體_") == "斜體"


class TestStripMarkdownCode:
    def test_inline_code(self):
        assert ResponseGuard.strip_markdown("`hello`") == "hello"

    def test_code_block(self):
        result = ResponseGuard.strip_markdown("```python\nprint('hi')\n```")
        assert "print('hi')" in result
        assert "```" not in result

    def test_code_block_no_lang(self):
        result = ResponseGuard.strip_markdown("```\nsome code\n```")
        assert "some code" in result
        assert "```" not in result


class TestStripMarkdownLinks:
    def test_markdown_link(self):
        assert ResponseGuard.strip_markdown("[文字](https://example.com)") == "文字"

    def test_link_in_sentence(self):
        result = ResponseGuard.strip_markdown("請參考[這裡](https://example.com)的說明")
        assert "這裡" in result
        assert "https://example.com" not in result
        assert "[" not in result


class TestStripMarkdownHorizontalRule:
    def test_dash_hr(self):
        result = ResponseGuard.strip_markdown("文字\n\n---\n\n更多文字")
        assert "---" not in result
        assert "文字" in result
        assert "更多文字" in result

    def test_asterisk_hr(self):
        result = ResponseGuard.strip_markdown("文字\n\n***\n\n更多文字")
        assert "***" not in result


class TestStripMarkdownExcessiveBlankLines:
    def test_three_blank_lines_collapsed(self):
        result = ResponseGuard.strip_markdown("A\n\n\n\nB")
        assert "\n\n\n" not in result
        assert "A" in result
        assert "B" in result


class TestSanitizeIncludesMarkdownStrip:
    def test_sanitize_removes_markdown_headers(self):
        """sanitize_for_group 的輸出不應包含 markdown 標記."""
        text = "## 分析結果\n\n| 指標 | 數值 |\n|---|---|\n| Q1 | 好 |"
        result = ResponseGuard.sanitize_for_group(text)
        assert "##" not in result
        assert "|---" not in result

    def test_sanitize_preserves_content(self):
        """清理後內容應保留。"""
        text = "## 分析結果\n\n**重點**：這是一個測試"
        result = ResponseGuard.sanitize_for_group(text)
        assert "分析結果" in result
        assert "重點" in result
        assert "這是一個測試" in result

    def test_sanitize_removes_bold_markers(self):
        text = "**重要**的決策不可忽略"
        result = ResponseGuard.sanitize_for_group(text)
        assert "**" not in result
        assert "重要" in result

    def test_sanitize_plain_text_unchanged(self):
        """純文字應通過且不被破壞。"""
        text = "這是一段普通的中文訊息，沒有任何 markdown 格式。"
        result = ResponseGuard.sanitize_for_group(text)
        assert result == text
