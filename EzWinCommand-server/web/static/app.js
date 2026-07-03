// ============================================================
// EzWinCommand Web UI — 双模式：配对页 / 控制面板
// ============================================================

const DEVICE_KEY_STORAGE = "ez_device_key";
const POLL_INTERVAL = 3000; // 配对页轮询间隔（毫秒）

// ---- 工具函数 ----

/** 获取当前已存储的设备密钥 */
function storedKey() {
    return localStorage.getItem(DEVICE_KEY_STORAGE);
}

/** 构造带鉴权的 fetch headers */
function authHeaders(extra = {}) {
    const key = storedKey();
    const headers = { ...extra };
    if (key) {
        headers["Authorization"] = `Bearer ${key}`;
    }
    return headers;
}

/** 带鉴权的 fetch 封装 */
async function authFetch(url, options = {}) {
    const headers = authHeaders(options.headers || {});
    return fetch(url, { ...options, headers });
}

// ---- 页面切换 ----

/** 显示配对页，隐藏控制面板 */
function showPairingPage() {
    document.getElementById("pairing-page").style.display = "";
    document.getElementById("dashboard").style.display = "none";
}

/** 显示控制面板，隐藏配对页 */
function showDashboard() {
    document.getElementById("pairing-page").style.display = "none";
    document.getElementById("dashboard").style.display = "";
    // 首次进入控制面板时加载数据
    loadStatus();
    loadActions();
    loadDevices();
    setInterval(loadStatus, 5000);
    setInterval(loadDevices, 30000); // 每 30 秒刷新设备列表
}

// ---- 配对页逻辑 ----

let pairingPollTimer = null;

/** 停止配对码轮询 */
function stopPairingPoll() {
    if (pairingPollTimer) {
        clearInterval(pairingPollTimer);
        pairingPollTimer = null;
    }
}

/** 更新配对码显示 */
async function refreshPairingCode() {
    try {
        const resp = await fetch("/api/pairing-code");
        const data = await resp.json();
        return data;
    } catch {
        return null;
    }
}

/** 轮询配对码 — 配对页启动后周期性检查 */
async function pollPairingCode() {
    const data = await refreshPairingCode();
    if (!data) return;

    if (data.code) {
        document.getElementById("pairing-code").textContent = data.code;
    }

    // 如果另一设备已配对成功（has_devices 变为 true），自动切换
    if (data.has_devices && storedKey()) {
        stopPairingPoll();
        showDashboard();
        return;
    }

    // 如果 has_devices 变为 true 但本地无 key，说明是另一设备配对了，
    // 此时配对码显示会变为 ----（后端 code 为 null），页面保持在配对页
    // 用户可以通过页面上的配对码输入区域输入自己的配对码
}

/** 处理配对码输入焦点跳转 */
function setupCodeInputs() {
    const cells = document.querySelectorAll(".code-cell");
    cells.forEach((cell, index) => {
        cell.addEventListener("input", () => {
            const val = cell.value.replace(/[^0-9a-z]/gi, "").toLowerCase();
            cell.value = val.slice(-1);
            if (val && index < cells.length - 1) {
                cells[index + 1].focus();
            }
        });
        cell.addEventListener("keydown", (e) => {
            if (e.key === "Backspace" && !cell.value && index > 0) {
                cells[index - 1].focus();
            }
        });
        // 粘贴支持：粘贴 4 位码自动填充
        cell.addEventListener("paste", (e) => {
            e.preventDefault();
            const pasted = (e.clipboardData || window.clipboardData).getData("text").trim();
            const cleaned = pasted.replace(/[^0-9a-z]/gi, "").toLowerCase().slice(0, 4);
            for (let i = 0; i < 4; i++) {
                cells[i].value = cleaned[i] || "";
            }
            // 焦点跳到最后一个有值的格子或末尾
            const focusIdx = Math.min(cleaned.length, 3);
            cells[focusIdx].focus();
        });
    });
}

/** 获取 4 位输入框拼合的配对码 */
function readPairingCode() {
    const cells = document.querySelectorAll(".code-cell");
    return Array.from(cells).map(c => c.value).join("");
}

/** 配对按钮点击处理 */
async function handlePair() {
    const code = readPairingCode();
    const errorEl = document.getElementById("pair-error");

    if (code.length !== 4) {
        errorEl.textContent = "请输入完整的 4 位配对码";
        return;
    }

    errorEl.textContent = "";
    document.getElementById("pair-btn").disabled = true;

    try {
        const resp = await fetch("/api/authorize", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ token: code, name: navigator.platform || "Web 浏览器" }),
        });
        const data = await resp.json();

        if (data.success && data.device_key) {
            localStorage.setItem(DEVICE_KEY_STORAGE, data.device_key);
            stopPairingPoll();
            showDashboard();
        } else {
            errorEl.textContent = data.message || "配对失败，请重试";
        }
    } catch (e) {
        errorEl.textContent = "网络错误，请检查连接";
    } finally {
        document.getElementById("pair-btn").disabled = false;
    }
}

