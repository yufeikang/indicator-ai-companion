"""UI 文案的多语言表。

新增一门语言:加一个 Strings 实例进 TABLE。若该语言用到内嵌字库
(GB2312 + ASCII)以外的字形(如日文假名),还需相应扩充 firmware 字体。
"""
from dataclasses import dataclass

# 语言无关的状态语义键,与固件 show_card 的 status 配色分支一一对应
STATUS_READY = "ready"
STATUS_THINK = "think"
STATUS_RUN = "run"
STATUS_WAIT = "wait"
STATUS_DONE = "done"
STATUS_ONLINE = "online"
STATUS_IDLE = "idle"


@dataclass(frozen=True)
class Strings:
    mood_ready: str
    mood_think: str
    mood_run: str
    mood_wait: str
    mood_done: str
    mood_online: str
    mood_hello: str
    title_session: str
    title_thinking: str
    body_got_request: str
    title_need_you: str
    notify_default: str
    title_done: str
    body_tools_fmt: str
    body_wait_next: str
    title_bridge_up: str
    body_waiting_cc: str
    title_button_tap: str
    body_companion_offline: str
    fallback_project: str


ZH = Strings(
    mood_ready="就绪",
    mood_think="思考中",
    mood_run="运行中",
    mood_wait="待确认",
    mood_done="完成",
    mood_online="在线",
    mood_hello="你好",
    title_session="会话开始",
    title_thinking="正在想…",
    body_got_request="收到你的请求",
    title_need_you="需要你",
    notify_default="需要你确认",
    title_done="搞定",
    body_tools_fmt="本回合 {n} 次工具调用",
    body_wait_next="等待下一步",
    title_bridge_up="Bridge 已连",
    body_waiting_cc="等待 Claude Code…",
    title_button_tap="点了一下",
    body_companion_offline="伴侣端点离线",
    fallback_project="Claude Code",
)

EN = Strings(
    mood_ready="Ready",
    mood_think="Thinking",
    mood_run="Working",
    mood_wait="Waiting",
    mood_done="Done",
    mood_online="Online",
    mood_hello="Hi",
    title_session="Session start",
    title_thinking="Thinking…",
    body_got_request="Got your request",
    title_need_you="Needs you",
    notify_default="Waiting for input",
    title_done="Done",
    body_tools_fmt="{n} tool calls this turn",
    body_wait_next="Awaiting next step",
    title_bridge_up="Bridge connected",
    body_waiting_cc="Waiting for Claude Code…",
    title_button_tap="Tapped",
    body_companion_offline="Companion endpoint offline",
    fallback_project="Claude Code",
)

TABLE: dict[str, Strings] = {"zh": ZH, "en": EN}
DEFAULT_LANG = "zh"


def get_strings(lang: str | None) -> Strings:
    return TABLE.get((lang or DEFAULT_LANG).lower(), TABLE[DEFAULT_LANG])
