# Changelog

## 0.3.0 — 2026-10-25 (native Python preview)

- Replace the standard WebKit path with native GTK3/Cairo drawing and direct touch/mouse handling. No browser, HTTP server, pip, Node or virtual environment is required.
- Reuse the standard-library demo/HA data adapter directly in a background worker; legacy web preview stays separate.
- Install only missing native distribution packages; no default browser launch or download.
- Share circular geometry between drawing and touch, serialize data/writes, handle secondary contacts and cancellations.
- Ignore stale, unlistened screen-test sockets without deleting another tool’s files.
- Verified 800x800@60 HDMI-A-2 demo rendering and native touch on Pi; user confirmed complete display, step buttons and ring drag. Other configurations and live HA remain separately scoped.

## 0.2.0 — 2026-10-25 (software preview)

- Add the standard project entrypoint: info, check, run, start, status, logs, restart and stop.
- Declare the versioned single-round/touch/climate profile; reject unsupported shapes, dual panels, readonly/non-touch modes and invalid contexts.
- Bind a WebKitGTK view to a uniquely identified HDMI monitor using GTK layer-shell, with viewport verification and disconnect/mode-change detection.
- Add per-user/output leases, private instance control sockets, readiness supervision, idempotent startup and same-app replacement rollback.
- Isolate demo from inherited HA credentials; live reads a private token file and never falls back to demo.
- Add circular safe margins, touch-sized step buttons, ring-only gesture initiation, primary-pointer ownership and cancellation handling.
- Keep legacy Chromium launchers and detect the old user-service conflict. No new autostart is installed.
- Add backend/contract/lifecycle tests and browser touch checks at 360/480/720/800.
- Hardware acceptance is pending: native WebKitGTK, physical HDMI binding and touch calibration must be verified on the target Raspberry Pi.
