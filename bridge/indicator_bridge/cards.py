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


MAX_SLOTS = 4  # 图标条最多并排显示的 session 数(与固件 set_sessions 槽位数一致)


def _now() -> str:
    return time.strftime("%H:%M")


def project_name(cwd: str) -> str:
    return os.path.basename(cwd.rstrip("/")) if cwd else ""


# 向后兼容的私有别名(render_hook 内部仍用 _project)
_project = project_name


def _slot_label(s: str) -> str:
    return sanitize_text(s)[:7]


def _slot_provider(provider: str) -> str:
    p = (provider or "").lower()
    return p if p in ("claude", "codex") else "claude"


def sessions_args(slots: list[tuple[str, str, str]], focus_idx: int) -> dict:
    """把已按显示顺序排好的 (status, label, provider) 列表组装成 set_sessions 入参。"""
    slots = slots[:MAX_SLOTS]
    n = len(slots)
    args: dict[str, object] = {
        "count": n,
        "focus": max(0, min(focus_idx, n - 1)) if n else 0,
    }
    for i in range(MAX_SLOTS):
        st, lb, provider = slots[i] if i < n else ("", "", "")
        args[f"s{i}_status"] = st
        args[f"s{i}_label"] = _slot_label(lb)
        args[f"s{i}_provider"] = _slot_provider(provider)
    return args


def event_payload(payload: dict) -> dict:
    """Return hook payload fields with wrapper metadata merged in.

    push-event.sh wraps hook stdin as {"cwd": "...", "payload": {...}} so the
    bridge can always recover the working directory. Direct legacy Claude
    payloads are still accepted.
    """
    inner = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    if not inner:
        return payload
    merged = dict(inner)
    for key in ("cwd", "hook_event", "source", "session_id", "thread_id", "conversation_id"):
        if payload.get(key) and not merged.get(key):
            merged[key] = payload[key]
    return merged


def session_key(payload: dict) -> str:
    p = event_payload(payload)
    for key in ("session_id", "thread_id", "conversation_id", "assigned_thread_id"):
        value = p.get(key)
        if value:
            return str(value)
    return "default"


def provider_name(payload: dict) -> str:
    p = event_payload(payload)
    source = str(p.get("source") or "").lower()
    if source in ("claude", "codex"):
        return source
    event = str(p.get("hook_event") or "").lower()
    if "codex" in event:
        return "codex"
    return "claude"


def _footer(payload: dict) -> str:
    p = event_payload(payload)
    proj = _project(p.get("cwd", ""))
    return f"{proj} · {_now()}" if proj else _now()


def _tool_name(payload: dict) -> str:
    p = event_payload(payload)
    for key in ("tool_name", "toolName", "name"):
        value = p.get(key)
        if value:
            return str(value)
    for key in ("tool", "tool_call", "call"):
        value = p.get(key)
        if isinstance(value, dict):
            for name_key in ("name", "tool_name", "toolName"):
                name = value.get(name_key)
                if name:
                    return str(name)
    return ""


def _tool_input(payload: dict) -> dict:
    p = event_payload(payload)
    for key in ("tool_input", "toolInput", "input", "arguments", "args"):
        value = p.get(key)
        if isinstance(value, dict):
            return value
    for key in ("tool", "tool_call", "call"):
        value = p.get(key)
        if isinstance(value, dict):
            for input_key in ("input", "arguments", "args", "tool_input", "toolInput"):
                inner = value.get(input_key)
                if isinstance(inner, dict):
                    return inner
    return {}


def _payload_message(payload: dict) -> str:
    p = event_payload(payload)
    for key in ("message", "reason", "prompt", "description", "summary"):
        value = p.get(key)
        if value:
            return str(value)
    return ""


def _tool_summary(tool_name: str, tool_input: dict | None) -> str:
    ti = tool_input or {}
    name = tool_name.rsplit(".", 1)[-1]
    if tool_name in ("Bash", "functions.exec_command", "exec_command") or name == "exec_command":
        return str(ti.get("command") or ti.get("cmd") or "")
    if tool_name in ("Edit", "Write", "Read", "NotebookEdit", "apply_patch") or name in (
        "apply_patch",
        "view_image",
    ):
        return os.path.basename(str(ti.get("file_path") or ti.get("path") or "")) or "patch"
    if tool_name in ("Grep", "find") or name == "find":
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


def _ask_card(tool_input: dict, footer: str, s: Strings) -> "Card":
    """AskUserQuestion 的 tool_input -> 一张带真实问题/选项的 wait 卡。"""
    qs = tool_input.get("questions") or []
    if not qs:
        return Card(s.mood_wait, s.title_need_you, s.notify_default, footer, STATUS_WAIT)
    if len(qs) == 1:
        q0 = qs[0]
        body = q0.get("question", "") or s.notify_default
        opts = [o.get("label", "") for o in (q0.get("options") or [])]
        if opts:
            body = f"{body} ｜ " + " / ".join(opts)
        return Card(s.mood_wait, s.title_need_you, body, footer, STATUS_WAIT)
    # 多问:逐条编号列出,而非只显示第 1 问
    body = "  ".join(
        f"{i}.{(q.get('question') or '').strip()}" for i, q in enumerate(qs, 1)
    )
    title = f"{s.title_need_you} ({len(qs)})"
    return Card(s.mood_wait, title, body, footer, STATUS_WAIT)


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
            self.last_tool = _tool_name(payload)


def render_hook(
    event: str, payload: dict, stats: Stats, s: Strings, prev_status: str = ""
) -> Card | None:
    """把一个 agent hook 事件渲染成一张 HUD 卡片(None 表示该事件不出卡)。"""
    payload = event_payload(payload)
    footer = _footer(payload)

    if event == "post-tool":
        # 工具执行完(= 用户已确认权限 / 已回答提问)后最先触发的 hook。
        # 仅当之前处于 wait 时用它及时清除告警,回到 think;否则不抢镜(避免每个工具都闪)。
        if prev_status == STATUS_WAIT:
            return Card(s.mood_think, s.title_thinking, s.body_got_request, footer, STATUS_THINK)
        return None

    if event == "session-start":
        proj = _project(payload.get("cwd", "")) or s.fallback_project
        return Card(s.mood_ready, s.title_session, proj, footer, STATUS_READY)

    if event == "user-prompt":
        return Card(s.mood_think, s.title_thinking, s.body_got_request, footer, STATUS_THINK)

    if event == "pre-tool":
        tn = _tool_name(payload) or "tool"
        ti = _tool_input(payload)
        if tn in ("AskUserQuestion", "request_user_input", "functions.request_user_input"):
            return _ask_card(ti, footer, s)
        return Card(s.mood_run, tn, _tool_summary(tn, ti), footer, STATUS_RUN)

    if event == "permission-request":
        tn = _tool_name(payload)
        ti = _tool_input(payload)
        msg = _payload_message(payload) or _tool_summary(tn, ti) or s.notify_default
        title = s.title_approve if tn else s.title_need_you
        return Card(s.mood_wait, title, msg, footer, STATUS_WAIT)

    if event == "notification":
        ntype = payload.get("notification_type", "")
        # Agent 干完活等下一步 / 认证成功:不抢镜,留给 stop 卡
        if ntype in ("idle_prompt", "auth_success", "elicitation_complete", "elicitation_response"):
            return None
        title = s.title_approve if ntype == "permission_prompt" else s.title_need_you
        msg = payload.get("message", "") or s.notify_default
        return Card(s.mood_wait, title, msg, footer, STATUS_WAIT)

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
