import asyncio
import logging
import time

from aiohttp import web

from .cards import Card, Stats, format_metrics, render_hook
from .companion import Companion
from .config import Config
from .device import Indicator
from .i18n import STATUS_ONLINE, get_strings

log = logging.getLogger("indicator.app")


class Bridge:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.strings = get_strings(cfg.lang)
        self.device = Indicator(cfg.host, cfg.noise_psk, on_button=self.on_button)
        self.queue: asyncio.Queue[Card] = asyncio.Queue(maxsize=8)
        self.stats = Stats()
        self.last_event = 0.0
        self.last_companion = 0.0
        self.companion = Companion(
            cfg.companion_base_url, cfg.companion_model, cfg.companion_api_key, cfg.lang
        )

    # ---- 入队(满则丢最旧的,保证最新状态优先) ----
    def enqueue(self, card: Card) -> None:
        if self.queue.full():
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            self.queue.put_nowait(card)
        except asyncio.QueueFull:
            pass

    async def on_hook(self, event: str, payload: dict) -> None:
        self.stats.observe(event, payload)
        card = render_hook(event, payload, self.stats, self.strings)
        if card:
            self.last_event = time.monotonic()
            self.enqueue(card)

    async def on_button(self) -> None:
        log.info("button pressed -> companion card")
        self.last_companion = time.monotonic()
        card = await self.companion.generate(trigger="button")
        s = self.strings
        self.enqueue(card or Card(s.mood_hello, s.title_button_tap, s.body_companion_offline, ""))

    # ---- 后台任务 ----
    async def _pusher(self) -> None:
        while True:
            card = await self.queue.get()
            await self.device.show_card(card)

    async def _companion_loop(self) -> None:
        while True:
            await asyncio.sleep(15)
            now = time.monotonic()
            idle = self.last_event == 0.0 or (now - self.last_event) >= self.cfg.idle_seconds
            due = (now - self.last_companion) >= self.cfg.companion_interval
            if idle and due:
                self.last_companion = now
                card = await self.companion.generate(trigger="idle")
                if card:
                    self.enqueue(card)

    # ---- HTTP(接收 Claude Code hook 事件) ----
    async def _http_hook(self, request: web.Request) -> web.Response:
        event = request.match_info["event"]
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        try:
            await self.on_hook(event, payload)
        except Exception:
            log.exception("on_hook failed for %s", event)
        return web.Response(status=204)

    async def _http_metrics(self, request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        try:
            text = format_metrics(payload)
            if text:
                await self.device.set_metrics(text)
        except Exception:
            log.exception("metrics handler failed")
        return web.Response(status=204)

    async def run(self) -> None:
        app = web.Application()
        app.router.add_post("/hook/{event}", self._http_hook)
        app.router.add_post("/metrics", self._http_metrics)
        app.router.add_get("/healthz", lambda r: web.json_response({"ok": True}))
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, self.cfg.http_host, self.cfg.http_port)
        await site.start()
        log.info("hook endpoint: http://%s:%d/hook/<event>", self.cfg.http_host, self.cfg.http_port)

        await self.device.start()
        s = self.strings
        self.enqueue(Card(s.mood_online, s.title_bridge_up, s.body_waiting_cc, "", STATUS_ONLINE))

        await asyncio.gather(self._pusher(), self._companion_loop())
