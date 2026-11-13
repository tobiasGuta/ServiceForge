"""Native GTK journal history viewer, scoped to a selected service."""

from concurrent.futures import Future

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk, Pango  # noqa: E402

from serviceforge.backend.journal_reader import JournalClient
from serviceforge.models.journal import (
    JournalBoot,
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
    """The most recent readable entries from the selected boot."""

    def __init__(self, back_callback) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        toolbar = Adw.ToolbarView()
        toolbar.set_hexpand(True)
        toolbar.set_vexpand(True)
        self.append(toolbar)
        self._client = JournalClient()
        self._selected: ServiceRecord | None = None
        self._serial = 0
        self._history_request: Future[list[JournalEntry]] | None = None
        self._boot_request: Future[list[JournalBoot]] | None = None
        self._boots: list[JournalBoot] = []
        self._entries: list[JournalEntry] = []
        self._display_text = ""

        header = Adw.HeaderBar()
        self._back = Gtk.Button.new_from_icon_name("go-previous-symbolic")
        self._back.set_tooltip_text("Back to Service Inspector")
        self._back.connect("clicked", lambda *_: back_callback())
        header.pack_start(self._back)

        self._title = Gtk.Label(label="Service journal")
        self._title.add_css_class("title")
        self._title.set_ellipsize(Pango.EllipsizeMode.END)
        header.set_title_widget(self._title)

        self._refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        self._refresh.set_tooltip_text("Reload the selected boot’s journal history")
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

        boot_controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        boot_label = Gtk.Label.new_with_mnemonic("_Boot")
        self._boot = Gtk.DropDown.new_from_strings(["Current boot"])
        self._boot.connect("notify::selected", self._refresh_clicked)
        boot_label.set_mnemonic_widget(self._boot)
        boot_controls.append(boot_label)
        boot_controls.append(self._boot)
        self._boot_status = Gtk.Label(xalign=0, wrap=True)
        self._boot_status.add_css_class("dim-label")
        boot_controls.append(self._boot_status)
        content.append(boot_controls)

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
                "Logs may contain sensitive information; review before copying."
            ),
            xalign=0,
        )
        note.set_wrap(True)
        note.add_css_class("dim-label")
        content.append(note)
        toolbar.set_content(content)

    def open(self, record: ServiceRecord) -> None:
        self.close()
        self._boots = []
        self._boot.set_model(Gtk.StringList.new(["Current boot"]))
        self._boot.set_sensitive(False)
        self._boot_status.set_text("Looking for previous boots…")
        self._selected = record
        self._title.set_text(f"{record.name} · {record.scope_label} logs")
        self._search.set_text("")
        self._severity.set_selected(0)
        self.refresh()

        def loaded(boots: list[JournalBoot]) -> None:
            if self._boot_request is not request:
                return
            self._boots = boots
            model = self._boot.get_model()
            model.splice(1, 0, [boot.label for boot in boots])
            self._boot.set_sensitive(bool(boots))
            self._boot_status.set_text("" if boots else "No previous boots are readable.")

        def unavailable(_message: str) -> None:
            if self._boot_request is request:
                self._boot_status.set_text("Could not list previous boots.")

        request = self._client.fetch_boots(loaded, unavailable)
        self._boot_request = request

    def close(self) -> None:
        """Invalidate callbacks when leaving the journal screen."""
        self._serial += 1
        self._selected = None
        for request in (self._history_request, self._boot_request):
            if request is not None:
                request.cancel()
        self._history_request = None
        self._boot_request = None

    def _refresh_clicked(self, *_unused: object) -> None:
        self.refresh()

    def refresh(self) -> None:
        record = self._selected
        if record is None:
            return
        self._serial += 1
        serial = self._serial
        boot_index = self._boot.get_selected()
        boot_id = (
            self._boots[boot_index - 1].boot_id
            if 0 < boot_index <= len(self._boots)
            else None
        )
        if self._history_request is not None:
            self._history_request.cancel()
        self._entries.clear()
        self._render()
        self._error.set_visible(False)
        self._refresh.set_sensitive(False)
        self._spinner.set_visible(True)
        self._spinner.start()
        self._status.set_text("Reading the selected boot’s journal entries…")

        def is_current() -> bool:
            return serial == self._serial and self._selected is record

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

        self._history_request = self._client.fetch(
            record.scope, record.name, success, error, boot_id=boot_id,
        )

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
                    "No matching journal entries are accessible for this service "
                    "in the selected boot. Journal permissions can limit visibility."
                )
            else:
                self._status.set_text(
                    f"Showing {len(visible)} of {len(self._entries)} latest "
                    "readable messages (up to 200 from the selected boot)."
                )

    def _copy_clicked(self, *_unused: object) -> None:
        if self._display_text:
            self.get_display().get_clipboard().set_text(self._display_text)

    def shutdown(self) -> None:
        self._client.shutdown()
