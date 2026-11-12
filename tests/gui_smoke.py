"""Headless GTK widget construction smoke test for Fedora CI.

Run under Xvfb. This checks our new overview/journal widgets but cannot
prove journal permissions, display styling, or D-Bus connectivity.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw  # noqa: E402

from serviceforge.models.service import ServiceRecord
from serviceforge.models.details import ServiceDetails
from serviceforge.backend.systemd_client import SystemdClient
from serviceforge.ui.main_window import MainWindow
from unittest.mock import patch
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

    # Suppress the initial D-Bus request: CI has no running systemd manager.
    app = Adw.Application(application_id="io.github.tobiasGuta.ServiceForge")
    with patch.object(SystemdClient, "fetch_services", lambda *_: None):
        window = MainWindow(application=app)
    window._current_record = record
    window._detail_unit = ServiceDetails(
        scope="system",
        requested_name=record.name,
        unit={"CanReload": True, "CanStart": True, "CanStop": True},
        service={},
    )
    window._update_action_buttons()
    assert window._action_buttons["start"].get_sensitive()
    assert not window._action_buttons["stop"].get_sensitive()
    assert not window._action_buttons["restart"].get_sensitive()

    active_record = ServiceRecord(
        scope="system",
        name="active-test.service",
        description="Active test service",
        load_state="loaded",
        active_state="active",
        sub_state="running",
        unit_file_state="enabled",
    )
    window._current_record = active_record
    window._detail_unit = ServiceDetails(
        scope="system",
        requested_name=active_record.name,
        unit={"CanReload": True, "CanStart": True, "CanStop": True},
        service={},
    )
    window._update_action_buttons()
    assert window._action_buttons["stop"].get_sensitive()
    assert window._action_buttons["restart"].get_sensitive()
    assert window._action_buttons["reload"].get_sensitive()
    assert not window._action_buttons["start"].get_sensitive()
    window.destroy()
    print("GTK overview, journal and management controls constructed successfully")


if __name__ == "__main__":
    run()
