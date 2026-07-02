# REQ-002-01: BasePlugin 扩展 get_sub_actions() 和 label 属性

- **父需求**: REQ-002
- **日期**: 2026-07-02
- **状态**: 已完成

## 设计概述

在 `BasePlugin` 基类中新增两个成员，为子操作声明能力打下基础：

- `label` 类属性：人类可读的插件名称，默认为空字符串。
- `get_sub_actions()` 方法：返回插件支持的子操作列表，默认为空列表。

子类只需覆写这两个成员即可声明自身的子操作能力，无需修改基类。

## 涉及文件

| 文件 | 变更类型 | 说明 |
|---|---|---|
| `EzWinCommand-server/plugins/base.py` | 修改 | 新增 `label` 属性和 `get_sub_actions()` 方法 |
| `EzWinCommand-server/plugins/volume.py` | 修改 | 添加 `label`，覆写 `get_sub_actions()` 返回 +/−/静音 |
| `EzWinCommand-server/plugins/calculator.py` | 修改 | 添加 `label = "计算器"`（在后续 fix commit 中完成） |

## 实现要点

### BasePlugin 变更

```python
label: str = ""  # 人类可读名称，为空时回退到 name

def get_sub_actions(self) -> list[dict[str, str]]:
    """返回支持的子操作列表。

    每个子操作是一个 dict：
        - id:   子操作标识符（传给 execute 的 params.sub_action）
        - label: 人类可读的显示文本

    返回空列表表示该插件是简单触发型（如 calculator）。
    """
    return []
```

- `label` 为类属性，允许子类直接覆盖。默认空字符串，Dispatcher 输出时做回退处理。
- `get_sub_actions()` 返回 `list[dict[str, str]]`，每个 dict 是 `{"id": ..., "label": ...}` 的二元素结构。
- 默认返回空列表，确保所有已有插件无需修改即兼容。

### volume 插件适配

- 添加 `label = "音量控制"`
- 覆写 `get_sub_actions()` 返回三个子操作：`up`(+)、`down`(-)、`mute`(静音)
- `execute()` 原本就通过 `params.get("sub_action", "up")` 分派，现有逻辑无需改动

### calculator 插件适配

- 添加 `label = "计算器"`（在 fix commit `ce8a5a4` 中补上）
- 不覆写 `get_sub_actions()`，保持默认空列表（简单触发型）
