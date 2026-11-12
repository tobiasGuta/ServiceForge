# Safe Fedora system-service authorization and Polkit test

This checks ServiceForge's **system manager** path with a disposable unit,
not a real Fedora network, authentication, display, or audit service.

**Important:** We cannot verify your local Polkit policy remotely. Fedora may
allow an authorized administrator without a prompt, ask for authentication,
or deny the request depending on the account and policy. Authentication UI
is provided by the desktop agent, not ServiceForge.

## 1. Create a harmless system service definition

This uses one specifically named file under `/etc/systemd/system`. Creation
and cleanup require `sudo`, but **ServiceForge itself must never be run as
root**.

```bash
sudo tee /etc/systemd/system/serviceforge-polkit-test.service >/dev/null <<'EOF'
[Unit]
Description=Disposable ServiceForge Polkit test

[Service]
Type=simple
ExecStart=/usr/bin/sleep infinity
Restart=no

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
systemctl is-enabled serviceforge-polkit-test.service || true
systemctl is-active serviceforge-polkit-test.service || true
```

It should be disabled and inactive initially. Do not enable any real system
service as part of this test.

## 2. Inspect and test authorization

Run ServiceForge normally from your repository:

```bash
PYTHONPATH=src python3 -m serviceforge
```

Select **System services**, search for
`serviceforge-polkit-test.service`, and open the Inspector.

- Verify the Enable button is available and opens a dialog.
- Cancel the ServiceForge confirmation; no D-Bus write should occur.
- Confirm **Enable** and enter the exact service name. Polkit may authenticate
  or allow/deny according to system policy.
- If authentication appears, **cancel it once**. ServiceForge should explain
  that authorization was denied or the operation was not verified. The unit
  should remain disabled. This tests the denial path without weakening policy.
- Retry and, if authorized, verify that `is-enabled` becomes `enabled`.
- **Disable**, confirm the typed name, and verify `is-enabled` becomes
  `disabled`. The service should remain inactive throughout.
- To test the runtime Polkit action, optionally **Start** then **Stop** only
  this disposable test service. Both use `manage-units`, while Enable/Disable
  use `manage-unit-files`.

Use terminal checks after each operation:

```bash
systemctl is-enabled serviceforge-polkit-test.service || true
systemctl is-active serviceforge-polkit-test.service || true
systemctl show serviceforge-polkit-test.service -p LoadState -p ActiveState -p UnitFileState
```

If no authentication prompt appears, that's not automatically a bug: policy
and cached authorization vary. If access is denied, don't run the entire GUI
under `sudo`, disable SELinux, loosen Polkit rules, or add blanket privileges.

### Masking is deliberately separate

Do **not** use this system test file to test Mask. It lives in
`/etc/systemd/system`, where a persistent mask would try to replace the
existing file. ServiceForge's `force=false` prevents that, correctly.

Use the disposable user unit in
[unit-file testing](unit-file-testing.md) for Mask/Unmask instead.

## 3. Cleanup (even if authorization failed)

```bash
sudo systemctl stop serviceforge-polkit-test.service || true
sudo systemctl disable serviceforge-polkit-test.service || true
sudo rm -f /etc/systemd/system/serviceforge-polkit-test.service
sudo systemctl daemon-reload
sudo systemctl reset-failed serviceforge-polkit-test.service || true
```

This cleans up **only** the named disposable unit. If you observe an unexpected
authorization result or behavior, save the specific D-Bus error and the
`is-enabled` output (not your password, credentials, or sensitive logs).
