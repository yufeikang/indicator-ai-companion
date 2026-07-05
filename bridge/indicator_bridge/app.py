import asyncio
import logging
import random
import time
from dataclasses import dataclass, field

from aiohttp import web

from .cards import (
    MAX_SLOTS,
    Card,
    Stats,
    format_metrics,
    event_payload,
    project_name,
    provider_name,
    render_hook,
    sanitize_text,
    session_key,
    sessions_args,
)
from .companion import Companion
from .config import Config
from .device import Indicator
from .i18n import STATUS_ONLINE, STATUS_WAIT, get_strings

log = logging.getLogger("indicator.app")

PIN_TTL = 45.0          # 手点某图标后,焦点钉在它身上的有效时长(秒)
SESSION_TTL = 1800.0    # 一个 session 多久无事件后从图标条移除(秒)
SAVER_LINE_TTL = 120.0  # 屏保期间俏皮话多久换一句(秒)

EVENT_ALIASES = {
    "SessionStart": "session-start",
    "SessionEnd": "session-end",
    "UserPromptSubmit": "user-prompt",
    "PreToolUse": "pre-tool",
    "PermissionRequest": "permission-request",
    "PostToolUse": "post-tool",
    "Notification": "notification",
    "Stop": "stop",
}


def normalize_event(event: str) -> str:
    return EVENT_ALIASES.get(event, event).strip().lower()


@dataclass
class SessionState:
    sid: str
    project: str = ""
    provider: str = "claude"
    card: Card | None = None
    status: str = ""
    stats: Stats = field(default_factory=Stats)
    first_seen: float = 0.0
    last_seen: float = 0.0


