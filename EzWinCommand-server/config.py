"""配置管理：本地配置 + CLI 覆盖。

优先级（从低到高）：
  1. 默认值 0.0.0.0:8080
  2. .env（旧版兼容，低优先级）
  3. config.local.env（主配置文件，首次启动自动创建）
  4. CLI --host / --port 临时覆盖

模块级导出 HOST / PORT 供现有代码使用。
"""
from dataclasses import dataclass
from pathlib import Path

CONFIG_FILE = Path(__file__).resolve().parent / "config.local.env"
LEGACY_ENV_FILE = Path(__file__).resolve().parent / ".env"
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8080



@dataclass
class Settings:
    host: str
    port: int


# ── 内部实现 ──


def _auto_create_config() -> None:
    """若 config.local.env 不存在则创建；存在旧 .env 时迁移 HOST/PORT。"""
    if CONFIG_FILE.exists():
        return
    legacy = _parse_env_file(LEGACY_ENV_FILE)
    host = legacy.get("HOST", DEFAULT_HOST)
    port = legacy.get("PORT", str(DEFAULT_PORT))
    CONFIG_FILE.write_text(
        "# 本地配置（首次启动自动生成，不提交 Git）\n"
        "# HOST=0.0.0.0 表示允许局域网设备访问；如只允许本机访问可改为 127.0.0.1\n"
        f"HOST={host}\n"
        "# 默认端口\n"
        f"PORT={port}\n",
        encoding="utf-8",
    )


def _parse_env_value(value: str) -> str:
    """解析基础 dotenv 值，兼容单/双引号包裹。"""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _parse_env_file(path: Path) -> dict[str, str]:
    """读取 KEY=VALUE 文件，跳过注释和空行。"""
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            result[k.strip()] = _parse_env_value(v)
    return result

def _normalize_host(value: str) -> str:
    """校验并标准化监听地址。"""
    host = value.strip()
    if not host:
        raise ValueError("HOST 不能为空")
    return host


def parse_port(value: str | int) -> int:
    """校验端口号。"""
    try:
        port = int(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"PORT 必须是整数: {value!r}") from exc
    if not 1 <= port <= 65535:
        raise ValueError(f"PORT 必须在 1..65535 范围内: {port}")
    return port


def _load_settings() -> Settings:
    """从文件加载配置，config.local.env 优先级高于 .env。"""
    _auto_create_config()
    env: dict[str, str] = {}
    # 旧版 .env（低优先级）
    env.update(_parse_env_file(LEGACY_ENV_FILE))
    # 主配置（高优先级）
    env.update(_parse_env_file(CONFIG_FILE))

    host = _normalize_host(env.get("HOST", DEFAULT_HOST))
    port = parse_port(env.get("PORT", DEFAULT_PORT))
    return Settings(host=host, port=port)


# ── 模块级导出（兼容 import config; config.HOST / config.PORT）──

_settings: Settings = _load_settings()
HOST: str = _settings.host
PORT: int = _settings.port


def override(host: str | None = None, port: int | None = None) -> Settings:
    """应用 CLI 覆盖并刷新模块级导出。

    Args:
        host: CLI --host 值（None 表示不覆盖）。
        port: CLI --port 值（None 表示不覆盖）。

    Returns:
        最终 Settings 实例。
    """
    global _settings, HOST, PORT
    if host is not None:
        _settings.host = _normalize_host(host)
    if port is not None:
        _settings.port = parse_port(port)
    HOST = _settings.host
    PORT = _settings.port
    return _settings
