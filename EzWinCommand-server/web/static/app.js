// ============================================================
// EzWinCommand Web UI — 双模式：PC 管理面板 / 外部页面
// ============================================================

const DEVICE_KEY_STORAGE = "ez_device_key";
const DEVICE_POLL_MS = 30000;    // 外部设备列表轮询间隔

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
const COMMAND_POLL_INTERVAL_MS = 1000;
const COMMAND_POLL_LIMIT = 60;
const pendingCommandTimers = new Map();
function pendingCommandKey(action, params) { return `ez_pending_command_${action}_${params && params.sub_action ? params.sub_action : ""}`; }
function commandStatusMessage(status) { return status.status === "succeeded" ? (status.message || "命令执行成功") : ((status.error && status.error.message) || status.message || "命令执行失败"); }
const pendingCommandInflight = new Map();
async function submitAndTrackCommand(action, params = {}, opts = {}) {
    const key = pendingCommandKey(action, params);
    const active = pendingCommandInflight.get(key);
    if (active) return active;
    const run = (async () => {
        const { errorElementId = "ext-error", authorized = false } = opts;
        const request = { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action, params }) };
        let resp, data;
        const existing = sessionStorage.getItem(key);
        if (existing) {
            resp = { status: 202, ok: true };
            data = { command_id: existing, status: "queued" };
        } else {
            resp = authorized ? await authFetch("/api/command", request) : await fetch("/api/command", request);
            data = await resp.json().catch(() => ({}));
        }
        if (resp.status === 401 || resp.status === 403) {
            if (authorized) { clearStoredKey(); setUiError(errorElementId, "授权已失效，请重新配对"); await extReturnToPairing(); }
            throw new Error("授权已失效，请重新配对");
        }
        if (!resp.ok) { const msg = data.message || data.detail || `请求失败 (${resp.status})`; setUiError(errorElementId, msg); throw new Error(msg); }
        if (resp.status !== 202) { console.log(action, data); return; }
        const id = data.command_id;
        if (!id) throw new Error("服务器未返回 command_id");
        sessionStorage.setItem(key, id);
        setUiError(errorElementId, "已提交，正在执行…");
        const deadlineNow = () => (typeof performance !== "undefined" && typeof performance.now === "function") ? performance.now() : Date.now();
        const deadlineAt = deadlineNow() + COMMAND_POLL_LIMIT * COMMAND_POLL_INTERVAL_MS;
        return await new Promise((resolve, reject) => {
            let timer = null;
            let settled = false;
            let activeController = null;
            const finish = (value, error = null) => {
                if (settled) return;
                settled = true;
                clearTimeout(timer);
                if (activeController) {
                    try { activeController.abort(); } catch (_) { /* ignore */ }
                    activeController = null;
                }
                pendingCommandTimers.delete(key);
                error ? reject(error) : resolve(value);
            };
            const softTimeout = () => {
                setUiError(errorElementId, "仍在服务端执行，可稍后继续查询");
                finish({ status: "queued", command_id: id });
            };
            const poll = async () => {
                if (settled) return;
                const remainingBefore = deadlineAt - deadlineNow();
                if (remainingBefore <= 0) {
                    softTimeout();
                    return;
                }
                const controller = new AbortController();
                activeController = controller;
                // 单次请求只受总 deadline 剩余时间约束；轮询间隔仅用于终态前的等待。
                const abortTimer = setTimeout(() => {
                    try { controller.abort(); } catch (_) { /* ignore */ }
                }, Math.max(1, remainingBefore));
                try {
                    const fetchOpts = { signal: controller.signal };
                    const r = authorized
                        ? await authFetch(`/api/commands/${encodeURIComponent(id)}`, fetchOpts)
                        : await fetch(`/api/commands/${encodeURIComponent(id)}`, fetchOpts);
                    if (settled) return;
                    const s = await r.json().catch(() => ({}));
                    if (deadlineNow() >= deadlineAt) {
                        softTimeout();
                        return;
                    }
                    if (r.status === 404) {
                        sessionStorage.removeItem(key);
                        setUiError(errorElementId, "命令已过期，请重新提交");
                        finish(null, new Error("命令已过期，请重新提交"));
                        return;
                    }
                    if (r.status === 401 || r.status === 403) {
                        if (authorized) {
                            clearStoredKey();
                            setUiError(errorElementId, "授权已失效，请重新配对");
                            await extReturnToPairing();
                        }
                        finish(null, new Error("授权已失效，请重新配对"));
                        return;
                    }
                    if (!r.ok) throw new Error(s.message || s.detail || `请求失败 (${r.status})`);
                    if (s.status === "succeeded" || s.status === "failed") {
                        sessionStorage.removeItem(key);
                        setUiError(errorElementId, commandStatusMessage(s));
                        console.log(action, s);
                        finish(s);
                        return;
                    }
                } catch (e) {
                    if (settled) return;
                    if (deadlineNow() >= deadlineAt) {
                        softTimeout();
                        return;
                    }
                    // abort/network 错误：未到总 deadline 时继续下一轮
                } finally {
                    clearTimeout(abortTimer);
                    if (activeController === controller) activeController = null;
                }
                if (settled) return;
                const remaining = deadlineAt - deadlineNow();
                if (remaining <= 0) {
                    softTimeout();
                    return;
                }
                timer = setTimeout(poll, Math.min(COMMAND_POLL_INTERVAL_MS, remaining));
                pendingCommandTimers.set(key, timer);
            };
            poll();
        });
    })();
    pendingCommandInflight.set(key, run);
    try { return await run; } finally { pendingCommandInflight.delete(key); }
}

