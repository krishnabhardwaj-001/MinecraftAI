import json
from pathlib import Path
from urllib.request import Request, urlopen


VERSION = "1.21.11"

BASE_DIR = Path(__file__).resolve().parent

OUTPUT_DIR = (
    BASE_DIR
    / "java"
    / VERSION
    / "tables"
)

INDEX_FILE = (
    BASE_DIR
    / f"loot_index_{VERSION}.json"
)

TREE_URL = (
    "https://api.github.com/repos/"
    "InventivetalentDev/minecraft-assets/"
    f"git/trees/{VERSION}?recursive=1"
)

RAW_BASE = (
    "https://raw.githubusercontent.com/"
    "InventivetalentDev/minecraft-assets/"
    f"{VERSION}/data/minecraft/loot_table"
)


def fetch_json(url):
    request = Request(
        url,
        headers={
            "User-Agent": "MinecraftAI-LootKnowledgeBuilder"
        }
    )

    with urlopen(request, timeout=60) as response:
        return json.loads(
            response.read().decode("utf-8")
        )


def download_file(relative_path):
    url = f"{RAW_BASE}/{relative_path}"

    request = Request(
        url,
        headers={
            "User-Agent": "MinecraftAI-LootKnowledgeBuilder"
        }
    )

    with urlopen(request, timeout=60) as response:
        data = response.read()

    # Validate that the downloaded file is valid JSON.
    parsed = json.loads(
        data.decode("utf-8")
    )

    destination = (
        OUTPUT_DIR / relative_path
    )

    destination.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    destination.write_bytes(data)

    return parsed


def discover_loot_tables():
    print("[1/4] Getting Minecraft 1.21.11 repository tree...")

    tree_data = fetch_json(TREE_URL)

    if tree_data.get("truncated"):
        raise RuntimeError(
            "GitHub returned a truncated repository tree."
        )

    prefix = "data/minecraft/loot_table/"

    files = []

    for item in tree_data.get("tree", []):
        if item.get("type") != "blob":
            continue

        path = item.get("path", "")

        if not path.startswith(prefix):
            continue

        if not path.endswith(".json"):
            continue

        relative_path = path[len(prefix):]

        # Ignore directory metadata if present.
        if Path(relative_path).name == "_list.json":
            continue

        files.append(relative_path)

    return sorted(set(files))


def build_index(files, downloaded_data):
    print("\n[3/4] Building loot-table index...")

    entries = []

    for relative_path in files:
        if relative_path not in downloaded_data:
            continue

        data = downloaded_data[relative_path]

        parts = relative_path.split("/")

        category = (
            parts[0]
            if len(parts) > 1
            else "root"
        )

        entries.append(
            {
                "version": VERSION,
                "edition": "Java",
                "path": relative_path,
                "category": category,
                "type": data.get("type"),
                "pool_count": len(
                    data.get("pools", [])
                ),
                "file": str(
                    Path("java")
                    / VERSION
                    / "tables"
                    / relative_path
                ).replace("\\", "/")
            }
        )

    index_data = {
        "version": VERSION,
        "edition": "Java",
        "total_tables": len(entries),
        "tables": entries
    }

    INDEX_FILE.write_text(
        json.dumps(
            index_data,
            indent=2
        ),
        encoding="utf-8"
    )

    return len(entries)


def main():
    print("=" * 60)
    print("Minecraft Loot Knowledge Builder")
    print(f"Minecraft Java Edition: {VERSION}")
    print("=" * 60)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------
    # STEP 1
    # --------------------------------------------------

    try:
        files = discover_loot_tables()

    except Exception as exc:
        print(
            f"\n[FATAL] Could not discover loot tables:"
            f"\n{exc}"
        )
        return

    print(
        f"Found {len(files)} loot-table JSON files."
    )

    if not files:
        print(
            "\n[FATAL] No loot tables found."
        )
        return

    # --------------------------------------------------
    # STEP 2
    # --------------------------------------------------

    print("\n[2/4] Downloading loot tables...")

    successful = 0
    failed = 0

    downloaded_data = {}

    for number, relative_path in enumerate(
        files,
        start=1
    ):
        print(
            f"[{number}/{len(files)}] "
            f"{relative_path}"
        )

        try:
            data = download_file(
                relative_path
            )

            downloaded_data[
                relative_path
            ] = data

            successful += 1

        except Exception as exc:
            failed += 1

            print(
                f"    [ERROR] {exc}"
            )

    # --------------------------------------------------
    # STEP 3
    # --------------------------------------------------

    indexed = build_index(
        files,
        downloaded_data
    )

    # --------------------------------------------------
    # STEP 4
    # --------------------------------------------------

    print("\n[4/4] Complete.")
    print("=" * 60)
    print(f"Discovered: {len(files)}")
    print(f"Downloaded: {successful}")
    print(f"Failed:     {failed}")
    print(f"Indexed:    {indexed}")
    print()
    print(f"Tables: {OUTPUT_DIR}")
    print(f"Index:  {INDEX_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()