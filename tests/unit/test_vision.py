"""Vision 模組測試 — 圖片到 Anthropic Vision API content block."""

import base64
import json
import tempfile
from pathlib import Path

import pytest

from museon.llm.vision import (
    EXT_TO_MIME,
    MAX_IMAGE_BYTES,
    SUPPORTED_MEDIA_TYPES,
    build_vision_content,
    prepare_image_block,
)


# ═══════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════


@pytest.fixture
def tiny_jpeg(tmp_path):
    """建立一個最小的有效 JPEG 檔案."""
    # 最小 JPEG: SOI + APP0 + EOI
    jpeg_data = bytes([
        0xFF, 0xD8,  # SOI
        0xFF, 0xE0,  # APP0 marker
        0x00, 0x10,  # Length
        0x4A, 0x46, 0x49, 0x46, 0x00,  # "JFIF\0"
        0x01, 0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00,
        0xFF, 0xD9,  # EOI
    ])
    fp = tmp_path / "test.jpg"
    fp.write_bytes(jpeg_data)
    return fp, jpeg_data


@pytest.fixture
def tiny_png(tmp_path):
    """建立一個最小的有效 PNG 檔案 (1x1 紅色像素)."""
    import struct
    import zlib

    def _chunk(ctype, data):
        chunk = ctype + data
        return struct.pack(">I", len(data)) + chunk + struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF)

    png_data = b"\x89PNG\r\n\x1a\n"
    png_data += _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    raw_data = zlib.compress(b"\x00\xff\x00\x00")
    png_data += _chunk(b"IDAT", raw_data)
    png_data += _chunk(b"IEND", b"")

    fp = tmp_path / "test.png"
    fp.write_bytes(png_data)
    return fp, png_data


# ═══════════════════════════════════════════
# prepare_image_block 測試
# ═══════════════════════════════════════════


class TestPrepareImageBlock:
    """prepare_image_block() 的單元測試."""

    def test_valid_jpeg(self, tiny_jpeg):
        """有效的 JPEG 應回傳 image block."""
        fp, data = tiny_jpeg
        result = prepare_image_block({
            "local_path": str(fp),
            "mime_type": "image/jpeg",
        })
        assert result is not None
        assert result["type"] == "image"
        assert result["source"]["type"] == "base64"
        assert result["source"]["media_type"] == "image/jpeg"
        # 驗證 base64 可解碼回原始資料
        decoded = base64.standard_b64decode(result["source"]["data"])
        assert decoded == data

    def test_valid_png(self, tiny_png):
        """有效的 PNG 應回傳 image block."""
        fp, data = tiny_png
        result = prepare_image_block({
            "local_path": str(fp),
            "mime_type": "image/png",
        })
        assert result is not None
        assert result["source"]["media_type"] == "image/png"

    def test_mime_fallback_from_extension(self, tiny_jpeg):
        """缺少 mime_type 時應從副檔名推斷."""
        fp, _ = tiny_jpeg
        result = prepare_image_block({
            "local_path": str(fp),
            "mime_type": None,
        })
        assert result is not None
        assert result["source"]["media_type"] == "image/jpeg"

    def test_unsupported_format(self, tmp_path):
        """不支援的格式應回傳 None."""
        fp = tmp_path / "test.bmp"
        fp.write_bytes(b"BM" + b"\x00" * 50)
        result = prepare_image_block({
            "local_path": str(fp),
            "mime_type": "image/bmp",
        })
        assert result is None

    def test_file_not_exists(self):
        """檔案不存在應回傳 None."""
        result = prepare_image_block({
            "local_path": "/nonexistent/path/image.jpg",
            "mime_type": "image/jpeg",
        })
        assert result is None

    def test_missing_local_path(self):
        """缺少 local_path 應回傳 None."""
        result = prepare_image_block({})
        assert result is None

    def test_none_local_path(self):
        """local_path 為 None 應回傳 None."""
        result = prepare_image_block({"local_path": None})
        assert result is None


# ═══════════════════════════════════════════
# build_vision_content 測試
# ═══════════════════════════════════════════


class TestBuildVisionContent:
    """build_vision_content() 的單元測試."""

    def test_no_file_info_returns_text(self):
        """無 file_info 應回傳原始文字."""
        result = build_vision_content("hello", None)
        assert result == "hello"
        assert isinstance(result, str)

    def test_empty_file_info_returns_text(self):
        """空 file_info 應回傳原始文字."""
        result = build_vision_content("hello", {})
        assert result == "hello"

    def test_invalid_file_returns_text(self):
        """無效檔案路徑應回傳原始文字."""
        result = build_vision_content("hello", {
            "local_path": "/nonexistent.jpg",
            "mime_type": "image/jpeg",
        })
        assert result == "hello"
        assert isinstance(result, str)

    def test_valid_image_returns_list(self, tiny_jpeg):
        """有效圖片應回傳 multimodal content blocks."""
        fp, _ = tiny_jpeg
        result = build_vision_content("[🖼️ 圖片上傳]", {
            "local_path": str(fp),
            "mime_type": "image/jpeg",
        })
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["type"] == "text"
        assert result[0]["text"] == "[🖼️ 圖片上傳]"
        assert result[1]["type"] == "image"
        assert result[1]["source"]["media_type"] == "image/jpeg"

    def test_empty_text_only_image(self, tiny_jpeg):
        """空文字 + 有效圖片 → 只有 image block."""
        fp, _ = tiny_jpeg
        result = build_vision_content("", {
            "local_path": str(fp),
            "mime_type": "image/jpeg",
        })
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["type"] == "image"

    def test_result_is_json_serializable(self, tiny_jpeg):
        """結果必須可 JSON 序列化."""
        fp, _ = tiny_jpeg
        result = build_vision_content("test", {
            "local_path": str(fp),
            "mime_type": "image/jpeg",
        })
        serialized = json.dumps(result)
        assert len(serialized) > 0


# ═══════════════════════════════════════════
# 常數測試
# ═══════════════════════════════════════════


class TestConstants:
    """常數與映射表的一致性測試."""

    def test_ext_to_mime_covers_supported(self):
        """所有 EXT_TO_MIME 的值都在 SUPPORTED_MEDIA_TYPES 中."""
        for ext, mime in EXT_TO_MIME.items():
            assert mime in SUPPORTED_MEDIA_TYPES, f"{ext} → {mime} not supported"

    def test_max_image_bytes_reasonable(self):
        """MAX_IMAGE_BYTES 在合理範圍."""
        assert 1 * 1024 * 1024 <= MAX_IMAGE_BYTES <= 20 * 1024 * 1024
