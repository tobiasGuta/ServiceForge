"""Headless GTK widget construction smoke test for Fedora CI.

Run under Xvfb. This checks our new overview/journal widgets but cannot
prove journal permissions, display styling, or D-Bus connectivity.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw  # noqa: E402

from serviceforge.models.service import ServiceRecord
from serviceforge.ui.overview_view import OverviewView
from serviceforge.ui.journal_view import JournalView


def run() -> None:
    Adw.init()
    record = ServiceRecord(
        scope="system",
        name="test.service",
        description="A test service",
        load_state="loaded",
        active_state="failed",
        sub_state="failed",
        unit_file_state="enabled",
    )
    overview = OverviewView(
        show_services=lambda: None,
        inspect_service=lambda _record: None,
        refresh_services=lambda: None,
    )
    overview.update([record], scope="system")
    overview.update([], scope="user")
    overview.show_error("Expected smoke-test error", scope="system")

    journal = JournalView(lambda: None)
    journal.close()
    journal.shutdown()
    print("GTK overview and journal widgets constructed successfully")


if __name__ == "__main__":
    run()
