import json
import logging
import re

import aiohttp

from .cards import Card
from .i18n import DEFAULT_LANG

log = logging.getLogger("indicator.companion")

SYSTEM_ZH = """你是一块放在程序员键盘旁的 480x480 桌面小屏上的 AI 伴侣。\
说话简短、温暖,偶尔机智或有点洞见。

只回复一个紧凑的 JSON 对象,不要任何别的文字:
{"mood": "...", "title": "...", "body": "...", "footer": "..."}

约束(屏幕较小,务必简短):
- mood:一个词的心情/状态,<= 4 个汉字(如 平静、专注、灵感、放空)
- title:<= 10 个汉字
- body:一句话正文,<= 36 个汉字
- footer:<= 10 个汉字,一个小标签或提示
用简体中文(常用字)。不要 markdown,不要前后多余文字,只要那个 JSON 对象。"""

SYSTEM_EN = """You are an AI companion living on a 480x480 desk screen next to a \
programmer's keyboard. Keep it short and warm, occasionally witty or insightful.

Reply with ONE compact JSON object and nothing else:
{"mood": "...", "title": "...", "body": "...", "footer": "..."}

Constraints (the screen is small, stay terse):
- mood: a one-word mood/state, <= 8 letters (e.g. Calm, Focused, Spark)
- title: <= 18 chars
- body: a single sentence, <= 70 chars
- footer: <= 16 chars, a tiny tag or hint
Use plain English. No markdown, no extra text, just that JSON object."""

SYSTEM = {"zh": SYSTEM_ZH, "en": SYSTEM_EN}

_TRIGGER = {
    "zh": {"idle": "空闲", "button": "按下按钮"},
    "en": {"idle": "idle", "button": "button press"},
}
_USER_PROMPT = {
    "zh": "触发场景:{ctx}。给我一张此刻的桌面伴侣卡片,每次换不同的心情和内容,别老是问候语。/no_think",
    "en": "Trigger: {ctx}. Give me a desk-companion card for this moment; vary the mood and"
          " content each time, don't always greet. /no_think",
}


def _extract_json(text: str) -> dict:
    # 去掉 qwen 等模型的 <think>...</think> 段
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # 卡片 JSON 是扁平的(无嵌套),抓最后一个能解析的 {...}
    for chunk in reversed(re.findall(r"\{[^{}]*\}", text, flags=re.DOTALL)):
        try:
            return json.loads(chunk)
        except json.JSONDecodeError:
            pass
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    return {}


class Companion:
    """通过 OpenAI 兼容 chat/completions 端点生成伴侣卡(本地/局域网模型,免 key)。"""

    def __init__(
        self, base_url: str, model: str, api_key: str | None = None, lang: str = DEFAULT_LANG
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.lang = (lang or DEFAULT_LANG).lower()
        if self.lang not in SYSTEM:
            self.lang = DEFAULT_LANG

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    async def generate(self, trigger: str = "idle") -> Card | None:
        ctx = _TRIGGER[self.lang].get(trigger, trigger)
        prompt = _USER_PROMPT[self.lang].format(ctx=ctx)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM[self.lang]},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 300,
            "temperature": 0.9,
        }
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=self._headers(),
                ) as resp:
                    if resp.status != 200:
                        log.warning("companion HTTP %s: %s", resp.status, (await resp.text())[:200])
                        return None
                    data = await resp.json()
            text = data["choices"][0]["message"]["content"]
            parsed = _extract_json(text)
            if not parsed:
                log.warning("companion: no JSON parsed from %r", text[:160])
                return None
            return Card(
                mood=str(parsed.get("mood", "")),
                title=str(parsed.get("title", "")),
                body=str(parsed.get("body", "")),
                footer=str(parsed.get("footer", "")),
            )
        except Exception:
            log.exception("companion generate failed")
            return None
