Name:           serviceforge
Version:        0.1.0
Release:        1%{?dist}
Summary:        Native GNOME systemd service diagnostics

License:        GPL-3.0-or-later
URL:            https://github.com/tobiasGuta/ServiceForge
Source0:        %{url}/archive/refs/tags/v%{version}.tar.gz#/ServiceForge-%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  pyproject-rpm-macros
BuildRequires:  desktop-file-utils

Requires:       python3-gobject
Requires:       python3-systemd
Requires:       gtk4
Requires:       libadwaita
Requires:       systemd

%description
ServiceForge is a GNOME desktop application for inspecting system and user
services, following systemd activity, and reading the journal.

%prep
%autosetup -n ServiceForge-%{version}

%generate_buildrequires
%pyproject_buildrequires

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files -l serviceforge
desktop-file-install --dir=%{buildroot}%{_datadir}/applications packaging/io.github.tobiasGuta.ServiceForge.desktop

%check
%{python3} -m unittest discover -s tests
desktop-file-validate %{buildroot}%{_datadir}/applications/io.github.tobiasGuta.ServiceForge.desktop

%files -f %{pyproject_files}
%doc README.md
%{_bindir}/serviceforge
%{_datadir}/applications/io.github.tobiasGuta.ServiceForge.desktop

%changelog
* Fri Nov 13 2026 ServiceForge contributors - 0.1.0-1
- Package the first ServiceForge preview.
