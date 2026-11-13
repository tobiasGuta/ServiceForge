"""Native service explorer with read-only diagnostics and confirmed actions."""

from concurrent.futures import Future
from dataclasses import replace
from datetime import datetime

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GObject, Gtk, Pango  # noqa: E402

from serviceforge.backend.systemd_client import SystemdClient
from serviceforge.backend.journal_reader import JournalClient
from serviceforge.backend.live_monitor import LiveMonitor
from serviceforge.backend.service_actions import ServiceActions
from serviceforge.backend.unit_file_actions import UnitFileActions
from serviceforge.models.actions import (
    ActionOutcome, allowed_actions, confirmation_text,
)
from serviceforge.models.details import ServiceDetails
from serviceforge.models.journal import JournalEntry
from serviceforge.models.service import Scope, ServiceRecord
from serviceforge.models.overview import summarize_services
from serviceforge.models.monitoring import ActivityEvent, ActivityFeed
from serviceforge.models.unit_files import (
    FileActionOutcome, file_action_allowed, file_action_message,
    requires_typed_confirmation,
)
from serviceforge.ui.overview_view import OverviewView
from serviceforge.ui.journal_view import JournalView


FILTER_OPTIONS = (
    "All services", "Loaded", "Unloaded", "Active", "Inactive",
    "Failed", "Enabled", "Masked",
)


class ServiceItem(GObject.Object):
    """GObject adapter for immutable service records in GTK list models."""

    def __init__(self, record: ServiceRecord) -> None:
        super().__init__()
        self.record = record


