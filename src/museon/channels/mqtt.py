"""MQTT Adapter for IoT Devices -- MUSEON Phase 4 EXT-02.

透過 MQTT 協議整合 IoT 裝置：
- 訂閱 MQTT topics（預設 museon/#）
- 接收感測器數據、裝置狀態
- 發送控制指令到 IoT 裝置
- EventBus 整合（IOT_EVENT_RECEIVED / IOT_COMMAND_SENT）

依賴：
- paho-mqtt（lazy import，未安裝時 graceful degradation）
- aiohttp 用於內部 HTTP 回報（選用）

設計原則：
- MQTT callback 為同步，收到訊息後透過 asyncio 佇列橋接 async 世界
- 所有外部操作 try/except
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

# ═══════════════════════════════════════
# Lazy import paho-mqtt
# ═══════════════════════════════════════

try:
    import paho.mqtt.client as paho_mqtt
    _HAS_PAHO = True
except ImportError:
    paho_mqtt = None  # type: ignore[assignment]
    _HAS_PAHO = False

# EventBus event names
IOT_EVENT_RECEIVED = "IOT_EVENT_RECEIVED"
IOT_COMMAND_SENT = "IOT_COMMAND_SENT"


class MQTTAdapter:
    """MQTT 通道轉接器，橋接 IoT 裝置與 MUSEON 事件匯流排.

    Args:
        config: MQTT 設定字典，支援以下欄位：
            - broker (str): MQTT Broker 位址（預設 127.0.0.1）
            - port (int): MQTT Broker 端口（預設 1883）
            - topics (List[str]): 訂閱 topics（預設 ["museon/#"]）
            - username (str): MQTT 使用者名稱（選用）
            - password (str): MQTT 密碼（選用）
            - client_id (str): MQTT Client ID（預設 museon-iot）
            - keepalive (int): 心跳間隔秒數（預設 60）
            - qos (int): 預設 QoS 等級（0, 1, 2）
        event_bus: EventBus 實例
    """

    def __init__(
        self,
        config: Dict,
        event_bus: Any = None,
    ) -> None:
        self._broker = config.get("broker", "127.0.0.1")
        self._port = config.get("port", 1883)
        self._topics: List[str] = config.get("topics", ["museon/#"])
        self._username = config.get("username")
        self._password = config.get("password")
        self._client_id = config.get("client_id", "museon-iot")
        self._keepalive = config.get("keepalive", 60)
        self._qos = config.get("qos", 1)
        self._event_bus = event_bus

        self._client: Any = None  # paho.mqtt.client.Client
        self._connected = False
        self._running = False

        # 非同步訊息佇列（供 async 消費者使用）
        self._message_queue: asyncio.Queue = asyncio.Queue()

        # 已註冊裝置 device_id -> {topic, last_seen, status}
        self._devices: Dict[str, Dict] = {}

        # 訊息統計
        self._stats = {
            "messages_received": 0,
            "commands_sent": 0,
            "errors": 0,
            "started_at": None,
        }

    # ─── Lifecycle ───────────────────────

    async def start(self) -> bool:
        """啟動 MQTT 連線並訂閱 topics.

        Returns:
            True 表示成功連線，False 表示失敗。
        """
        if not _HAS_PAHO:
            logger.error(
                "[MQTTAdapter] paho-mqtt 未安裝。"
                "請執行 pip install paho-mqtt"
            )
            return False

        if self._running:
            logger.warning("[MQTTAdapter] already running")
            return True

        try:
            self._client = paho_mqtt.Client(
                client_id=self._client_id,
                protocol=paho_mqtt.MQTTv311,
            )

            # 設定回呼
            self._client.on_connect = self._on_connect
            self._client.on_disconnect = self._on_disconnect
            self._client.on_message = self._on_message

            # 認證
            if self._username:
                self._client.username_pw_set(
                    self._username, self._password or "",
                )

            # 連線（非阻塞 loop_start）
            self._client.connect_async(
                self._broker, self._port, self._keepalive,
            )
            self._client.loop_start()

            self._running = True
            self._stats["started_at"] = datetime.now(TZ8).isoformat()
            logger.info(
                f"[MQTTAdapter] connecting to {self._broker}:{self._port}"
            )
            return True

        except Exception as e:
            logger.error(f"[MQTTAdapter] start failed: {e}")
            self._stats["errors"] += 1
            return False

    async def stop(self) -> None:
        """斷開 MQTT 連線."""
        if not self._running or not self._client:
            return

        try:
            self._client.loop_stop()
            self._client.disconnect()
        except Exception as e:
            logger.error(f"[MQTTAdapter] stop error: {e}")
        finally:
            self._running = False
            self._connected = False
            logger.info("[MQTTAdapter] stopped")

    # ─── Paho Callbacks (sync) ───────────

    def _on_connect(
        self,
        client: Any,
        userdata: Any,
        flags: Any,
        rc: int,
    ) -> None:
        """MQTT 連線成功回呼."""
        if rc == 0:
            self._connected = True
            logger.info(
                f"[MQTTAdapter] connected to {self._broker}:{self._port}"
            )
            # 訂閱 topics
            for topic in self._topics:
                try:
                    client.subscribe(topic, qos=self._qos)
                    logger.info(f"[MQTTAdapter] subscribed: {topic}")
                except Exception as e:
                    logger.error(
                        f"[MQTTAdapter] subscribe {topic} failed: {e}"
                    )
        else:
            rc_names = {
                1: "incorrect protocol",
                2: "invalid client id",
                3: "server unavailable",
                4: "bad credentials",
                5: "not authorized",
            }
            reason = rc_names.get(rc, f"unknown rc={rc}")
            logger.error(f"[MQTTAdapter] connection refused: {reason}")
            self._stats["errors"] += 1

    def _on_disconnect(
        self,
        client: Any,
        userdata: Any,
        rc: int,
    ) -> None:
        """MQTT 斷線回呼."""
        self._connected = False
        if rc != 0:
            logger.warning(
                f"[MQTTAdapter] unexpected disconnect (rc={rc}), "
                "will auto-reconnect"
            )

    def _on_message(
        self,
        client: Any,
        userdata: Any,
        msg: Any,
    ) -> None:
        """MQTT 訊息回呼（同步）.

        解析 payload 並放入 async 佇列 + 發布 EventBus 事件。
        """
        self._stats["messages_received"] += 1
        now = datetime.now(TZ8)

        try:
            topic = msg.topic
            raw_payload = msg.payload.decode("utf-8", errors="replace")

            # 嘗試 JSON 解析
            try:
                payload = json.loads(raw_payload)
            except (json.JSONDecodeError, ValueError):
                payload = {"raw": raw_payload}

            event_data = {
                "topic": topic,
                "payload": payload,
                "qos": msg.qos,
                "retain": msg.retain,
                "received_at": now.isoformat(),
            }

            # 提取 device_id（from topic 或 payload）
            device_id = self._extract_device_id(topic, payload)
            if device_id:
                event_data["device_id"] = device_id
                self._devices[device_id] = {
                    "topic": topic,
                    "last_seen": now.isoformat(),
                    "status": "online",
                }

            # 放入 async 佇列
            try:
                self._message_queue.put_nowait(event_data)
            except asyncio.QueueFull:
                logger.warning("[MQTTAdapter] message queue full, dropping")

            # 發布 EventBus 事件
            try:
                if self._event_bus:
                    self._event_bus.publish(IOT_EVENT_RECEIVED, event_data)
            except Exception as e:
                logger.debug(f"[MQTTAdapter] event_bus publish error: {e}")

            logger.debug(
                f"[MQTTAdapter] message: {topic} "
                f"(device={device_id or 'unknown'})"
            )

        except Exception as e:
            logger.error(f"[MQTTAdapter] _on_message error: {e}")
            self._stats["errors"] += 1

    # ─── Publish / Command ───────────────

    async def publish(self, topic: str, payload: Dict) -> bool:
        """發布 MQTT 訊息.

        Args:
            topic: MQTT topic
            payload: 訊息內容（dict，會序列化為 JSON）

        Returns:
            True 表示成功發布。
        """
        if not self._client or not self._connected:
            logger.warning("[MQTTAdapter] not connected, cannot publish")
            return False

        try:
            message = json.dumps(payload, ensure_ascii=False)
            info = self._client.publish(
                topic, message.encode("utf-8"), qos=self._qos,
            )
            if info.rc == 0:
                logger.debug(f"[MQTTAdapter] published to {topic}")
                return True
            logger.warning(
                f"[MQTTAdapter] publish failed: rc={info.rc}"
            )
            return False

        except Exception as e:
            logger.error(f"[MQTTAdapter] publish error: {e}")
            self._stats["errors"] += 1
            return False

    async def send_command(
        self,
        device_id: str,
        command: str,
        params: Optional[Dict] = None,
    ) -> bool:
        """發送 IoT 控制指令到裝置.

        指令格式：museon/command/{device_id}

        Args:
            device_id: 目標裝置 ID
            command: 指令名稱（如 "turn_on", "set_temp"）
            params: 指令參數

        Returns:
            True 表示成功發送。
        """
        topic = f"museon/command/{device_id}"
        payload = {
            "command": command,
            "params": params or {},
            "timestamp": datetime.now(TZ8).isoformat(),
            "source": "museon",
        }

        success = await self.publish(topic, payload)

        if success:
            self._stats["commands_sent"] += 1

            # 發布 EventBus 事件
            try:
                if self._event_bus:
                    self._event_bus.publish(IOT_COMMAND_SENT, {
                        "device_id": device_id,
                        "command": command,
                        "params": params or {},
                        "timestamp": datetime.now(TZ8).isoformat(),
                    })
            except Exception as e:
                logger.debug(f"[MQTTAdapter] event_bus publish error: {e}")

            logger.info(
                f"[MQTTAdapter] command sent: {device_id}/{command}"
            )

        return success

    # ─── Async Message Consumer ──────────

    async def get_message(self, timeout: float = 5.0) -> Optional[Dict]:
        """從訊息佇列取得下一則 MQTT 訊息.

        Args:
            timeout: 等待秒數

        Returns:
            訊息 dict，逾時回傳 None。
        """
        try:
            return await asyncio.wait_for(
                self._message_queue.get(), timeout=timeout,
            )
        except asyncio.TimeoutError:
            return None

    # ─── Device Registry ─────────────────

    def list_devices(self) -> List[Dict]:
        """列出已知 IoT 裝置."""
        result = []
        for device_id, info in self._devices.items():
            result.append({"device_id": device_id, **info})
        return result

    def get_device(self, device_id: str) -> Optional[Dict]:
        """取得單一裝置資訊."""
        info = self._devices.get(device_id)
        if info:
            return {"device_id": device_id, **info}
        return None

    # ─── Status ──────────────────────────

    def get_status(self) -> Dict[str, Any]:
        """取得 MQTT 轉接器狀態."""
        return {
            "running": self._running,
            "connected": self._connected,
            "broker": f"{self._broker}:{self._port}",
            "topics": self._topics,
            "devices_count": len(self._devices),
            "queue_size": self._message_queue.qsize(),
            "stats": dict(self._stats),
            "paho_installed": _HAS_PAHO,
        }

    @property
    def is_connected(self) -> bool:
        """是否已連線到 MQTT Broker."""
        return self._connected

    # ─── Helpers ─────────────────────────

    @staticmethod
    def _extract_device_id(
        topic: str,
        payload: Dict,
    ) -> Optional[str]:
        """從 topic 或 payload 提取 device_id.

        支援格式：
        - museon/devices/{device_id}/...
        - museon/sensor/{device_id}/...
        - payload 中的 "device_id" 欄位
        """
        # 從 payload 提取
        if isinstance(payload, dict) and "device_id" in payload:
            return str(payload["device_id"])

        # 從 topic 提取
        parts = topic.split("/")
        if len(parts) >= 3 and parts[0] == "museon":
            if parts[1] in ("devices", "sensor", "actuator", "status"):
                return parts[2]

        return None
