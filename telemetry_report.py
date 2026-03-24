#!/usr/bin/env python3
import argparse
import json
import os
import sqlite3
import sys
from typing import Any, Dict, List, Tuple


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate summary and anomaly report from CubeSat telemetry SQLite database."
    )
    parser.add_argument("--db", default="data/telemetry.db", help="SQLite database path")
    parser.add_argument("--limit", type=int, default=0, help="Only analyze last N records (0 = all)")
    parser.add_argument("--json", action="store_true", help="Output report as JSON")
    parser.add_argument("--soc-low", type=float, default=25.0, help="Low battery SOC threshold (%)")
    parser.add_argument("--soc-high", type=float, default=98.0, help="High battery SOC threshold (%)")
    parser.add_argument("--temp-high", type=float, default=45.0, help="High bus temp threshold (C)")
    parser.add_argument("--temp-low", type=float, default=-10.0, help="Low bus temp threshold (C)")
    parser.add_argument("--snr-low", type=float, default=3.0, help="Low SNR threshold (dB)")
    parser.add_argument("--rssi-low", type=float, default=-120.0, help="Low RSSI threshold (dBm)")
    parser.add_argument("--alt-low", type=float, default=120.0, help="Low altitude threshold (km)")
    parser.add_argument("--alt-high", type=float, default=2000.0, help="High altitude threshold (km)")
    return parser.parse_args()


def get_where_clause(limit: int) -> Tuple[str, Tuple[Any, ...]]:
    if limit <= 0:
        return "", ()
    return "WHERE id IN (SELECT id FROM telemetry ORDER BY id DESC LIMIT ?)", (limit,)


def display_path(path: str) -> str:
    try:
        abs_path = os.path.abspath(path)
        rel_path = os.path.relpath(abs_path, os.getcwd())
        if not rel_path.startswith(".."):
            return rel_path
        return os.path.basename(path)
    except Exception:
        return path


def fetch_scalar(cur: sqlite3.Cursor, query: str, params: Tuple[Any, ...] = ()) -> Any:
    cur.execute(query, params)
    row = cur.fetchone()
    return row[0] if row else None


def fetch_metric_stats(cur: sqlite3.Cursor, metric: str, where_clause: str, params: Tuple[Any, ...]) -> Dict[str, Any]:
    query = f"""
        SELECT
            COUNT({metric}),
            MIN({metric}),
            MAX({metric}),
            AVG({metric})
        FROM telemetry
        {where_clause}
    """
    cur.execute(query, params)
    row = cur.fetchone()
    return {
        "count": row[0] if row else 0,
        "min": row[1] if row else None,
        "max": row[2] if row else None,
        "avg": row[3] if row else None,
    }


def fetch_anomalies(
    cur: sqlite3.Cursor,
    where_clause: str,
    params: Tuple[Any, ...],
    thresholds: Dict[str, float],
) -> Dict[str, int]:
    anomaly_queries = {
        "battery_soc_low": f"SELECT COUNT(*) FROM telemetry {where_clause} {'AND' if where_clause else 'WHERE'} eps_battery_soc_pct < ?",
        "battery_soc_high": f"SELECT COUNT(*) FROM telemetry {where_clause} {'AND' if where_clause else 'WHERE'} eps_battery_soc_pct > ?",
        "bus_temp_high": f"SELECT COUNT(*) FROM telemetry {where_clause} {'AND' if where_clause else 'WHERE'} thermal_bus_c > ?",
        "bus_temp_low": f"SELECT COUNT(*) FROM telemetry {where_clause} {'AND' if where_clause else 'WHERE'} thermal_bus_c < ?",
        "snr_low": f"SELECT COUNT(*) FROM telemetry {where_clause} {'AND' if where_clause else 'WHERE'} comms_snr_db < ?",
        "rssi_low": f"SELECT COUNT(*) FROM telemetry {where_clause} {'AND' if where_clause else 'WHERE'} comms_rssi_dbm < ?",
        "altitude_low": f"SELECT COUNT(*) FROM telemetry {where_clause} {'AND' if where_clause else 'WHERE'} orbit_altitude_km < ?",
        "altitude_high": f"SELECT COUNT(*) FROM telemetry {where_clause} {'AND' if where_clause else 'WHERE'} orbit_altitude_km > ?",
    }

    values = {
        "battery_soc_low": thresholds["soc_low"],
        "battery_soc_high": thresholds["soc_high"],
        "bus_temp_high": thresholds["temp_high"],
        "bus_temp_low": thresholds["temp_low"],
        "snr_low": thresholds["snr_low"],
        "rssi_low": thresholds["rssi_low"],
        "altitude_low": thresholds["alt_low"],
        "altitude_high": thresholds["alt_high"],
    }

    anomalies: Dict[str, int] = {}
    for key, query in anomaly_queries.items():
        cur.execute(query, params + (values[key],))
        row = cur.fetchone()
        anomalies[key] = int(row[0] if row else 0)
    return anomalies


