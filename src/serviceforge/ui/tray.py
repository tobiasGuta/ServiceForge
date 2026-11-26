"""StatusNotifierItem (system tray) support for ServiceForge."""

from typing import Callable
import gi

gi.require_version("Gio", "2.0")
gi.require_version("Dbusmenu", "0.4")

from gi.repository import Dbusmenu, Gio, GLib  # noqa: E402


SNI_XML = """
<node>
  <interface name="org.kde.StatusNotifierItem">
    <property name="Category" type="s" access="read"/>
    <property name="Id" type="s" access="read"/>
    <property name="Title" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="WindowId" type="i" access="read"/>
    <property name="IconThemePath" type="s" access="read"/>
    <property name="ItemIsMenu" type="b" access="read"/>
    <property name="Menu" type="o" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="OverlayIconName" type="s" access="read"/>
    <property name="AttentionIconName" type="s" access="read"/>
    <property name="ToolTip" type="(sa(iiay)ss)" access="read"/>

    <method name="ContextMenu">
      <arg name="x" type="i" direction="in"/>
      <arg name="y" type="i" direction="in"/>
    </method>
    <method name="Activate">
      <arg name="x" type="i" direction="in"/>
      <arg name="y" type="i" direction="in"/>
    </method>
    <method name="SecondaryActivate">
      <arg name="x" type="i" direction="in"/>
      <arg name="y" type="i" direction="in"/>
    </method>
    <method name="Scroll">
      <arg name="delta" type="i" direction="in"/>
      <arg name="orientation" type="s" direction="in"/>
    </method>

    <signal name="NewTitle"/>
    <signal name="NewIcon"/>
    <signal name="NewAttentionIcon"/>
    <signal name="NewOverlayIcon"/>
    <signal name="NewToolTip"/>
    <signal name="NewStatus">
      <arg name="status" type="s"/>
    </signal>
  </interface>
</node>
"""


