"""Headless GTK widget construction smoke test for Fedora CI.

Run under Xvfb. This checks our new overview/journal widgets but cannot
prove journal permissions, display styling, or D-Bus connectivity.
"""

from concurrent.futures import Future
from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import patch

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio  # noqa: E402

from serviceforge.models.service import ServiceRecord
from serviceforge.models.details import ServiceDetails
from serviceforge.backend.systemd_client import SystemdClient
from serviceforge.backend.live_monitor import LiveMonitor
from serviceforge.models.monitoring import ActivityEvent
from serviceforge.models.journal import JournalBoot, JournalEntry
from serviceforge.ui.main_window import MainWindow, ServiceItem
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
    overview.set_activity((
        ActivityEvent(
            "system", "2026-11-11 15:20:00", "Job finished",
            "Result: done", "test.service",
        ),
    ))
    overview.set_monitor_status("Live · test manager")
    overview.update([], scope="user")
    overview.show_error("Expected smoke-test error", scope="system")

    journal = JournalView(lambda: None)
    journal.close()
    journal.shutdown()

    # Suppress the initial D-Bus request: CI has no running systemd manager.
    app = Adw.Application(
        application_id="io.github.tobiasGuta.ServiceForge.Test",
        flags=Gio.ApplicationFlags.NON_UNIQUE,
    )
    app.register(None)
    with patch.object(SystemdClient, "fetch_services", lambda *_: None), patch.object(
        LiveMonitor, "start", lambda *_: None
    ):
        window = MainWindow(application=app)
    assert window._live_button.get_active()
    assert window._monitor_status is not None
    assert "system" in window._activity_feeds
    # GTK can display manager events and keep user/system activity separate.
    observed = ActivityEvent(
        "system", "2026-11-11 15:30:00", "Job finished",
        "Result: done", "test.service",
    )
    window._on_monitor_activity(observed)
    assert window._activity_feeds["system"].recent() == (observed,)
    assert window._activity_feeds["user"].recent() == ()
    assert window._overview._events == (observed,)
    window._store.append(ServiceItem(record))
    assert window._inspect_button.get_sensitive()
    with patch.object(SystemdClient, "fetch_services"), patch.object(LiveMonitor, "start"):
        window._scope.set_selected(1)
        assert window._store.get_n_items() == 0
        assert not window._inspect_button.get_sensitive()
        window._open_inspector(record)
        assert window._current_record is None
        window._scope.set_selected(0)
    window._current_record = record
    window._detail_unit = ServiceDetails(
        scope="system",
        requested_name=record.name,
        unit={
            "LoadState": "loaded", "ActiveState": "failed",
            "CanReload": True, "CanStart": True, "CanStop": True,
        },
        service={},
    )
    window._update_action_buttons()
    assert window._action_buttons["start"].get_sensitive()
    assert not window._action_buttons["stop"].get_sensitive()
    assert not window._action_buttons["restart"].get_sensitive()
    assert len(window._file_buttons) == 4
    assert not window._file_buttons["mask"].get_sensitive()

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
        unit={
            "LoadState": "loaded", "ActiveState": "active",
            "CanReload": True, "CanStart": True, "CanStop": True,
        },
        service={},
    )
    window._update_action_buttons()
    assert window._action_buttons["stop"].get_sensitive()
    assert window._action_buttons["restart"].get_sensitive()
    assert window._action_buttons["reload"].get_sensitive()
    assert not window._action_buttons["start"].get_sensitive()

    # Simulate a completed Stop job: the selected list record is stale,
    # but the latest D-Bus unit properties already say inactive.
    window._detail_unit = ServiceDetails(
        scope="system",
        requested_name=active_record.name,
        unit={
            "LoadState": "loaded", "ActiveState": "inactive",
            "CanStart": True, "CanStop": True, "CanReload": False,
        },
        service={},
    )
    window._update_action_buttons()
    assert window._action_buttons["start"].get_sensitive()
    assert not window._action_buttons["stop"].get_sensitive()
    assert not window._action_buttons["restart"].get_sensitive()

    # Simulate a stopped service with a real installed unit-file entry.
    file_record = ServiceRecord(
        scope="user",
        name="serviceforge-config-test.service",
        description="Startup configuration smoke test",
        load_state="loaded",
        active_state="inactive",
        sub_state="dead",
        unit_file_state="disabled",
        unit_file_path=(
            "/home/example/.local/share/systemd/user/"
            "serviceforge-config-test.service"
        ),
    )
    details = ServiceDetails(
        scope="user",
        requested_name=file_record.name,
        unit={
            "Id": file_record.name,
            "Description": file_record.description,
            "LoadState": "loaded",
            "ActiveState": "inactive",
            "SubState": "dead",
            "UnitFileState": "disabled",
            "CanStart": True,
            "CanStop": True,
        },
        service={"Type": "simple"},
    )
    window._current_record = file_record
    with patch.object(
        window._client, "fetch_details",
        side_effect=lambda _scope, _name, success, _error, **_kw: success(details),
    ), patch.object(
        window._file_client, "get_state",
        side_effect=lambda _scope, _name, success, _error: success("disabled"),
    ):
        window._load_details(file_record)

    assert window._file_buttons["enable"].get_sensitive()
    assert window._file_buttons["mask"].get_sensitive()
    assert not window._file_buttons["disable"].get_sensitive()
    assert not window._file_buttons["unmask"].get_sensitive()

    first = window._detail_groups.get_first_child()
    assert first.get_expanded()
    second = first.get_next_sibling()
    assert not second.get_expanded()
    window._scope.set_selected(1)
    window._current_record = file_record
    with patch.object(window, "refresh"), patch.object(window, "_load_details") as reload:
        window._on_monitor_refresh({"another.service"})
        reload.assert_not_called()
        window._on_monitor_refresh({file_record.name})
        reload.assert_called_once_with(file_record)

    failed_details = replace(
        details,
        unit={**details.unit, "ActiveState": "failed"},
        service={"Result": "exit-code", "ExecMainCode": 1, "ExecMainStatus": 23, "NRestarts": 0},
    )
    with patch.object(window._failure_journal, "fetch", return_value=None):
        window._update_failure_preview(file_record, failed_details)
        assert window._failure_panel.get_visible()
        assert "Exit status 23" in window._failure_summary.get_text()

    boot = JournalBoot("a" * 32, datetime(2026, 11, 12, tzinfo=timezone.utc))
    viewer = window._journal
    with (
        patch.object(viewer._client, "fetch_boots", return_value=Future()) as boot_list,
        patch.object(viewer._client, "fetch", side_effect=lambda *_, **__: Future()) as history,
    ):
        viewer.open(file_record)
        first_read = history.call_args
        boot_list.call_args.args[0]([boot])
        assert viewer._boot.get_sensitive()
        viewer._boot.set_selected(1)
        assert history.call_args.kwargs["boot_id"] == boot.boot_id
        first_read.args[2]([JournalEntry("now", 3, "Stale current-boot entry")])
        assert viewer._entries == []
        previous = JournalEntry("earlier", 3, "Previous-boot entry")
        history.call_args.args[2]([previous])
        assert viewer._entries == [previous]
    window.close()
    print("GTK overview, journal, Inspector and file controls constructed successfully")


if __name__ == "__main__":
    run()
