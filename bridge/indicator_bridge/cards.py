import os
import time
from dataclasses import dataclass

from .i18n import (
    STATUS_DONE,
    STATUS_READY,
    STATUS_RUN,
    STATUS_THINK,
    STATUS_WAIT,
    Strings,
)

# 屏幕字库 = ASCII + GB2312 一级汉字 + 常用中文标点。
# 推屏前剔除字库外字符(emoji、生僻 SMP、控制符),避免显示成豆腐块。
_PUNCT = set("，。、；：？！“”‘’（）《》【】…—～·「」『』　％℃°→←↑↓")


def sanitize_text(s: str) -> str:
    out = []
    for c in s or "":
        o = ord(c)
        if 0x20 <= o < 0x7F or 0x4E00 <= o <= 0x9FFF or c in _PUNCT:
            out.append(c)
    return "".join(out).strip()


@dataclass
class Card:
    mood: str = ""
    title: str = ""
    body: str = ""
    footer: str = ""
    status: str = ""  # 语言无关语义键,驱动设备端配色(见 i18n.STATUS_*)

    def to_data(self) -> dict[str, str]:
        return {
            "status": self.status,
            "mood": sanitize_text(self.mood)[:8],
            "title": sanitize_text(self.title)[:18],
            "body": sanitize_text(self.body)[:110],
            "footer": sanitize_text(self.footer)[:24],
        }


def _now() -> str:
    return time.strftime("%H:%M")


def _project(cwd: str) -> str:
    return os.path.basename(cwd.rstrip("/")) if cwd else ""


def _footer(payload: dict) -> str:
    proj = _project(payload.get("cwd", ""))
    return f"{proj} · {_now()}" if proj else _now()


def _tool_summary(tool_name: str, tool_input: dict | None) -> str:
    ti = tool_input or {}
    if tool_name == "Bash":
        return str(ti.get("command", ""))
    if tool_name in ("Edit", "Write", "Read", "NotebookEdit"):
        return os.path.basename(str(ti.get("file_path", "")))
    if tool_name == "Grep":
        return "grep " + str(ti.get("pattern", ""))
    if tool_name == "Glob":
        return str(ti.get("pattern", ""))
    if tool_name in ("Agent", "Task"):
        return str(ti.get("description", ""))
    if tool_name == "WebFetch":
        return str(ti.get("url", ""))
    if tool_name == "WebSearch":
        return str(ti.get("query", ""))
    if tool_name.startswith("mcp__"):
        return tool_name.split("__", 2)[-1]
    return ""


class Stats:
    """每个对话回合的轻量计数(从 hook 事件流里推断)。"""

    def __init__(self) -> None:
        self.tools_this_turn = 0
        self.last_tool = ""

    def observe(self, event: str, payload: dict) -> None:
        if event == "user-prompt":
            self.tools_this_turn = 0
        elif event == "pre-tool":
            self.tools_this_turn += 1
            self.last_tool = payload.get("tool_name", "")


def render_hook(event: str, payload: dict, stats: Stats, s: Strings) -> Card | None:
    """把一个 Claude Code hook 事件渲染成一张 HUD 卡片(None 表示该事件不出卡)。"""
    footer = _footer(payload)

    if event == "session-start":
        proj = _project(payload.get("cwd", "")) or s.fallback_project
        return Card(s.mood_ready, s.title_session, proj, footer, STATUS_READY)

    if event == "user-prompt":
        return Card(s.mood_think, s.title_thinking, s.body_got_request, footer, STATUS_THINK)

    if event == "pre-tool":
        tn = payload.get("tool_name", "工具")
        return Card(s.mood_run, tn, _tool_summary(tn, payload.get("tool_input")), footer, STATUS_RUN)

    if event == "notification":
        msg = payload.get("message", "") or s.notify_default
        return Card(s.mood_wait, s.title_need_you, msg, footer, STATUS_WAIT)

    if event == "stop":
        n = stats.tools_this_turn
        body = s.body_tools_fmt.format(n=n) if n else s.body_wait_next
        return Card(s.mood_done, s.title_done, body, footer, STATUS_DONE)

    return None


def format_metrics(payload: dict) -> str:
    """从 statusLine JSON 组装 metrics 文本(context 用量 + 5h limit + 重置倒计时)。"""
    cw = payload.get("context_window") or {}
    ctx = cw.get("used_percentage")
    rl = (payload.get("rate_limits") or {}).get("five_hour") or {}
    limit = rl.get("used_percentage")
    reset = rl.get("resets_at")
    parts = []
    if isinstance(ctx, (int, float)):
        parts.append(f"ctx {int(round(ctx))}%")
    if isinstance(limit, (int, float)):
        s = f"5h {int(round(limit))}%"
        if isinstance(reset, (int, float)):
            mins = int((reset - time.time()) / 60)
            if mins > 0:
                h, m = divmod(mins, 60)
                s += f" {h}h{m:02d}m" if h else f" {m}m"
        parts.append(s)
    return "   ".join(parts)
