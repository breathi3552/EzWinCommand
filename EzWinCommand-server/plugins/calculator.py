"""Demo 插件：打开/关闭 Windows 计算器。"""
import subprocess
from typing import Any

import psutil

from plugins.base import BasePlugin, CommandResult


class CalculatorPlugin(BasePlugin):
    name = "calculator"

    def execute(self, params: dict[str, Any]) -> CommandResult:
        action = params.get("sub_action", "open")

        if action == "open":
            return self._open()
        elif action == "close":
            return self._close()
        else:
            return CommandResult(success=False, message=f"未知操作: {action}")

    @staticmethod
    def _open() -> CommandResult:
        try:
            subprocess.Popen("calc.exe")
            return CommandResult(success=True, message="计算器已启动")
        except Exception as exc:
            return CommandResult(success=False, message=f"启动计算器失败: {exc}")

    @staticmethod
    def _close() -> CommandResult:
        killed = 0
        for proc in psutil.process_iter(["name"]):
            try:
                if proc.info["name"] and proc.info["name"].lower() == "calculatorapp.exe":
                    proc.kill()
                    killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if killed == 0:
            return CommandResult(success=True, message="计算器未在运行")
        return CommandResult(success=True, message=f"已关闭 {killed} 个计算器进程")
