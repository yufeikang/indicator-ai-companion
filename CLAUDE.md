# CLAUDE.md — Indicator AI Companion

把 Seeed SenseCAP Indicator D1(ESP32-S3 + 4″ 480×480 触摸屏)做成 **Claude Code 物理状态屏(HUD)+ AI 桌面伴侣**。完整说明、上手与故障排查见 README.md。

## 架构
- `firmware/` — ESPHome + LVGL 全屏 UI。两个 API action:`show_card(status,mood,title,body,footer)`、`set_metrics(metrics)`。`status` 是语言无关语义键(run/think/wait/done/ready/online),驱动设备端配色;`mood/title/body` 是本地化文案。
- `bridge/` — Python daemon(Docker 常驻)。收 Claude Code hooks 渲染 HUD;调 OpenAI 兼容端点生成伴侣卡;收 statusLine 指标。文案语言由 `BRIDGE_LANG`(zh/en)控制,字符串表在 `indicator_bridge/i18n.py`。
- `hooks/` — `push-event.sh`(hook→bridge)、`statusline-wrapper.sh`(包装 claude-hud + 推 metrics)。

## 常用命令
```bash
# 校验 + 刷固件(USB 最稳;改了 show_card 参数后必须重刷)
uv run --with esphome esphome config firmware/indicator-companion.yaml
uv run --with esphome esphome upload firmware/indicator-companion.yaml --device /dev/cu.usbserial-XXXX

# bridge(Docker)
docker compose up -d --build
docker logs indicator-bridge -f
```

## 注意
- 改 `show_card` 参数后,设备与 bridge 必须同步:重刷固件 + 重建容器。
- 真实凭据在 gitignore 的 `firmware/secrets.yaml` / `bridge/.env`,不入库;固件 `api_key` 必须 == bridge `INDICATOR_NOISE_PSK`。
