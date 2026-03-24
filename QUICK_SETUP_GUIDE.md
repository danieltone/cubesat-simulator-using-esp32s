# Quick Setup Guide (1-2-3)

This is the fastest way to run the CubeSat simulator and show the dashboards.

## Fastest possible preview (almost zero effort)

If you just want to immediately see what the dashboard experience looks like, open the prebuilt demo landing page:

```bash
xdg-open demo/dashboards/index.html
```

That is the quickest way to preview sample scenarios in your browser.

## Path A: Instant Demo (no hardware)

### 1) Generate demo dashboards

```bash
python3 generate_demo_dashboards.py
```

### 2) Open demo landing page

```bash
xdg-open demo/dashboards/index.html
```

### 3) Click through the three scenarios

- `Nominal Operations`
- `Eclipse-Heavy Passes`
- `Anomaly Storm`

Use this path for presentations and product walkthroughs.

---

## Path B: Live Workflow (with XIAO ESP32-C3)

### One-command launcher (fastest live path)

```bash
bash run_live_demo.sh
```

This starts the serial logger + auto-refresh dashboard server together, opens the dashboard in your browser, and stops both with Ctrl+C.

For receiver-based ground-station mode (ESP-WROOM-32 usually appears as `/dev/ttyUSB0`):

```bash
SERIAL_PORT=/dev/ttyUSB0 bash run_live_demo.sh
```

Tested end-to-end hardware pair:

- XIAO ESP32-C3 as transmitter
- ESP-WROOM-32 as ground receiver

Important: replace `GROUND_STATION_MAC` in `cubesat_simulator.ino` with **your own receiver MAC**.
The included MAC is only a proof-of-concept from one test setup.

For realistic OTA behavior, this path uses **two boards**:

- Transmitter node: XIAO ESP32-C3 running `cubesat_simulator.ino`
- Receiver node: ESP32 running `ground_station_receiver.ino`

The host (Raspberry Pi/PC) connects to the receiver over USB serial.

If your host already has a compatible radio front-end and decoder path, that can replace the separate receiver board.

Before wiring/connecting, see `SERIAL_CONNECTIONS.md` for minimal cabling and safe serial setup.

### 1) Flash and start telemetry source

- Flash `cubesat_simulator.ino` to the XIAO ESP32-C3
- Confirm it emits JSON every 15s on serial (`115200` baud)

### 2) Flash/start ground receiver (OTA mode)

- Flash `ground_station_receiver.ino` to a second ESP32
- Read receiver MAC and set `GROUND_STATION_MAC` in transmitter firmware
- Enable `ENABLE_ESPNOW = true` in transmitter firmware

### 3) Start ground ingest logger

```bash
python3 ground_station_logger.py --port /dev/ttyACM0 --baud 115200 --echo
```

This writes:

- `data/telemetry.csv`
- `data/telemetry.db`

### 4) Start live dashboard server and open UI

In another terminal:

```bash
python3 live_dashboard_server.py --interval 5 --port 8000
xdg-open http://127.0.0.1:8000/dashboard.html
```

---

## Optional: quick analysis commands

Text report:

```bash
python3 telemetry_report.py --limit 100
```

JSON report:

```bash
python3 telemetry_report.py --limit 100 --json
```

One-shot dashboard refresh:

```bash
python3 live_dashboard_server.py --refresh-only
```