class Bridge:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.strings = get_strings(cfg.lang)
        self.device = Indicator(
            cfg.host, cfg.noise_psk,
            on_button=self.on_button,
            on_select=self.on_select,
            on_connect=self.on_connect,
            on_wake=self.on_wake,
        )
        self.sessions: dict[str, SessionState] = {}
        self.focused_sid: str | None = None
        self.pin_until = 0.0
        self.slot_order: list[str] = []     # 上次推送的槽位顺序(触摸 idx -> sid 的映射依据)
        self.idle_card: Card | None = None   # 无活跃 session 时详情区展示(伴侣卡/等待)
        self.last_event = 0.0
        self.last_companion = 0.0
        self.started_at = 0.0
        self.screensaver_on = False
        self.last_wake = 0.0
        self.last_saver_line = 0.0
        self.companion = Companion(
            cfg.companion_base_url, cfg.companion_model, cfg.companion_api_key, cfg.lang
        )
        self._lock = asyncio.Lock()
        # 去重缓存:与上次一致则跳过推送
        self._last_sessions_args: dict | None = None
        self._last_card_data: dict | None = None

    # ---- 焦点 / 图标条计算 ----
    def _active(self, now: float) -> list[SessionState]:
        """活跃(未过期)的 session,按显示顺序(出现先后)排好并限 MAX_SLOTS 个。"""
        alive = [s for s in self.sessions.values() if now - s.last_seen <= SESSION_TTL]
        # 先按最近活跃挑出要保留的若干个,再按首次出现排序 -> 槽位左右稳定不乱跳
        alive.sort(key=lambda s: s.last_seen, reverse=True)
        keep = alive[:MAX_SLOTS]
        keep.sort(key=lambda s: s.first_seen)
        return keep

    async def _push(self) -> None:
        """重算图标条与焦点,推送 set_sessions + 焦点详情卡(或待机卡)。"""
        async with self._lock:
            now = time.monotonic()
            order = self._active(now)
            self.slot_order = [s.sid for s in order]

            pinned = (
                self.focused_sid in self.slot_order and now < self.pin_until
            )
            if not pinned:
                # wait 状态优先获得焦点,否则跟随最近活跃
                waiting = [s for s in order if s.status == STATUS_WAIT]
                pool = waiting or order
                self.focused_sid = (
                    max(pool, key=lambda s: s.last_seen).sid if pool else None
                )
            focus_idx = (
                self.slot_order.index(self.focused_sid)
                if self.focused_sid in self.slot_order else 0
            )

            slots = [(s.status, s.project or "ai", s.provider) for s in order]
            sargs = sessions_args(slots, focus_idx)
            if sargs != self._last_sessions_args:
                self._last_sessions_args = sargs
                await self.device.set_sessions(sargs)

            card = None
            if self.focused_sid and self.focused_sid in self.sessions:
                card = self.sessions[self.focused_sid].card
            if card is None:
                card = self.idle_card
            if card is not None:
                cdata = card.to_data()
                if cdata != self._last_card_data:
                    self._last_card_data = cdata
                    await self.device.show_card(card)

    # ---- Agent hook 事件 ----
    async def on_hook(self, event: str, payload: dict) -> None:
        event = normalize_event(event)
        now = time.monotonic()
        sid = session_key(payload)
        self.last_event = now
        woke_from_saver = False
        if self.screensaver_on:
            woke_from_saver = True
            await self._exit_screensaver()

        if event == "session-end":
            self.sessions.pop(sid, None)
            if self.focused_sid == sid:
                self.focused_sid = None
                self.pin_until = 0.0  # 解除残留钉住
            await self._push()
            return

        sess = self.sessions.get(sid)
        existed = sess is not None
        if sess is None:
            sess = SessionState(sid=sid, first_seen=now, last_seen=now)

        prev_status = sess.status
        sess.stats.observe(event, payload)
        card = render_hook(event, payload, sess.stats, self.strings, prev_status)

        # 不出卡的新 session 不登记,避免幽灵槽位
        if card is None and not existed and not sess.status:
            if woke_from_saver:
                await self._push()
            return

        self.sessions[sid] = sess
        sess.last_seen = now
        sess.provider = provider_name(payload)
        hook_payload = event_payload(payload)
        proj = project_name(hook_payload.get("cwd") or payload.get("cwd", ""))
        if proj:
            sess.project = proj
        if card:
            sess.card = card
            if card.status:
                sess.status = card.status
        await self._push()

    async def on_select(self, idx: int) -> None:
        # 持锁读 slot_order,防与 _push 并发错位
        async with self._lock:
            if not (0 <= idx < len(self.slot_order)):
                return
            self.focused_sid = self.slot_order[idx]
            self.pin_until = time.monotonic() + PIN_TTL
            log.info("touch -> focus session %s (slot %d)", self.focused_sid, idx)
        await self._push()

    async def on_button(self) -> None:
        # 物理键智能切换:屏保中 -> 醒(退屏保);待机 -> 睡(进屏保)。都由 bridge 统一控制。
        if self.screensaver_on:
            log.info("button -> wake (exit screensaver)")
            self.last_wake = time.monotonic()
            await self._exit_screensaver()
            await self._push()
        else:
            log.info("button -> sleep (enter screensaver)")
            # 用当前伴侣卡 body 即时进屏保,再后台现编一句刷新(避免按下等 LLM)
            await self._enter_screensaver(fresh=False)
            asyncio.get_running_loop().create_task(self._refresh_saver_line())

    async def on_wake(self) -> None:
        # 点屏唤醒:固件已本地隐藏覆盖层,这里重置计时并刷新待机卡
        log.info("touch wake -> exit screensaver")
        self.last_wake = time.monotonic()
        self.screensaver_on = False
        await self._push()

    async def on_connect(self) -> None:
        # 重连后主动清屏保覆盖层,再清缓存强制全量重推
        self._last_sessions_args = None
        self._last_card_data = None
        self.screensaver_on = False
        await self.device.set_screensaver(False, "", "")
        await self._push()

    # ---- 后台任务 ----
    async def _companion_loop(self) -> None:
        while True:
            await asyncio.sleep(15)
            now = time.monotonic()
            # 过期 session 清理 -> 图标条收敛
            stale = [sid for sid, s in self.sessions.items() if now - s.last_seen > SESSION_TTL]
            for sid in stale:
                self.sessions.pop(sid, None)
            if stale:
                await self._push()

            idle = self.last_event == 0.0 or (now - self.last_event) >= self.cfg.idle_seconds
            due = (now - self.last_companion) >= self.cfg.companion_interval
            no_active = not self._active(now)
            if idle and due and no_active and not self.screensaver_on:
                self.last_companion = now
                card = await self.companion.generate(trigger="idle")
                if card:
                    self.idle_card = card
                    await self._push()

            await self._maybe_screensaver(now)

    async def _maybe_screensaver(self, now: float) -> None:
        # needs-you(wait)告警时不睡;否则距最后活动/唤醒超时即全屏大眼睛
        waiting = any(s.status == STATUS_WAIT for s in self._active(now))
        idle_ref = max(self.last_event, self.last_wake, self.started_at)
        long_idle = (now - idle_ref) >= self.cfg.screensaver_seconds
        if waiting and self.screensaver_on:
            await self._exit_screensaver()
            await self._push()
            return
        if waiting or not long_idle:
            return
        if not self.screensaver_on or (now - self.last_saver_line) >= SAVER_LINE_TTL:
            await self._enter_screensaver(fresh=True)

    def _saver_line(self) -> str:
        # 屏保俏皮话 = 伴侣卡正文(与待机同一条 LLM 生成路径);无卡则回退内置文案
        body = self.idle_card.body if self.idle_card else ""
        return sanitize_text(body or "")[:80] or random.choice(self.strings.screensaver_lines)

    async def _enter_screensaver(self, fresh: bool = True) -> None:
        # fresh=True:先现编一张新伴侣卡(自动超时/换句场景,可容忍数秒延迟),
        #   期间若有新活动/告警则放弃;fresh=False:用当前卡即时进入(按钮场景,零等待)。
        if fresh:
            card = await self.companion.generate(trigger="idle")
            now = time.monotonic()
            idle_ref = max(self.last_event, self.last_wake, self.started_at)
            if not self.screensaver_on and (now - idle_ref) < self.cfg.screensaver_seconds:
                return
            if any(s.status == STATUS_WAIT for s in self._active(now)):
                return
            if card:
                self.idle_card = card
                self.last_companion = now
                self._last_card_data = card.to_data()
        self.screensaver_on = True
        self.last_saver_line = time.monotonic()
        await self.device.set_screensaver(True, self._saver_line(), self.strings.screensaver_hint)

    async def _refresh_saver_line(self) -> None:
        # 按钮即时进屏保后,后台现编一句刷新(仍在屏保时才推)
        card = await self.companion.generate(trigger="idle")
        if not card or not self.screensaver_on:
            return
        self.idle_card = card
        self.last_companion = time.monotonic()
        self.last_saver_line = self.last_companion
        self._last_card_data = card.to_data()
        await self.device.set_screensaver(True, self._saver_line(), self.strings.screensaver_hint)

    async def _exit_screensaver(self) -> None:
        if not self.screensaver_on:
            return
        self.screensaver_on = False
        await self.device.set_screensaver(False, "", "")

    # ---- HTTP(接收 agent hook 事件) ----
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
        self.started_at = time.monotonic()
        app = web.Application()
        app.router.add_post("/hook/{event}", self._http_hook)
        app.router.add_post("/metrics", self._http_metrics)
        app.router.add_get("/healthz", lambda r: web.json_response({"ok": True}))
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, self.cfg.http_host, self.cfg.http_port)
        await site.start()
        log.info("hook endpoint: http://%s:%d/hook/<event>", self.cfg.http_host, self.cfg.http_port)

        s = self.strings
        self.idle_card = Card(s.mood_online, s.title_bridge_up, s.body_waiting_agent, "", STATUS_ONLINE)
        await self.device.start()  # on_connect 回调会在连上后推首屏(眼睛 + 等待卡)

        await self._companion_loop()
