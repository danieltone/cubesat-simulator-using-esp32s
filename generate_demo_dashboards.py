#!/usr/bin/env python3
import json
import math
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List


SCHEMA_SQL = """
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


def ensure_dirs(base: Path) -> Dict[str, Path]:
    demo_dir = base / "demo"
    db_dir = demo_dir / "db"
    html_dir = demo_dir / "dashboards"
    db_dir.mkdir(parents=True, exist_ok=True)
    html_dir.mkdir(parents=True, exist_ok=True)
    return {"demo": demo_dir, "db": db_dir, "html": html_dir}


def insert_rows(db_path: Path, rows: Iterable[Dict]) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(SCHEMA_SQL)
    conn.execute("DELETE FROM telemetry")
    insert_sql = """
    INSERT INTO telemetry (
        timestamp_utc, node, type, mission_time_s, heartbeat_s,
        orbit_altitude_km, orbit_inclination_deg, orbit_latitude_deg, orbit_longitude_deg, orbit_eclipse,
        eps_battery_soc_pct, eps_battery_v, eps_battery_i_a, eps_solar_w, eps_load_w,
        thermal_bus_c, thermal_battery_c, thermal_payload_c,
        adcs_roll_deg, adcs_pitch_deg, adcs_yaw_deg,
        comms_downlink_bps, comms_snr_db, comms_rssi_dbm,
        raw_json
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """
    values: List[tuple] = []
    for record in rows:
        values.append(
            (
                record["timestamp_utc"],
                record.get("node", "SIM-DEMO"),
                "telemetry",
                record["mission_time_s"],
                15,
                record["orbit_altitude_km"],
                51.6,
                record["orbit_latitude_deg"],
                record["orbit_longitude_deg"],
                1 if record["orbit_eclipse"] else 0,
                record["eps_battery_soc_pct"],
                record["eps_battery_v"],
                record["eps_battery_i_a"],
                record["eps_solar_w"],
                record["eps_load_w"],
                record["thermal_bus_c"],
                record["thermal_battery_c"],
                record["thermal_payload_c"],
                record["adcs_roll_deg"],
                record["adcs_pitch_deg"],
                record["adcs_yaw_deg"],
                9600,
                record["comms_snr_db"],
                record["comms_rssi_dbm"],
                json.dumps(record, separators=(",", ":")),
            )
        )
    conn.executemany(insert_sql, values)
    conn.commit()
    conn.close()


def scenario_rows(name: str, n: int = 220) -> List[Dict]:
    start = datetime.now(timezone.utc) - timedelta(seconds=n * 15)
    rows: List[Dict] = []

    for i in range(n):
        t = i * 15
        theta = (2.0 * math.pi * i) / n
        lat = 51.6 * math.sin(theta)
        lon = ((i * 3.7) % 360) - 180
        eclipse = 0.33 < (i / n) < 0.67

        if name == "nominal":
            soc = 76 + 9 * math.sin(theta)
            temp = 22 + (4 if not eclipse else -3) + 0.8 * math.sin(2 * theta)
            snr = 10 + 2.5 * math.sin(1.3 * theta)
            rssi = -106 + 5 * math.sin(0.9 * theta)
            solar = 5.8 if not eclipse else 0.0
            load = 2.6 + 0.2 * math.sin(theta)
            alt = 525 + 2.5 * math.sin(0.2 * theta)
        elif name == "eclipse_heavy":
            eclipse = (i % 8) < 5
            soc = 64 + 14 * math.sin(theta) - (8 if eclipse else 0)
            temp = 17 + (5 if not eclipse else -6) + 1.4 * math.sin(1.8 * theta)
            snr = 8.5 + 2.2 * math.sin(1.1 * theta)
            rssi = -110 + 6.5 * math.sin(1.0 * theta)
            solar = 5.2 if not eclipse else 0.0
            load = 2.8 + 0.25 * math.sin(1.4 * theta)
            alt = 522 + 3.0 * math.sin(0.25 * theta)
        elif name == "anomaly_storm":
            soc = 42 + 22 * math.sin(1.5 * theta)
            temp = 30 + 18 * math.sin(0.8 * theta)
            snr = 4 + 5 * math.sin(1.6 * theta)
            rssi = -118 + 14 * math.sin(1.2 * theta)
            solar = 4.8 if not eclipse else 0.0
            load = 3.1 + 0.5 * math.sin(2.2 * theta)
            alt = 530 + 12 * math.sin(0.5 * theta)
            if 80 < i < 120:
                temp += 10
                snr -= 3
                rssi -= 8
        else:
            raise ValueError(f"Unknown scenario: {name}")

        soc = max(10.0, min(99.0, soc))
        battery_v = 3.45 + 0.75 * (soc / 100.0)
        batt_i = max(-1.5, min(1.5, (solar - load) / 3.7))

        row = {
            "timestamp_utc": (start + timedelta(seconds=t)).isoformat(),
            "node": f"SIM-{name.upper()}",
            "mission_time_s": t,
            "orbit_altitude_km": round(alt, 2),
            "orbit_latitude_deg": round(lat, 3),
            "orbit_longitude_deg": round(lon, 3),
            "orbit_eclipse": bool(eclipse),
            "eps_battery_soc_pct": round(soc, 2),
            "eps_battery_v": round(battery_v, 3),
            "eps_battery_i_a": round(batt_i, 3),
            "eps_solar_w": round(solar, 2),
            "eps_load_w": round(load, 2),
            "thermal_bus_c": round(temp, 2),
            "thermal_battery_c": round(temp - 2.0, 2),
            "thermal_payload_c": round(temp + 3.0, 2),
            "adcs_roll_deg": round(2.2 * math.sin(0.7 * theta), 3),
            "adcs_pitch_deg": round(1.9 * math.cos(0.8 * theta), 3),
            "adcs_yaw_deg": round((i * 1.6) % 360, 3),
            "comms_snr_db": round(snr, 2),
            "comms_rssi_dbm": round(rssi, 2),
        }
        rows.append(row)

    return rows


def render_dashboard(base: Path, db_path: Path, out_path: Path) -> None:
    db_arg = os.path.relpath(db_path, base)
    out_arg = os.path.relpath(out_path, base)
    cmd = [
        sys.executable,
        str(base / "telemetry_dashboard.py"),
        "--db",
        db_arg,
        "--out",
        out_arg,
        "--limit",
        "0",
    ]
    proc = subprocess.run(cmd, cwd=str(base), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())


def write_demo_index(html_dir: Path) -> Path:
        index_path = html_dir / "index.html"
        index_html = """<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>CubeSat Simulator Demo Dashboards</title>
    <style>
        body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 1.5rem; background: #0b1020; color: #e6edf3; }
        h1 { margin-bottom: 0.3rem; }
        .sub { color: #9fb0c0; margin-top: 0; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem; margin-top: 1.2rem; }
        .card { background: #121a2b; border: 1px solid #2f3f5a; border-radius: 10px; padding: 1rem; }
        .title { font-size: 1.05rem; margin-top: 0; }
        .desc { color: #a8b6c7; min-height: 3.2rem; }
        .btn { display: inline-block; margin-top: 0.5rem; padding: 0.45rem 0.75rem; border-radius: 8px; text-decoration: none; background: #2563eb; color: white; }
        .btn:hover { background: #1d4ed8; }
        code { background: #0a1222; border: 1px solid #22334f; border-radius: 6px; padding: 0.15rem 0.4rem; }
    </style>
</head>
<body>
    <h1>CubeSat Simulator Demo Dashboards</h1>
    <p class="sub">Use these sample dashboards to demo normal operations, eclipse behavior, and anomaly detection.</p>

    <div class="grid">
        <div class="card">
            <h2 class="title">1) Nominal Operations</h2>
            <p class="desc">Balanced power and thermal profile with healthy link quality and no significant anomalies.</p>
            <a class="btn" href="dashboard_sample_1_nominal.html">Open Dashboard</a>
        </div>

        <div class="card">
            <h2 class="title">2) Eclipse-Heavy Passes</h2>
            <p class="desc">Frequent eclipse periods showing SOC sag, cooler thermal behavior, and reduced solar input.</p>
            <a class="btn" href="dashboard_sample_2_eclipse_heavy.html">Open Dashboard</a>
        </div>

        <div class="card">
            <h2 class="title">3) Anomaly Storm</h2>
            <p class="desc">Injected comms/thermal stress to demonstrate threshold alerts and anomaly counting.</p>
            <a class="btn" href="dashboard_sample_3_anomaly_storm.html">Open Dashboard</a>
        </div>
    </div>

    <p style="margin-top:1.3rem;color:#8da2b8;">Tip: regenerate all demo artifacts anytime with <code>python3 generate_demo_dashboards.py</code>.</p>
</body>
</html>
"""
        index_path.write_text(index_html, encoding="utf-8")
        return index_path


def main() -> int:
    base = Path(__file__).resolve().parent
    paths = ensure_dirs(base)

    scenarios = [
        ("nominal", "dashboard_sample_1_nominal.html"),
        ("eclipse_heavy", "dashboard_sample_2_eclipse_heavy.html"),
        ("anomaly_storm", "dashboard_sample_3_anomaly_storm.html"),
    ]

    outputs = []
    for scenario_name, html_name in scenarios:
        db_path = paths["db"] / f"{scenario_name}.db"
        out_path = paths["html"] / html_name
        insert_rows(db_path, scenario_rows(scenario_name))
        render_dashboard(base, db_path, out_path)
        outputs.append(os.path.relpath(out_path, base))

    index_path = write_demo_index(paths["html"])

    print(
        json.dumps(
            {
                "event": "demo_dashboards_generated",
                "files": outputs,
                "index": os.path.relpath(index_path, base),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
