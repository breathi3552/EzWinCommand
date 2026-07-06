// ============================================================
// EzWinCommand Web UI — 双模式：PC 管理面板 / 外部页面
// ============================================================

const DEVICE_KEY_STORAGE = "ez_device_key";
const PC_CODE_POLL_MS = 3000;   // PC 端配对码服务器轮询间隔
const EXT_POLL_MS = 3000;        // 外部页面配对码轮询间隔
const COUNTDOWN_TICK_MS = 1000;  // 倒计时每秒更新
const STATUS_POLL_MS = 5000;     // 系统状态轮询间隔
const DEVICE_POLL_MS = 30000;    // 设备列表轮询间隔

// ============================================================
// 工具函数
// ============================================================

/** 判断是否为 PC 端（localhost 访问） */
function isPC() {
    const hostname = location.hostname;
    return hostname === "127.0.0.1" || hostname === "::1" || hostname === "localhost";
}

/** 获取当前已存储的设备密钥 */
function storedKey() {
    return localStorage.getItem(DEVICE_KEY_STORAGE);
}

/** 构造带鉴权的 fetch headers */
function authHeaders(extra = {}) {
    const key = storedKey();
    const headers = { ...extra };
    if (key) {
        headers["Authorization"] = "Bearer " + key;
    }
    return headers;
}

/** 清除当前设备密钥 */
function clearStoredKey() {
    localStorage.removeItem(DEVICE_KEY_STORAGE);
}

/** 显示可见错误信息 */
function setUiError(elementId, message) {
    const el = document.getElementById(elementId);
    if (el) {
        el.textContent = message || "";
    }
}

/** 普通 JSON fetch：检查 HTTP 状态并解析错误消息 */
async function fetchJson(url, options = {}, errorElementId = null) {
    const resp = await fetch(url, options);
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
        const message = data.message || `请求失败 (${resp.status})`;
        if (errorElementId) setUiError(errorElementId, message);
        throw new Error(message);
    }
    if (errorElementId) setUiError(errorElementId, "");
    return data;
}

/** 带鉴权的 fetch 封装 */
async function authFetch(url, options = {}) {
    const headers = authHeaders(options.headers || {});
    return fetch(url, { ...options, headers });
}

/** 带鉴权的 JSON fetch：401/403 时清除本地 key 并回到配对流程 */
async function authFetchJson(url, options = {}, errorElementId = "ext-error") {
    const resp = await authFetch(url, options);
    const data = await resp.json().catch(() => ({}));
    if (resp.status === 401 || resp.status === 403) {
        clearStoredKey();
        setUiError(errorElementId, "授权已失效，请重新配对");
        await extReturnToPairing();
        throw new Error("授权已失效，请重新配对");
    }
    if (!resp.ok) {
        const message = data.message || `请求失败 (${resp.status})`;
        setUiError(errorElementId, message);
        throw new Error(message);
    }
    setUiError(errorElementId, "");
    return data;
}

// ============================================================
// PC 管理面板
// ============================================================

let pcCountdownTimer = null;   // 倒计时定时器 ID
let pcCountdownRemain = 0;     // 剩余秒数
let pcPollTimer = null;        // 服务器轮询定时器 ID

/** 获取当前配对码信息 */
async function pcFetchPairingCode() {
    try {
        return await fetchJson("/api/pairing-code", {}, "pc-error");
    } catch {
        return null;
    }
}

/** 刷新（生成）配对码 */
async function pcRefreshPairingCode() {
    try {
        return await fetchJson("/api/pairing-code/refresh", { method: "POST" }, "pc-error");
    } catch {
        return null;
    }
}

/** 显示配对码区域（有码状态） */
function pcShowPairingActive(code) {
    document.getElementById("pc-pairing-empty").style.display = "none";
    document.getElementById("pc-pairing-active").style.display = "";
    document.getElementById("pc-pairing-code").textContent = code;
}

/** 显示配对码区域（无码状态） */
function pcShowPairingEmpty() {
    document.getElementById("pc-pairing-empty").style.display = "";
    document.getElementById("pc-pairing-active").style.display = "none";
    document.getElementById("pc-pairing-code").textContent = "";
    document.getElementById("pc-countdown").textContent = "05:00";
}

