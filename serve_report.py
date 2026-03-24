"""
serve_report.py — Serve the SFR report locally and optionally share via SSH tunnel.

Usage:
    python serve_report.py                                    # local only on :8080
    python serve_report.py --port 9000                        # custom port
    python serve_report.py --share samlai@devserver.com       # local + SSH tunnel
    python serve_report.py --share samlai@1.2.3.4 --remote-port 9090
"""

from __future__ import annotations

import argparse
import functools
import signal
import subprocess
import sys
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from app_config import cfg


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Serve the SFR report over HTTP (and optionally via SSH tunnel)."
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Local HTTP server port (default: 8080)",
    )
    parser.add_argument(
        "--share",
        metavar="USER@HOST",
        help="Open an SSH reverse tunnel so the report is reachable on the remote host",
    )
    parser.add_argument(
        "--remote-port",
        type=int,
        default=None,
        help="Port on the remote host (defaults to same as --port)",
    )
    return parser.parse_args()


def _start_ssh_tunnel(
    user_host: str, local_port: int, remote_port: int
) -> subprocess.Popen:
    cmd = [
        "ssh",
        "-R",
        f"{remote_port}:localhost:{local_port}",
        user_host,
        "-N",
    ]
    print(f"Starting SSH tunnel: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd)
    host = user_host.split("@", 1)[-1]
    print(f"Shareable URL: http://{host}:{remote_port}/sfr_report.html")
    return proc


def main() -> None:
    args = _parse_args()
    local_port: int = args.port
    remote_port: int = args.remote_port if args.remote_port is not None else local_port

    serve_dir = cfg.output_folder
    if not serve_dir.is_dir():
        print(f"Error: output folder does not exist: {serve_dir}")
        sys.exit(1)

    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(serve_dir))
    server = HTTPServer(("", local_port), handler)

    ssh_proc: subprocess.Popen | None = None

    def _shutdown(signum, frame):
        print("\nShutting down...")
        server.shutdown()
        if ssh_proc is not None:
            ssh_proc.terminate()
            ssh_proc.wait()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    if args.share:
        ssh_proc = _start_ssh_tunnel(args.share, local_port, remote_port)

    local_url = f"http://localhost:{local_port}/sfr_report.html"
    print(f"Serving {serve_dir} on port {local_port}")
    print(f"Local URL: {local_url}")
    webbrowser.open(local_url)

    server.serve_forever()


if __name__ == "__main__":
    main()
