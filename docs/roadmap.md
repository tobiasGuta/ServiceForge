# Development roadmap

## Phase 1: Native read-only foundation — 0.1.0 (current)

- [x] Project identity and modular Python layout
- [x] Native GTK4/Libadwaita window
- [x] Asynchronous Gio D-Bus service discovery
- [x] Loaded service table, system/user scope, search, and manual refresh
- [x] Pure-Python normalization tests
- [ ] Fedora Workstation integration validation
- [x] Reconcile installed unit files with loaded units
- [ ] Validate unloaded-unit handling on the maintainer's Fedora desktop

## Phase 2: Accurate inspection (in progress)

- [x] On-demand Unit and Service D-Bus property queries
- [x] Service Inspector with PID, ExecStart, user, group, unit paths, restart policy, and dependencies
- [x] Active/inactive/failed status icons, summary counts, quick filters, and sortable columns
- [x] Pure-Python detail display tests
- [ ] Fedora desktop integration validation of inspector and filters
- [x] Installed-but-unloaded service discovery and inspection
- [ ] Signal-driven updates with limited fallback polling
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
- [ ] Manually validate persistent file actions on disposable user test unit
- [ ] Test system-manager Polkit authorization and denial using disposable system unit
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