class ServiceForgeTray:
    """Manages the FreeDesktop / StatusNotifierItem system tray presence."""

    def __init__(
        self,
        connection: Gio.DBusConnection,
        app_id: str,
        on_open: Callable[[], None],
        on_preferences: Callable[[], None],
        on_quit: Callable[[], None],
        on_toggle_live: Callable[[bool], None] | None = None,
    ) -> None:
        self._connection = connection
        self._app_id = app_id
        self._on_open = on_open
        self._on_preferences = on_preferences
        self._on_quit = on_quit
        self._on_toggle_live = on_toggle_live

        self._available = False
        self._status = "Active"
        self._tooltip_text = "All services operational"
        self._failed_count = 0
        self._registration_id = 0
        self._live_active = True

        self._node_info = Gio.DBusNodeInfo.new_for_xml(SNI_XML)
        self._interface_info = self._node_info.interfaces[0]

        self._setup_menu()
        self._register_dbus_object()
        self._register_with_watcher()

    @property
    def is_available(self) -> bool:
        return self._available

    def _setup_menu(self) -> None:
        self._menu_server = Dbusmenu.Server.new("/MenuBar")
        root = Dbusmenu.Menuitem.new()
        self._menu_server.set_root(root)

        # 1. Open
        item_open = Dbusmenu.Menuitem.new()
        item_open.property_set(Dbusmenu.MENUITEM_PROP_LABEL, "Open ServiceForge")
        item_open.property_set_bool(Dbusmenu.MENUITEM_PROP_VISIBLE, True)
        item_open.property_set_bool(Dbusmenu.MENUITEM_PROP_ENABLED, True)
        item_open.connect(
            Dbusmenu.MENUITEM_SIGNAL_ITEM_ACTIVATED,
            lambda *_: self._on_open(),
        )
        root.child_append(item_open)

        # Separator
        sep1 = Dbusmenu.Menuitem.new()
        sep1.property_set(Dbusmenu.MENUITEM_PROP_TYPE, Dbusmenu.CLIENT_TYPES_SEPARATOR)
        sep1.property_set_bool(Dbusmenu.MENUITEM_PROP_VISIBLE, True)
        root.child_append(sep1)

        # 2. Status item (informational)
        self._status_item = Dbusmenu.Menuitem.new()
        self._status_item.property_set(
            Dbusmenu.MENUITEM_PROP_LABEL, "Status: Monitoring active"
        )
        self._status_item.property_set_bool(Dbusmenu.MENUITEM_PROP_VISIBLE, True)
        self._status_item.property_set_bool(Dbusmenu.MENUITEM_PROP_ENABLED, False)
        root.child_append(self._status_item)

        # 3. Live Monitoring toggle
        self._live_item = Dbusmenu.Menuitem.new()
        self._live_item.property_set(Dbusmenu.MENUITEM_PROP_LABEL, "Live Monitoring")
        self._live_item.property_set(
            Dbusmenu.MENUITEM_PROP_TOGGLE_TYPE, Dbusmenu.MENUITEM_TOGGLE_CHECK
        )
        self._live_item.property_set_int(
            Dbusmenu.MENUITEM_PROP_TOGGLE_STATE, Dbusmenu.MENUITEM_TOGGLE_STATE_CHECKED
        )
        self._live_item.property_set_bool(Dbusmenu.MENUITEM_PROP_VISIBLE, True)
        self._live_item.property_set_bool(Dbusmenu.MENUITEM_PROP_ENABLED, True)
        self._live_item.connect(
            Dbusmenu.MENUITEM_SIGNAL_ITEM_ACTIVATED,
            self._handle_live_toggle,
        )
        root.child_append(self._live_item)

        # 4. Preferences
        item_prefs = Dbusmenu.Menuitem.new()
        item_prefs.property_set(Dbusmenu.MENUITEM_PROP_LABEL, "Preferences…")
        item_prefs.property_set_bool(Dbusmenu.MENUITEM_PROP_VISIBLE, True)
        item_prefs.property_set_bool(Dbusmenu.MENUITEM_PROP_ENABLED, True)
        item_prefs.connect(
            Dbusmenu.MENUITEM_SIGNAL_ITEM_ACTIVATED,
            lambda *_: self._on_preferences(),
        )
        root.child_append(item_prefs)

        # Separator
        sep2 = Dbusmenu.Menuitem.new()
        sep2.property_set(Dbusmenu.MENUITEM_PROP_TYPE, Dbusmenu.CLIENT_TYPES_SEPARATOR)
        sep2.property_set_bool(Dbusmenu.MENUITEM_PROP_VISIBLE, True)
        root.child_append(sep2)

        # 5. Quit
        item_quit = Dbusmenu.Menuitem.new()
        item_quit.property_set(Dbusmenu.MENUITEM_PROP_LABEL, "Quit")
        item_quit.property_set_bool(Dbusmenu.MENUITEM_PROP_VISIBLE, True)
        item_quit.property_set_bool(Dbusmenu.MENUITEM_PROP_ENABLED, True)
        item_quit.connect(
            Dbusmenu.MENUITEM_SIGNAL_ITEM_ACTIVATED,
            lambda *_: self._on_quit(),
        )
        root.child_append(item_quit)

    def _handle_live_toggle(self, *_args: object) -> None:
        new_state = not self._live_active
        self.set_live_active(new_state)
        if self._on_toggle_live:
            self._on_toggle_live(new_state)

    def set_live_active(self, active: bool) -> None:
        self._live_active = active
        toggle_val = (
            Dbusmenu.MENUITEM_TOGGLE_STATE_CHECKED
            if active
            else Dbusmenu.MENUITEM_TOGGLE_STATE_UNCHECKED
        )
        self._live_item.property_set_int(
            Dbusmenu.MENUITEM_PROP_TOGGLE_STATE, toggle_val
        )

    def update_status(self, failed_count: int, total_count: int, scope: str = "system") -> None:
        self._failed_count = failed_count
        scope_name = "System" if scope == "system" else "User"

        old_status = self._status
        if failed_count > 0:
            self._status = "NeedsAttention"
            label = f"⚠️ {failed_count} failed in {scope_name.lower()}"
            self._tooltip_text = f"{scope_name}: {failed_count} failed of {total_count} services"
        else:
            self._status = "Active"
            label = f"Status: {scope_name} OK ({total_count} loaded)"
            self._tooltip_text = f"{scope_name}: All {total_count} loaded services OK"

        self._status_item.property_set(Dbusmenu.MENUITEM_PROP_LABEL, label)

        if old_status != self._status:
            self._emit_signal("NewStatus", GLib.Variant("(s)", (self._status,)))
        self._emit_signal("NewToolTip", None)

    def _register_dbus_object(self) -> None:
        try:
            self._registration_id = self._connection.register_object(
                "/StatusNotifierItem",
                self._interface_info,
                self._handle_method_call,
                self._handle_get_property,
                None,
            )
        except Exception:
            self._registration_id = 0

    def _register_with_watcher(self) -> None:
        if not self._registration_id:
            return

        try:
            self._connection.call_sync(
                "org.kde.StatusNotifierWatcher",
                "/StatusNotifierWatcher",
                "org.kde.StatusNotifierWatcher",
                "RegisterStatusNotifierItem",
                GLib.Variant("(s)", ("/StatusNotifierItem",)),
                None,
                Gio.DBusCallFlags.NONE,
                1000,
                None,
            )
            self._available = True
        except Exception:
            self._available = False

    def _handle_get_property(
        self,
        _conn: Gio.DBusConnection,
        _sender: str,
        _path: str,
        _iface: str,
        prop: str,
    ) -> GLib.Variant | None:
        props = {
            "Category": GLib.Variant("s", "ApplicationStatus"),
            "Id": GLib.Variant("s", self._app_id),
            "Title": GLib.Variant("s", "ServiceForge"),
            "Status": GLib.Variant("s", self._status),
            "WindowId": GLib.Variant("i", 0),
            "IconThemePath": GLib.Variant("s", ""),
            "ItemIsMenu": GLib.Variant("b", False),
            "Menu": GLib.Variant("o", "/MenuBar"),
            "IconName": GLib.Variant("s", self._app_id),
            "OverlayIconName": GLib.Variant("s", ""),
            "AttentionIconName": GLib.Variant("s", self._app_id),
            "ToolTip": GLib.Variant(
                "(sa(iiay)ss)",
                (self._app_id, [], "ServiceForge", self._tooltip_text),
            ),
        }
        return props.get(prop)

    def _handle_method_call(
        self,
        _conn: Gio.DBusConnection,
        _sender: str,
        _path: str,
        _iface: str,
        method: str,
        _params: GLib.Variant,
        invocation: Gio.DBusMethodInvocation,
    ) -> None:
        if method in ("Activate", "SecondaryActivate"):
            self._on_open()
        invocation.return_value(None)

    def _emit_signal(self, name: str, params: GLib.Variant | None) -> None:
        if not self._registration_id:
            return
        try:
            self._connection.emit_signal(
                None,
                "/StatusNotifierItem",
                "org.kde.StatusNotifierItem",
                name,
                params,
            )
        except Exception:
            pass

    def destroy(self) -> None:
        if self._registration_id and self._connection:
            try:
                self._connection.unregister_object(self._registration_id)
            except Exception:
                pass
            self._registration_id = 0
            self._available = False