// ============================================================
// PC 管理面板
// ============================================================

let pcEventSource = null;
let pcPairingExpiryTimer = null;
async function pcFetchPairings() { return fetchJson("/api/local/pairings", {}, "pc-error"); }
function pcPairingStatus(status) {
    return {
        pending: "等待输入",
        locked: "已锁定",
        consumed: "已完成",
        cancelled: "已取消",
        expired: "已过期",
    }[status] || "状态未知";
}

function pcPairingShortId(pairingId) {
    const value = String(pairingId || "");
    return value ? value.slice(0, 8) : "未知";
}

function pcRenderPairings(data) {
    const root = document.getElementById("pc-pairing-list");
    if (!root) return;
    clearTimeout(pcPairingExpiryTimer);
    pcPairingExpiryTimer = null;
    root.replaceChildren();
    const pairings = ((data && Array.isArray(data.pairings)) ? data.pairings : [])
        .filter(pairing => pairing.status === "pending" || pairing.status === "locked");
    if (pairings.length === 0) {
        const empty = document.createElement("p");
        empty.className = "pairing-empty";
        empty.textContent = "等待手机发起配对";
        root.appendChild(empty);
        return;
    }
    const nextExpiry = Math.min(...pairings.map(pairing => Math.max(0, Number(pairing.expires_in) || 0)));
    pcPairingExpiryTimer = setTimeout(pcRefreshPairings, (nextExpiry + 1) * 1000);

    for (const pairing of pairings) {
        const card = document.createElement("article");
        card.className = "pairing-card pairing-card--active";

        const header = document.createElement("div");
        header.className = "pairing-header";
        const deviceName = document.createElement("strong");
        deviceName.className = "pairing-device-name";
        deviceName.textContent = pairing.device_name || "Android";
        const pairingId = document.createElement("span");
        pairingId.className = "pairing-id";
        pairingId.textContent = `配对 ${pcPairingShortId(pairing.pairing_id)}`;
        header.append(deviceName, pairingId);
        card.appendChild(header);

        const code = String(pairing.code || "");
        if (/^\d{4}$/.test(code)) {
            const codeElement = document.createElement("div");
            codeElement.className = "pairing-code";
            codeElement.textContent = code;
            codeElement.setAttribute("aria-label", "四位配对验证码");
            card.appendChild(codeElement);
        }

        const meta = document.createElement("div");
        meta.className = "pairing-meta";
        const countdown = document.createElement("span");
        countdown.className = "pairing-countdown";
        countdown.textContent = `剩余 ${Math.max(0, Number(pairing.expires_in) || 0)} 秒`;
        meta.appendChild(countdown);
        const status = document.createElement("span");
        status.className = `pairing-status pairing-status--${String(pairing.status || "unknown")}`;
        status.textContent = pcPairingStatus(pairing.status);
        meta.appendChild(status);
        card.appendChild(meta);
        root.appendChild(card);
    }
}
async function pcRefreshPairings() { pcRenderPairings(await pcFetchPairings()); }

function pcRefreshSnapshots() {
    pcRefreshPairings();
    pcLoadDevices();
}

function pcStartEvents() {
    if (pcEventSource) pcEventSource.close();
    pcEventSource = new EventSource("/api/local/events");
    pcEventSource.addEventListener("open", pcRefreshSnapshots);
    pcEventSource.addEventListener("changed", event => {
        try {
            const domains = JSON.parse(event.data).domains || [];
            if (domains.includes("pairings")) pcRefreshPairings();
            if (domains.includes("devices")) pcLoadDevices();
        } catch (error) {
            console.error("管理事件解析失败:", error);
            pcRefreshSnapshots();
        }
    });
}

// ---- PC 设备管理 ----

/** 加载设备列表（PC 端，无需鉴权） */
async function pcLoadDevices() {
    try {
        const data = await fetchJson("/api/devices");
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
            pcLoadDevices();
        } else {
            setUiError("pc-error", data.message || "撤销设备失败");
        }
    } catch {
        // 错误已在页面显示
    }
}

