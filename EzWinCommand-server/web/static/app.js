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

        for (const action of data.actions) {
            const btn = document.createElement("button");
            btn.textContent = action;
            btn.addEventListener("click", () => sendCommand(action));
            container.appendChild(btn);
        }
    } catch {
        // 忽略
    }
}

async function sendCommand(action) {
    try {
        const resp = await fetch("/api/command", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action }),
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
