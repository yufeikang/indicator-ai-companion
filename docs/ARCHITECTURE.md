# 架构与性能(含动画规划)

## 核心原则:动画在设备端,bridge 只推语义

WiFi + ESPHome API 每帧一次 RPC,根本做不了流畅动画。所以:

- **bridge 只推「状态/数据」**(mood、事件类型、卡片内容),频率低(事件驱动)。
- **设备端 LVGL 用 `lv_anim` 把状态演绎成动画**,本地 240MHz 双核 + PSRAM 渲染,可 30–60fps。
- 状态 → 动画的映射逻辑**写在固件里**,不在网络上。

```
bridge ──(低频:mood/event/内容)──▶ 设备
                                     │
                  设备端 LVGL: 状态 → 预定义动画(本地高帧率)
```

## 三层 UI 结构(为动画分层)

| 层 | 内容 | 刷新特性 |
|---|---|---|
| 背景层 | 静态深色图 `bg.png` | 不动 → LVGL 部分刷新下基本不重绘 |
| 内容层 | 卡片文字(mood/title/body/footer) | 切换时淡入淡出 |
| 动效层 | 状态指示器(spinner / 呼吸 / 脉冲 / 粒子) | mood 驱动,局部小区域重绘 |

## 动画类型 × 性能预算

| 类型 | LVGL 实现 | 性能 |
|---|---|---|
| 状态指示:呼吸 / 脉冲 / spinner / arc | `lv_anim` 改透明度/角度/缩放,局部小区域 | ✅ 轻,流畅 |
| mood 配色(青=运行/橙=等待/绿=完成/红=错误)+ 渐变过渡 | 改 style color | ✅ 轻 |
| 卡片切换过渡:淡入 / 滑动 | LVGL anim / 多对象 | ✅ 中 |
| 全屏粒子 / 星空流动 | 多对象 anim 或 canvas | ⚠️ 重,限粒子数 |
| 帧动画 / GIF(桌面宠物) | `lv_gif` / ESPHome animation 组件 | ⚠️ 吃 flash+CPU,只做小尺寸局部 |

## 性能关键点(现在就定好,别踩)

1. **LVGL 部分刷新**:只重绘 invalidated 脏区域。静态背景不每帧重绘;**动画务必限局部**,
   重绘面积小 = 流畅。避免「全屏每帧动画」(那会撑满 PSRAM 带宽,直接掉帧)。
2. **buffer_size**:静态 UI 25% 够;一旦上动画,提到 50% 减少 flush 次数(PSRAM octal 8MB 够)。
3. **背景图代价**:全屏 RGB565 在 flash,LVGL blit;动画区域会连背景一起重绘该局部(可接受)。
   若要「全屏动效」,改用 LVGL 渐变对象(gradient)而非位图,省带宽。
4. **mipi_rgb**:RGB 并口 + framebuffer in PSRAM,ESP32-S3 带宽足够局部动画;
   不要指望全屏 60fps 视频级。
5. **刷新驱动**:静态 UI `lvgl: update_interval` 可低;动画由 `lv_anim` 自驱高帧率,
   只在动画期间拉高刷新,空闲回落省电。

## 多 session 图标条 + 触摸切换

一个 bridge 可同时服务多个 Claude Code 会话——每个会话的 hook 都 POST 到同一 bridge,
payload 带 `session_id` 区分。bridge 按 `session_id` 维护注册表,顶部图标条最多并排 4 个
**Claude 官方星芒 mark**(每个 = 一个 session)。

```
session A ─┐
session B ─┼─hooks(带 session_id)─▶ bridge ─set_sessions(count,focus,...)─▶ 图标条
session C ─┘                          │      └─show_card(焦点 session)──────▶ 详情卡
                                       ▲
设备触摸某图标 ─selected_session(传感器状态)─┘  (本地闭环:切焦点,不回传 Claude Code)
```

- **图标语义**:星芒固定 Claude 品牌色 `0xD97757`(彩屏保真);**动画即状态**——run/think 呼吸+满亮,
  其余静止+变暗。精确状态色放在图标下方项目名文字上(青/蓝/橙/绿/灰)。这延续「动画在设备端、
  bridge 只推语义」原则:bridge 只推 `count/focus/status/label`,呼吸由固件 `animimg` 本地自驱。
- **焦点**:详情卡显示「焦点」session。默认跟随最近活跃的会话;手点某图标则钉住它 `PIN_TTL` 秒
  (期间别的会话有活动也不抢焦点),到期回落自动跟随。
- **触摸为何只到 bridge 为止**:点图标只是本地切换「看哪个 session」,是设备↔bridge 的闭环,
  无需回传 Claude Code。若想反向用触摸**回答** Claude Code 的提问(如选项选择),内置
  `AskUserQuestion` 无法被 hook 注入答案——那需要另起一个自建 MCP 工具让模型同步阻塞等待触摸,
  不在本组件范围。
- **生命周期**:`session-end` hook 即时移除;另有 `SESSION_TTL` 兜底过期清理。无活跃 session 时
  图标条隐藏、改显待机眨眼睛 + 伴侣卡。
- **屏保**:距最后活动超 `SCREENSAVER_SECONDS`(默认 300s)且无 needs-you 告警时,`set_screensaver`
  推全屏大眼睛(待机眼帧 `transform_scale` 放大,零额外 flash)+ 俏皮话;任何 hook 或点屏(`screensaver_wake`)退出。

## 接口演进

- 保留 `show_card(status,mood,title,body,footer)` 推焦点内容、`set_sessions(...)` 推图标条。
- 动画**不新增网络帧接口**;`status` 字段即动画触发器——固件按 status 切换配色/呼吸。
- 触摸输入经 `selected_session` / `screensaver_wake` 传感器状态上报(复用 ESPHome `subscribe_states`,与物理刷新键同机制)。

## 建议落地顺序

1. **(已做)** 中文 PingFang 字体 + 深色背景。
2. mood → 配色主题 + 一个轻量状态动效(呼吸/spinner)作 PoC,实测帧率。
3. 卡片切换淡入淡出。
4. 按需:局部粒子 / 桌面宠物(先评估性能再上)。