/** 格式化秒数为 MM:SS */
function pcFormatCountdown(seconds) {
    const m = Math.floor(Math.max(0, seconds) / 60);
    const s = Math.max(0, seconds) % 60;
    return String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0");
}

/** 启动倒计时 */
function pcStartCountdown(seconds) {
    pcStopCountdown();
    pcCountdownRemain = seconds;
    document.getElementById("pc-countdown").textContent = pcFormatCountdown(seconds);

    pcCountdownTimer = setInterval(() => {
        pcCountdownRemain--;
        document.getElementById("pc-countdown").textContent = pcFormatCountdown(pcCountdownRemain);

        if (pcCountdownRemain <= 0) {
            pcStopCountdown();
            pcStopPolling();
            pcShowPairingEmpty();
        }
    }, COUNTDOWN_TICK_MS);
}

/** 停止倒计时 */
function pcStopCountdown() {
    if (pcCountdownTimer) {
        clearInterval(pcCountdownTimer);
        pcCountdownTimer = null;
    }
    pcCountdownRemain = 0;
}

/** 启动服务器轮询（同步过期状态） */
function pcStartPolling() {
    pcStopPolling();
    pcPollTimer = setInterval(async () => {
        const data = await pcFetchPairingCode();
        if (!data || !data.code) {
            // 服务器端已过期或无码
            pcStopCountdown();
            pcStopPolling();
            pcShowPairingEmpty();
        }
    }, PC_CODE_POLL_MS);
}

/** 停止服务器轮询 */
function pcStopPolling() {
    if (pcPollTimer) {
        clearInterval(pcPollTimer);
        pcPollTimer = null;
    }
}

/** 处理「生成配对码」按钮 */
async function pcHandleGenerate() {
    const btn = document.getElementById("pc-generate-btn");
    btn.disabled = true;
    btn.textContent = "生成中…";

    const data = await pcRefreshPairingCode();
    btn.disabled = false;
    btn.textContent = "生成配对码";

    if (data && data.code) {
        pcShowPairingActive(data.code);
        const expiresIn = data.expires_in || 300;
        pcStartCountdown(expiresIn);
        pcStartPolling();
    }
}

/** 处理「刷新」按钮 */
async function pcHandleRefresh() {
    const btn = document.getElementById("pc-refresh-btn");
    btn.disabled = true;
    btn.textContent = "刷新中…";

    const data = await pcRefreshPairingCode();
    btn.disabled = false;
    btn.textContent = "刷新";

    if (data && data.code) {
        document.getElementById("pc-pairing-code").textContent = data.code;
        const expiresIn = data.expires_in || 300;
        pcStartCountdown(expiresIn);
    }
}

// ---- PC 设备管理 ----

/** 加载设备列表（PC 端，无需鉴权） */
async function pcLoadDevices() {
    try {
        const data = await fetchJson("/api/devices", {}, "pc-error");
        const tbody = document.getElementById("pc-device-tbody");
        const emptyEl = document.getElementById("pc-device-empty");
        tbody.innerHTML = "";

        const devices = data.devices || [];
        if (devices.length === 0) {
            emptyEl.style.display = "";
            return;
        }
        emptyEl.style.display = "none";

        for (const dev of devices) {
            const tr = document.createElement("tr");

            // 设备名（可点击编辑）
            const tdName = document.createElement("td");
            tdName.className = "device-name-cell";
            const nameSpan = document.createElement("span");
            nameSpan.textContent = dev.name;
            nameSpan.className = "device-name-text";
            nameSpan.title = "点击编辑名称";
            nameSpan.addEventListener("click", () => pcStartRename(dev.key, dev.name, nameSpan));
            tdName.appendChild(nameSpan);
            tr.appendChild(tdName);

            // 最后活跃
            const tdLastSeen = document.createElement("td");
            tdLastSeen.textContent = formatTime(dev.last_seen);
            tr.appendChild(tdLastSeen);

            // 操作
            const tdAction = document.createElement("td");
            const revokeBtn = document.createElement("button");
            revokeBtn.className = "revoke-btn";
            revokeBtn.textContent = "撤销";
            revokeBtn.addEventListener("click", () => pcRevokeDevice(dev.key, tr));
            tdAction.appendChild(revokeBtn);
            tr.appendChild(tdAction);

            tbody.appendChild(tr);
        }
    } catch {
        // 错误已在页面显示
    }
}