class MainWindow(Adw.ApplicationWindow):
    """Inspect services and perform explicitly confirmed systemd operations."""

    def __init__(self, application: Adw.Application) -> None:
        super().__init__(
            application=application,
            title="ServiceForge",
            default_width=1120,
            default_height=730,
        )
        self._client = SystemdClient()
        self._actions_client = ServiceActions()
        self._file_client = UnitFileActions()
        self._failure_journal = JournalClient()
        self._failure_request: Future[list[JournalEntry]] | None = None
        self._detail_unit: ServiceDetails | None = None
        self._file_state: str | None = None
        self._file_state_request_id = 0
        self._action_pending = False
        self._action_buttons: dict[str, Gtk.Button] = {}
        self._file_buttons: dict[str, Gtk.Button] = {}
        self._request_id = 0
        self._detail_request_id = 0
        self._inspector_session = 0
        self._detail_refresh_pending = False
        self._current_record: ServiceRecord | None = None
        self._closing = False
        self._store = Gio.ListStore.new(ServiceItem)
        self._activity_feeds = {
            "system": ActivityFeed(), "user": ActivityFeed(),
        }
        self._monitor = LiveMonitor(
            self._on_monitor_refresh,
            self._on_monitor_activity,
            self._on_monitor_status,
        )

        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self._stack.set_vhomogeneous(True)
        self._stack.set_hhomogeneous(True)
        self._stack.add_named(self._create_explorer(), "explorer")
        self._stack.add_named(self._create_inspector(), "inspector")
        self._overview = OverviewView(
            self._show_services, self._open_inspector, self.refresh
        )
        self._stack.add_named(self._overview, "overview")
        self._journal = JournalView(self._on_journal_back)
        self._stack.add_named(self._journal, "journal")
        self.set_content(self._stack)

        self._search.connect("search-changed", self._on_filter_changed)
        self._filter_choice.connect("notify::selected", self._on_filter_changed)
        self._filtered.connect("notify::n-items", self._update_summary)
        self._scope.connect("notify::selected", self._on_scope_changed)
        self._refresh.connect("clicked", self._on_refresh_clicked)
        self._selection.connect("notify::selected-item", self._on_selected_changed)
        self._view.connect("activate", self._on_row_activated)
        self._inspect_button.connect("clicked", self._on_inspect_clicked)
        self._detail_back.connect("clicked", self._on_back_clicked)
        self._detail_refresh.connect("clicked", self._on_detail_refresh_clicked)
        self._overview_button.connect("clicked", self._on_overview_clicked)
        self._live_button.connect("toggled", self._on_live_toggled)
        self._logs_button.connect("clicked", self._on_logs_clicked)
        self.connect("close-request", self._on_window_close)
        self._on_selected_changed()
        self.refresh()
        self._monitor.start("system")

    def _create_explorer(self) -> Adw.ToolbarView:
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        title = Gtk.Label(label="ServiceForge")
        title.add_css_class("title")
        header.set_title_widget(title)

        self._scope = Gtk.DropDown.new_from_strings(
            ["System services", "User services"]
        )
        self._scope.set_tooltip_text("Choose the systemd manager")
        header.pack_start(self._scope)

        self._overview_button = Gtk.Button(label="Overview")
        self._overview_button.set_tooltip_text("View loaded-service summary and failures")
        header.pack_start(self._overview_button)

        self._refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        self._refresh.set_tooltip_text("Refresh services and unit files")
        header.pack_end(self._refresh)

        self._live_button = Gtk.ToggleButton(label="Live")
        self._live_button.set_active(True)
        self._live_button.set_tooltip_text(
            "Toggle automatic monitoring for the selected systemd manager"
        )
        header.pack_end(self._live_button)
        menu = Gio.Menu()
        menu.append("About ServiceForge", "app.about")
        menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu)
        menu_button.set_tooltip_text("Main menu")
        header.pack_end(menu_button)
        toolbar.add_top_bar(header)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_top(16)
        content.set_margin_bottom(16)
        content.set_margin_start(18)
        content.set_margin_end(18)

        tools = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self._search = Gtk.SearchEntry()
        self._search.set_placeholder_text("Search services or states")
        self._search.set_hexpand(True)
        tools.append(self._search)

        self._filter_choice = Gtk.DropDown.new_from_strings(list(FILTER_OPTIONS))
        self._filter_choice.set_tooltip_text("Filter by runtime or startup state")
        tools.append(self._filter_choice)

        self._inspect_button = Gtk.Button(label="Inspect")
        self._inspect_button.set_tooltip_text("Inspect the selected service")
        tools.append(self._inspect_button)

        self._spinner = Gtk.Spinner()
        self._spinner.set_visible(False)
        tools.append(self._spinner)
        content.append(tools)

        self._notice = Gtk.Label(xalign=0)
        self._notice.set_wrap(True)
        self._notice.add_css_class("error")
        self._notice.set_visible(False)
        content.append(self._notice)

        self._filter = Gtk.CustomFilter.new(self._match_service)
        self._filtered = Gtk.FilterListModel.new(self._store, self._filter)

        # ColumnView's sorter only works when passed to a SortListModel
        # between the filter and the selection model.
        self._view = Gtk.ColumnView()
        self._sorted = Gtk.SortListModel.new(self._filtered, self._view.get_sorter())
        self._selection = Gtk.SingleSelection.new(self._sorted)
        self._view.set_model(self._selection)
        self._view.set_hexpand(True)
        self._view.set_vexpand(True)
        self._view.set_single_click_activate(True)
        self._view.add_css_class("data-table")

        first = self._add_column("Service", "name", expand=True)
        self._add_column("Load", "load_state")
        self._add_column("Active", "active_state", status=True)
        self._add_column("Substate", "sub_state")
        self._add_column("Startup", "startup_display")
        self._add_column("Description", "description", expand=True)
        self._view.sort_by_column(first, Gtk.SortType.ASCENDING)

        scroller = Gtk.ScrolledWindow()
        scroller.set_hexpand(True)
        scroller.set_vexpand(True)
        scroller.set_child(self._view)
        content.append(scroller)

        self._summary = Gtk.Label(xalign=0)
        self._summary.add_css_class("dim-label")
        content.append(self._summary)

        self._monitor_status = Gtk.Label(xalign=0)
        self._monitor_status.set_wrap(True)
        self._monitor_status.add_css_class("dim-label")
        self._monitor_status.set_text("Connecting to systemd events…")
        content.append(self._monitor_status)

        toolbar.set_content(content)
        return toolbar

    def _add_column(
        self,
        title: str,
        property_name: str,
        *,
        expand: bool = False,
        status: bool = False,
    ) -> Gtk.ColumnViewColumn:
        factory = Gtk.SignalListItemFactory()

        def setup(_factory: Gtk.SignalListItemFactory, item: Gtk.ListItem) -> None:
            label = Gtk.Label(xalign=0)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_margin_start(7)
            label.set_margin_end(7)
            label.set_margin_top(9)
            label.set_margin_bottom(9)
            if status:
                box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
                icon = Gtk.Image()
                box.append(icon)
                box.append(label)
                item.set_child(box)
            else:
                item.set_child(label)

        def bind(_factory: Gtk.SignalListItemFactory, item: Gtk.ListItem) -> None:
            record = item.get_item().record
            text = str(getattr(record, property_name))
            if status:
                box = item.get_child()
                image = box.get_first_child()
                label = image.get_next_sibling()
                for css in ("success", "error", "dim-label"):
                    label.remove_css_class(css)
                if record.active_state == "active":
                    image.set_from_icon_name("emblem-ok-symbolic")
                    label.add_css_class("success")
                elif record.active_state == "failed":
                    image.set_from_icon_name("dialog-error-symbolic")
                    label.add_css_class("error")
                elif record.active_state == "inactive":
                    image.set_from_icon_name("media-playback-pause-symbolic")
                    label.add_css_class("dim-label")
                elif not record.loaded:
                    image.set_from_icon_name("media-playback-stop-symbolic")
                    label.add_css_class("dim-label")
                else:
                    image.set_from_icon_name("dialog-question-symbolic")
                label.set_text(text)
            else:
                item.get_child().set_text(text)

        factory.connect("setup", setup)
        factory.connect("bind", bind)
        column = Gtk.ColumnViewColumn.new(title, factory)
        column.set_resizable(True)
        column.set_expand(expand)

        def compare(a: ServiceItem, b: ServiceItem, _data: object) -> Gtk.Ordering:
            left = str(getattr(a.record, property_name)).casefold()
            right = str(getattr(b.record, property_name)).casefold()
            if left < right:
                return Gtk.Ordering.SMALLER
            if left > right:
                return Gtk.Ordering.LARGER
            return Gtk.Ordering.EQUAL

        column.set_sorter(Gtk.CustomSorter.new(compare, None))
        self._view.append_column(column)
        return column

    def _create_inspector(self) -> Adw.ToolbarView:
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self._detail_back = Gtk.Button.new_from_icon_name("go-previous-symbolic")
        self._detail_back.set_tooltip_text("Back to services")
        header.pack_start(self._detail_back)
        self._detail_title = Adw.WindowTitle(title="Service Inspector")
        header.set_title_widget(self._detail_title)
        self._detail_refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        self._detail_refresh.set_tooltip_text("Refresh selected service details")
        header.pack_end(self._detail_refresh)
        self._logs_button = Gtk.Button(label="Logs")
        self._logs_button.set_tooltip_text("Read this service’s journal history")
        header.pack_end(self._logs_button)
        toolbar.add_top_bar(header)

        scroller = Gtk.ScrolledWindow()
        scroller.set_vexpand(True)
        self._detail_content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=16
        )
        self._detail_content.set_margin_top(20)
        self._detail_content.set_margin_bottom(24)
        self._detail_content.set_margin_start(24)
        self._detail_content.set_margin_end(24)

        self._detail_checked = Gtk.Label(xalign=0)
        self._detail_checked.add_css_class("dim-label")
        self._detail_content.append(self._detail_checked)

        self._failure_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._failure_panel.set_visible(False)
        failure_title = Gtk.Label(label="Service failed", xalign=0)
        failure_title.add_css_class("title-3")
        self._failure_panel.append(failure_title)
        self._failure_summary = Gtk.Label(xalign=0, wrap=True, selectable=True)
        self._failure_panel.append(self._failure_summary)
        self._failure_logs = Gtk.Label(xalign=0, wrap=True, selectable=True)
        self._failure_logs.set_lines(7)
        self._failure_logs.set_ellipsize(Pango.EllipsizeMode.END)
        self._failure_panel.append(self._failure_logs)
        view_logs = Gtk.Button(label="View journal")
        view_logs.set_halign(Gtk.Align.START)
        view_logs.connect("clicked", self._on_logs_clicked)
        self._failure_panel.append(view_logs)
        self._detail_content.append(self._failure_panel)

        runtime_title = Gtk.Label(label="Runtime controls", xalign=0)
        runtime_title.add_css_class("title-4")
        self._detail_content.append(runtime_title)
        runtime_note = Gtk.Label(
            label="Changes the service's running state now, not its boot configuration.",
            xalign=0,
        )
        runtime_note.add_css_class("dim-label")
        runtime_note.set_wrap(True)
        self._detail_content.append(runtime_note)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_halign(Gtk.Align.START)
        for operation, label in (
            ("start", "Start"),
            ("stop", "Stop"),
            ("restart", "Restart"),
            ("reload", "Reload"),
        ):
            button = Gtk.Button(label=label)
            button.set_sensitive(False)
            if operation in ("stop", "restart"):
                button.add_css_class("destructive-action")
            button.connect(
                "clicked",
                lambda _button, requested=operation: self._confirm_action(requested),
            )
            self._action_buttons[operation] = button
            actions.append(button)
        self._detail_content.append(actions)

        file_title = Gtk.Label(label="Startup configuration", xalign=0)
        file_title.add_css_class("title-4")
        self._detail_content.append(file_title)
        file_note = Gtk.Label(
            label=(
                "Persistent unit-file changes across restarts and reboots. "
                "Enable/Disable do not start/stop; Mask blocks activation."
            ),
            xalign=0,
        )
        file_note.set_wrap(True)
        file_note.add_css_class("dim-label")
        self._detail_content.append(file_note)

        file_actions = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=8
        )
        file_actions.set_halign(Gtk.Align.START)
        for operation, label in (
            ("enable", "Enable"),
            ("disable", "Disable"),
            ("mask", "Mask"),
            ("unmask", "Unmask"),
        ):
            button = Gtk.Button(label=label)
            button.set_sensitive(False)
            if operation == "mask":
                button.add_css_class("destructive-action")
            button.connect(
                "clicked",
                lambda _button, requested=operation: self._confirm_file_action(requested),
            )
            self._file_buttons[operation] = button
            file_actions.append(button)
        self._detail_content.append(file_actions)
        self._file_status = Gtk.Label(xalign=0)
        self._file_status.set_wrap(True)
        self._file_status.add_css_class("dim-label")
        self._detail_content.append(self._file_status)

        self._action_notice = Gtk.Label(xalign=0)
        self._action_notice.set_wrap(True)
        self._action_notice.set_selectable(True)
        self._action_notice.set_visible(False)
        self._detail_content.append(self._action_notice)

        self._detail_spinner = Gtk.Spinner()
        self._detail_spinner.set_halign(Gtk.Align.START)
        self._detail_spinner.set_visible(False)
        self._detail_content.append(self._detail_spinner)

        self._detail_notice = Gtk.Label(xalign=0)
        self._detail_notice.set_wrap(True)
        self._detail_notice.set_visible(False)
        self._detail_content.append(self._detail_notice)

        self._detail_groups = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=16
        )
        self._detail_content.append(self._detail_groups)
        scroller.set_child(self._detail_content)
        toolbar.set_content(scroller)
        return toolbar

    def _match_service(self, item: ServiceItem, *_unused: object) -> bool:
        record = item.record
        choice = self._filter_choice.get_selected()
        if choice == 1 and not record.loaded:
            return False
        if choice == 2 and record.loaded:
            return False
        if choice == 3 and record.active_state != "active":
            return False
        if choice == 4 and record.active_state != "inactive":
            return False
        if choice == 5 and record.active_state != "failed":
            return False
        if choice == 6 and record.unit_file_state not in ("enabled", "enabled-runtime"):
            return False
        if choice == 7 and (
            record.unit_file_state not in ("masked", "masked-runtime")
            and record.load_state != "masked"
        ):
            return False

        query = self._search.get_text().strip().casefold()
        if not query:
            return True
        return any(
            query in value.casefold()
            for value in (
                record.name,
                record.description,
                record.load_state,
                record.active_state,
                record.sub_state,
                record.startup_display,
            )
        )

    def _on_filter_changed(self, *_args: object) -> None:
        self._filter.changed(Gtk.FilterChange.DIFFERENT)
        self._update_summary()

    def _on_selected_changed(self, *_args: object) -> None:
        self._inspect_button.set_sensitive(self._selection.get_selected_item() is not None)

    def _selected_scope(self) -> Scope:
        return "system" if self._scope.get_selected() == 0 else "user"

    def _on_monitor_refresh(self, affected_units: set[str] | None) -> None:
        self.refresh()
        record = self._current_record
        if record is None or record.scope != self._selected_scope():
            return
        details = self._detail_unit
        if affected_units is not None and not affected_units.intersection((
            record.name, record.object_path,
            details.object_path if details else None,
            details.display_name if details else None,
        )):
            return
        if self._action_pending:
            return
        if not self._detail_refresh.get_sensitive():
            self._detail_refresh_pending = True
            return
        self._load_details(record)

    def _on_monitor_activity(self, event: ActivityEvent) -> None:
        self._activity_feeds[event.scope].add(event)
        if event.scope == self._selected_scope():
            self._overview.set_activity(
                self._activity_feeds[event.scope].recent(),
            )

    def _on_monitor_status(self, message: str) -> None:
        self._monitor_status.set_text(message)
        self._overview.set_monitor_status(message)

    def _on_live_toggled(self, button: Gtk.ToggleButton) -> None:
        if button.get_active():
            self._monitor.start(self._selected_scope())
            self._on_monitor_refresh(None)
        else:
            self._monitor.stop()
            self._detail_refresh_pending = False

    def _on_scope_changed(self, *_args: object) -> None:
        self._journal.close()
        self._on_back_clicked()
        self._store.remove_all()
        self._on_selected_changed()
        scope = self._selected_scope()
        self._overview.set_activity(self._activity_feeds[scope].recent())
        if self._live_button.get_active():
            self._monitor.start(scope)
        self.refresh()

    def _on_refresh_clicked(self, *_args: object) -> None:
        self.refresh()

    def _on_inspect_clicked(self, *_args: object) -> None:
        item = self._selection.get_selected_item()
        if item is not None:
            self._open_inspector(item.record)

    def _on_row_activated(self, _view: Gtk.ColumnView, position: int) -> None:
        item = self._selection.get_item(position)
        if item is not None:
            self._open_inspector(item.record)

    def _show_services(self) -> None:
        self._stack.set_visible_child_name("explorer")

    def _on_overview_clicked(self, *_args: object) -> None:
        self._stack.set_visible_child_name("overview")

    def _on_logs_clicked(self, *_args: object) -> None:
        record = self._current_record
        if record is None:
            return
        if self._detail_unit is not None:
            record = replace(record, name=self._detail_unit.display_name)
        self._stack.set_visible_child_name("journal")
        self._journal.open(record)

    def _on_journal_back(self) -> None:
        self._journal.close()
        self._stack.set_visible_child_name("inspector")

    def _on_window_close(self, *_args: object) -> bool:
        self._closing = True
        self._monitor.stop()
        self._journal.close()
        self._journal.shutdown()
        self._cancel_failure_preview()
        self._failure_journal.shutdown()
        self._current_record = None
        self._request_id += 1
        return False

    def _on_back_clicked(self, *_args: object) -> None:
        self._inspector_session += 1
        self._detail_refresh_pending = False
        self._cancel_failure_preview()
        self._current_record = None
        self._detail_unit = None
        self._file_state = None
        self._update_action_buttons()
        self._stack.set_visible_child_name("explorer")

    def _on_detail_refresh_clicked(self, *_args: object) -> None:
        if self._current_record is not None:
            self._load_details(self._current_record)

    def _open_inspector(self, record: ServiceRecord) -> None:
        if record.scope != self._selected_scope():
            return
        self._inspector_session += 1
        self._detail_refresh_pending = False
        self._cancel_failure_preview()
        self._clear_detail_groups()
        self._failure_panel.set_visible(False)
        self._detail_notice.set_visible(False)
        self._detail_checked.set_text("Checking service status…")
        self._current_record = record
        self._action_notice.set_visible(False)
        self._detail_title.set_title(record.name)
        self._detail_title.set_subtitle(f"{record.scope_label} service")
        self._stack.set_visible_child_name("inspector")
        self._detail_back.grab_focus()
        self._load_details(record)

    def _eligible_actions(self) -> set[str]:
        record = self._current_record
        details = self._detail_unit
        if record is None or details is None:
            return set()
        props = details.unit
        # ServiceRecord comes from a prior list snapshot. Inspector properties
        # are more recent, especially after a Start/Stop/Restart job completes.
        load_state = props.get("LoadState")
        active_state = props.get("ActiveState")
        unit_file_state = props.get("UnitFileState")
        if not isinstance(load_state, str) or not isinstance(active_state, str):
            return set()
        current = replace(
            record,
            load_state=load_state,
            active_state=active_state,
            unit_file_state=(
                unit_file_state
                if isinstance(unit_file_state, str) and unit_file_state
                else record.unit_file_state
            ),
        )
        return allowed_actions(
            current,
            can_start=props.get("CanStart") is True,
            can_stop=props.get("CanStop") is True,
            can_reload=props.get("CanReload") is True,
            refuse_manual_start=props.get("RefuseManualStart") is True,
            refuse_manual_stop=props.get("RefuseManualStop") is True,
        )

    def _current_active_state(self) -> str | None:
        if self._detail_unit is None:
            return None
        value = self._detail_unit.unit.get("ActiveState")
        return value if isinstance(value, str) else None

    def _eligible_file_actions(self) -> set[str]:
        record = self._current_record
        if record is None:
            return set()
        return {
            action
            for action in ("enable", "disable", "mask", "unmask")
            if file_action_allowed(
                record, action, self._file_state,
                active_state=self._current_active_state(),
            )
        }

    def _update_action_buttons(self) -> None:
        available = self._eligible_actions()
        for action, button in self._action_buttons.items():
            button.set_sensitive(action in available and not self._action_pending)
        file_available = self._eligible_file_actions()
        for action, button in self._file_buttons.items():
            button.set_sensitive(
                action in file_available and not self._action_pending
            )

    def _load_file_state(self, record: ServiceRecord) -> None:
        self._file_state_request_id += 1
        request_id = self._file_state_request_id
        self._file_state = None
        self._update_action_buttons()
        if not record.unit_file_path:
            self._file_status.set_text(
                "No matching installed unit-file entry. "
                "Persistent actions are unavailable."
            )
            return
        self._file_status.set_text("Checking current unit-file state…")

        def current() -> bool:
            return (
                request_id == self._file_state_request_id
                and record is self._current_record
            )

        def success(state: str) -> None:
            if not current():
                return
            self._file_state = state
            self._file_status.set_text(
                f"Current unit-file state: {state}. "
                "Only supported persistent transitions are offered."
            )
            self._update_action_buttons()

        def failure(message: str) -> None:
            if not current():
                return
            self._file_status.set_text(
                "Cannot verify unit-file configuration. "
                "Changes are disabled. " + message
            )
            self._update_action_buttons()

        self._file_client.get_state(
            record.scope, record.name, success, failure,
        )

    def _confirm_file_action(self, action: str) -> None:
        record = self._current_record
        state = self._file_state
        if (
            record is None
            or state is None
            or self._action_pending
            or action not in self._eligible_file_actions()
        ):
            return

        dialog = Adw.AlertDialog(
            heading=f"{action.capitalize()} {record.name}?",
            body=f"Manager: {record.scope_label}\n\n" + file_action_message(action, record),
        )
        session = self._inspector_session
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("apply", action.capitalize())
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        if action in ("disable", "mask"):
            dialog.set_response_appearance(
                "apply", Adw.ResponseAppearance.DESTRUCTIVE
            )

        if requires_typed_confirmation(record, action):
            entry = Gtk.Entry()
            entry.set_placeholder_text(f"Type {record.name} to confirm")
            entry.set_tooltip_text("Type the exact service name to unlock this action")
            entry.set_hexpand(True)
            dialog.set_extra_child(entry)
            dialog.set_response_enabled("apply", False)
            entry.connect(
                "changed",
                lambda widget: dialog.set_response_enabled(
                    "apply", widget.get_text() == record.name,
                ),
            )

        def responded(_dialog: Adw.AlertDialog, response: str) -> None:
            if (
                response == "apply"
                and session == self._inspector_session
                and record.scope == self._selected_scope()
                and self._file_state == state
                and action in self._eligible_file_actions()
                and not self._action_pending
            ):
                self._execute_file_action(record, action, state)

        dialog.connect("response", responded)
        dialog.present(self)

    def _execute_file_action(
        self, record: ServiceRecord, action: str, expected_state: str,
    ) -> None:
        if self._action_pending:
            return
        self._action_pending = True
        self._update_action_buttons()
        self._action_notice.set_text(
            f"Applying persistent {action} to {record.name} through systemd…"
        )
        self._action_notice.set_visible(True)
        original_active_state = self._current_active_state()

        def success(outcome: FileActionOutcome) -> None:
            self._action_pending = False
            if record is self._current_record:
                if outcome.verified:
                    notice = (
                        f"{action.capitalize()} verified: unit-file state is "
                        f"{outcome.current_state}. "
                        f"{len(outcome.changes)} file change(s) reported. "
                        "The service's current running state is unchanged "
                        "by this operation."
                    )
                else:
                    notice = (
                        f"Systemd returned from {action}, but reported state "
                        f"{outcome.current_state!r}. Refresh and verify before "
                        "trying another change."
                    )
                self._action_notice.set_text(notice)
                self._load_details(record)
            self._update_action_buttons()
            self.refresh()

        def error(message: str) -> None:
            self._action_pending = False
            if record is self._current_record:
                self._action_notice.set_text(
                    f"{action.capitalize()} was not verified: {message}"
                )
                self._load_details(record)
            self._update_action_buttons()
            self.refresh()

        self._file_client.execute(
            record, action, expected_state, original_active_state,
            success, error,
        )

    def _confirm_action(self, action: str) -> None:
        record = self._current_record
        if (
            record is None
            or self._action_pending
            or action not in self._eligible_actions()
        ):
            return
        heading = f"{action.capitalize()} {record.name}?"
        dialog = Adw.AlertDialog(
            heading=heading,
            body=f"Manager: {record.scope_label}\n\n" + confirmation_text(action, record),
        )
        session = self._inspector_session
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("proceed", action.capitalize())
        dialog.set_close_response("cancel")
        dialog.set_default_response("cancel")
        if action in ("stop", "restart"):
            dialog.set_response_appearance(
                "proceed", Adw.ResponseAppearance.DESTRUCTIVE
            )

        def responded(_dialog: Adw.AlertDialog, response: str) -> None:
            if (
                response == "proceed"
                and session == self._inspector_session
                and record.scope == self._selected_scope()
                and action in self._eligible_actions()
            ):
                self._execute_action(action, record)

        dialog.connect("response", responded)
        dialog.present(self)

    def _execute_action(self, action: str, record: ServiceRecord) -> None:
        if self._action_pending:
            return
        self._action_pending = True
        self._update_action_buttons()
        self._action_notice.set_text(
            f"Requesting {action} for {record.name} through systemd…"
        )
        self._action_notice.set_visible(True)

        def completed(outcome: ActionOutcome) -> None:
            self._action_pending = False
            if self._current_record is record:
                if outcome.succeeded:
                    status = (
                        f"{action.capitalize()} job finished (done). "
                        "Refreshing current service information."
                    )
                else:
                    status = (
                        f"Systemd {action} job finished with result "
                        f"'{outcome.result}'. Check the service status and logs."
                    )
                self._action_notice.set_text(status)
                self._load_details(record)
            self._update_action_buttons()
            self.refresh()

        def failed(message: str) -> None:
            self._action_pending = False
            if self._current_record is record:
                self._action_notice.set_text(
                    f"{action.capitalize()} was not confirmed: {message}"
                )
                self._action_notice.set_visible(True)
                self._load_details(record)
            self._update_action_buttons()
            self.refresh()

        self._actions_client.execute(
            record.scope, record.name, action, completed, failed
        )

    def _clear_detail_groups(self) -> None:
        child = self._detail_groups.get_first_child()
        while child is not None:
            self._detail_groups.remove(child)
            child = self._detail_groups.get_first_child()

    def _cancel_failure_preview(self) -> None:
        if self._failure_request is not None:
            self._failure_request.cancel()
            self._failure_request = None

    def _update_failure_preview(self, record: ServiceRecord, details: ServiceDetails) -> None:
        summary = details.failure_summary
        was_visible = self._failure_panel.get_visible()
        self._failure_panel.set_visible(summary is not None)
        if summary is None:
            self._cancel_failure_preview()
            return
        self._failure_summary.set_text(summary)
        if not was_visible:
            self._failure_logs.set_text("Reading recent errors from this boot…")
        self._cancel_failure_preview()

        def show_errors(entries: list[JournalEntry]) -> None:
            if self._current_record is not record or self._detail_unit is not details:
                return
            self._failure_logs.set_text(
                "\n".join(
                    f"{entry.timestamp}  {entry.message[:320]}" for entry in reversed(entries)
                ) if entries else "No readable error messages from this boot."
            )

        def unavailable(_message: str) -> None:
            if self._current_record is record and self._detail_unit is details:
                self._failure_logs.set_text("Could not read recent errors. Open Logs for details.")

        self._failure_request = self._failure_journal.fetch(
            record.scope, details.display_name, show_errors, unavailable,
            limit=3, max_priority=3,
        )

    def _load_details(self, record: ServiceRecord) -> None:
        self._detail_request_id += 1
        request_id = self._detail_request_id
        previous_details = self._detail_unit
        self._detail_unit = None
        self._load_file_state(record)
        self._update_action_buttons()
        self._detail_refresh.set_sensitive(False)
        self._detail_spinner.set_visible(True)
        self._detail_spinner.start()

        def current() -> bool:
            return (
                request_id == self._detail_request_id
                and self._current_record is record
            )

        def finished() -> None:
            self._detail_spinner.stop()
            self._detail_spinner.set_visible(False)
            self._detail_refresh.set_sensitive(True)
            if self._detail_refresh_pending:
                self._detail_refresh_pending = False
                self._load_details(record)

        def succeeded(details: ServiceDetails) -> None:
            if not current():
                return
            self._detail_unit = details
            self._update_action_buttons()
            self._detail_title.set_title(details.display_name)
            self._detail_checked.set_text(f"Last checked at {datetime.now():%H:%M:%S}")
            self._detail_notice.set_visible(bool(details.service_warning))
            if details.service_warning:
                self._detail_notice.set_text(
                    "Some service-specific properties could not be read: "
                    + details.service_warning
                )
            self._update_failure_preview(record, details)
            sections = details.sections()
            if previous_details is None or previous_details.sections() != sections:
                expanded = {}
                child = self._detail_groups.get_first_child()
                while child is not None:
                    expanded[child.get_label()] = child.get_expanded()
                    child = child.get_next_sibling()
                self._clear_detail_groups()
                for group_title, rows in sections:
                    group = Adw.PreferencesGroup()
                    for field_title, value in rows:
                        row = Adw.ActionRow()
                        row.set_title(field_title)
                        row.set_use_markup(False)
                        row.set_subtitle(value)
                        row.set_subtitle_lines(
                            2 if group_title == "Identity and state" else 4
                        )
                        row.set_subtitle_selectable(True)
                        group.add(row)
                    expander = Gtk.Expander(label=group_title)
                    expander.set_expanded(
                        expanded.get(group_title, group_title == "Identity and state")
                    )
                    expander.set_child(group)
                    self._detail_groups.append(expander)
            finished()

        def failed(message: str) -> None:
            if not current():
                return
            self._clear_detail_groups()
            self._cancel_failure_preview()
            self._failure_panel.set_visible(False)
            self._detail_checked.set_text("Service status unavailable")
            self._detail_notice.set_text(message)
            self._detail_notice.set_visible(True)
            finished()

        self._client.fetch_details(
            record.scope, record.name, succeeded, failed,
            known_unit_file=bool(record.unit_file_path),
        )

    def _update_summary(self, *_args: object) -> None:
        records = [
            self._store.get_item(i).record for i in range(self._store.get_n_items())
        ]
        snapshot = summarize_services(records)
        parts = [
            f"Showing {self._filtered.get_n_items()} of {len(records)} services",
            f"{snapshot.total} loaded",
            f"{len(records) - snapshot.total} unloaded",
            f"{snapshot.active} active",
            f"{snapshot.inactive} inactive",
            f"{snapshot.failed} failed",
        ]
        if snapshot.other:
            parts.append(f"{snapshot.other} other")
        self._summary.set_text("  ·  ".join(parts))

    def refresh(self) -> None:
        if self._closing:
            return
        self._request_id += 1
        request_id = self._request_id
        scope = self._selected_scope()
        self._overview.update(None, scope=scope)
        self._notice.set_visible(False)
        self._refresh.set_sensitive(False)
        self._spinner.set_visible(True)
        self._spinner.start()
        self._summary.set_text(f"Loading {scope} services…")

        def succeeded(records: list[ServiceRecord], warning: str | None) -> None:
            if request_id != self._request_id:
                return
            # One model notification rather than hundreds of append events
            # during automatic refresh, preserving GTK responsiveness.
            self._store.splice(
                0, self._store.get_n_items(),
                [ServiceItem(record) for record in records],
            )
            self._overview.update(records, scope=scope)
            self._set_idle()
            if warning:
                self._notice.set_text(
                    "Loaded services found; installed-unit discovery unavailable: "
                    + warning
                )
                self._notice.set_visible(True)
            self._update_summary()

        def failed(message: str) -> None:
            if request_id != self._request_id:
                return
            self._store.remove_all()
            self._overview.show_error(message, scope=scope)
            self._set_idle()
            self._notice.set_text(message)
            self._notice.set_visible(True)
            self._summary.set_text("Unable to load services")

        self._client.fetch_services(scope, succeeded, failed)

    def _set_idle(self) -> None:
        self._spinner.stop()
        self._spinner.set_visible(False)
        self._refresh.set_sensitive(True)
