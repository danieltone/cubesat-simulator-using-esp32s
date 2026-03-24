#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Auto-refresh CubeSat dashboard generator + local HTTP server."
    )
    parser.add_argument("--db", default="data/telemetry.db", help="Telemetry SQLite DB path")
    parser.add_argument("--dashboard", default="data/dashboard.html", help="Dashboard HTML output path")
    parser.add_argument("--limit", type=int, default=500, help="Records to include in dashboard")
    parser.add_argument("--interval", type=float, default=5.0, help="Dashboard refresh interval (seconds)")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind host")
    parser.add_argument("--port", type=int, default=8000, help="HTTP bind port")
    parser.add_argument(
        "--refresh-only",
        action="store_true",
        help="Generate dashboard once and exit (no HTTP server)",
    )
    return parser.parse_args()


def generate_dashboard(py_exec: str, script_dir: Path, db: str, dashboard: str, limit: int) -> int:
    cmd = [
        py_exec,
        str(script_dir / "telemetry_dashboard.py"),
        "--db",
        db,
        "--out",
        dashboard,
        "--limit",
        str(limit),
    ]
    proc = subprocess.run(cmd, cwd=str(script_dir), capture_output=True, text=True)
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)
    return proc.returncode


def refresher_loop(stop_event: threading.Event, py_exec: str, script_dir: Path, db: str, dashboard: str, limit: int, interval: float) -> None:
    while not stop_event.is_set():
        rc = generate_dashboard(py_exec, script_dir, db, dashboard, limit)
        if rc != 0:
            print('{"event":"refresh_error","msg":"dashboard generation failed"}', file=sys.stderr)
        stop_event.wait(interval)


def main() -> int:
    args = parse_args()
    script_dir = Path(__file__).resolve().parent
    py_exec = sys.executable

    db_path = Path(args.db)
    dashboard_path = Path(args.dashboard)
    if not db_path.is_absolute():
        db_path = script_dir / db_path
    if not dashboard_path.is_absolute():
        dashboard_path = script_dir / dashboard_path

    dashboard_path.parent.mkdir(parents=True, exist_ok=True)

    rc = generate_dashboard(py_exec, script_dir, str(db_path), str(dashboard_path), args.limit)
    if rc != 0:
        return rc

    if args.refresh_only:
        print('{"event":"refresh_only_done"}')
        return 0

    stop_event = threading.Event()
    thread = threading.Thread(
        target=refresher_loop,
        args=(stop_event, py_exec, script_dir, str(db_path), str(dashboard_path), args.limit, args.interval),
        daemon=True,
    )
    thread.start()

    os.chdir(str(dashboard_path.parent))
    handler = SimpleHTTPRequestHandler
    server = ThreadingHTTPServer((args.host, args.port), handler)
    url = f"http://{args.host}:{args.port}/{dashboard_path.name}"
    print(f'{{"event":"live_server_started","url":"{url}","refresh_s":{args.interval}}}')

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        server.shutdown()
        server.server_close()
        print('{"event":"live_server_stopped"}')

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
