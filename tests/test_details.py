"""Pure-Python detail tests; do not require GTK or running systemd."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from serviceforge.models.details import ServiceDetails  # noqa: E402


class ServiceDetailsTests(unittest.TestCase):
    def rows(self, unit=None, service=None):
        details = ServiceDetails("system", "example.service", unit or {}, service or {})
        return {label: value for _, rows in details.sections() for label, value in rows}

    def test_absent_values_remain_unavailable(self):
        rows = self.rows()
        self.assertEqual(rows["Unit file"], "Not available")
        self.assertEqual(rows["Current main PID"], "Not available")
        self.assertEqual(rows["Restart counter"], "Not available")
        self.assertEqual(rows["Requires"], "Not available")

    def test_zero_main_pid_is_not_a_live_process(self):
        rows = self.rows(service={"MainPID": 0, "ExecMainPID": 1234, "NRestarts": 0})
        self.assertEqual(rows["Current main PID"], "No current main PID")
        self.assertEqual(rows["Most recent main PID"], "1234")
        self.assertEqual(rows["Restart counter"], "0")

    def test_deps_and_ordering_are_separate(self):
        rows = self.rows(unit={
            "Requires": ["network.target"],
            "After": ["network.target", "basic.target"],
            "Wants": [],
        })
        self.assertEqual(rows["Requires"], "network.target")
        self.assertEqual(rows["After (ordering)"], "basic.target\nnetwork.target")
        self.assertEqual(rows["Wants"], "None reported")

    def test_exec_start_command_uses_argv(self):
        rows = self.rows(service={
            "ExecStart": [("/usr/bin/echo", ["/usr/bin/echo", "hello world"], False)],
        })
        self.assertEqual(rows["ExecStart commands"], "/usr/bin/echo 'hello world'")

    def test_empty_user_is_not_assumed_root(self):
        rows = self.rows(service={"User": "", "Group": ""})
        self.assertEqual(rows["Configured user"], "Manager default")
        self.assertEqual(rows["Configured group"], "Manager default")

    def test_control_group_comes_from_service_interface(self):
        rows = self.rows(unit={"ControlGroup": "/wrong/manager"}, service={
            "ControlGroup": "/system.slice/example.service"
        })
        self.assertEqual(rows["Control group"], "/system.slice/example.service")

    def test_no_service_interface_does_not_hide_unit_fields(self):
        rows = self.rows(unit={"Id": "example.service", "FragmentPath": "/usr/lib/systemd/system/example.service"})
        self.assertEqual(rows["Unit file"], "/usr/lib/systemd/system/example.service")
        self.assertEqual(rows["Restart policy"], "Not available")


if __name__ == "__main__":
    unittest.main()