/** 开始重命名：将 span 替换为 input */
function pcStartRename(key, currentName, spanEl) {
    // 如果已有编辑中的 input，先取消
    const existing = document.querySelector(".device-name-input");
    if (existing) {
        pcCancelRename(existing);
    }

    const input = document.createElement("input");
    input.type = "text";
    input.className = "device-name-input";
    input.value = currentName;
    input.setAttribute("data-device-key", key);
    input.setAttribute("data-original-name", currentName);

    spanEl.replaceWith(input);
    input.focus();
    input.select();

    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            pcCommitRename(input);
        } else if (e.key === "Escape") {
            pcCancelRename(input);
        }
    });
    input.addEventListener("blur", () => {
        // 延迟执行，让 Enter/Escape 先触发
        setTimeout(() => {
            if (document.body.contains(input)) {
                pcCancelRename(input);
            }
        }, 150);
    });
}

/** 提交重命名 */
async function pcCommitRename(inputEl) {
    const key = inputEl.getAttribute("data-device-key");
    const newName = inputEl.value.trim();
    const originalName = inputEl.getAttribute("data-original-name");

    if (!newName || newName === originalName) {
        pcCancelRename(inputEl);
        return;
    }

    try {
        const data = await fetchJson("/api/devices/" + encodeURIComponent(key), {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: newName }),
        }, "pc-error");
        if (data.success) {
            pcLoadDevices();
        } else {
            setUiError("pc-error", data.message || "重命名失败");
            pcCancelRename(inputEl);
        }
    } catch {
        pcCancelRename(inputEl);
    }
}

/** 取消重命名，恢复为 span */
function pcCancelRename(inputEl) {
    const originalName = inputEl.getAttribute("data-original-name");
    const span = document.createElement("span");
    span.textContent = originalName;
    span.className = "device-name-text";
    span.title = "点击编辑名称";
    const key = inputEl.getAttribute("data-device-key");
    span.addEventListener("click", () => pcStartRename(key, originalName, span));
    inputEl.replaceWith(span);
}

/** 撤销设备授权 */
async function pcRevokeDevice(key, rowEl) {
    if (!confirm("确定要撤销此设备的授权吗？")) return;

    try {
        const data = await fetchJson("/api/devices/" + encodeURIComponent(key), {
            method: "DELETE",
        }, "pc-error");
        if (data.success) {
            rowEl.remove();
            const tbody = document.getElementById("pc-device-tbody");
            if (tbody.children.length === 0) {
                document.getElementById("pc-device-empty").style.display = "";
            }
        } else {
            setUiError("pc-error", data.message || "撤销设备失败");
        }
    } catch {
        // 错误已在页面显示
    }
}

// ---- PC 控制面板 ----

/** 加载系统状态（PC 端，无需鉴权） */
async function pcLoadStatus() {
    try {
        const data = await fetchJson("/api/status", {}, "pc-error");
        document.getElementById("pc-cpu").textContent = data.cpu_percent.toFixed(1);
        document.getElementById("pc-memory").textContent = data.memory.percent.toFixed(1);
    } catch {
        // 错误已在页面显示
    }
}

/** 加载操作按钮（PC 端，无需鉴权） */
async function pcLoadActions() {
    try {
        const data = await fetchJson("/api/actions", {}, "pc-error");
        const container = document.getElementById("pc-actions");
        container.innerHTML = "";

        for (const plugin of data.actions) {
            const card = document.createElement("div");
            card.className = "plugin-card";

            const title = document.createElement("h3");
            title.textContent = plugin.label;
            card.appendChild(title);

            const subActions = Array.isArray(plugin.sub_actions) ? plugin.sub_actions : [];

            if (subActions.length === 0) {
                const btn = document.createElement("button");
                btn.textContent = plugin.label;
                btn.addEventListener("click", () =>
                    pcSendCommand(plugin.name)
                );
                card.appendChild(btn);
            } else {
                const group = document.createElement("div");
                group.className = "btn-group";

                for (const sub of subActions) {
                    const btn = document.createElement("button");
                    btn.textContent = sub.label;
                    btn.addEventListener("click", () =>
                        pcSendCommand(plugin.name, { sub_action: sub.id })
                    );
                    group.appendChild(btn);
                }
                card.appendChild(group);
            }

            container.appendChild(card);
        }
    } catch {
        // 错误已在页面显示
    }
}

