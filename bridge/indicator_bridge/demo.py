"""Demo 模式:向运行中的 bridge 回放一段脚本化的假 hook 事件流。

不接真实 agent 即可完整演示 HUD:多 session 图标条(Claude + Codex)、工具卡、
needs-you 告警、AskUserQuestion、焦点切换、metrics、session 收尾。
所有数据均为虚构的非敏感样例,走与真实 hooks 相同的 HTTP 路径。

用法: cd bridge && uv run indicator-bridge-demo [--speed 2] [--loop]
录屏提示: 想连屏保/伴侣卡一起拍,先把 .env 的 IDLE_SECONDS / SCREENSAVER_SECONDS 调小。
"""

import argparse
import json
import time
import urllib.error
import urllib.request

CLAUDE = ("claude", "session_id")
CODEX = ("codex", "thread_id")

SHOP = ("demo-claude-shop", "/home/dev/rocket-shop", CLAUDE)
PIPE = ("demo-codex-pipe", "/home/dev/data-pipeline", CODEX)
BLOG = ("demo-claude-blog", "/home/dev/blog", CLAUDE)


class Demo:
    def __init__(self, base: str, speed: float) -> None:
        self.base = base.rstrip("/")
        self.speed = max(speed, 0.1)

    def _post(self, path: str, body: dict) -> None:
        req = urllib.request.Request(
            f"{self.base}{path}",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=3).close()
        except urllib.error.URLError as e:
            raise SystemExit(f"bridge 不可达 ({self.base}): {e}")

    def hook(self, event: str, sess: tuple, payload: dict | None = None) -> None:
        sid, cwd, (source, key) = sess
        print(f"  {event:<19} {source}:{cwd.rsplit('/', 1)[-1]}")
        self._post(f"/hook/{event}", {
            "cwd": cwd,
            "hook_event": event,
            "source": source,
            "agent_pid": "0",
            "payload": {key: sid, "cwd": cwd, **(payload or {})},
        })

    def metrics(self, ctx: int, five_h: int, reset_min: int) -> None:
        print(f"  metrics             ctx {ctx}% · 5h {five_h}%")
        self._post("/metrics", {
            "context_window": {"used_percentage": ctx},
            "rate_limits": {
                "five_hour": {
                    "used_percentage": five_h,
                    "resets_at": time.time() + reset_min * 60,
                }
            },
        })

    def pause(self, seconds: float) -> None:
        time.sleep(seconds / self.speed)

    def run(self) -> None:
        say = print
        say("== Phase 1: 单 Claude session — ready/think/run/wait/done 全状态 ==")
        self.metrics(34, 12, 128)
        self.hook("session-start", SHOP)
        self.pause(3)
        self.hook("user-prompt", SHOP)
        self.pause(2.5)
        self.hook("pre-tool", SHOP, {"tool_name": "Bash", "tool_input": {"command": "pnpm test"}})
        self.pause(3)
        self.hook("notification", SHOP, {
            "notification_type": "permission_prompt",
            "message": "Claude needs your permission to use Bash",
        })
        self.pause(6)
        self.hook("post-tool", SHOP, {"tool_name": "Bash"})
        self.pause(2.5)
        self.hook("pre-tool", SHOP, {"tool_name": "Edit", "tool_input": {"file_path": "src/checkout.tsx"}})
        self.pause(3)
        self.hook("pre-tool", SHOP, {"tool_name": "Grep", "tool_input": {"pattern": "useCart"}})
        self.pause(3)
        self.hook("stop", SHOP)
        self.pause(4)

        say("== Phase 2: Codex session 加入 — 双图标 + PermissionRequest ==")
        self.hook("session-start", PIPE)
        self.pause(3)
        self.hook("user-prompt", PIPE)
        self.pause(2.5)
        self.hook("pre-tool", PIPE, {"tool_name": "exec_command", "tool_input": {"command": "uv run pytest -q"}})
        self.pause(3)
        self.hook("permission-request", PIPE, {
            "tool_name": "exec_command",
            "message": "docker build -t pipeline .",
        })
        self.pause(6)
        self.hook("post-tool", PIPE, {"tool_name": "exec_command"})
        self.pause(2.5)
        self.hook("pre-tool", PIPE, {"tool_name": "apply_patch", "tool_input": {"path": "train.py"}})
        self.pause(3)
        self.metrics(52, 37, 96)
        self.hook("stop", PIPE)
        self.pause(4)

        say("== Phase 3: 第三个 session + AskUserQuestion — 此时可点图标试焦点钉住 ==")
        self.hook("session-start", BLOG)
        self.pause(3)
        self.hook("user-prompt", SHOP)
        self.pause(2)
        self.hook("pre-tool", SHOP, {"tool_name": "AskUserQuestion", "tool_input": {
            "questions": [{
                "question": "Deploy to staging?",
                "options": [{"label": "Yes"}, {"label": "No"}],
            }],
        }})
        self.pause(6)
        self.hook("post-tool", SHOP, {"tool_name": "AskUserQuestion"})
        self.pause(2.5)
        self.hook("pre-tool", SHOP, {"tool_name": "Write", "tool_input": {"file_path": "deploy.yaml"}})
        self.pause(3)
        self.hook("stop", SHOP)
        self.pause(3)
        self.hook("user-prompt", BLOG)
        self.pause(2)
        self.hook("pre-tool", BLOG, {"tool_name": "WebSearch", "tool_input": {"query": "lvgl partial refresh"}})
        self.pause(3)
        self.hook("stop", BLOG)
        say("  (3 个图标已就位,点任意图标可切换/钉住焦点)")
        self.pause(8)

        say("== Phase 4: session 逐个收尾 ==")
        self.hook("session-end", BLOG)
        self.pause(2)
        self.hook("session-end", PIPE)
        self.pause(2)
        self.hook("session-end", SHOP)
        say("完成。bridge 回到空闲:伴侣卡在 IDLE_SECONDS 后出现,屏保在 SCREENSAVER_SECONDS 后接管。")


def main() -> None:
    ap = argparse.ArgumentParser(description="向 bridge 回放脚本化假事件,免真实 agent 演示 HUD")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9527)
    ap.add_argument("--speed", type=float, default=1.0, help="播放倍速(2 = 快一倍)")
    ap.add_argument("--loop", action="store_true", help="循环播放直到 Ctrl-C")
    args = ap.parse_args()

    demo = Demo(f"http://{args.host}:{args.port}", args.speed)
    try:
        while True:
            demo.run()
            if not args.loop:
                break
            demo.pause(10)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
