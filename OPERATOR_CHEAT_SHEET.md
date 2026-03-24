# Operator Cheat Sheet

Copy/paste commands for running demos and live telemetry quickly.

## 0) Open project folder

```bash
cd /path/to/cubesat_simulator
```

---

## Demo mode (no hardware)

### 1) Generate sample dashboards

```bash
python3 generate_demo_dashboards.py
```

### 2) Open demo landing page

```bash
xdg-open demo/dashboards/index.html
```

---

## Live mode (with XIAO ESP32-C3)

OTA mode requires both components:

- Transmitter: XIAO ESP32-C3 (`cubesat_simulator.ino`)
- Receiver: second ESP32 (`ground_station_receiver.ino`)

If your host has a compatible radio interface + decoder, that can replace the separate receiver board.

### Terminal A: logger (ingest serial)

```bash
python3 ground_station_logger.py --port /dev/ttyACM0 --baud 115200 --echo
```

### Terminal B: live dashboard

```bash
python3 live_dashboard_server.py --interval 5 --port 8000
```

### Open dashboard in browser

```bash
xdg-open http://127.0.0.1:8000/dashboard.html
```

---

## Quick report commands

### Text summary

```bash
python3 telemetry_report.py --limit 100
```

### JSON summary

```bash
python3 telemetry_report.py --limit 100 --json
```

### One-shot dashboard refresh

```bash
python3 live_dashboard_server.py --refresh-only
```

---

## Typical files to show in demo

- `demo/dashboards/index.html`
- `data/dashboard.html`
- `data/telemetry.csv`
- `data/telemetry.db`
