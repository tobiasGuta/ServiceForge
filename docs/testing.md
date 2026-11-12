# Safe manual testing: runtime actions

**Do not test ServiceForge service-changing operations on real networking,
authentication, display management, audit, or other critical Fedora services.**

This creates an ordinary, harmless user-level unit using `sleep`. It can be
started, stopped, and restarted without administrative privileges.

## 1. Create a disposable user service

On your Fedora machine, run:

```bash
mkdir -p ~/.config/systemd/user

cat > ~/.config/systemd/user/serviceforge-test.service <<'EOF'
[Unit]
Description=Disposable ServiceForge runtime-action test

[Service]
Type=simple
ExecStart=/usr/bin/sleep infinity
Restart=no
EOF

systemctl --user daemon-reload
systemctl --user start serviceforge-test.service
systemctl --user status serviceforge-test.service
```

## 2. Test ServiceForge

Launch the app normally:

```bash
PYTHONPATH=src python3 -m serviceforge
```

Switch the top-left dropdown to **User services**, search
`serviceforge-test.service`, and open its **Inspector**.

- When the unit is active, Stop and Restart should be available.
- Reload should be disabled, because this unit has no reload implementation.
- A confirmation should appear before any action is sent.
- After confirming Restart, verify a systemd job result appears, then
  verify that MainPID or state changed on refresh.
- Try Stop, then refresh or search again. The stopped unit may remain loaded,
  but availability depends on the systemd manager's unit lifecycle.
- If the unit is still visible when inactive, Start should become available.
- Check Logs for entries. It may contain lifecycle events emitted by the
  user manager, but no output from `sleep` itself is expected.

For an independent check:

```bash
systemctl --user show serviceforge-test.service -p ActiveState -p SubState -p MainPID
journalctl --user -u serviceforge-test.service -b --no-pager -n 25
```

Journal entries are not guaranteed for every service. A lack of messages
must not be treated as a service failure.

## 3. Cleanup

```bash
systemctl --user stop serviceforge-test.service
rm ~/.config/systemd/user/serviceforge-test.service
systemctl --user daemon-reload
```

If you see a D-Bus or Polkit error, copy the **error message**, not sensitive
journal contents. Do not broaden permissions or disable SELinux to make tests
pass.

This test validates user-manager runtime actions. System-manager Polkit
integration must be tested separately against an equally disposable system
unit, with explicit attention to its security effects.
