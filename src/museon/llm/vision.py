"""Multimodal 工具模組 — 將圖片/PDF 轉為 Anthropic API content block.

單一職責：讀取檔案 → 驗證格式/大小 → base64 編碼 → 回傳 content block。
不涉及任何 Brain/LLM 邏輯。

支援：
  - 圖片（Vision API）：JPEG, PNG, GIF, WebP → image block
  - PDF（Document API）：PDF → document block
"""

import base64
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# 常數
# ═══════════════════════════════════════════

# Anthropic Vision API 支援的圖片 MIME types
SUPPORTED_IMAGE_TYPES = {
    "image/jpeg", "image/png", "image/gif", "image/webp",
}

# Anthropic Document API 支援的文件 MIME types
SUPPORTED_DOCUMENT_TYPES = {
    "application/pdf",
}

# 所有支援的多媒體 MIME types
SUPPORTED_MEDIA_TYPES = SUPPORTED_IMAGE_TYPES | SUPPORTED_DOCUMENT_TYPES

# 副檔名 → MIME type 對照（metadata 缺 mime_type 時 fallback）
EXT_TO_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
}

# 大小限制（bytes）
MAX_IMAGE_BYTES = 5 * 1024 * 1024    # 5 MB（圖片）
MAX_PDF_BYTES = 32 * 1024 * 1024     # 32 MB（PDF，Anthropic 限制約 100 頁）


# ═══════════════════════════════════════════
# 核心函數
# ═══════════════════════════════════════════


def prepare_image_block(file_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """從 file_info 準備 Anthropic Vision image content block.

    Args:
        file_info: {local_path, file_name, file_size, mime_type, file_id}

    Returns:
        {"type": "image", "source": {"type": "base64", ...}} 或 None
    """
    local_path = file_info.get("local_path")
    if not local_path:
        return None

    path = Path(local_path)
    if not path.exists():
        logger.warning(f"[Vision] 圖片檔案不存在: {local_path}")
        return None

    # 決定 MIME type
    mime_type = _resolve_mime(file_info, path)
    if mime_type not in SUPPORTED_IMAGE_TYPES:
        logger.info(f"[Vision] 不支援的圖片格式: {mime_type or path.suffix}")
        return None

    # 讀取並檢查大小
    file_size = path.stat().st_size
    if file_size > MAX_IMAGE_BYTES:
        image_data = _try_resize(path, mime_type)
        if image_data is None:
            logger.warning(
                f"[Vision] 圖片過大且縮圖失敗: {file_size / 1024 / 1024:.1f}MB"
            )
            return None
    else:
        image_data = path.read_bytes()

    b64_data = base64.standard_b64encode(image_data).decode("ascii")

    logger.info(
        f"[Vision] 圖片已編碼 | format={mime_type} | "
        f"size={len(image_data)/1024:.0f}KB | b64_len={len(b64_data)}"
    )

    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": mime_type,
            "data": b64_data,
        },
    }


def prepare_pdf_block(file_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """從 file_info 準備 Anthropic Document PDF content block.

    Args:
        file_info: {local_path, file_name, file_size, mime_type, file_id}

    Returns:
        {"type": "document", "source": {"type": "base64", ...}} 或 None
    """
    local_path = file_info.get("local_path")
    if not local_path:
        return None

    path = Path(local_path)
    if not path.exists():
        logger.warning(f"[PDF] 檔案不存在: {local_path}")
        return None

    # 驗證是 PDF
    mime_type = _resolve_mime(file_info, path)
    if mime_type != "application/pdf":
        return None

    # 檢查大小
    file_size = path.stat().st_size
    if file_size > MAX_PDF_BYTES:
        logger.warning(
            f"[PDF] 檔案過大: {file_size / 1024 / 1024:.1f}MB（上限 {MAX_PDF_BYTES // 1024 // 1024}MB）"
        )
        return None

    pdf_data = path.read_bytes()

    # 簡單驗證 PDF 魔數
    if not pdf_data[:5] == b"%PDF-":
        logger.warning(f"[PDF] 檔案不是有效 PDF: {local_path}")
        return None

    b64_data = base64.standard_b64encode(pdf_data).decode("ascii")

    logger.info(
        f"[PDF] 文件已編碼 | size={len(pdf_data)/1024:.0f}KB | "
        f"b64_len={len(b64_data)}"
    )

    return {
        "type": "document",
        "source": {
            "type": "base64",
            "media_type": "application/pdf",
            "data": b64_data,
        },
    }


def build_multimodal_content(
    text: str,
    file_info: Optional[Dict[str, Any]],
) -> Union[str, List[Dict[str, Any]]]:
    """構建可能包含圖片或 PDF 的 user message content.

    自動判斷檔案類型，構建對應的 content blocks。
    若不支援或失敗，回傳原始 text str（向後相容）。

    Args:
        text: 原始使用者訊息文字
        file_info: metadata["file"] 或 None

    Returns:
        str（純文字，向後相容）或 List[Dict]（multimodal blocks）
    """
    if not file_info:
        return text

    # 判斷檔案類型
    mime_type = _resolve_mime(file_info, Path(file_info.get("local_path", "")))

    media_block = None
    if mime_type in SUPPORTED_IMAGE_TYPES:
        media_block = prepare_image_block(file_info)
    elif mime_type in SUPPORTED_DOCUMENT_TYPES:
        media_block = prepare_pdf_block(file_info)

    if media_block is None:
        return text

    # 組合：text block + media block
    blocks: List[Dict[str, Any]] = []
    if text and text.strip():
        blocks.append({"type": "text", "text": text})
    blocks.append(media_block)
    return blocks


# 向後相容別名
build_vision_content = build_multimodal_content


# ═══════════════════════════════════════════
# 內部工具
# ═══════════════════════════════════════════


def _resolve_mime(file_info: Dict[str, Any], path: Path) -> str:
    """從 file_info 或副檔名推斷 MIME type."""
    mime_type = file_info.get("mime_type") or ""
    if mime_type and mime_type in SUPPORTED_MEDIA_TYPES:
        return mime_type
    return EXT_TO_MIME.get(path.suffix.lower(), mime_type)


def _try_resize(path: Path, mime_type: str) -> Optional[bytes]:
    """嘗試縮小圖片到 MAX_IMAGE_BYTES 以下.

    使用 Pillow（如果可用）。如果 Pillow 未安裝，回傳 None。
    """
    try:
        from PIL import Image
        import io

        img = Image.open(path)

        # 保持比例，逐步縮小直到符合大小限制
        quality = 85
        for scale in (0.75, 0.5, 0.35, 0.25):
            new_w = int(img.width * scale)
            new_h = int(img.height * scale)
            resized = img.resize((new_w, new_h), Image.LANCZOS)

            buf = io.BytesIO()
            fmt = "JPEG" if mime_type in ("image/jpeg",) else "PNG"
            if fmt == "JPEG":
                if resized.mode in ("RGBA", "LA", "P"):
                    resized = resized.convert("RGB")
                resized.save(buf, format=fmt, quality=quality)
            else:
                resized.save(buf, format=fmt)

            if buf.tell() <= MAX_IMAGE_BYTES:
                logger.info(
                    f"[Vision] 縮圖成功: {img.width}x{img.height} → "
                    f"{new_w}x{new_h} ({buf.tell()/1024:.0f}KB)"
                )
                return buf.getvalue()

        logger.warning("[Vision] 縮圖後仍超過大小限制")
        return None

    except ImportError:
        logger.info("[Vision] Pillow 未安裝，無法縮圖")
        return None
    except Exception as e:
        logger.warning(f"[Vision] 縮圖失敗: {e}")
        return None
