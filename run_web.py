import argparse
import sys
import uvicorn


def main():
    parser = argparse.ArgumentParser(
        description="MinecraftAI Web Interface Server (Java 1.21.11 / Pack 94.1)"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host address to bind to (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to listen on (default: 8000)"
    )

    args = parser.parse_args()

    print("=" * 70)
    print("MinecraftAI Web Interface Server")
    print("Target: Minecraft Java Edition 1.21.11 | Data Pack Version 94.1")
    print(f"Starting server at: http://{args.host}:{args.port}")
    print("=" * 70)

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