/** 发送命令（PC 端，无需鉴权） */
async function pcSendCommand(action, params = {}) {
    try {
        const result = await fetchJson("/api/command", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action, params }),
        }, "pc-error");
        console.log(action, result);
    } catch (e) {
        console.error("命令发送失败:", e);
    }
}

/** 初始化 PC 管理面板 */
async function initPCPanel() {
    document.getElementById("pc-panel").style.display = "";

    // 绑定按钮事件
    document.getElementById("pc-generate-btn").addEventListener("click", pcHandleGenerate);
    document.getElementById("pc-refresh-btn").addEventListener("click", pcHandleRefresh);

    // 加载配对码状态
    const data = await pcFetchPairingCode();
    if (data && data.code) {
        pcShowPairingActive(data.code);
        // 倒计时使用服务器返回的剩余秒数
        const expiresIn = data.expires_in || 300;
        pcStartCountdown(expiresIn);
        pcStartPolling();
    } else {
        pcShowPairingEmpty();
    }

    // 加载设备列表
    pcLoadDevices();
    setInterval(pcLoadDevices, DEVICE_POLL_MS);

    // 加载系统状态和操作
    pcLoadStatus();
    pcLoadActions();
    setInterval(pcLoadStatus, STATUS_POLL_MS);
}

// ============================================================
// 外部页面
// ============================================================

let extPollTimer = null;

/** 获取当前配对码信息 */
async function extFetchPairingCode() {
    try {
        return await fetchJson("/api/pairing-code");
    } catch {
        return null;
    }
}

/** 显示配对待机页 */
function extShowStandby() {
    document.getElementById("ext-standby").style.display = "";
    document.getElementById("ext-pairing").style.display = "none";
    document.getElementById("ext-dashboard").style.display = "none";
}

/** 显示配对输入页 */
function extShowPairing() {
    document.getElementById("ext-standby").style.display = "none";
    document.getElementById("ext-pairing").style.display = "";
    document.getElementById("ext-dashboard").style.display = "none";
}

/** 显示外部控制面板 */
function extShowDashboard() {
    extStopPolling();
    document.getElementById("ext-standby").style.display = "none";
    document.getElementById("ext-pairing").style.display = "none";
    document.getElementById("ext-dashboard").style.display = "";

    extLoadStatus();
    extLoadActions();
    extLoadDevices();
    setInterval(extLoadStatus, STATUS_POLL_MS);
    setInterval(extLoadDevices, DEVICE_POLL_MS);
}

/** 回到待机/配对流程 */
async function extReturnToPairing() {
    const data = await extFetchPairingCode();
    if (data && data.has_code) {
        extShowPairing();
    } else {
        extShowStandby();
        extStartPolling();
    }
}

// ---- 外部配对逻辑 ----

/** 处理配对码输入焦点跳转与粘贴 */
function setupCodeInputs() {
    const cells = document.querySelectorAll("#ext-pairing .code-cell");
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
        cell.addEventListener("paste", (e) => {
            e.preventDefault();
            const pasted = (e.clipboardData || window.clipboardData).getData("text").trim();
            const cleaned = pasted.replace(/[^0-9a-z]/gi, "").toLowerCase().slice(0, 4);
            for (let i = 0; i < 4; i++) {
                cells[i].value = cleaned[i] || "";
            }
            const focusIdx = Math.min(cleaned.length, 3);
            cells[focusIdx].focus();
        });
    });
}

/** 获取 4 位输入框拼合的配对码 */
function readPairingCode() {
    const cells = document.querySelectorAll("#ext-pairing .code-cell");
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
        const data = await fetchJson("/api/authorize", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ token: code, name: navigator.platform || "Web 浏览器" }),
        }, "pair-error");

        if (data.success && data.device_key) {
            localStorage.setItem(DEVICE_KEY_STORAGE, data.device_key);
            extStopPolling();
            extShowDashboard();
        } else {
            errorEl.textContent = data.message || "配对失败，请重试";
        }
    } catch (e) {
        errorEl.textContent = e.message || "网络错误，请检查连接";
    } finally {
        document.getElementById("pair-btn").disabled = false;
    }
}

