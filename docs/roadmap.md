# Development roadmap

## Phase 1: Native read-only foundation — 0.1.0 (current)

- [x] Project identity and modular Python layout
- [x] Native GTK4/Libadwaita window
- [x] Asynchronous Gio D-Bus service discovery
- [x] Loaded service table, system/user scope, search, and manual refresh
- [x] Pure-Python normalization tests
- [ ] Fedora Workstation integration validation
- [ ] Expand unit-file reconciliation to installed-but-unloaded services

## Phase 2: Accurate inspection (in progress)

- [x] On-demand Unit and Service D-Bus property queries
- [x] Service Inspector with PID, ExecStart, user, group, unit paths, restart policy, and dependencies
- [x] Active/inactive/failed status icons, summary counts, quick filters, and sortable columns
- [x] Pure-Python detail display tests
- [ ] Fedora desktop integration validation of inspector and filters
- [ ] Installed-but-unloaded service discovery
- [ ] Signal-driven updates with limited fallback polling
- [ ] D-Bus error/permission integration tests

## Phase 3: Service management

- Polkit-mediated start/stop/restart, enable/disable
- Confirmation dialogs, action gating, and job-completion tracking
- Test against disposable services only

## Phase 4: Diagnostics (begun early, read-only)

- [x] Loaded-service Overview with failure navigation
- [x] Bounded current-boot journal history per selected service
- [x] Local severity filtering, text search and explicit copy action
- [x] Journal reader pure-Python tests using a fake Reader
- [ ] Fedora desktop validation for Overview and Logs
- [ ] Live journal streaming and richer matching of manager-generated unit messages
- [ ] Resource accounting where available
- [ ] Security hardening assessments and boot diagnostics

## Phase 5: Release engineering

- Full Fedora test matrix, CI improvements, accessibility
- Complete contributor and security documentation
- Finalize license and add LICENSE
- Desktop metadata, icons, RPM/COPR evaluation
