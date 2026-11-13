# Live monitoring — Fedora integration test

This verifies the signal-driven explorer and recent activity feed with a
**disposable user service**. It does not test privileged system operations
and does not require root access.

## Setup

Update and launch the app from your ServiceForge repository:

```bash
git pull --ff-only
PYTHONPATH=src python3 -m serviceforge
```

In a second terminal, create a disposable unit:

```bash
mkdir -p ~/.config/systemd/user

cat > ~/.config/systemd/user/serviceforge-monitor-test.service <<'EOF'
[Unit]
Description=Disposable ServiceForge live-monitor test

[Service]
Type=simple
ExecStart=/usr/bin/sleep infinity
Restart=no
EOF

systemctl --user daemon-reload
```

## Verify the UI

1. Switch ServiceForge to **User services**. Confirm the top-right **Live**
   button is active and the footer says `Live · systemd events` (or shows an
   explicit fallback/polling reason).
2. Search for `serviceforge-monitor-test.service`. It may initially appear
   as `unloaded / unknown` because its unit file is installed but not loaded.
3. Run in the second terminal:

   ```bash
   systemctl --user start serviceforge-monitor-test.service
   ```

   With Live monitoring available, the row should update to
   `active / running` automatically after a brief debounce. If the footer
   says Polling, updates may take up to 45 seconds.
   Open the Inspector and repeat a stop and start from the terminal. Check
   that the running state, current PID, available actions, and last-checked
   time update while the Inspector is open.
4. Click **Overview**. You should see recent events such as a systemd
   job finishing and a unit being loaded. These are live observations,
   **not** historical journal messages.
5. Run:

   ```bash
   systemctl --user stop serviceforge-monitor-test.service
   ```

   The row should change or return to an unloaded state; the installed
   file should still be discoverable. Overview should record manager
   activity observed while Live was enabled.
6. Turn **Live** off. Run the start command again. The app should not
   automatically refresh due to D-Bus events while monitoring is paused.
   Manual Refresh should still work.
7. Re-enable **Live** and refresh. Verify it reconnects to the selected
   user manager and resumes responding to service events.
8. Switch between **System services** and **User services**; activity
   histories should remain scoped and must not show user units under the
   system manager. The previous list should clear while the new scope loads.

If the footer shows a D-Bus subscription problem, share its **error text**
but do not loosen permissions or run the GUI with sudo. The 45-second
fallback is deliberate. The separate journal viewer may show additional
manager lifecycle messages, but log access depends on your normal account.

## Cleanup

```bash
systemctl --user stop serviceforge-monitor-test.service || true
rm -f ~/.config/systemd/user/serviceforge-monitor-test.service
systemctl --user daemon-reload
```

This only deletes the disposable unit you created. It does not touch
existing user or system service files.
