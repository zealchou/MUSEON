"""Image Generation via Stability API / SDXL -- MUSEON Phase 4 EXT-05.

透過 Stability AI REST API 生成圖片：
- text-to-image（文字轉圖片）
- image-to-image（圖片轉圖片）
- 自動存檔到 data/generated_images/
- EventBus 整合（IMAGE_GENERATED）

依賴：
- aiohttp（async HTTP 呼叫）
- STABILITY_API_KEY 環境變數

設計原則：
- 每日生成上限保護（MAX_DAILY_GENERATIONS）
- 所有外部呼叫 try/except + graceful degradation
"""

from __future__ import annotations

import base64
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

# ═══════════════════════════════════════
# Constants
# ═══════════════════════════════════════

SUPPORTED_STYLES = [
    "photographic",
    "analog-film",
    "anime",
    "cinematic",
    "comic-book",
    "digital-art",
    "enhance",
    "fantasy-art",
    "isometric",
    "line-art",
    "low-poly",
    "neon-punk",
    "origami",
    "pixel-art",
    "3d-model",
]

MAX_DAILY_GENERATIONS = 50

# EventBus event name
IMAGE_GENERATED = "IMAGE_GENERATED"

# ═══════════════════════════════════════
# Lazy import aiohttp
# ═══════════════════════════════════════

try:
    import aiohttp
    _HAS_AIOHTTP = True
except ImportError:
    aiohttp = None  # type: ignore[assignment]
    _HAS_AIOHTTP = False


