"""防火墙规则同步逻辑测试。

使用标准库 unittest.mock 模拟 netsh 调用，不修改真实 Windows 防火墙。
"""
import unittest
from unittest.mock import patch
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import firewall


class FirewallRuleTests(unittest.TestCase):
    PORT = 8080

    def test_existing_rule_calls_set_and_returns_true(self):
        with patch.object(firewall, "rule_exists", return_value=True), \
             patch.object(firewall, "_run_netsh", return_value=(True, "")) as run_netsh:
            self.assertIs(firewall.add_rule(self.PORT), True)

        args = run_netsh.call_args.args[0]
        self.assertEqual(args[:2], ["set", "rule"])
        self.assertIn(f"localport={self.PORT}", args)
        self.assertIn("profile=any", args)
        self.assertIn("enable=yes", args)
        self.assertIn("dir=in", args)
        self.assertIn("action=allow", args)

    def test_new_rule_calls_add_and_returns_true(self):
        with patch.object(firewall, "rule_exists", return_value=False), \
             patch.object(firewall, "_run_netsh", return_value=(True, "")) as run_netsh:
            self.assertIs(firewall.add_rule(self.PORT), True)

        args = run_netsh.call_args.args[0]
        self.assertEqual(args[:2], ["add", "rule"])
        self.assertIn(f"localport={self.PORT}", args)
        self.assertIn("profile=any", args)
        self.assertIn("enable=yes", args)

    def test_elevation_error_triggers_uac_and_returns_false(self):
        with patch.object(firewall, "rule_exists", return_value=False), \
             patch.object(firewall, "_run_netsh", return_value=(False, "Access is denied")), \
             patch.object(firewall, "_request_elevated_netsh", return_value=True) as elevated:
            self.assertIs(firewall.add_rule(self.PORT), False)
            elevated.assert_called_once()

    def test_elevation_error_user_cancels_uac_returns_false(self):
        with patch.object(firewall, "rule_exists", return_value=True), \
             patch.object(firewall, "_run_netsh", return_value=(False, "需要提升")), \
             patch.object(firewall, "_request_elevated_netsh", return_value=False) as elevated:
            self.assertIs(firewall.add_rule(self.PORT), False)
            elevated.assert_called_once()

    def test_non_elevation_error_returns_false_without_uac(self):
        with patch.object(firewall, "rule_exists", return_value=False), \
             patch.object(firewall, "_run_netsh", return_value=(False, "netsh 不可用")), \
             patch.object(firewall, "_request_elevated_netsh", return_value=True) as elevated:
            self.assertIs(firewall.add_rule(self.PORT), False)
            elevated.assert_not_called()

    def test_rule_name(self):
        self.assertEqual(firewall._rule_name(8080), "EzWinCommand 8080")
        self.assertEqual(firewall._rule_name(443), "EzWinCommand 443")

    def test_detects_elevation_errors(self):
        for output in [
            "需要提升",
            "需要管理员权限",
            "access is denied",
            "This command requires elevation",
            "Access is denied. (0x5)",
        ]:
            with self.subTest(output=output):
                self.assertIs(firewall._looks_like_elevation_error(output), True)

    def test_rejects_non_elevation_errors(self):
        for output in [
            "",
            "命令成功",
            "The rule was not found",
            "系统找不到指定的文件",
            "参数错误",
        ]:
            with self.subTest(output=output):
                self.assertIs(firewall._looks_like_elevation_error(output), False)


if __name__ == "__main__":
    unittest.main()
