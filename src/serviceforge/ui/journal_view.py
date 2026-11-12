"""Native GTK journal history viewer, scoped to a selected service."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk  # noqa: E402

from serviceforge.backend.journal_reader import JournalClient
from serviceforge.models.journal import (
    JournalEntry,
    filter_entries,
    format_entries,
)
from serviceforge.models.service import ServiceRecord


SEVERITIES: tuple[tuple[str, int | None], ...] = (
    ("All levels", None),
    ("Errors and above", 3),
    ("Warnings and above", 4),
    ("Information and above", 6),
    ("Debug and above", 7),
)


class JournalView(Gtk.Box):
    """The most recent 200 readable entries for the current boot, no live tail."""

    def __init__(self, back_callback) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        toolbar = Adw.ToolbarView()
        toolbar.set_hexpand(True)
        toolbar.set_vexpand(True)
        self.append(toolbar)
        self._client = JournalClient()
        self._selected: ServiceRecord | None = None
        self._serial = 0
        self._entries: list[JournalEntry] = []
        self._display_text = ""

        header = Adw.HeaderBar()
        self._back = Gtk.Button.new_from_icon_name("go-previous-symbolic")
        self._back.set_tooltip_text("Back to Service Inspector")
        self._back.connect("clicked", lambda *_: back_callback())
        header.pack_start(self._back)

        self._title = Gtk.Label(label="Service journal")
        self._title.add_css_class("title")
        header.set_title_widget(self._title)

        self._refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        self._refresh.set_tooltip_text("Reload current boot journal history")
        self._refresh.connect("clicked", self._refresh_clicked)
        header.pack_end(self._refresh)
        toolbar.add_top_bar(header)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for edge in ("top", "bottom", "start", "end"):
            getattr(content, f"set_margin_{edge}")(16)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self._search = Gtk.SearchEntry()
        self._search.set_hexpand(True)
        self._search.set_placeholder_text("Search loaded log messages")
        self._search.connect("search-changed", lambda *_: self._render())
        controls.append(self._search)

        self._severity = Gtk.DropDown.new_from_strings(
            [label for label, _ in SEVERITIES]
        )
        self._severity.connect("notify::selected", lambda *_: self._render())
        controls.append(self._severity)

        self._copy = Gtk.Button(label="Copy shown logs")
        self._copy.set_sensitive(False)
        self._copy.connect("clicked", self._copy_clicked)
        controls.append(self._copy)
        content.append(controls)

        self._spinner = Gtk.Spinner()
        self._spinner.set_halign(Gtk.Align.START)
        self._spinner.set_visible(False)
        content.append(self._spinner)

        self._error = Gtk.Label(xalign=0)
        self._error.set_wrap(True)
        self._error.set_visible(False)
        self._error.add_css_class("error")
        content.append(self._error)

        self._view = Gtk.TextView()
        self._view.set_editable(False)
        self._view.set_cursor_visible(False)
        self._view.set_monospace(True)
        self._view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self._view.set_left_margin(12)
        self._view.set_right_margin(12)
        self._view.set_top_margin(12)
        self._view.set_bottom_margin(12)

        scroller = Gtk.ScrolledWindow()
        scroller.set_hexpand(True)
        scroller.set_vexpand(True)
        scroller.set_child(self._view)
        content.append(scroller)

        self._status = Gtk.Label(xalign=0)
        self._status.add_css_class("dim-label")
        self._status.set_wrap(True)
        content.append(self._status)
        self._status.set_text("Select a service to view recent journal messages.")

        note = Gtk.Label(
            label=(
                "Only accessible entries from the current boot are shown. "
                "Logs may contain sensitive information; review before copying."
            ),
            xalign=0,
        )
        note.set_wrap(True)
        note.add_css_class("dim-label")
        content.append(note)
        toolbar.set_content(content)

    def open(self, record: ServiceRecord) -> None:
        self._selected = record
        self._title.set_text(record.name + " · Logs")
        self._search.set_text("")
        self._severity.set_selected(0)
        self.refresh()

    def close(self) -> None:
        """Invalidate callbacks when leaving the journal screen."""
        self._serial += 1
        self._selected = None

    def _refresh_clicked(self, *_unused: object) -> None:
        self.refresh()

    def refresh(self) -> None:
        record = self._selected
        if record is None:
            return
        self._serial += 1
        serial = self._serial
        self._entries.clear()
        self._render()
        self._error.set_visible(False)
        self._refresh.set_sensitive(False)
        self._spinner.set_visible(True)
        self._spinner.start()
        self._status.set_text("Reading this boot's journal entries…")

        def is_current() -> bool:
            return serial == self._serial and self._selected == record

        def finish() -> None:
            self._spinner.stop()
            self._spinner.set_visible(False)
            self._refresh.set_sensitive(True)

        def success(entries: list[JournalEntry]) -> None:
            if not is_current():
                return
            finish()
            self._entries = entries
            self._render()

        def error(message: str) -> None:
            if not is_current():
                return
            finish()
            self._entries.clear()
            self._render()
            self._error.set_text(
                "Could not read journal for this service: " + message
            )
            self._error.set_visible(True)
            self._status.set_text(
                "Journal permissions may limit visibility. ServiceForge does not elevate."
            )

        self._client.fetch(record.scope, record.name, success, error)

    def _render(self) -> None:
        selected = self._severity.get_selected()
        threshold = SEVERITIES[selected][1] if selected < len(SEVERITIES) else None
        visible = filter_entries(
            self._entries, self._search.get_text(), threshold
        )
        self._display_text = format_entries(visible)
        self._view.get_buffer().set_text(self._display_text)
        self._copy.set_sensitive(bool(self._display_text))
        if not self._spinner.get_visible():
            if not self._entries:
                self._status.set_text(
                    "No readable messages matched this service in the current boot. "
                    "Some system journal entries may require additional permissions."
                )
            else:
                self._status.set_text(
                    f"Showing {len(visible)} of {len(self._entries)} latest "
                    "readable messages (up to 200, current boot)."
                )

    def _copy_clicked(self, *_unused: object) -> None:
        if self._display_text:
            self.get_display().get_clipboard().set_text(self._display_text)

    def shutdown(self) -> None:
        self._client.shutdown()