// ---- PC 控制面板 ----


/** 加载操作按钮（PC 端，无需鉴权） */
async function pcLoadActions() {
    try {
        const data = await fetchJson("/api/actions", {}, "pc-error");
        renderPluginCards("pc-actions", data.actions, pcSendCommand);
    } catch {
        // 错误已在页面显示
    }
}

/** 发送命令（PC 端，无需鉴权） */
async function pcSendCommand(action, params = {}) {
    try { await submitAndTrackCommand(action, params, { errorElementId: "pc-error" }); }
    catch (e) { console.error("命令发送失败:", e); }
}

/** 初始化 PC 管理面板 */
async function initPCPanel() {
    document.getElementById("pc-panel").style.display = "";

    document.getElementById("pc-refresh-btn").addEventListener("click", pcRefreshPairings);
    pcStartEvents();

    // 加载操作按钮
    pcLoadActions();
}

// ============================================================
// 外部页面
// ============================================================

/** 远程页面不得读取仅限 localhost 的配对码接口。 */

/** 显示配对待机页 */
function extShowStandby() {
    document.getElementById("ext-standby").style.display = "";
    document.getElementById("ext-dashboard").style.display = "none";
}

/** 未授权远程页面保持等待状态，配对由 Android App 发起。 */

/** 显示外部控制面板 */
function extShowDashboard() {
    document.getElementById("ext-standby").style.display = "none";
    document.getElementById("ext-dashboard").style.display = "";
    extLoadActions();
    extLoadDevices();
    setInterval(extLoadDevices, DEVICE_POLL_MS);
}

function extReturnToPairing() {
    extShowStandby();
}

// ---- 外部控制面板 ----


async function extLoadActions() {
    try {
        const data = await authFetchJson("/api/actions");
        renderPluginCards("ext-actions", data.actions, extSendCommand);
    } catch {
        // 错误已在页面显示
    }
}

async function extSendCommand(action, params = {}) {
    try { await submitAndTrackCommand(action, params, { errorElementId: "ext-error", authorized: true }); }
    catch (e) { console.error("命令发送失败:", e); }
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

    // 情况 1：本地有 device_key → 先用 /api/actions 校验，再进入控制面板
    if (storedKey()) {
        try {
            await authFetchJson("/api/actions");
            extShowDashboard();
            return;
        } catch {
            clearStoredKey();
        }
    }

    // 情况 2：无有效本地 key，保持待机；配对请求与验证码由 Android App / PC 本机页处理
    extReturnToPairing();
}


/** 归一化插件数据：兼容旧字段 {name,label,sub_actions} 与新字段 {description,version,actions} */
function normalizePlugin(plugin) {
    const subActions = Array.isArray(plugin.sub_actions) ? plugin.sub_actions
        : Array.isArray(plugin.actions) ? plugin.actions
        : [];
    return {
        name: plugin.name,
        label: plugin.label || plugin.name,
        description: plugin.description || "",
        version: plugin.version || "",
        sub_actions: subActions,
    };
}

/** 共享渲染：将 actions 列表渲染为插件卡片，填入 containerId 容器 */
function renderPluginCards(containerId, actions, sendCommand) {
    const container = document.getElementById(containerId);
    container.innerHTML = "";

    if (!actions || actions.length === 0) {
        const empty = document.createElement("p");
        empty.className = "plugin-empty";
        empty.textContent = "暂无可用插件";
        container.appendChild(empty);
        return;
    }

    for (const raw of actions) {
        const plugin = normalizePlugin(raw);
        const card = document.createElement("div");
        card.className = "plugin-card";

        // 标题 + 说明提示
        const title = document.createElement("h3");
        title.className = "plugin-title";

        const titleText = document.createElement("span");
        titleText.textContent = plugin.label;
        title.appendChild(titleText);

        if (plugin.description || plugin.version) {
            const tip = document.createElement("span");
            tip.className = "plugin-info";
            tip.textContent = "i";
            tip.tabIndex = 0;
            tip.setAttribute("aria-label", "插件说明");
            const tipLines = [];
            if (plugin.description) tipLines.push(plugin.description);
            if (plugin.version) tipLines.push("版本: " + plugin.version);
            tip.setAttribute("data-tooltip", tipLines.join("\n"));
            title.appendChild(tip);
        }

        card.appendChild(title);

        // 子操作按钮
        const subActions = plugin.sub_actions;
        if (subActions.length === 0) {
            const btn = document.createElement("button");
            btn.textContent = plugin.label;
            btn.addEventListener("click", () => sendCommand(plugin.name));
            card.appendChild(btn);
        } else {
            const group = document.createElement("div");
            group.className = "plugin-actions";
            for (const sub of subActions) {
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
