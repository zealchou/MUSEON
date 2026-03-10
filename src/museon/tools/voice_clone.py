"""Voice Cloning via XTTS v2 Docker Service -- MUSEON Phase 4 EXT-06.

透過 XTTS v2 Docker 服務進行語音合成與聲音克隆：
- text-to-speech（支援中文）
- 聲音克隆（reference audio → voice profile）
- 情緒映射（文字情緒 → 語速/語調參數）
- 健康檢查（XTTS Docker 服務可用性）

依賴：
- aiohttp（async HTTP 呼叫）
- XTTS v2 Docker service（預設 http://127.0.0.1:8020）

設計原則：
- 文字長度限制保護（MAX_TEXT_LENGTH）
- 所有外部呼叫 try/except + graceful degradation
- EventBus 整合（VOICE_SYNTHESIZED）
"""

from __future__ import annotations

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

MAX_TEXT_LENGTH = 1000

EMOTION_MAP: Dict[str, Dict[str, Any]] = {
    "neutral": {
        "speed": 1.0,
        "temperature": 0.75,
        "description": "中性語調",
    },
    "happy": {
        "speed": 1.1,
        "temperature": 0.85,
        "description": "開心、活潑",
    },
    "sad": {
        "speed": 0.85,
        "temperature": 0.65,
        "description": "悲傷、低沉",
    },
    "angry": {
        "speed": 1.15,
        "temperature": 0.9,
        "description": "憤怒、激動",
    },
    "gentle": {
        "speed": 0.9,
        "temperature": 0.7,
        "description": "溫柔、輕聲",
    },
    "excited": {
        "speed": 1.2,
        "temperature": 0.9,
        "description": "興奮、激昂",
    },
    "serious": {
        "speed": 0.95,
        "temperature": 0.7,
        "description": "嚴肅、正式",
    },
}

# EventBus event name
VOICE_SYNTHESIZED = "VOICE_SYNTHESIZED"

# ═══════════════════════════════════════
# Lazy import aiohttp
# ═══════════════════════════════════════

try:
    import aiohttp
    _HAS_AIOHTTP = True
except ImportError:
    aiohttp = None  # type: ignore[assignment]
    _HAS_AIOHTTP = False


