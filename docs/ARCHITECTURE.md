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

## 接口演进

- 保留 `show_card(mood,title,body,footer)` 推内容。
- 动画**不新增网络帧接口**;mood 字段即动画触发器——固件按 mood 文本切换配色 + 对应动效。
- 如需更强控制,加一个 `set_state(mood, anim_hint)` action(仍是低频语义,不是帧)。

## 建议落地顺序

1. **(已做)** 中文 PingFang 字体 + 深色背景。
2. mood → 配色主题 + 一个轻量状态动效(呼吸/spinner)作 PoC,实测帧率。
3. 卡片切换淡入淡出。
4. 按需:局部粒子 / 桌面宠物(先评估性能再上)。