def build_report(args: argparse.Namespace) -> Dict[str, Any]:
    if not os.path.exists(args.db):
        raise FileNotFoundError(f"Database not found: {args.db}")

    conn = sqlite3.connect(args.db)
    cur = conn.cursor()

    where_clause, params = get_where_clause(args.limit)

    total_records = fetch_scalar(cur, f"SELECT COUNT(*) FROM telemetry {where_clause}", params)
    first_ts = fetch_scalar(cur, f"SELECT MIN(timestamp_utc) FROM telemetry {where_clause}", params)
    last_ts = fetch_scalar(cur, f"SELECT MAX(timestamp_utc) FROM telemetry {where_clause}", params)
    nodes = fetch_scalar(cur, f"SELECT COUNT(DISTINCT node) FROM telemetry {where_clause}", params)

    metrics = {
        "eps_battery_soc_pct": fetch_metric_stats(cur, "eps_battery_soc_pct", where_clause, params),
        "eps_battery_v": fetch_metric_stats(cur, "eps_battery_v", where_clause, params),
        "thermal_bus_c": fetch_metric_stats(cur, "thermal_bus_c", where_clause, params),
        "orbit_altitude_km": fetch_metric_stats(cur, "orbit_altitude_km", where_clause, params),
        "comms_snr_db": fetch_metric_stats(cur, "comms_snr_db", where_clause, params),
        "comms_rssi_dbm": fetch_metric_stats(cur, "comms_rssi_dbm", where_clause, params),
    }

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

    anomalies = fetch_anomalies(cur, where_clause, params, thresholds)
    anomaly_total = sum(anomalies.values())

    latest_query = f"""
        SELECT
            timestamp_utc, node, mission_time_s,
            eps_battery_soc_pct, thermal_bus_c, orbit_altitude_km,
            comms_snr_db, comms_rssi_dbm
        FROM telemetry
        {where_clause}
        ORDER BY id DESC
        LIMIT 1
    """
    cur.execute(latest_query, params)
    latest_row = cur.fetchone()
    latest = None
    if latest_row:
        latest = {
            "timestamp_utc": latest_row[0],
            "node": latest_row[1],
            "mission_time_s": latest_row[2],
            "eps_battery_soc_pct": latest_row[3],
            "thermal_bus_c": latest_row[4],
            "orbit_altitude_km": latest_row[5],
            "comms_snr_db": latest_row[6],
            "comms_rssi_dbm": latest_row[7],
        }

    conn.close()

    return {
        "source_db": display_path(args.db),
        "records_analyzed": int(total_records or 0),
        "window": {"limit": args.limit, "first_timestamp_utc": first_ts, "last_timestamp_utc": last_ts},
        "distinct_nodes": int(nodes or 0),
        "metrics": metrics,
        "thresholds": thresholds,
        "anomalies": anomalies,
        "anomaly_total": anomaly_total,
        "latest": latest,
    }


def format_float(v: Any, decimals: int = 2) -> str:
    if v is None:
        return "n/a"
    try:
        return f"{float(v):.{decimals}f}"
    except Exception:
        return str(v)


def print_text_report(report: Dict[str, Any]) -> None:
    print("CubeSat Telemetry Report")
    print("=======================")
    print(f"DB: {report['source_db']}")
    print(f"Records analyzed: {report['records_analyzed']}")
    print(f"Time range: {report['window']['first_timestamp_utc']} -> {report['window']['last_timestamp_utc']}")
    print(f"Distinct nodes: {report['distinct_nodes']}")
    print()

    print("Metric summary (min / max / avg)")
    print("--------------------------------")
    for key, stats in report["metrics"].items():
        print(
            f"{key}: {format_float(stats['min'])} / {format_float(stats['max'])} / {format_float(stats['avg'])}"
        )
    print()

    print("Anomalies")
    print("---------")
    for key, count in report["anomalies"].items():
        print(f"{key}: {count}")
    print(f"TOTAL: {report['anomaly_total']}")
    print()

    latest = report.get("latest")
    if latest:
        print("Latest record")
        print("-------------")
        print(json.dumps(latest, indent=2))


def main() -> int:
    args = parse_args()
    try:
        report = build_report(args)
    except Exception as ex:
        print(json.dumps({"event": "report_error", "error": str(ex)}), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_text_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
