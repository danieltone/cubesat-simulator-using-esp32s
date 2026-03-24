#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import json
import os
import sqlite3
import sys
import time
from collections import deque
from typing import Any, Dict, Optional, Tuple

try:
    import serial  # type: ignore
except Exception:
    serial = None


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def nested_get(data: Dict[str, Any], path: Tuple[str, ...], default: Any = None) -> Any:
    cursor: Any = data
    for key in path:
        if not isinstance(cursor, dict) or key not in cursor:
            return default
        cursor = cursor[key]
    return cursor


def normalize_message(obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if obj.get("type") == "telemetry":
        return obj

    if obj.get("event") == "rx" and isinstance(obj.get("payload"), str):
        payload = obj["payload"]
        try:
            inner = json.loads(payload)
            return inner
        except json.JSONDecodeError:
            return None

    return None


def flatten_telemetry(msg: Dict[str, Any]) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "timestamp_utc": utc_now_iso(),
        "node": msg.get("node"),
        "type": msg.get("type", msg.get("t", "unknown")),
        "mission_time_s": msg.get("mission_time_s", msg.get("mt")),
        "heartbeat_s": msg.get("heartbeat_s"),
        "orbit_altitude_km": nested_get(msg, ("orbit", "altitude_km")),
        "orbit_inclination_deg": nested_get(msg, ("orbit", "inclination_deg")),
        "orbit_latitude_deg": nested_get(msg, ("orbit", "latitude_deg"), msg.get("lat")),
        "orbit_longitude_deg": nested_get(msg, ("orbit", "longitude_deg"), msg.get("lon")),
        "orbit_eclipse": nested_get(msg, ("orbit", "eclipse"), msg.get("e")),
        "eps_battery_soc_pct": nested_get(msg, ("eps", "battery_soc_pct"), msg.get("soc")),
        "eps_battery_v": nested_get(msg, ("eps", "battery_v")),
        "eps_battery_i_a": nested_get(msg, ("eps", "battery_i_a")),
        "eps_solar_w": nested_get(msg, ("eps", "solar_w")),
        "eps_load_w": nested_get(msg, ("eps", "load_w")),
        "thermal_bus_c": nested_get(msg, ("thermal", "bus_c"), msg.get("tb", msg.get("temp"))),
        "thermal_battery_c": nested_get(msg, ("thermal", "battery_c")),
        "thermal_payload_c": nested_get(msg, ("thermal", "payload_c")),
        "adcs_roll_deg": nested_get(msg, ("adcs", "attitude_euler_deg", "roll")),
        "adcs_pitch_deg": nested_get(msg, ("adcs", "attitude_euler_deg", "pitch")),
        "adcs_yaw_deg": nested_get(msg, ("adcs", "attitude_euler_deg", "yaw")),
        "comms_downlink_bps": nested_get(msg, ("comms", "downlink_bps")),
        "comms_snr_db": nested_get(msg, ("comms", "snr_db"), msg.get("snr")),
        "comms_rssi_dbm": nested_get(msg, ("comms", "rssi_dbm"), msg.get("rssi")),
        "raw_json": json.dumps(msg, separators=(",", ":")),
    }
    if record["orbit_altitude_km"] is None:
        record["orbit_altitude_km"] = msg.get("alt")
    return record


