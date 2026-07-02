"""插件基类与接口契约。

每个插件必须继承 BasePlugin 并实现 execute()。
"""

from abc import ABC, abstractmethod
from typing import Any


class CommandResult:
    """插件执行结果。

    Attributes:
        success: 是否执行成功。
        message: 人类可读的描述信息。
        data: 附加的结构化数据。
    """

    def __init__(
        self,
        success: bool,
        message: str = "",
        data: dict[str, Any] | None = None,
    ) -> None:
        self.success = success
        self.message = message
        self.data = data

    def to_dict(self) -> dict:
        return {"success": self.success, "message": self.message, "data": self.data}


class BasePlugin(ABC):
    """插件基类。

    子类需要：
    1. 设置 name 属性（用于路由分发）。
    2. 实现 execute(params) 方法。
    3. 可选实现 get_status() 方法（状态采集）。
    """

    name: str = ""

    label: str = ""  # 人类可读名称，为空时回退到 name
    def get_sub_actions(self) -> list[dict[str, str]]:
        """返回支持的子操作列表。

        每个子操作是一个 dict：
            - id:   子操作标识符（传给 execute 的 params.sub_action）
            - label: 人类可读的显示文本

        返回空列表表示该插件是简单触发型（如 calculator）。
        """
        return []

    @abstractmethod
    def execute(self, params: dict[str, Any]) -> CommandResult:
        """执行插件逻辑。"""
        ...

    def get_status(self) -> dict[str, Any] | None:
        """可选：采集该插件相关的系统状态。"""
        return None