// ---- 控制面板逻辑 ----

/** 加载系统状态 */
async function loadStatus() {
    try {
        const resp = await authFetch("/status");
        const data = await resp.json();
        document.getElementById("cpu").textContent = data.cpu_percent.toFixed(1);
        document.getElementById("memory").textContent = data.memory.percent.toFixed(1);
    } catch {
        // 忽略网络错误，下次轮询会重试
    }
}

/** 加载操作按钮 */
async function loadActions() {
    try {
        const resp = await authFetch("/api/actions");
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
                const btn = document.createElement("button");
                btn.textContent = plugin.label;
                btn.addEventListener("click", () =>
                    sendCommand(plugin.name)
                );
                card.appendChild(btn);
            } else {
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

/** 发送命令 */
async function sendCommand(action, params = {}) {
    try {
        const resp = await authFetch("/api/command", {
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

// ---- 设备管理 ----

/** 加载设备列表 */
async function loadDevices() {
    try {
        const resp = await authFetch("/api/devices");
        const data = await resp.json();
        const tbody = document.getElementById("device-tbody");
        const emptyEl = document.getElementById("device-empty");
        tbody.innerHTML = "";

        const devices = data.devices || [];
        if (devices.length === 0) {
            emptyEl.style.display = "";
            return;
        }
        emptyEl.style.display = "none";

        for (const dev of devices) {
            const tr = document.createElement("tr");

            const tdName = document.createElement("td");
            tdName.textContent = dev.name;
            tr.appendChild(tdName);

            const tdCreated = document.createElement("td");
            tdCreated.textContent = formatTime(dev.created_at);
            tr.appendChild(tdCreated);

            const tdLastSeen = document.createElement("td");
            tdLastSeen.textContent = formatTime(dev.last_seen);
            tr.appendChild(tdLastSeen);

            const tdAction = document.createElement("td");
            const revokeBtn = document.createElement("button");
            revokeBtn.className = "revoke-btn";
            revokeBtn.textContent = "撤销";
            revokeBtn.addEventListener("click", () => revokeDevice(dev.key, tr));
            tdAction.appendChild(revokeBtn);
            tr.appendChild(tdAction);

            tbody.appendChild(tr);
        }
    } catch {
        // 忽略
    }
}

/** 格式化 ISO 时间戳为可读时间 */
function formatTime(iso) {
    if (!iso) return "--";
    try {
        const d = new Date(iso);
        return d.toLocaleString("zh-CN", {
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
        });
    } catch {
        return iso;
    }
}

/** 撤销设备授权 */
async function revokeDevice(key, rowEl) {
    if (!confirm("确定要撤销此设备的授权吗？")) return;

    try {
        const resp = await authFetch(`/api/devices/${encodeURIComponent(key)}`, {
            method: "DELETE",
        });
        const data = await resp.json();
        if (data.success) {
            // 如果撤销的是自己，清除本地存储并回到配对页
            if (key === storedKey()) {
                localStorage.removeItem(DEVICE_KEY_STORAGE);
                // 刷新页面回到初始状态
                location.reload();
            } else {
                rowEl.remove();
                // 检查是否还有设备
                const tbody = document.getElementById("device-tbody");
                if (tbody.children.length === 0) {
                    document.getElementById("device-empty").style.display = "";
                }
            }
        }
    } catch {
        // 忽略
    }
}

// ---- 初始化 ----

async function init() {
    // 先检查配对状态
    try {
        const data = await refreshPairingCode();

        // 情况 1：本地有 device_key → 直接进入控制面板
        if (storedKey()) {
            showDashboard();
            return;
        }

        // 情况 2：无本地 key，显示配对页
        showPairingPage();
        setupCodeInputs();
        document.getElementById("pair-btn").addEventListener("click", handlePair);

        // 首次刷新配对码显示
        if (data && data.code) {
            document.getElementById("pairing-code").textContent = data.code;
        }

        // 启动轮询
        pairingPollTimer = setInterval(pollPairingCode, POLL_INTERVAL);
    } catch {
        // 网络不可达时仍然显示配对页，让用户稍后重试
        showPairingPage();
        setupCodeInputs();
        document.getElementById("pair-btn").addEventListener("click", handlePair);
        pairingPollTimer = setInterval(pollPairingCode, POLL_INTERVAL);
    }
}

// 页面加载完成后初始化
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
} else {
    init();
}
