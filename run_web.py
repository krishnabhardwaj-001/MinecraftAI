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


def main():
    parser = argparse.ArgumentParser(
        description="MinecraftAI Web Interface Server (Java 1.21.11 / Pack 94.1)"
    )
    default_host = os.getenv("HOST", "127.0.0.1")
    default_port = int(os.getenv("PORT", "8000"))
    env_open_browser = os.getenv("OPEN_BROWSER", "false").lower() in ("true", "1", "yes")

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
        default=env_open_browser,
        help="Automatically open the default web browser once the server is ready."
    )

    args = parser.parse_args()

    # Verify port availability to prevent duplicate server instances
    if not check_port_available(args.host, args.port):
        print(f"\n[ERROR] Port {args.port} is already in use on {args.host}.")
        print("MinecraftAI is likely already running, or another application is using this port.")
        print(f"Please stop the existing process or run with: python run_web.py --port <different_port>\n")
        sys.exit(1)

    print("=" * 70)
    print("MinecraftAI Web Interface Server")
    print("Target: Minecraft Java Edition 1.21.11 | Data Pack Version 94.1")
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
