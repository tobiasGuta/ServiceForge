"""Native read-only service explorer for systemd's system and user managers."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GObject, Gtk, Pango  # noqa: E402

from serviceforge.backend.systemd_client import SystemdClient
from serviceforge.models.service import ServiceRecord


class ServiceItem(GObject.Object):
    """Adapter object used by Gio.ListStore and Gtk.ColumnView."""

    def __init__(self, record: ServiceRecord) -> None:
        super().__init__()
        self.record = record


class MainWindow(Adw.ApplicationWindow):
    """Search and inspect actual loaded services without changing their state."""

    def __init__(self, application: Adw.Application) -> None:
        super().__init__(
            application=application,
            title="ServiceForge",
            default_width=1050,
            default_height=660,
        )
        self._client = SystemdClient()
        self._request_id = 0
        self._store = Gio.ListStore.new(ServiceItem)

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        title = Gtk.Label(label="ServiceForge")
        title.add_css_class("title")
        header.set_title_widget(title)

        self._scope = Gtk.DropDown.new_from_strings(
            ["System services", "User services"]
        )
        self._scope.set_tooltip_text("Choose which systemd manager to inspect")
        header.pack_start(self._scope)

        self._refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        self._refresh.set_tooltip_text("Refresh services")
        header.pack_end(self._refresh)
        toolbar.add_top_bar(header)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_top(16)
        content.set_margin_bottom(16)
        content.set_margin_start(18)
        content.set_margin_end(18)

        tools = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self._search = Gtk.SearchEntry()
        self._search.set_placeholder_text("Search services or states")
        self._search.set_hexpand(True)
        tools.append(self._search)

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
        self._selection = Gtk.SingleSelection.new(self._filtered)
        self._view = Gtk.ColumnView.new(self._selection)
        self._view.set_hexpand(True)
        self._view.set_vexpand(True)
        self._view.add_css_class("data-table")

        self._add_column("Service", "name", expand=True)
        self._add_column("Load", "load_state")
        self._add_column("Active", "active_state")
        self._add_column("Substate", "sub_state")
        self._add_column("Startup", "startup_display")
        self._add_column("Description", "description", expand=True)

        scroller = Gtk.ScrolledWindow()
        scroller.set_hexpand(True)
        scroller.set_vexpand(True)
        scroller.set_child(self._view)
        content.append(scroller)

        self._summary = Gtk.Label(xalign=0)
        self._summary.add_css_class("dim-label")
        content.append(self._summary)

        toolbar.set_content(content)
        self.set_content(toolbar)

        self._search.connect("search-changed", self._on_search_changed)
        self._filtered.connect("notify::n-items", self._update_summary)
        self._scope.connect("notify::selected", self._on_scope_changed)
        self._refresh.connect("clicked", self._on_refresh_clicked)
        self.refresh()

    def _add_column(self, title: str, property_name: str, *, expand: bool = False) -> None:
        factory = Gtk.SignalListItemFactory()

        def setup(_factory: Gtk.SignalListItemFactory, item: Gtk.ListItem) -> None:
            label = Gtk.Label(xalign=0)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_margin_start(7)
            label.set_margin_end(7)
            label.set_margin_top(9)
            label.set_margin_bottom(9)
            item.set_child(label)

        def bind(_factory: Gtk.SignalListItemFactory, item: Gtk.ListItem) -> None:
            model_item = item.get_item()
            item.get_child().set_text(str(getattr(model_item.record, property_name)))

        factory.connect("setup", setup)
        factory.connect("bind", bind)
        column = Gtk.ColumnViewColumn.new(title, factory)
        column.set_resizable(True)
        column.set_expand(expand)
        self._view.append_column(column)

    def _match_service(self, item: ServiceItem, *_unused: object) -> bool:
        query = self._search.get_text().strip().casefold()
        if not query:
            return True
        record = item.record
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

    def _on_search_changed(self, *_args: object) -> None:
        self._filter.changed(Gtk.FilterChange.DIFFERENT)
        self._update_summary()

    def _on_scope_changed(self, *_args: object) -> None:
        self.refresh()

    def _on_refresh_clicked(self, *_args: object) -> None:
        self.refresh()

    def _update_summary(self, *_args: object) -> None:
        visible = self._filtered.get_n_items()
        total = self._store.get_n_items()
        self._summary.set_text(f"Showing {visible} of {total} loaded services")

    def refresh(self) -> None:
        self._request_id += 1
        request_id = self._request_id
        scope = "system" if self._scope.get_selected() == 0 else "user"
        self._notice.set_visible(False)
        self._refresh.set_sensitive(False)
        self._spinner.set_visible(True)
        self._spinner.start()
        self._summary.set_text(f"Loading {scope} services…")

        def succeeded(records: list[ServiceRecord], warning: str | None) -> None:
            if request_id != self._request_id:
                return  # A newer request or manager selection superseded this reply.
            self._store.remove_all()
            for record in records:
                self._store.append(ServiceItem(record))
            self._set_idle()
            if warning:
                self._notice.set_text(
                    "Service list loaded, but startup configuration is unavailable: "
                    + warning
                )
                self._notice.set_visible(True)
            self._update_summary()

        def failed(message: str) -> None:
            if request_id != self._request_id:
                return
            self._store.remove_all()  # Never display stale data under another scope.
            self._set_idle()
            self._notice.set_text(message)
            self._notice.set_visible(True)
            self._summary.set_text("Unable to load services")

        self._client.fetch_services(scope, succeeded, failed)

    def _set_idle(self) -> None:
        self._spinner.stop()
        self._spinner.set_visible(False)
        self._refresh.set_sensitive(True)