/** 停止外部轮询 */
function extStopPolling() {
    if (extPollTimer) {
        clearInterval(extPollTimer);
        extPollTimer = null;
    }
}

/** 启动配对码轮询（待机页用） */
function extStartPolling() {
    extStopPolling();
    extPollTimer = setInterval(async () => {
        const data = await extFetchPairingCode();
        if (data && data.has_code) {
            // 配对码出现，切换到配对输入页；外部页面不显示配对码正文
            extStopPolling();
            extShowPairing();
        }
    }, EXT_POLL_MS);
}

// ---- 外部控制面板 ----

async function extLoadStatus() {
    try {
        const data = await authFetchJson("/api/status");
        document.getElementById("ext-cpu").textContent = data.cpu_percent.toFixed(1);
        document.getElementById("ext-memory").textContent = data.memory.percent.toFixed(1);
    } catch {
        // 错误已在页面显示
    }
}

async function extLoadActions() {
    try {
        const data = await authFetchJson("/api/actions");
        const container = document.getElementById("ext-actions");
        container.innerHTML = "";

        for (const plugin of data.actions) {
            const card = document.createElement("div");
            card.className = "plugin-card";

            const title = document.createElement("h3");
            title.textContent = plugin.label;
            card.appendChild(title);

            const subActions = Array.isArray(plugin.sub_actions) ? plugin.sub_actions : [];

            if (subActions.length === 0) {
                const btn = document.createElement("button");
                btn.textContent = plugin.label;
                btn.addEventListener("click", () =>
                    extSendCommand(plugin.name)
                );
                card.appendChild(btn);
            } else {
                const group = document.createElement("div");
                group.className = "btn-group";

                for (const sub of subActions) {
                    const btn = document.createElement("button");
                    btn.textContent = sub.label;
                    btn.addEventListener("click", () =>
                        extSendCommand(plugin.name, { sub_action: sub.id })
                    );
                    group.appendChild(btn);
                }
                card.appendChild(group);
            }

            container.appendChild(card);
        }
    } catch {
        // 错误已在页面显示
    }
}

async function extSendCommand(action, params = {}) {
    try {
        const result = await authFetchJson("/api/command", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action, params }),
        });
        console.log(action, result);
    } catch (e) {
        console.error("命令发送失败:", e);
    }
}

// ---- 外部设备管理 ----

async function extLoadDevices() {
    try {
        const data = await authFetchJson("/api/devices");
        const tbody = document.getElementById("ext-device-tbody");
        const emptyEl = document.getElementById("ext-device-empty");
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
            revokeBtn.addEventListener("click", () => extRevokeDevice(dev.key, tr));
            tdAction.appendChild(revokeBtn);
            tr.appendChild(tdAction);

            tbody.appendChild(tr);
        }
    } catch {
        // 错误已在页面显示
    }
}

async function extRevokeDevice(key, rowEl) {
    if (!confirm("确定要撤销此设备的授权吗？")) return;

    try {
        const data = await authFetchJson("/api/devices/" + encodeURIComponent(key), {
            method: "DELETE",
        });
        if (data.success) {
            if (key === storedKey()) {
                clearStoredKey();
                await extReturnToPairing();
            } else {
                rowEl.remove();
                const tbody = document.getElementById("ext-device-tbody");
                if (tbody.children.length === 0) {
                    document.getElementById("ext-device-empty").style.display = "";
                }
            }
        } else {
            setUiError("ext-error", data.message || "撤销设备失败");
        }
    } catch {
        // 错误已在页面显示
    }
}

// ---- 外部页面初始化 ----

async function initExternal() {
    document.getElementById("external-page").style.display = "";

    // 情况 1：本地有 device_key → 先用 /api/status 校验，再进入控制面板
    if (storedKey()) {
        try {
            await authFetchJson("/api/status");
            extShowDashboard();
            return;
        } catch {
            clearStoredKey();
        }
    }

    // 情况 2：无有效本地 key，检查是否有配对码
    await extReturnToPairing();

    // 绑定配对页事件
    setupCodeInputs();
    document.getElementById("pair-btn").addEventListener("click", handlePair);
}

// ============================================================
// 通用工具
// ============================================================

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

// ============================================================
// 入口
// ============================================================

async function init() {
    if (isPC()) {
        await initPCPanel();
    } else {
        await initExternal();
    }
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
} else {
    init();
}
