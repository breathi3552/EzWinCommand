from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
from pathlib import Path
from urllib.parse import quote


def _copy(source, target) -> None:
    while chunk := source.read(65536):
        target.write(chunk)
        target.flush()


def _forward_client_messages(source, target, workspace: Path) -> None:
    workspace_uri = "file:///" + quote(workspace.as_posix(), safe="/:.")
    while True:
        headers: list[bytes] = []
        content_length: int | None = None
        while True:
            line = source.readline()
            if not line:
                return
            headers.append(line)
            if line in (b"\r\n", b"\n"):
                break
            name, _, value = line.partition(b":")
            if name.lower() == b"content-length":
                content_length = int(value.strip())
        if content_length is None:
            raise RuntimeError("LSP 消息缺少 Content-Length")

        payload = source.read(content_length)
        message = json.loads(payload)
        if message.get("method") == "initialize":
            params = message.setdefault("params", {})
            params["rootUri"] = workspace_uri
            params["rootPath"] = str(workspace)
            params["workspaceFolders"] = [
                {"uri": workspace_uri, "name": workspace.name}
            ]
            payload = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

        target.write(f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii"))
        target.write(payload)
        target.flush()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", required=True)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--system-path")
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    command = [args.server]
    if args.system_path:
        command.extend(["--stdio", "--system-path", args.system_path])
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    assert process.stderr is not None

    threading.Thread(target=_copy, args=(process.stdout, sys.stdout.buffer), daemon=True).start()
    threading.Thread(target=_copy, args=(process.stderr, sys.stderr.buffer), daemon=True).start()
    try:
        _forward_client_messages(sys.stdin.buffer, process.stdin, workspace)
    finally:
        process.stdin.close()
        process.terminate()
    return process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
