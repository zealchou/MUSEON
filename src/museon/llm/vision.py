"""Vision 工具模組 — 將圖片檔案轉為 Anthropic Vision API content block.

單一職責：讀取圖片 → 驗證格式/大小 → base64 編碼 → 回傳 content block。
不涉及任何 Brain/LLM 邏輯。
"""

import base64
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# 常數
# ═══════════════════════════════════════════

# Anthropic Vision API 支援的 MIME types
SUPPORTED_MEDIA_TYPES = {
    "image/jpeg", "image/png", "image/gif", "image/webp",
}

# 副檔名 → MIME type 對照（metadata 缺 mime_type 時 fallback）
EXT_TO_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

# Anthropic API 建議的最大圖片大小（bytes）
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB


# ═══════════════════════════════════════════
# 核心函數
# ═══════════════════════════════════════════


def prepare_image_block(file_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """從 file_info dict 準備一個 Anthropic Vision image content block.

    Args:
        file_info: telegram._download_telegram_file() 回傳的 dict
                   keys: local_path, file_name, file_size, mime_type, file_id

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
    mime_type = file_info.get("mime_type") or ""
    if not mime_type or mime_type not in SUPPORTED_MEDIA_TYPES:
        mime_type = EXT_TO_MIME.get(path.suffix.lower(), "")
    if mime_type not in SUPPORTED_MEDIA_TYPES:
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


def build_vision_content(
    text: str,
    file_info: Optional[Dict[str, Any]],
) -> Union[str, List[Dict[str, Any]]]:
    """構建可能包含圖片的 user message content.

    若 file_info 有效且為支援的圖片格式，回傳 List[Dict]（multimodal content blocks）。
    否則回傳原始 text str（向後相容）。

    Args:
        text: 原始使用者訊息文字
        file_info: metadata["file"] 或 None

    Returns:
        str（純文字，向後相容）或 List[Dict]（multimodal blocks）
    """
    if not file_info:
        return text

    image_block = prepare_image_block(file_info)
    if image_block is None:
        return text

    # 組合：text block + image block
    blocks: List[Dict[str, Any]] = []
    if text and text.strip():
        blocks.append({"type": "text", "text": text})
    blocks.append(image_block)
    return blocks


# ═══════════════════════════════════════════
# 內部工具
# ═══════════════════════════════════════════


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
                # JPEG 不支援 alpha 通道，先轉 RGB
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