class ImageGenerator:
    """Stability AI 圖片生成器.

    Args:
        api_key: Stability API Key（也可透過 STABILITY_API_KEY 環境變數）
        api_url: Stability API 基底 URL
        event_bus: EventBus 實例
        output_dir: 圖片儲存目錄（預設 data/generated_images）
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: str = "https://api.stability.ai",
        event_bus: Any = None,
        output_dir: Optional[str] = None,
    ) -> None:
        self._api_key = api_key or os.getenv("STABILITY_API_KEY", "")
        self._api_url = api_url.rstrip("/")
        self._event_bus = event_bus

        museon_home = os.getenv("MUSEON_HOME", str(Path.home() / "MUSEON"))
        self._output_dir = Path(
            output_dir or os.path.join(museon_home, "data", "generated_images")
        )
        self._output_dir.mkdir(parents=True, exist_ok=True)

        # 每日生成計數（簡易限流）
        self._daily_count = 0
        self._daily_date: Optional[str] = None

    # ─── Text-to-Image ───────────────────

    async def generate(
        self,
        prompt: str,
        width: int = 1024,
        height: int = 1024,
        style: str = "photographic",
        model: str = "stable-diffusion-xl-1024-v1-0",
        negative_prompt: str = "",
        cfg_scale: float = 7.0,
        steps: int = 30,
        seed: int = 0,
    ) -> Dict:
        """文字轉圖片.

        Args:
            prompt: 圖片描述文字
            width: 圖片寬度（px）
            height: 圖片高度（px）
            style: 風格預設（見 SUPPORTED_STYLES）
            model: 模型名稱
            negative_prompt: 負面提示詞
            cfg_scale: CFG 引導強度
            steps: 推理步數
            seed: 隨機種子（0 = 隨機）

        Returns:
            metadata dict，含 file_path, prompt, dimensions 等。
            失敗時含 error 欄位。
        """
        if not self._check_prerequisites():
            return {"error": "前置條件不滿足（aiohttp 或 API Key）"}

        if not self._check_daily_limit():
            return {
                "error": f"已達每日生成上限 ({MAX_DAILY_GENERATIONS})"
            }

        url = (
            f"{self._api_url}/v1/generation/{model}/text-to-image"
        )
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "text_prompts": [
                {"text": prompt, "weight": 1.0},
            ],
            "cfg_scale": cfg_scale,
            "width": width,
            "height": height,
            "steps": steps,
            "style_preset": style if style in SUPPORTED_STYLES else "photographic",
            "samples": 1,
        }
        if negative_prompt:
            payload["text_prompts"].append(
                {"text": negative_prompt, "weight": -1.0}
            )
        if seed > 0:
            payload["seed"] = seed

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(
                            f"[ImageGen] API error {resp.status}: "
                            f"{error_text[:200]}"
                        )
                        return {
                            "error": f"API HTTP {resp.status}",
                            "detail": error_text[:200],
                        }

                    data = await resp.json()

            # 解碼並儲存圖片
            artifacts = data.get("artifacts", [])
            if not artifacts:
                return {"error": "API 未回傳圖片"}

            image_b64 = artifacts[0].get("base64", "")
            if not image_b64:
                return {"error": "API 回傳空白圖片"}

            metadata = self._save_image(
                image_b64, prompt, width, height, style, model,
            )

            self._increment_daily_count()

            # 發布 EventBus 事件
            try:
                if self._event_bus:
                    self._event_bus.publish(IMAGE_GENERATED, metadata)
            except Exception as e:
                logger.debug(f"[ImageGen] event_bus publish error: {e}")

            logger.info(
                f"[ImageGen] generated: {metadata.get('file_path', '?')}"
            )
            return metadata

        except Exception as e:
            logger.error(f"[ImageGen] generate failed: {e}")
            return {"error": str(e)}

    # ─── Image-to-Image ──────────────────

    async def generate_from_image(
        self,
        image_path: str,
        prompt: str,
        strength: float = 0.7,
        model: str = "stable-diffusion-xl-1024-v1-0",
    ) -> Dict:
        """圖片轉圖片（img2img）.

        Args:
            image_path: 來源圖片路徑
            prompt: 轉換描述文字
            strength: 轉換強度（0.0 ~ 1.0，越高越不像原圖）
            model: 模型名稱

        Returns:
            metadata dict，失敗時含 error 欄位。
        """
        if not self._check_prerequisites():
            return {"error": "前置條件不滿足（aiohttp 或 API Key）"}

        if not self._check_daily_limit():
            return {
                "error": f"已達每日生成上限 ({MAX_DAILY_GENERATIONS})"
            }

        src = Path(image_path)
        if not src.exists():
            return {"error": f"來源圖片不存在: {image_path}"}

        url = (
            f"{self._api_url}/v1/generation/{model}/image-to-image"
        )
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        }

        try:
            form_data = aiohttp.FormData()
            form_data.add_field(
                "init_image",
                open(image_path, "rb"),
                filename=src.name,
                content_type="image/png",
            )
            form_data.add_field(
                "text_prompts[0][text]", prompt,
            )
            form_data.add_field(
                "text_prompts[0][weight]", "1.0",
            )
            form_data.add_field(
                "image_strength", str(strength),
            )

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    data=form_data,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(
                            f"[ImageGen] img2img API error {resp.status}: "
                            f"{error_text[:200]}"
                        )
                        return {
                            "error": f"API HTTP {resp.status}",
                            "detail": error_text[:200],
                        }

                    data = await resp.json()

            artifacts = data.get("artifacts", [])
            if not artifacts:
                return {"error": "API 未回傳圖片"}

            image_b64 = artifacts[0].get("base64", "")
            if not image_b64:
                return {"error": "API 回傳空白圖片"}

            metadata = self._save_image(
                image_b64, prompt, 0, 0, "img2img", model,
                source_image=image_path,
            )

            self._increment_daily_count()

            try:
                if self._event_bus:
                    self._event_bus.publish(IMAGE_GENERATED, metadata)
            except Exception as e:
                logger.debug(f"[ImageGen] event_bus publish error: {e}")

            logger.info(
                f"[ImageGen] img2img generated: "
                f"{metadata.get('file_path', '?')}"
            )
            return metadata

        except Exception as e:
            logger.error(f"[ImageGen] generate_from_image failed: {e}")
            return {"error": str(e)}

    # ─── Listing ─────────────────────────

    def list_generated(self, limit: int = 20) -> List[Dict]:
        """列出最近生成的圖片.

        Args:
            limit: 最多回傳數量

        Returns:
            圖片 metadata 列表（新的在前）。
        """
        meta_dir = self._output_dir / "_meta"
        if not meta_dir.exists():
            return []

        meta_files = sorted(
            meta_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        results: List[Dict] = []
        for mf in meta_files[:limit]:
            try:
                data = json.loads(mf.read_text(encoding="utf-8"))
                results.append(data)
            except Exception:
                continue

        return results

    # ─── Internal Helpers ────────────────

    def _check_prerequisites(self) -> bool:
        """檢查前置條件."""
        if not _HAS_AIOHTTP:
            logger.warning("[ImageGen] aiohttp 未安裝")
            return False
        if not self._api_key:
            logger.warning("[ImageGen] STABILITY_API_KEY 未設定")
            return False
        return True

    def _check_daily_limit(self) -> bool:
        """檢查每日生成限額."""
        today = datetime.now(TZ8).strftime("%Y-%m-%d")
        if self._daily_date != today:
            self._daily_date = today
            self._daily_count = 0
        return self._daily_count < MAX_DAILY_GENERATIONS

    def _increment_daily_count(self) -> None:
        """增加每日計數."""
        today = datetime.now(TZ8).strftime("%Y-%m-%d")
        if self._daily_date != today:
            self._daily_date = today
            self._daily_count = 0
        self._daily_count += 1

    def _save_image(
        self,
        image_b64: str,
        prompt: str,
        width: int,
        height: int,
        style: str,
        model: str,
        source_image: Optional[str] = None,
    ) -> Dict:
        """解碼 base64 並儲存圖片 + metadata.

        Returns:
            metadata dict
        """
        now = datetime.now(TZ8)
        ts = now.strftime("%Y%m%d_%H%M%S")
        uid = uuid.uuid4().hex[:8]
        filename = f"{ts}_{uid}.png"

        # 儲存圖片
        file_path = self._output_dir / filename
        file_path.write_bytes(base64.b64decode(image_b64))

        # 儲存 metadata
        metadata = {
            "file_path": str(file_path),
            "filename": filename,
            "prompt": prompt,
            "width": width,
            "height": height,
            "style": style,
            "model": model,
            "generated_at": now.isoformat(),
        }
        if source_image:
            metadata["source_image"] = source_image

        meta_dir = self._output_dir / "_meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        meta_path = meta_dir / f"{ts}_{uid}.json"
        meta_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return metadata
