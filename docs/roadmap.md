# Development roadmap

## Phase 1: Native read-only foundation — 0.1.0 (current)

- [x] Project identity and modular Python layout
- [x] Native GTK4/Libadwaita window
- [x] Asynchronous Gio D-Bus service discovery
- [x] Loaded service table, system/user scope, search, and manual refresh
- [x] Pure-Python normalization tests
- [ ] Fedora Workstation integration validation
- [ ] Expand unit-file reconciliation to installed-but-unloaded services

## Phase 2: Accurate inspection

- Service details with optional properties
- Unit file paths, states, and common relationships
- Signal-driven updates with limited fallback polling
- Robust error and permission tests

## Phase 3: Service management

- Polkit-mediated start/stop/restart, enable/disable
- Confirmation dialogs, action gating, and job-completion tracking
- Test against disposable services only

## Phase 4: Diagnostics

- Journald historical entries and live streaming
- Dependencies and failure-focused inspection
- Resource accounting where available
- Security hardening assessments and boot diagnostics

## Phase 5: Release engineering

- Full Fedora test matrix, CI improvements, accessibility
- Complete contributor and security documentation
- Finalize license and add LICENSE
- Desktop metadata, icons, RPM/COPR evaluation
