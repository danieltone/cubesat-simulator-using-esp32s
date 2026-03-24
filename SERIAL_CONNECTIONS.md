# Serial Connections: ESP32 ↔ Raspberry Pi / Computer

This guide explains the simplest and safest ways to connect your ESP32 boards for telemetry.

## Recommended path (modern ESP32 dev boards)

For most modern ESP32 boards (including XIAO ESP32-C3), the easiest path is:

1. Plug board into host with USB cable
2. Use host serial device (for example `/dev/ttyACM0` or `/dev/ttyUSB0`)
3. Run logger with `--port <device> --baud 115200`

No external USB-UART converter is required in this case.

---

## USB-UART adapter path (when board USB is unavailable)

If your board does not expose usable USB serial, use a cheap USB-UART adapter.

### Minimum wiring (3 wires)

- Adapter `GND` → ESP32 `GND`
- Adapter `TX`  → ESP32 `RX`
- Adapter `RX`  → ESP32 `TX`

This is the minimum data path.

### Powering

- Preferred: power ESP32 from its own USB port, and use adapter only for serial data
- If you must power from adapter, verify voltage compatibility first

Important:

- Use **3.3V logic-level UART**
- Do not connect mismatched logic voltages
- Avoid dual-power backfeed (for example USB power + adapter 5V) unless you know the board power design

---

## Raspberry Pi-specific notes

### Option A: USB cable (recommended)

Use USB from ESP32 (or USB-UART adapter) into Pi USB port.

Find serial port:

```bash
ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null
```

Run logger:

```bash
python3 ground_station_logger.py --port /dev/ttyACM0 --baud 115200 --echo
```

### Option B: Pi GPIO UART pins (advanced)

Possible, but more setup/risk than USB path:

- Keep both sides at 3.3V UART logic
- Ensure Linux serial console is not conflicting on that UART
- Still requires common GND and crossed TX/RX

For most users, USB path is faster and more reliable.

---

## Quick connection test

After connecting board, verify serial traffic:

```bash
python3 - <<'PY'
import serial
s = serial.Serial('/dev/ttyACM0', 115200, timeout=2)
for _ in range(5):
    line = s.readline().decode(errors='ignore').strip()
    if line:
        print(line)
PY
```

Then run normal pipeline:

```bash
python3 ground_station_logger.py --port /dev/ttyACM0 --baud 115200 --echo
python3 live_dashboard_server.py --interval 5 --port 8000
```

---

## Is this a good idea?

Yes. For this simulator, serial-over-USB is usually the best choice:

- lowest complexity
- stable and repeatable
- cheap
- easy to debug

Use OTA radio link mode when you specifically want to demonstrate transmitter/receiver architecture.
