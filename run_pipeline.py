import sys
from pathlib import Path
from typing import Any, Callable, List, Optional

from pipeline import run_minecraft_pipeline


def run_cli(
    args: Optional[List[str]] = None,
    input_fn: Callable[[str], str] = input,
    pipeline_fn: Callable[..., Any] = run_minecraft_pipeline
) -> int:
    """
    Executes the MinecraftAI CLI with interactive clarification support.
    Returns exit code (0 for success, 1 for error/failure, 2 for aborted clarification).
    """
    print("=" * 70)
    print("MinecraftAI - End-to-End Datapack Pipeline")
    print("Target: Minecraft Java Edition 1.21.11 | Data Pack Version 94.1")
    print("=" * 70)

    cli_args = sys.argv[1:] if args is None else args

    if cli_args:
        request = " ".join(cli_args).strip()
    else:
        try:
            request = input_fn("\nEnter Minecraft natural-language request: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            return 0

    if not request:
        print("Error: Request cannot be empty.")
        return 1

    while True:
        print()
        result = pipeline_fn(
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

            try:
                clarification = input_fn("\nEnter clarification (or press Enter to cancel): ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nAborted.")
                return 0

            if not clarification:
                print("\nClarification cancelled by user.")
                return 2

            # Generic prompt refinement matching web/app.js pattern
            request = f"{request} Specifically: {clarification}."
            print(f"\n[+] Refining request with clarification: '{request}'")
            continue

        elif result.is_success:
            print("\n[+] SUCCESS: Validated Datapack Ready for Minecraft 1.21.11!")
            print(f"    Datapack Folder: {result.final_datapack_path}")
            print(f"    Datapack ZIP:    {result.final_zip_path}")
            return 0
        else:
            print("\n[-] PIPELINE FAILED:")
            for err in result.errors:
                print(f"    - {err}")
            if result.repair and result.repair.attempts:
                print("\n    Repair diagnostics:")
                for att in result.repair.attempts:
                    print(f"      Attempt #{att.attempt_number} [{att.validation_status}]: {att.repair_reasoning[:100]}...")
            return 1


def main():
    sys.exit(run_cli())


if __name__ == "__main__":
    main()

