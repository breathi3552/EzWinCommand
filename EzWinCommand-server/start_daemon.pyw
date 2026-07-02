"""EzWinCommand 静默启动器。

双击此文件即可后台启动服务，系统托盘可见。
使用 .pyw 扩展名确保无控制台窗口。
"""
import subprocess
import sys
from pathlib import Path


def main() -> None:
    project_dir = Path(__file__).resolve().parent
    pythonw = Path(sys.executable).parent / "pythonw.exe"
    app = project_dir / "app.py"

    subprocess.Popen(
        [str(pythonw), str(app)],
        cwd=str(project_dir),
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )


if __name__ == "__main__":
    main()
