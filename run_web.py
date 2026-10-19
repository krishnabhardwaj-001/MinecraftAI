import argparse
import os
import socket
import sys
import threading
import time
import webbrowser
import uvicorn


def check_port_available(host: str, port: int) -> bool:
    """Checks whether the specified host and port can be bound."""
    target_host = "127.0.0.1" if host in ("0.0.0.0", "") else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((target_host, port))
            return True
        except OSError:
            return False


def _wait_and_open_browser(host: str, port: int, delay_s: float = 0.5, timeout_s: float = 10.0):
    """Waits for the web server to start accepting connections, then opens the browser."""
    target_ip = "127.0.0.1" if host in ("0.0.0.0", "localhost", "") else host
    display_host = "127.0.0.1" if host == "0.0.0.0" else host
    url = f"http://{display_host}:{port}"
    start_time = time.time()

    while time.time() - start_time < timeout_s:
        try:
            with socket.create_connection((target_ip, port), timeout=0.5):
                time.sleep(delay_s)
                print(f"\n[+] Opening browser at: {url}\n")
                webbrowser.open(url)
                return
        except (OSError, ConnectionRefusedError):
            time.sleep(0.3)

    # Fallback attempt even if socket poll timed out
    webbrowser.open(url)


from typing import Dict, List, Optional


def resolve_server_config(
    args: Optional[List[str]] = None,
    env: Optional[Dict[str, str]] = None
) -> argparse.Namespace:
    """
    Resolves host, port, and browser options from CLI arguments and environment variables.
    CLI arguments have the highest precedence, followed by HOST and PORT env vars,
    falling back to 127.0.0.1:8000.
    """
    if env is None:
        env = dict(os.environ)

    raw_host = env.get("HOST", "").strip()
    default_host = raw_host if raw_host else "127.0.0.1"

    raw_port = env.get("PORT", "").strip()
    try:
        default_port = int(raw_port) if raw_port else 8000
    except ValueError:
        default_port = 8000

    raw_open_browser = env.get("OPEN_BROWSER", "false").strip().lower()
    default_open_browser = raw_open_browser in ("true", "1", "yes")

    parser = argparse.ArgumentParser(
        description="MinecraftAI Web Interface Server (Java 1.21.11 / 1.21.1)"
    )
    parser.add_argument(
        "--host",
        type=str,
        default=default_host,
        help=f"Host address to bind to (default: {default_host})"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=default_port,
        help=f"Port to listen on (default: {default_port})"
    )
    parser.add_argument(
        "--open-browser",
        action="store_true",
        default=default_open_browser,
        help="Automatically open the default web browser once the server is ready."
    )

    return parser.parse_args(args)


def main(argv: Optional[List[str]] = None):
    args = resolve_server_config(args=argv)

    # Verify port availability to prevent duplicate server instances
    if not check_port_available(args.host, args.port):
        print(f"\n[ERROR] Port {args.port} is already in use on {args.host}.")
        print("MinecraftAI is likely already running, or another application is using this port.")
        print(f"Please stop the existing process or run with: python run_web.py --port <different_port>\n")
        sys.exit(1)

    print("=" * 70)
    print("MinecraftAI Web Interface Server")
    print("Supported: Minecraft Java Edition 1.21.11 & 1.21.1")
    print(f"Starting server at: http://{args.host}:{args.port}")
    if args.open_browser:
        print("Browser will open automatically once the server is listening.")
    print("=" * 70)

    if args.open_browser:
        threading.Thread(
            target=_wait_and_open_browser,
            args=(args.host, args.port),
            daemon=True
        ).start()

    try:
        uvicorn.run(
            "web.app:app",
            host=args.host,
            port=args.port,
            log_level="info",
            reload=False
        )
    except KeyboardInterrupt:
        print("\nShutting down server.")
        sys.exit(0)


if __name__ == "__main__":
    main()