def ensure_parent(path: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def display_path(path: str) -> str:
    try:
        abs_path = os.path.abspath(path)
        rel_path = os.path.relpath(abs_path, os.getcwd())
        if not rel_path.startswith(".."):
            return rel_path
        return os.path.basename(path)
    except Exception:
        return path


def init_csv(csv_path: str, fieldnames: list[str]) -> Tuple[Any, csv.DictWriter]:
    ensure_parent(csv_path)
    exists = os.path.exists(csv_path)
    csv_file = open(csv_path, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
    if not exists:
        writer.writeheader()
        csv_file.flush()
    return csv_file, writer


def init_db(db_path: str) -> sqlite3.Connection:
    ensure_parent(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS telemetry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp_utc TEXT,
            node TEXT,
            type TEXT,
            mission_time_s REAL,
            heartbeat_s REAL,
            orbit_altitude_km REAL,
            orbit_inclination_deg REAL,
            orbit_latitude_deg REAL,
            orbit_longitude_deg REAL,
            orbit_eclipse INTEGER,
            eps_battery_soc_pct REAL,
            eps_battery_v REAL,
            eps_battery_i_a REAL,
            eps_solar_w REAL,
            eps_load_w REAL,
            thermal_bus_c REAL,
            thermal_battery_c REAL,
            thermal_payload_c REAL,
            adcs_roll_deg REAL,
            adcs_pitch_deg REAL,
            adcs_yaw_deg REAL,
            comms_downlink_bps REAL,
            comms_snr_db REAL,
            comms_rssi_dbm REAL,
            raw_json TEXT
        )
        """
    )
    conn.commit()
    return conn


def insert_db(conn: sqlite3.Connection, rec: Dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO telemetry (
            timestamp_utc, node, type, mission_time_s, heartbeat_s,
            orbit_altitude_km, orbit_inclination_deg, orbit_latitude_deg, orbit_longitude_deg, orbit_eclipse,
            eps_battery_soc_pct, eps_battery_v, eps_battery_i_a, eps_solar_w, eps_load_w,
            thermal_bus_c, thermal_battery_c, thermal_payload_c,
            adcs_roll_deg, adcs_pitch_deg, adcs_yaw_deg,
            comms_downlink_bps, comms_snr_db, comms_rssi_dbm,
            raw_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            rec.get("timestamp_utc"),
            rec.get("node"),
            rec.get("type"),
            rec.get("mission_time_s"),
            rec.get("heartbeat_s"),
            rec.get("orbit_altitude_km"),
            rec.get("orbit_inclination_deg"),
            rec.get("orbit_latitude_deg"),
            rec.get("orbit_longitude_deg"),
            int(bool(rec.get("orbit_eclipse"))) if rec.get("orbit_eclipse") is not None else None,
            rec.get("eps_battery_soc_pct"),
            rec.get("eps_battery_v"),
            rec.get("eps_battery_i_a"),
            rec.get("eps_solar_w"),
            rec.get("eps_load_w"),
            rec.get("thermal_bus_c"),
            rec.get("thermal_battery_c"),
            rec.get("thermal_payload_c"),
            rec.get("adcs_roll_deg"),
            rec.get("adcs_pitch_deg"),
            rec.get("adcs_yaw_deg"),
            rec.get("comms_downlink_bps"),
            rec.get("comms_snr_db"),
            rec.get("comms_rssi_dbm"),
            rec.get("raw_json"),
        ),
    )


def open_source(args: argparse.Namespace):
    if args.stdin:
        return sys.stdin

    if serial is None:
        raise RuntimeError("pyserial is not installed. Install dependencies first.")
    if not args.port:
        raise RuntimeError("--port is required unless --stdin is used.")

    return serial.Serial(args.port, args.baud, timeout=0.5)


def maybe_init_plot(enabled: bool):
    if not enabled:
        return None

    import matplotlib.pyplot as plt  # type: ignore

    plt.ion()
    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    axes[0].set_ylabel("Battery SOC (%)")
    axes[1].set_ylabel("Bus Temp (C)")
    axes[2].set_ylabel("Altitude (km)")
    axes[2].set_xlabel("Samples")
    fig.suptitle("CubeSat Telemetry Live View")

    return {
        "plt": plt,
        "fig": fig,
        "axes": axes,
        "x": deque(maxlen=200),
        "soc": deque(maxlen=200),
        "temp": deque(maxlen=200),
        "alt": deque(maxlen=200),
        "counter": 0,
    }


def update_plot(plot_ctx, rec: Dict[str, Any]) -> None:
    if plot_ctx is None:
        return

    plot_ctx["counter"] += 1
    x = plot_ctx["counter"]
    plot_ctx["x"].append(x)
    plot_ctx["soc"].append(rec.get("eps_battery_soc_pct"))
    plot_ctx["temp"].append(rec.get("thermal_bus_c"))
    plot_ctx["alt"].append(rec.get("orbit_altitude_km"))

    axes = plot_ctx["axes"]
    for ax in axes:
        ax.cla()

    axes[0].plot(plot_ctx["x"], plot_ctx["soc"], color="tab:green")
    axes[1].plot(plot_ctx["x"], plot_ctx["temp"], color="tab:red")
    axes[2].plot(plot_ctx["x"], plot_ctx["alt"], color="tab:blue")

    axes[0].set_ylabel("Battery SOC (%)")
    axes[1].set_ylabel("Bus Temp (C)")
    axes[2].set_ylabel("Altitude (km)")
    axes[2].set_xlabel("Samples")
    plot_ctx["fig"].tight_layout()
    plot_ctx["plt"].pause(0.001)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ground-station logger for CubeSat simulator telemetry (Serial JSON stream)."
    )
    parser.add_argument("--port", default=None, help="Serial port (e.g., /dev/ttyACM0)")
    parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate")
    parser.add_argument("--stdin", action="store_true", help="Read newline JSON from stdin instead of serial")
    parser.add_argument("--csv", default="data/telemetry.csv", help="CSV output path")
    parser.add_argument("--db", default="data/telemetry.db", help="SQLite output path")
    parser.add_argument("--plot", action="store_true", help="Enable live plotting")
    parser.add_argument("--echo", action="store_true", help="Echo parsed telemetry summaries")
    parser.add_argument("--max-records", type=int, default=0, help="Stop after N records (0 = infinite)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    fieldnames = [
        "timestamp_utc",
        "node",
        "type",
        "mission_time_s",
        "heartbeat_s",
        "orbit_altitude_km",
        "orbit_inclination_deg",
        "orbit_latitude_deg",
        "orbit_longitude_deg",
        "orbit_eclipse",
        "eps_battery_soc_pct",
        "eps_battery_v",
        "eps_battery_i_a",
        "eps_solar_w",
        "eps_load_w",
        "thermal_bus_c",
        "thermal_battery_c",
        "thermal_payload_c",
        "adcs_roll_deg",
        "adcs_pitch_deg",
        "adcs_yaw_deg",
        "comms_downlink_bps",
        "comms_snr_db",
        "comms_rssi_dbm",
        "raw_json",
    ]

    csv_file, writer = init_csv(args.csv, fieldnames)
    conn = init_db(args.db)
    src = None
    plot_ctx = maybe_init_plot(args.plot)

    record_count = 0
    last_commit = time.time()

    try:
        src = open_source(args)
        print(
            json.dumps(
                {
                    "event": "logger_started",
                    "timestamp_utc": utc_now_iso(),
                    "port": args.port,
                    "baud": args.baud,
                    "stdin": args.stdin,
                    "csv": display_path(args.csv),
                    "db": display_path(args.db),
                    "plot": args.plot,
                }
            )
        )

        while True:
            line = src.readline()
            if not line:
                if plot_ctx is not None:
                    plot_ctx["plt"].pause(0.001)
                continue

            if isinstance(line, bytes):
                line = line.decode("utf-8", errors="replace")

            line = line.strip()
            if not line:
                continue

            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            normalized = normalize_message(msg)
            if normalized is None:
                continue

            rec = flatten_telemetry(normalized)
            writer.writerow(rec)
            csv_file.flush()

            insert_db(conn, rec)
            record_count += 1

            if time.time() - last_commit > 2.0:
                conn.commit()
                last_commit = time.time()

            if args.echo:
                print(
                    json.dumps(
                        {
                            "event": "record",
                            "count": record_count,
                            "node": rec.get("node"),
                            "mt": rec.get("mission_time_s"),
                            "soc": rec.get("eps_battery_soc_pct"),
                            "temp": rec.get("thermal_bus_c"),
                            "alt": rec.get("orbit_altitude_km"),
                        }
                    )
                )

            update_plot(plot_ctx, rec)

            if args.max_records > 0 and record_count >= args.max_records:
                break

    except KeyboardInterrupt:
        print('{"event":"logger_stopped","reason":"keyboard_interrupt"}')
    except Exception as ex:
        print(json.dumps({"event": "logger_error", "error": str(ex)}), file=sys.stderr)
        return 1
    finally:
        try:
            conn.commit()
            conn.close()
        except Exception:
            pass
        try:
            csv_file.close()
        except Exception:
            pass
        if src is not None and src is not sys.stdin:
            try:
                src.close()
            except Exception:
                pass

    print(json.dumps({"event": "logger_done", "records": record_count}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
