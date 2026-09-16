import sys
from pathlib import Path

from pipeline import run_minecraft_pipeline


def main():
    print("=" * 70)
    print("MinecraftAI - End-to-End Datapack Pipeline")
    print("Target: Minecraft Java Edition 1.21.11 | Data Pack Version 94.1")
    print("=" * 70)

    if len(sys.argv) > 1:
        request = " ".join(sys.argv[1:]).strip()
    else:
        try:
            request = input("\nEnter Minecraft natural-language request: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            sys.exit(0)

    if not request:
        print("Error: Request cannot be empty.")
        sys.exit(1)

    print()
    result = run_minecraft_pipeline(
        request=request,
        minecraft_version="1.21.11",
        provider="ollama",
        create_zip=True,
        verbose=True
    )

    print("\n" + "=" * 70)
    print("PIPELINE EXECUTION SUMMARY")
    print("=" * 70)
    print(result.summary())

    if result.status == "needs_clarification":
        print("\n[!] The AI needs clarification to proceed:")
        print(f"    {result.clarification}")
        sys.exit(2)
    elif result.is_success:
        print("\n[+] SUCCESS: Validated Datapack Ready for Minecraft 1.21.11!")
        print(f"    Datapack Folder: {result.final_datapack_path}")
        print(f"    Datapack ZIP:    {result.final_zip_path}")
        sys.exit(0)
    else:
        print("\n[-] PIPELINE FAILED:")
        for err in result.errors:
            print(f"    - {err}")
        if result.repair and result.repair.attempts:
            print("\n    Repair diagnostics:")
            for att in result.repair.attempts:
                print(f"      Attempt #{att.attempt_number} [{att.validation_status}]: {att.repair_reasoning[:100]}...")
        sys.exit(1)


if __name__ == "__main__":
    main()
