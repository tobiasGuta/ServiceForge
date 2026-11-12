# Persistent unit-file actions: safe manual test on Fedora

ServiceForge's Enable, Disable, Mask, and Unmask operations are **experimental**.
They change persistent unit-file configuration but do not start or stop a
running service. Test them only on a disposable unit that you create.

## Why a different unit file?

The earlier `serviceforge-test.service` fixture was **static** (no
`[Install]` section). Static units cannot be enabled normally. Also, masking a
file installed directly in the highest-priority
`~/.config/systemd/user/` directory would require replacing that existing
file, which ServiceForge deliberately refuses to force.

Instead, create the unit in the lower-priority user search location
`~/.local/share/systemd/user/`. Its persistent enablement symlinks and mask
can safely live in `~/.config/systemd/user/` without overwriting the original.

## 1. Create a disposable user unit

```bash
mkdir -p ~/.local/share/systemd/user
cat > ~/.local/share/systemd/user/serviceforge-config-test.service <<'EOF'
[Unit]
Description=Disposable ServiceForge file-action test

[Service]
Type=simple
ExecStart=/usr/bin/sleep infinity
Restart=no

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user is-enabled serviceforge-config-test.service || true
systemctl --user is-active serviceforge-config-test.service || true
```

The initial unit-file state should normally be `disabled` and the service
inactive. Do not start it for this configuration test.

## 2. Verify each action in ServiceForge

Open the GUI as your normal user:

```bash
PYTHONPATH=src python3 -m serviceforge
```

Choose **User services**, search for
`serviceforge-config-test.service`, and open its Inspector.

1. **Enable**: Confirm. Unit-file state should become `enabled`, without
   starting the service.
2. **Disable**: Confirm. State should return to `disabled`, still not running.
3. **Mask**: With the unit inactive and disabled, confirm and type the exact
   service name. State should become `masked`; Start must not be offered.
4. **Unmask**: Confirm and type the name. State should return to `disabled`
   or the actual state reported by systemd. This does not start or enable it.

Independently check state after each step:

```bash
systemctl --user is-enabled serviceforge-config-test.service || true
systemctl --user is-active serviceforge-config-test.service || true
systemctl --user status serviceforge-config-test.service --no-pager
```

If a step fails, do not use `--force` or edit systemd policy to make it
succeed. Record the error message and the output of `is-enabled`. Errors
indicating a file already exists can mean the unit was installed in the
wrong directory; the safe default is not to overwrite it.

## 3. Cleanup

Do not leave a disposable test unit enabled or masked. After testing:

```bash
systemctl --user stop serviceforge-config-test.service || true
systemctl --user unmask serviceforge-config-test.service || true
systemctl --user disable serviceforge-config-test.service || true
rm -f ~/.local/share/systemd/user/serviceforge-config-test.service
systemctl --user daemon-reload
systemctl --user reset-failed serviceforge-config-test.service || true
```

Only remove the disposable file you created; don't delete other service files
or recursively remove systemd directories.

## Scope and limitations

- Startup configuration is independent of current runtime state.
- Masking can break dependent services, so ServiceForge currently only offers
  it for a disabled and inactive unit with a known file path.
- `static`, `indirect`, `generated`, `alias`, and runtime-only state
  transitions are intentionally unsupported.
- The application uses persistent (`runtime=false`), non-forcing
  (`force=false`) manager methods with interactive Polkit allowed.
- On a system service, permission may be denied or a Polkit agent may prompt.
  See [system-service authorization test](authorization-testing.md).
