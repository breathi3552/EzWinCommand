async function loadStatus() {
    try {
        const resp = await fetch("/status");
        const data = await resp.json();
        document.getElementById("cpu").textContent = data.cpu_percent.toFixed(1);
        document.getElementById("memory").textContent = data.memory.percent.toFixed(1);
    } catch {
        // 忽略网络错误，下次轮询会重试
    }
}

async function loadActions() {
    try {
        const resp = await fetch("/api/actions");
        const data = await resp.json();
        const container = document.getElementById("actions");
        container.innerHTML = "";

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
    } catch {
        // 忽略
    }
}

async function sendCommand(action, params = {}) {
    try {
        const resp = await fetch("/api/command", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action, params }),
        });
        const result = await resp.json();
        console.log(action, result);
    } catch (e) {
        console.error("命令发送失败:", e);
    }
}

loadStatus();
loadActions();
setInterval(loadStatus, 5000);
