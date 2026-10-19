#!/usr/bin/env python3
"""
Mojang Official Server JAR Downloader.

Downloads official Minecraft server JARs and verifies checksums directly from
Mojang's version manifest API (piston-meta.mojang.com).

Usage:
    python scripts/download_server_jars.py --version 1.21.1
    python scripts/download_server_jars.py --version 1.21.1 --dry-run
    python scripts/download_server_jars.py --help
"""

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

MOJANG_MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"


def fetch_json(url: str, timeout: int = 15) -> dict:
    """Fetch and parse JSON from an HTTP URL."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "MinecraftAI-Setup/1.0 (https://github.com/krishnabhardwaj-001/MinecraftAI)"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def download_file(url: str, dest_path: Path, expected_sha1: str | None = None, chunk_size: int = 65536) -> bool:
    """Download a file with streaming and SHA1 verification."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = dest_path.with_suffix(".tmp")
    hasher = hashlib.sha1()

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "MinecraftAI-Setup/1.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response, open(temp_path, "wb") as out_file:
            while chunk := response.read(chunk_size):
                out_file.write(chunk)
                if expected_sha1:
                    hasher.update(chunk)
        
        if expected_sha1:
            digest = hasher.hexdigest().lower()
            if digest != expected_sha1.lower():
                temp_path.unlink(missing_ok=True)
                raise ValueError(f"Checksum mismatch: expected {expected_sha1}, got {digest}")

        temp_path.replace(dest_path)
        return True
    except Exception as e:
        temp_path.unlink(missing_ok=True)
        raise e


def resolve_server_download_info(version_id: str) -> dict:
    """
    Look up version details from Mojang's official version manifest.
    Returns dict with version_id, package_url, server_url, server_sha1, size.
    """
    manifest = fetch_json(MOJANG_MANIFEST_URL)
    versions = manifest.get("versions", [])
    matching = next((v for v in versions if v.get("id") == version_id), None)
    if not matching:
        available = [v["id"] for v in versions[:10]]
        raise ValueError(
            f"Version '{version_id}' not found in Mojang version manifest. "
            f"Recent available versions include: {', '.join(available)}..."
        )

    package_url = matching["url"]
    version_details = fetch_json(package_url)
    downloads = version_details.get("downloads", {})
    server_info = downloads.get("server")
    if not server_info:
        raise ValueError(f"No server download available for version '{version_id}'.")

    return {
        "version_id": version_id,
        "package_url": package_url,
        "server_url": server_info["url"],
        "server_sha1": server_info.get("sha1"),
        "size": server_info.get("size", 0)
    }


def download_server_jar(version_id: str, output_dir: Path | None = None, dry_run: bool = False) -> Path | None:
    """
    Download the server JAR for a specified version into output_dir.
    """
    repo_root = Path(__file__).resolve().parent.parent
    target_dir = output_dir or (repo_root / "versions" / version_id)
    target_file = target_dir / f"server-{version_id}.jar"

    print(f"Resolving official Mojang download info for Minecraft {version_id}...")
    info = resolve_server_download_info(version_id)
    print(f"  Server URL : {info['server_url']}")
    print(f"  SHA1       : {info['server_sha1']}")
    print(f"  Size       : {info['size'] / (1024 * 1024):.2f} MB")
    print(f"  Target File: {target_file}")

    if dry_run:
        print("[Dry-run] Verification passed; no files written.")
        return target_file

    if target_file.exists():
        # Check existing hash
        with open(target_file, "rb") as f:
            existing_hash = hashlib.sha1(f.read()).hexdigest().lower()
        if existing_hash == (info["server_sha1"] or "").lower():
            print(f"Server JAR already exists and passes SHA1 verification: {target_file}")
            return target_file
        else:
            print(f"Existing file does not match SHA1; re-downloading...")

    print(f"Downloading server JAR to {target_file}...")
    download_file(info["server_url"], target_file, expected_sha1=info["server_sha1"])
    print(f"Successfully downloaded and verified: {target_file}")
    return target_file


def main():
    parser = argparse.ArgumentParser(
        description="Download official Minecraft Java Edition server JARs from Mojang's version manifest."
    )
    parser.add_argument(
        "--version",
        default="1.21.1",
        help="Minecraft version ID to download (default: 1.21.1)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Target directory to place the server jar (default: versions/<version>)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Query and print download details without saving the file"
    )

    args = parser.parse_args()
    try:
        download_server_jar(version_id=args.version, output_dir=args.output_dir, dry_run=args.dry_run)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