class VoiceCloner:
    """XTTS v2 語音合成與克隆器.

    Args:
        xtts_url: XTTS Docker 服務 URL
        event_bus: EventBus 實例
        output_dir: 語音檔案儲存目錄（預設 data/generated_voices）
    """

    def __init__(
        self,
        xtts_url: str = "http://127.0.0.1:8020",
        event_bus: Any = None,
        output_dir: Optional[str] = None,
    ) -> None:
        self._xtts_url = xtts_url.rstrip("/")
        self._event_bus = event_bus

        museon_home = os.getenv("MUSEON_HOME", str(Path.home() / "MUSEON"))
        self._output_dir = Path(
            output_dir
            or os.path.join(museon_home, "data", "generated_voices")
        )
        self._output_dir.mkdir(parents=True, exist_ok=True)

        # Voice profiles: profile_name -> {reference_audio, created_at}
        self._profiles: Dict[str, Dict] = {}
        self._load_profiles()

    # ─── Text-to-Speech ──────────────────

    async def synthesize(
        self,
        text: str,
        speaker_wav: Optional[str] = None,
        language: str = "zh",
        emotion: Optional[str] = None,
    ) -> Dict:
        """文字轉語音.

        Args:
            text: 要合成的文字（最長 MAX_TEXT_LENGTH 字元）
            speaker_wav: 參考語音檔路徑（用於聲音克隆）
            language: 語言代碼（zh, en, ja, ko 等）
            emotion: 情緒標籤（見 EMOTION_MAP），影響語速/語調

        Returns:
            metadata dict，含 file_path, duration_estimate 等。
            失敗時含 error 欄位。
        """
        if not _HAS_AIOHTTP:
            return {"error": "aiohttp 未安裝"}

        # 文字長度檢查
        if len(text) > MAX_TEXT_LENGTH:
            return {
                "error": (
                    f"文字長度 {len(text)} 超過上限 "
                    f"{MAX_TEXT_LENGTH}"
                )
            }

        if not text.strip():
            return {"error": "文字不可為空"}

        # 情緒映射
        style_params = self._map_emotion(emotion or "neutral")

        url = f"{self._xtts_url}/tts_to_audio"
        payload: Dict[str, Any] = {
            "text": text,
            "language": language,
            "speed": style_params.get("speed", 1.0),
            "temperature": style_params.get("temperature", 0.75),
        }
        if speaker_wav and Path(speaker_wav).exists():
            payload["speaker_wav"] = speaker_wav

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(
                            f"[VoiceCloner] XTTS API error "
                            f"{resp.status}: {error_text[:200]}"
                        )
                        return {
                            "error": f"XTTS HTTP {resp.status}",
                            "detail": error_text[:200],
                        }

                    # XTTS 回傳 wav 二進位
                    content_type = resp.content_type or ""
                    audio_data = await resp.read()

            if not audio_data:
                return {"error": "XTTS 回傳空白音訊"}

            # 儲存檔案
            metadata = self._save_audio(
                audio_data, text, language, speaker_wav, emotion,
            )

            # 發布 EventBus 事件
            try:
                if self._event_bus:
                    self._event_bus.publish(VOICE_SYNTHESIZED, metadata)
            except Exception as e:
                logger.debug(
                    f"[VoiceCloner] event_bus publish error: {e}"
                )

            logger.info(
                f"[VoiceCloner] synthesized: "
                f"{metadata.get('file_path', '?')}"
            )
            return metadata

        except Exception as e:
            logger.error(f"[VoiceCloner] synthesize failed: {e}")
            return {"error": str(e)}

    # ─── Voice Clone (Profile) ───────────

    async def clone_voice(self, reference_audio: str) -> str:
        """註冊聲音設定檔.

        將參考音檔複製到 profiles 目錄，供後續 synthesize 使用。

        Args:
            reference_audio: 參考語音檔路徑（wav/mp3）

        Returns:
            profile_name（唯一識別碼），失敗時回傳空字串。
        """
        src = Path(reference_audio)
        if not src.exists():
            logger.error(
                f"[VoiceCloner] reference audio not found: "
                f"{reference_audio}"
            )
            return ""

        profiles_dir = self._output_dir / "_profiles"
        profiles_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now(TZ8)
        profile_name = f"voice_{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        ext = src.suffix or ".wav"
        dest = profiles_dir / f"{profile_name}{ext}"

        try:
            dest.write_bytes(src.read_bytes())

            self._profiles[profile_name] = {
                "reference_audio": str(dest),
                "original_path": str(src),
                "created_at": now.isoformat(),
            }
            self._save_profiles()

            logger.info(
                f"[VoiceCloner] voice profile registered: "
                f"{profile_name}"
            )
            return profile_name

        except Exception as e:
            logger.error(f"[VoiceCloner] clone_voice failed: {e}")
            return ""

    def get_profile_audio(self, profile_name: str) -> Optional[str]:
        """取得聲音設定檔的參考音檔路徑.

        Args:
            profile_name: 設定檔名稱

        Returns:
            音檔路徑，不存在則 None。
        """
        info = self._profiles.get(profile_name)
        if info:
            return info.get("reference_audio")
        return None

    def list_profiles(self) -> List[Dict]:
        """列出所有聲音設定檔."""
        return [
            {"profile_name": name, **info}
            for name, info in self._profiles.items()
        ]

    # ─── Emotion Mapping ─────────────────

    def _map_emotion(self, text_or_label: str) -> Dict:
        """映射情緒標籤到語音風格參數.

        如果輸入是已知情緒標籤，直接取用；否則透過簡易關鍵字匹配。

        Args:
            text_or_label: 情緒標籤或文字內容

        Returns:
            風格參數 dict（speed, temperature）。
        """
        # 直接標籤匹配
        if text_or_label in EMOTION_MAP:
            return dict(EMOTION_MAP[text_or_label])

        # 簡易中文關鍵字匹配
        label = text_or_label.lower()
        keyword_map = {
            "happy": ["開心", "高興", "快樂", "喜", "哈哈", "happy", "joy"],
            "sad": ["難過", "悲傷", "哭", "sad", "sorrow", "遺憾"],
            "angry": ["生氣", "憤怒", "怒", "angry", "mad"],
            "gentle": ["溫柔", "輕聲", "gentle", "soft"],
            "excited": ["興奮", "激動", "excited", "amazing"],
            "serious": ["嚴肅", "正式", "serious", "formal"],
        }

        for emotion, keywords in keyword_map.items():
            for kw in keywords:
                if kw in label:
                    return dict(EMOTION_MAP[emotion])

        # 預設中性
        return dict(EMOTION_MAP["neutral"])

    # ─── Health Check ────────────────────

    async def check_health(self) -> bool:
        """檢查 XTTS 服務是否可用.

        Returns:
            True 表示服務正常。
        """
        if not _HAS_AIOHTTP:
            return False

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self._xtts_url}/",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    return resp.status in (200, 404)
        except Exception as e:
            logger.debug(f"[VoiceCloner] health check failed: {e}")
            return False

    # ─── Internal Helpers ────────────────

    def _save_audio(
        self,
        audio_data: bytes,
        text: str,
        language: str,
        speaker_wav: Optional[str],
        emotion: Optional[str],
    ) -> Dict:
        """儲存音訊檔案 + metadata.

        Returns:
            metadata dict
        """
        now = datetime.now(TZ8)
        ts = now.strftime("%Y%m%d_%H%M%S")
        uid = uuid.uuid4().hex[:8]
        filename = f"{ts}_{uid}.wav"

        # 儲存音訊
        file_path = self._output_dir / filename
        file_path.write_bytes(audio_data)

        # 預估時長（粗略：wav 16kHz 16bit mono ~ 32KB/s）
        duration_estimate = round(len(audio_data) / 32000, 1)

        metadata = {
            "file_path": str(file_path),
            "filename": filename,
            "text": text[:100],  # 截斷保存
            "text_length": len(text),
            "language": language,
            "emotion": emotion or "neutral",
            "speaker_wav": speaker_wav,
            "duration_estimate_sec": duration_estimate,
            "file_size_bytes": len(audio_data),
            "generated_at": now.isoformat(),
        }

        # 儲存 metadata JSON
        meta_dir = self._output_dir / "_meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        meta_path = meta_dir / f"{ts}_{uid}.json"
        meta_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return metadata

    # ─── Profile Persistence ─────────────

    def _profiles_path(self) -> Path:
        """Voice profiles JSON 路徑."""
        return self._output_dir / "_profiles" / "profiles.json"

    def _load_profiles(self) -> None:
        """從檔案載入 voice profiles."""
        path = self._profiles_path()
        if path.exists():
            try:
                self._profiles = json.loads(
                    path.read_text(encoding="utf-8")
                )
            except Exception as e:
                logger.error(
                    f"[VoiceCloner] load profiles failed: {e}"
                )
                self._profiles = {}

    def _save_profiles(self) -> None:
        """將 voice profiles 寫入檔案."""
        path = self._profiles_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    self._profiles, ensure_ascii=False, indent=2,
                ),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(
                f"[VoiceCloner] save profiles failed: {e}"
            )
