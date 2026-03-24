#!/usr/bin/env python3
import argparse
import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate an offline HTML dashboard from CubeSat telemetry SQLite logs."
    )
    parser.add_argument("--db", default="data/telemetry.db", help="SQLite database path")
    parser.add_argument("--out", default="data/dashboard.html", help="Output HTML file path")
    parser.add_argument("--limit", type=int, default=500, help="Number of most recent records to chart")
    parser.add_argument("--soc-low", type=float, default=25.0)
    parser.add_argument("--soc-high", type=float, default=98.0)
    parser.add_argument("--temp-high", type=float, default=45.0)
    parser.add_argument("--temp-low", type=float, default=-10.0)
    parser.add_argument("--snr-low", type=float, default=3.0)
    parser.add_argument("--rssi-low", type=float, default=-120.0)
    parser.add_argument("--alt-low", type=float, default=120.0)
    parser.add_argument("--alt-high", type=float, default=2000.0)
    return parser.parse_args()


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


def fetch_rows(conn: sqlite3.Connection, limit: int) -> List[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    if limit > 0:
        cur.execute(
            """
            SELECT * FROM telemetry
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
    else:
        cur.execute("SELECT * FROM telemetry ORDER BY id DESC")
    rows = cur.fetchall()
    rows.reverse()
    return rows


def stats(values: List[float]) -> Dict[str, Any]:
    if not values:
        return {"count": 0, "min": None, "max": None, "avg": None}
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "avg": sum(values) / len(values),
    }


def build_payload(rows: List[sqlite3.Row], thresholds: Dict[str, float], db_path: str) -> Dict[str, Any]:
  db_display = display_path(db_path)

  labels: List[str] = []
  soc: List[float] = []
  bus_temp: List[float] = []
  altitude: List[float] = []
  snr: List[float] = []
  rssi: List[float] = []

  anomalies = {
    "battery_soc_low": 0,
    "battery_soc_high": 0,
    "bus_temp_high": 0,
    "bus_temp_low": 0,
    "snr_low": 0,
    "rssi_low": 0,
    "altitude_low": 0,
    "altitude_high": 0,
  }

  distinct_nodes = set()
  first_ts = None
  last_ts = None

  for row in rows:
    ts = row["timestamp_utc"]
    labels.append(ts)
    if first_ts is None:
      first_ts = ts
    last_ts = ts

    if row["node"]:
      distinct_nodes.add(row["node"])

    soc_val = row["eps_battery_soc_pct"]
    temp_val = row["thermal_bus_c"]
    alt_val = row["orbit_altitude_km"]
    snr_val = row["comms_snr_db"]
    rssi_val = row["comms_rssi_dbm"]

    soc.append(soc_val if soc_val is not None else float("nan"))
    bus_temp.append(temp_val if temp_val is not None else float("nan"))
    altitude.append(alt_val if alt_val is not None else float("nan"))
    snr.append(snr_val if snr_val is not None else float("nan"))
    rssi.append(rssi_val if rssi_val is not None else float("nan"))

    if soc_val is not None and soc_val < thresholds["soc_low"]:
      anomalies["battery_soc_low"] += 1
    if soc_val is not None and soc_val > thresholds["soc_high"]:
      anomalies["battery_soc_high"] += 1
    if temp_val is not None and temp_val > thresholds["temp_high"]:
      anomalies["bus_temp_high"] += 1
    if temp_val is not None and temp_val < thresholds["temp_low"]:
      anomalies["bus_temp_low"] += 1
    if snr_val is not None and snr_val < thresholds["snr_low"]:
      anomalies["snr_low"] += 1
    if rssi_val is not None and rssi_val < thresholds["rssi_low"]:
      anomalies["rssi_low"] += 1
    if alt_val is not None and alt_val < thresholds["alt_low"]:
      anomalies["altitude_low"] += 1
    if alt_val is not None and alt_val > thresholds["alt_high"]:
      anomalies["altitude_high"] += 1

  def finite(values: List[float]) -> List[float]:
    out: List[float] = []
    for value in values:
      if value == value:
        out.append(value)
    return out

  summary = {
    "generated_utc": datetime.now(timezone.utc).isoformat(),
    "db": db_display,
    "records": len(rows),
    "distinct_nodes": len(distinct_nodes),
    "first_timestamp_utc": first_ts,
    "last_timestamp_utc": last_ts,
    "stats": {
      "eps_battery_soc_pct": stats(finite(soc)),
      "thermal_bus_c": stats(finite(bus_temp)),
      "orbit_altitude_km": stats(finite(altitude)),
      "comms_snr_db": stats(finite(snr)),
      "comms_rssi_dbm": stats(finite(rssi)),
    },
    "anomalies": anomalies,
    "anomaly_total": sum(anomalies.values()),
    "thresholds": thresholds,
  }

  latest = None
  if rows:
    tail = rows[-1]
    latest = {
      "timestamp_utc": tail["timestamp_utc"],
      "node": tail["node"],
      "mission_time_s": tail["mission_time_s"],
      "eps_battery_soc_pct": tail["eps_battery_soc_pct"],
      "thermal_bus_c": tail["thermal_bus_c"],
      "orbit_altitude_km": tail["orbit_altitude_km"],
      "comms_snr_db": tail["comms_snr_db"],
      "comms_rssi_dbm": tail["comms_rssi_dbm"],
    }

  return {
    "summary": summary,
    "latest": latest,
    "series": {
      "labels": labels,
      "soc": soc,
      "bus_temp": bus_temp,
      "altitude": altitude,
      "snr": snr,
      "rssi": rssi,
    },
  }


def render_html(payload: Dict[str, Any]) -> str:
    payload_json = json.dumps(payload, separators=(",", ":"))
    template = """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\" />
  <title>CubeSat Telemetry Dashboard</title>
  <script src=\"https://cdn.jsdelivr.net/npm/chart.js\"></script>
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 1rem; background: #0f172a; color: #e2e8f0; }
    h1, h2 { margin: 0.2rem 0; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem; margin-top: 1rem; }
    .card { background: #111827; border: 1px solid #334155; border-radius: 10px; padding: 0.9rem; }
    .small { color: #94a3b8; font-size: 0.9rem; }
    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; padding: 0.35rem; border-bottom: 1px solid #1f2937; font-size: 0.92rem; }
    .ok { color: #22c55e; }
    .warn { color: #f59e0b; }
    canvas { width: 100% !important; max-height: 260px; }
    pre { white-space: pre-wrap; word-break: break-word; background: #020617; padding: 0.7rem; border-radius: 8px; border: 1px solid #1e293b; }
  </style>
</head>
<body>
  <h1>CubeSat Telemetry Dashboard</h1>
  <div id=\"meta\" class=\"small\"></div>

  <div class=\"grid\">
    <div class=\"card\">
      <h2>Summary</h2>
      <div id=\"summary\"></div>
    </div>
    <div class=\"card\">
      <h2>Anomalies</h2>
      <div id=\"anomalies\"></div>
    </div>
    <div class=\"card\">
      <h2>Latest Record</h2>
      <pre id=\"latest\"></pre>
    </div>
  </div>

  <div class=\"grid\">
    <div class=\"card\"><h2>Battery SOC (%)</h2><canvas id=\"socChart\"></canvas></div>
    <div class=\"card\"><h2>Bus Temp (°C)</h2><canvas id=\"tempChart\"></canvas></div>
    <div class=\"card\"><h2>Altitude (km)</h2><canvas id=\"altChart\"></canvas></div>
    <div class=\"card\"><h2>SNR (dB)</h2><canvas id=\"snrChart\"></canvas></div>
    <div class=\"card\"><h2>RSSI (dBm)</h2><canvas id=\"rssiChart\"></canvas></div>
  </div>

  <script>
    const payload = __PAYLOAD_JSON__;
    const summary = payload.summary;
    const series = payload.series;

    document.getElementById('meta').textContent =
      `Generated ${summary.generated_utc} | DB: ${summary.db} | Records: ${summary.records}`;

    const summaryHtml = `
      <table>
        <tr><th>Distinct nodes</th><td>${summary.distinct_nodes}</td></tr>
        <tr><th>Time range</th><td>${summary.first_timestamp_utc} → ${summary.last_timestamp_utc}</td></tr>
        <tr><th>Anomaly total</th><td class="${summary.anomaly_total > 0 ? 'warn' : 'ok'}">${summary.anomaly_total}</td></tr>
      </table>
      <h3>Metric Min / Max / Avg</h3>
      <table>
        ${Object.entries(summary.stats).map(([k,v]) => `<tr><th>${k}</th><td>${fmt(v.min)} / ${fmt(v.max)} / ${fmt(v.avg)}</td></tr>`).join('')}
      </table>
    `;
    document.getElementById('summary').innerHTML = summaryHtml;

    const anomalyHtml = `
      <table>
        ${Object.entries(summary.anomalies).map(([k,v]) => `<tr><th>${k}</th><td class="${v > 0 ? 'warn' : 'ok'}">${v}</td></tr>`).join('')}
      </table>
      <h3>Thresholds</h3>
      <table>
        ${Object.entries(summary.thresholds).map(([k,v]) => `<tr><th>${k}</th><td>${v}</td></tr>`).join('')}
      </table>
    `;
    document.getElementById('anomalies').innerHTML = anomalyHtml;

    document.getElementById('latest').textContent = JSON.stringify(payload.latest, null, 2);

    function fmt(v) {
      if (v === null || v === undefined || Number.isNaN(v)) return 'n/a';
      return Number(v).toFixed(2);
    }

    function mkChart(canvasId, data, label, color) {
      const elem = document.getElementById(canvasId);
      if (!window.Chart || !elem) return;
      new Chart(elem.getContext('2d'), {
        type: 'line',
        data: {
          labels: series.labels,
          datasets: [{ label, data, borderColor: color, pointRadius: 0, borderWidth: 1.5, tension: 0.15 }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: { x: { display: false } }
        }
      });
    }

    mkChart('socChart', series.soc, 'Battery SOC', '#22c55e');
    mkChart('tempChart', series.bus_temp, 'Bus Temp', '#ef4444');
    mkChart('altChart', series.altitude, 'Altitude', '#3b82f6');
    mkChart('snrChart', series.snr, 'SNR', '#f59e0b');
    mkChart('rssiChart', series.rssi, 'RSSI', '#a78bfa');
  </script>
</body>
</html>
"""
    return template.replace("__PAYLOAD_JSON__", payload_json)


def main() -> int:
    args = parse_args()
    if not os.path.exists(args.db):
        print(json.dumps({"event": "dashboard_error", "error": f"Database not found: {args.db}"}))
        return 1

    thresholds = {
        "soc_low": args.soc_low,
        "soc_high": args.soc_high,
        "temp_high": args.temp_high,
        "temp_low": args.temp_low,
        "snr_low": args.snr_low,
        "rssi_low": args.rssi_low,
        "alt_low": args.alt_low,
        "alt_high": args.alt_high,
    }

    conn = sqlite3.connect(args.db)
    rows = fetch_rows(conn, args.limit)
    conn.close()

    payload = build_payload(rows, thresholds, args.db)
    html = render_html(payload)

    ensure_parent(args.out)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)

    print(
        json.dumps(
            {
                "event": "dashboard_written",
          "out": display_path(args.out),
                "records": payload["summary"]["records"],
                "anomalies": payload["summary"]["anomaly_total"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
