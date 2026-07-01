import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    host: str
    noise_psk: str
    http_host: str
    http_port: int
    lang: str
    companion_base_url: str
    companion_model: str
    companion_api_key: str | None
    idle_seconds: float
    companion_interval: float
    screensaver_seconds: float


def load_config() -> Config:
    psk = os.environ.get("INDICATOR_NOISE_PSK")
    if not psk:
        raise SystemExit(
            "INDICATOR_NOISE_PSK 未设置。把 firmware/secrets.yaml 里的 api_key 填进 bridge/.env"
        )
    return Config(
        host=os.environ.get("INDICATOR_HOST", "indicator-companion.local"),
        noise_psk=psk,
        http_host=os.environ.get("BRIDGE_HTTP_HOST", "127.0.0.1"),
        http_port=int(os.environ.get("BRIDGE_HTTP_PORT", "9527")),
        # HUD / 伴侣卡文案语言(zh / en;见 i18n.TABLE)
        lang=os.environ.get("BRIDGE_LANG", "zh"),
        # 伴侣卡走 OpenAI 兼容端点(本地/局域网推理服务)
        companion_base_url=os.environ.get("COMPANION_BASE_URL", "http://localhost:1234/v1"),
        companion_model=os.environ.get("COMPANION_MODEL", "gemma-4-31b-it-qat"),
        companion_api_key=os.environ.get("COMPANION_API_KEY") or None,
        idle_seconds=float(os.environ.get("IDLE_SECONDS", "90")),
        companion_interval=float(os.environ.get("COMPANION_INTERVAL", "300")),
        # 距最后一次 Claude hook 事件多久无活动后进入全屏大眼睛屏保(点屏唤醒)
        screensaver_seconds=float(os.environ.get("SCREENSAVER_SECONDS", "300")),
    )
