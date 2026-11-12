# Development roadmap

## Phase 1: Native read-only foundation — 0.1.0 (current)

- [x] Project identity and modular Python layout
- [x] Native GTK4/Libadwaita window
- [x] Asynchronous Gio D-Bus service discovery
- [x] Loaded service table, system/user scope, search, and manual refresh
- [x] Pure-Python normalization tests
- [x] Fedora Workstation initial explorer integration validated in screenshots
- [x] Reconcile installed unit files with loaded units
- [x] Unloaded-unit lifecycle handling validated on the maintainer's Fedora desktop

## Phase 2: Accurate inspection (in progress)

- [x] On-demand Unit and Service D-Bus property queries
- [x] Service Inspector with PID, ExecStart, user, group, unit paths, restart policy, and dependencies
- [x] Active/inactive/failed status icons, summary counts, quick filters, and sortable columns
- [x] Pure-Python detail display tests
- [x] Fedora desktop integration validation of Inspector and filters (screenshots)
- [x] Installed-but-unloaded service discovery and inspection
- [x] Private D-Bus monitor with debounced events, 90s reconciliation and 45s fallback
- [x] In-session, bounded Overview activity feed
- [ ] Manually verify live monitoring, fallback state and pause/scope switching on Fedora GNOME
- [ ] D-Bus error/permission integration tests

## Phase 3: Service management (experimental)

- [x] Start/Stop/Restart/Reload via systemd D-Bus, opt-in after confirmation
- [x] Existing systemd/Polkit authorization integration
- [x] JobRemoved correlation and unknown-outcome timeout handling
- [x] Conservative runtime action policy and pure-Python tests
- [x] Disposable user-unit Restart and Stop demonstrated on Fedora
- [x] Start verified after unloaded user-unit Stop on Fedora
- [x] Implement persistent Enable/Disable/Mask/Unmask with fresh-state checks and manual confirmations
- [x] Mock authorization-denied and stale-state behavior in Fedora CI
- [x] User Enable/Disable/Mask/Unmask validated on Fedora test fixture (screenshots)
- [x] Maintainer reports system-manager authorization tests passed on disposable fixture
- [ ] Validate additional authorization variants and non-forcing mask edge case ([Issue #4](https://github.com/tobiasGuta/ServiceForge/issues/4))
- [ ] More comprehensive dependency-impact previews

## Phase 4: Diagnostics (begun early, read-only)

- [x] Loaded-service Overview with failure navigation
- [x] Bounded current-boot journal history per selected service
- [x] Local severity filtering, text search and explicit copy action
- [x] Journal reader pure-Python tests using a fake Reader
- [x] Expand journal matches with selected manager lifecycle entries
- [x] Fedora desktop validation of Overview and Logs (screenshots)
- [ ] Live journal streaming and richer matching of manager-generated unit messages
- [ ] Resource accounting where available
- [ ] Security hardening assessments and boot diagnostics

## Phase 5: Release engineering

- Full Fedora test matrix, CI improvements, accessibility
- Complete contributor and security documentation
- Finalize license and add LICENSE
- Desktop metadata, icons, RPM/COPR evaluation
