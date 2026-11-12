"""Native GNOME-style overview of the current loaded service snapshot."""

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk  # noqa: E402

from serviceforge.models.monitoring import ActivityEvent
from serviceforge.models.overview import summarize_services
from serviceforge.models.service import Scope, ServiceRecord


class OverviewView(Gtk.Box):
    """Counts reflect only loaded units in the selected systemd manager."""

    def __init__(
        self,
        show_services: Callable[[], None],
        inspect_service: Callable[[ServiceRecord], None],
        refresh_services: Callable[[], None],
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        toolbar = Adw.ToolbarView()
        toolbar.set_hexpand(True)
        toolbar.set_vexpand(True)
        self.append(toolbar)
        self._inspect_service = inspect_service
        self._records_by_name: dict[str, ServiceRecord] = {}
        self._events: tuple[ActivityEvent, ...] = ()

        header = Adw.HeaderBar()
        header.set_title_widget(Gtk.Label(label="Overview"))
        services_button = Gtk.Button(label="Services")
        services_button.connect("clicked", lambda *_: show_services())
        header.pack_start(services_button)
        refresh_button = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        refresh_button.set_tooltip_text("Refresh loaded services")
        refresh_button.connect("clicked", lambda *_: refresh_services())
        header.pack_end(refresh_button)
        toolbar.add_top_bar(header)

        scroller = Gtk.ScrolledWindow()
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        body.set_margin_top(24)
        body.set_margin_bottom(28)
        body.set_margin_start(24)
        body.set_margin_end(24)

        heading = Gtk.Label(label="Service health overview", xalign=0)
        heading.add_css_class("title-1")
        body.append(heading)

        self._scope_label = Gtk.Label(xalign=0)
        self._scope_label.add_css_class("dim-label")
        self._scope_label.set_wrap(True)
        body.append(self._scope_label)

        self._monitor_status = Gtk.Label(xalign=0)
        self._monitor_status.set_wrap(True)
        self._monitor_status.add_css_class("dim-label")
        body.append(self._monitor_status)

        cards = Gtk.FlowBox()
        cards.set_selection_mode(Gtk.SelectionMode.NONE)
        cards.set_column_spacing(12)
        cards.set_row_spacing(12)
        cards.set_min_children_per_line(2)
        cards.set_max_children_per_line(4)
        self._numbers: dict[str, Gtk.Label] = {}
        for key, label in (
            ("total", "Loaded services"),
            ("active", "Active"),
            ("inactive", "Inactive"),
            ("failed", "Failed"),
        ):
            frame = Gtk.Frame()
            frame.add_css_class("card")
            frame.set_size_request(172, 112)
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            content.set_margin_top(18)
            content.set_margin_bottom(18)
            content.set_margin_start(18)
            content.set_margin_end(18)
            number = Gtk.Label(label="—", xalign=0)
            number.add_css_class("title-1")
            description = Gtk.Label(label=label, xalign=0)
            description.add_css_class("dim-label")
            content.append(number)
            content.append(description)
            frame.set_child(content)
            cards.append(frame)
            self._numbers[key] = number
        body.append(cards)

        self._status = Gtk.Label(xalign=0)
        self._status.set_wrap(True)
        body.append(self._status)

        self._failed_container = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=10
        )
        body.append(self._failed_container)

        recent_heading = Gtk.Label(label="Recent manager activity", xalign=0)
        recent_heading.add_css_class("title-2")
        body.append(recent_heading)

        self._activity_container = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=10
        )
        body.append(self._activity_container)

        history_note = Gtk.Label(
            label=(
                "Only manager events observed while Live monitoring is active "
                "in this app session appear here. This is not journal history "
                "or a complete audit trail."
            ),
            xalign=0,
        )
        history_note.set_wrap(True)
        history_note.add_css_class("dim-label")
        body.append(history_note)

        explanation = Gtk.Label(
            label=(
                "Counts describe loaded systemd services only. They do not "
                "represent every installed unit file, and inactive services "
                "are not automatically failures."
            ),
            xalign=0,
        )
        explanation.set_wrap(True)
        explanation.add_css_class("dim-label")
        body.append(explanation)

        scroller.set_child(body)
        toolbar.set_content(scroller)
        self.update(None, scope="system")
        self.set_activity(())

    def set_monitor_status(self, message: str) -> None:
        self._monitor_status.set_text(message)

    def set_activity(self, events: tuple[ActivityEvent, ...]) -> None:
        """Show observed manager signals without inventing unit state changes."""
        self._events = events
        self._render_activity()

    def _render_activity(self) -> None:
        while (child := self._activity_container.get_first_child()) is not None:
            self._activity_container.remove(child)

        group = Adw.PreferencesGroup()
        if not self._events:
            row = Adw.ActionRow()
            row.set_title("No activity observed yet")
            row.set_subtitle("Start or stop a disposable service to see events here.")
            group.add(row)
        else:
            for event in self._events[:10]:
                row = Adw.ActionRow()
                row.set_title(event.title)
                row.set_use_markup(False)
                if event.unit:
                    subtitle = f"{event.when} · {event.unit} · {event.detail}"
                else:
                    subtitle = f"{event.when} · {event.detail}"
                row.set_subtitle(subtitle)
                row.set_subtitle_lines(2)
                row.set_subtitle_selectable(True)
                record = self._records_by_name.get(event.unit) if event.unit else None
                if record is not None:
                    button = Gtk.Button(label="Inspect")
                    button.set_valign(Gtk.Align.CENTER)
                    button.connect(
                        "clicked",
                        lambda _button, selected=record: self._inspect_service(selected),
                    )
                    row.add_suffix(button)
                    row.set_activatable_widget(button)
                group.add(row)
        self._activity_container.append(group)

    def update(
        self,
        records: list[ServiceRecord] | None,
        *,
        scope: Scope,
    ) -> None:
        manager_name = "System manager" if scope == "system" else "User manager"
        self._scope_label.set_text(manager_name + " · read-only loaded-unit snapshot")
        self._records_by_name = {
            record.name: record for record in records
        } if records is not None else {}
        self._render_activity()
        self._clear_failures()
        if records is None:
            for number in self._numbers.values():
                number.set_text("—")
            self._status.set_text("Loading service data…")
            return

        summary = summarize_services(records)
        for key in self._numbers:
            self._numbers[key].set_text(str(getattr(summary, key)))
        if summary.other:
            self._status.set_text(
                f"{summary.other} loaded services have other states "
                "(such as activating or deactivating)."
            )
        else:
            self._status.set_text("Snapshot loaded. Use Services to inspect individual units.")

        group = Adw.PreferencesGroup()
        group.set_title("Failed loaded services")
        if not summary.failed_units:
            row = Adw.ActionRow()
            row.set_title("No failed loaded services")
            row.set_subtitle("No units currently report ActiveState=failed in this snapshot.")
            group.add(row)
        else:
            for record in summary.failed_units[:15]:
                row = Adw.ActionRow()
                row.set_title(record.name)
                row.set_subtitle(record.description or "No description")
                button = Gtk.Button(label="Inspect")
                button.set_valign(Gtk.Align.CENTER)
                button.connect(
                    "clicked",
                    lambda _button, selected=record: self._inspect_service(selected),
                )
                row.add_suffix(button)
                row.set_activatable_widget(button)
                group.add(row)
            if summary.failed > 15:
                more = Adw.ActionRow()
                more.set_title(f"{summary.failed - 15} more failed loaded services")
                more.set_subtitle("Open Services and select the Failed filter.")
                group.add(more)
        self._failed_container.append(group)

    def show_error(self, message: str, *, scope: Scope) -> None:
        self.update(None, scope=scope)
        self._status.set_text("Unable to load service data: " + message)

    def _clear_failures(self) -> None:
        while True:
            child = self._failed_container.get_first_child()
            if child is None:
                return
            self._failed_container.remove(child)
