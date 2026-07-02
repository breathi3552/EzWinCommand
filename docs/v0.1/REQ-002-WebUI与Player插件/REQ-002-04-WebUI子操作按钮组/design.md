# REQ-002-04: Web UI 改造支持子操作按钮组

- **父需求**: REQ-002
- **日期**: 2026-07-02
- **状态**: 已完成

## 设计概述

改造前端 `app.js` 和 `style.css`，将原来的平铺按钮列表改为卡片式布局；根据每个插件的 `sub_actions` 数组长度决定渲染单个按钮（简单触发型）还是按钮组（子操作型）。

## 涉及文件

| 文件 | 变更类型 | 说明 |
|---|---|---|
| `EzWinCommand-server/web/static/app.js` | 修改 | 渲染逻辑从简单按钮列表改为卡片+子操作判断 |
| `EzWinCommand-server/web/static/style.css` | 修改 | 布局从 grid 改为 column flex，新增 `.plugin-card` 和 `.btn-group` 样式 |

## 实现要点

### app.js 改造

**改造前**（遍历 action 名称列表，生成平铺按钮）：
```javascript
for (const action of data.actions) {
    const btn = document.createElement("button");
    btn.textContent = action;
    btn.addEventListener("click", () => sendCommand(action));
    container.appendChild(btn);
}
```

**改造后**（遍历插件对象，卡片+子操作判断）：
```javascript
for (const plugin of data.actions) {
    const card = document.createElement("div");
    card.className = "plugin-card";

    const title = document.createElement("h3");
    title.textContent = plugin.label;
    card.appendChild(title);

    if (plugin.sub_actions.length === 0) {
        // 简单触发型：单个按钮
        const btn = document.createElement("button");
        btn.textContent = plugin.label;
        btn.addEventListener("click", () =>
            sendCommand(plugin.name)
        );
        card.appendChild(btn);
    } else {
        // 子操作型：按钮组
        const group = document.createElement("div");
        group.className = "btn-group";
        for (const sub of plugin.sub_actions) {
            const btn = document.createElement("button");
            btn.textContent = sub.label;
            btn.addEventListener("click", () =>
                sendCommand(plugin.name, { sub_action: sub.id })
            );
            group.appendChild(btn);
        }
        card.appendChild(group);
    }

    container.appendChild(card);
}
```

### sendCommand 增强

`sendCommand()` 的 `params` 参数在简单触发型插件调用时为空对象 `{}`，子操作型调用时传入 `{ sub_action: sub.id }`。该参数通过 `JSON.stringify({ action, params })` 发送到 `POST /api/command`。

### style.css 改造

**布局变更**：`#actions` 从 `grid` 布局改为 `flex-direction: column`，每个 `.plugin-card` 作为独立的卡片区块。

**卡片样式**：
- `.plugin-card`：边框、圆角、内边距、下边距，形成视觉分隔。
- `.plugin-card h3`：灰色小标题，显示插件 label。
- `.btn-group`：`display: flex; gap: 8px; flex-wrap: wrap`，子按钮横向排列。

### 渲染效果

| 插件 | 渲染形式 |
|---|---|
| calculator | 一张卡片，标题"计算器"，单个按钮"计算器" |
| volume | 一张卡片，标题"音量控制"，按钮组：`+` `-` `静音` |
| player | 一张卡片，标题"媒体控制"，按钮组：`播放/暂停` `上一曲` `下一曲` |
