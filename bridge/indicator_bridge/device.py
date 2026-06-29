import asyncio
import logging

from aioesphomeapi import APIClient, ReconnectLogic
from zeroconf.asyncio import AsyncZeroconf

from .cards import Card

log = logging.getLogger("indicator.device")


class Indicator:
    """维持与 Indicator 的 ESPHome 原生 API 长连接,推送卡片、监听按钮。"""

    def __init__(self, host: str, noise_psk: str, on_button=None) -> None:
        self.host = host
        self.noise_psk = noise_psk
        self.on_button = on_button
        self._connected = asyncio.Event()
        self._show_card = None
        self._set_metrics = None
        self._button_keys: set[int] = set()
        self._client: APIClient | None = None
        self._azc: AsyncZeroconf | None = None
        self._reconnect: ReconnectLogic | None = None

    async def start(self) -> None:
        self._azc = AsyncZeroconf()
        self._client = APIClient(
            self.host, 6053, None,
            noise_psk=self.noise_psk,
            zeroconf_instance=self._azc.zeroconf,
        )
        self._reconnect = ReconnectLogic(
            client=self._client,
            on_connect=self._on_connect,
            on_disconnect=self._on_disconnect,
            zeroconf_instance=self._azc.zeroconf,
        )
        await self._reconnect.start()
        log.info("connecting to %s ...", self.host)

    async def _on_connect(self) -> None:
        try:
            entities, services = await self._client.list_entities_services()
            self._show_card = next((s for s in services if s.name == "show_card"), None)
            self._set_metrics = next((s for s in services if s.name == "set_metrics"), None)
            self._button_keys = {
                e.key for e in entities
                if getattr(e, "object_id", "") == "refresh_button"
                or getattr(e, "name", "") == "Refresh Button"
            }
            self._client.subscribe_states(self._on_state)
            self._connected.set()
            log.info(
                "connected (show_card=%s, button_keys=%s)",
                bool(self._show_card), self._button_keys or "none",
            )
        except Exception:
            log.exception("on_connect setup failed")

    async def _on_disconnect(self, expected: bool) -> None:
        self._connected.clear()
        log.warning("disconnected (expected=%s)", expected)

    def _on_state(self, state) -> None:
        key = getattr(state, "key", None)
        if key in self._button_keys and getattr(state, "state", False):
            if self.on_button:
                asyncio.get_running_loop().create_task(self._safe_button())

    async def _safe_button(self) -> None:
        try:
            await self.on_button()
        except Exception:
            log.exception("on_button handler failed")

    async def show_card(self, card: Card) -> None:
        # 未连接时直接丢弃,绝不阻塞调用方(hook 推送链路)
        if not self._connected.is_set() or not self._show_card:
            log.debug("drop card (device not connected)")
            return
        try:
            res = self._client.execute_service(self._show_card, card.to_data())
            if asyncio.iscoroutine(res):
                await res
        except Exception:
            log.exception("execute_service show_card failed")

    async def set_metrics(self, text: str) -> None:
        if not self._connected.is_set() or not self._set_metrics:
            return
        try:
            res = self._client.execute_service(self._set_metrics, {"metrics": text})
            if asyncio.iscoroutine(res):
                await res
        except Exception:
            log.exception("execute_service set_metrics failed")
