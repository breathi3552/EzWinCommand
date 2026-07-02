"""EzWinCommand 端到端测试 — 使用系统 Edge 浏览器。

启动服务 → API 测试 → 浏览器自动化 → 截图验证 → 关闭。
"""
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# ── 配置 ──────────────────────────────────────────────
PORT = 8080
BASE = f"http://127.0.0.1:{PORT}"
TIMEOUT_START = 20   # 服务启动超时（秒）
POLL_INTERVAL = 0.5  # 轮询间隔（秒）
PROJECT_DIR = Path(__file__).resolve().parent
SCREENSHOT_DIR = PROJECT_DIR / "test_screenshots"

# ── 工具函数 ──────────────────────────────────────────

def _req(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    """发送 HTTP 请求，返回 (status_code, json_body)。"""
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception:
        return 0, {}


def _ok(cond: bool, tag: str) -> str:
    return f"  {cond and 'PASS' or 'FAIL'}  {tag}"


# ── 1. 启动服务 ──────────────────────────────────────

print("=" * 60)
print("EzWinCommand E2E Test (Edge 浏览器)")
print("=" * 60)

print("\n[1/4] 启动服务...")
env = os.environ.copy()
env["PYTHONUNBUFFERED"] = "1"

proc = subprocess.Popen(
    [sys.executable, "app.py"],
    cwd=str(PROJECT_DIR),
    env=env,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
)
print(f"  服务进程 PID={proc.pid}")

# 轮询 /ping
started = False
deadline = time.time() + TIMEOUT_START
while time.time() < deadline:
    if proc.poll() is not None:
        print(f"  服务异常退出，退出码={proc.returncode}")
        break
    try:
        with urllib.request.urlopen(f"{BASE}/ping", timeout=2) as resp:
            if resp.status == 200:
                started = True
                break
    except Exception:
        pass
    time.sleep(POLL_INTERVAL)

if not started:
    print("  FAIL: 服务未在时间内就绪")
    proc.kill()
    proc.wait()
    sys.exit(1)
print("  PASS: 服务就绪")

# ── 2. API 测试 ──────────────────────────────────────

print("\n[2/4] API 测试")

passes = 0
fails = 0

def test(name: str, cond: bool, detail: str = ""):
    global passes, fails
    if cond:
        passes += 1
        print(f"  PASS: {name} {detail}")
    else:
        fails += 1
        print(f"  FAIL: {name} {detail}")

# 2a. GET /ping
code, body = _req("GET", "/ping")
test("GET /ping → 200", code == 200, f"got {code}")
test("GET /ping body status=ok", body.get("status") == "ok", f"body={body}")

# 2b. GET /api/actions
code, body = _req("GET", "/api/actions")
test("GET /api/actions → 200", code == 200, f"got {code}")
actions = body.get("actions", [])
action_names = {a["name"] for a in actions}
for required in ("calculator", "player", "volume"):
    test(f"  actions 含 '{required}'", required in action_names, f"found: {sorted(action_names)}")

# 2c. POST /api/command {"action":"calculator"} → success=true
code, body = _req("POST", "/api/command", {"action": "calculator"})
test("POST calculator → 200", code == 200, f"got {code}")
test("POST calculator success=true", body.get("success") is True, f"body={body}")

print(f"\n  API 结果: {passes} pass, {fails} fail")
if fails:
    print("  API 测试失败，中止")
    proc.terminate()
    proc.wait()
    sys.exit(1)

# ── 3. 浏览器测试 (Playwright + Edge) ────────────────

print("\n[3/4] 浏览器测试 (Edge — 可见窗口)...")

SCREENSHOT_DIR.mkdir(exist_ok=True)

from playwright.sync_api import sync_playwright

browser_pass = 0
browser_fail = 0

def btest(name: str, cond: bool, detail: str = ""):
    global browser_pass, browser_fail
    if cond:
        browser_pass += 1
        print(f"  PASS: {name} {detail}")
    else:
        browser_fail += 1
        print(f"  FAIL: {name} {detail}")

try:
    pw = sync_playwright().start()

    # 使用系统 Edge，headless=False 让用户看到窗口
    browser = pw.chromium.launch(
        channel="msedge",
        headless=False,
    )
    print(f"  Edge 浏览器版本: {browser.version}")

    context = browser.new_context()
    page = context.new_page()

    # 打开页面
    page.goto(f"{BASE}/", timeout=15_000, wait_until="networkidle")
    btest("页面加载成功", True, f"URL: {page.url}")

    # 标题
    title = page.title()
    btest("页面标题为 'EzWinCommand'", title == "EzWinCommand", f"got: {title!r}")

    # 状态面板
    status_div = page.locator("#status")
    btest("状态面板 #status 存在", status_div.count() > 0)
    cpu_el = page.locator("#cpu")
    memory_el = page.locator("#memory")
    btest("CPU 显示 #cpu 存在", cpu_el.count() > 0)
    btest("内存显示 #memory 存在", memory_el.count() > 0)

    # 等待 status 和 actions 加载（JS fetch）
    page.wait_for_timeout(2000)
    cpu_text = cpu_el.text_content()
    memory_text = memory_el.text_content()
    btest("CPU 值非空且非'--'", cpu_text not in ("", "--", None), f"cpu={cpu_text}")
    btest("内存值非空且非'--'", memory_text not in ("", "--", None), f"mem={memory_text}")

    # 插件按钮
    actions_div = page.locator("#actions")
    btest("插件面板 #actions 存在", actions_div.count() > 0)
    cards = page.locator(".plugin-card")
    btest("至少一个 .plugin-card", cards.count() >= 1, f"共 {cards.count()} 个卡片")

    # 查找计算器按钮
    calc_button = page.locator("button:has-text('计算器')")
    if calc_button.count() == 0:
        # 可能文本不在 button 内，查找 plugin-card 内含"计算器"
        calc_button = page.locator(".plugin-card:has-text('计算器') button")
    btest("计算器按钮存在", calc_button.count() >= 1, f"找到 {calc_button.count()} 个")

    # ── 截图 1：初始状态 ──
    shot1 = str(SCREENSHOT_DIR / "01_initial.png")
    page.screenshot(path=shot1, full_page=True)
    print(f"  截图已保存: {shot1}")

    # ── 点击计算器 ──
    if calc_button.count() >= 1:
        calc_button.first.click()
        print(f"  已点击计算器按钮")
        # 给一点时间让 POST 发出
        page.wait_for_timeout(2000)

    # ── 截图 2：点击后状态 ──
    shot2 = str(SCREENSHOT_DIR / "02_after_calculator.png")
    page.screenshot(path=shot2, full_page=True)
    print(f"  截图已保存: {shot2}")

    # 关闭浏览器
    context.close()
    browser.close()
    pw.stop()

    print(f"\n  浏览器结果: {browser_pass} pass, {browser_fail} fail")

except Exception as exc:
    print(f"  FAIL: 浏览器测试异常: {exc}")
    browser_fail += 1

# ── 4. 关闭服务 ──────────────────────────────────────

print("\n[4/4] 关闭服务...")
proc.terminate()
try:
    proc.wait(timeout=5)
    print("  服务已正常退出")
except subprocess.TimeoutExpired:
    proc.kill()
    proc.wait()
    print("  服务被强制结束")

# ── 总结 ──────────────────────────────────────────────

total_pass = passes + browser_pass
total_fail = fails + browser_fail
total = total_pass + total_fail

print()
print("=" * 60)
print(f"测试完成: {total_pass}/{total} PASS")
if total_fail:
    print(f"           {total_fail}/{total} FAIL")
print(f"截图目录: {SCREENSHOT_DIR}")
print("=" * 60)

sys.exit(0 if total_fail == 0 else 1)
