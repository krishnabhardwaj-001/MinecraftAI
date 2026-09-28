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

            # Collect structured choices from clarification requirements
            available_options: List[str] = []
            for req in (result.clarification_requirements or []):
                if isinstance(req, dict):
                    opts = req.get("options") or []
                elif hasattr(req, "options"):
                    opts = getattr(req, "options", [])
                else:
                    opts = []
                for opt in opts:
                    if opt and str(opt) not in available_options:
                        available_options.append(str(opt))

            if available_options:
                print("\n    Available choices:")
                for opt_idx, opt in enumerate(available_options, 1):
                    print(f"      [{opt_idx}] {opt}")

            prompt_label = (
                f"\nSelect a choice [1-{len(available_options)}] or enter custom clarification (or press Enter to cancel): "
                if available_options
                else "\nEnter clarification (or press Enter to cancel): "
            )

            try:
                user_choice = input_fn(prompt_label).strip()
            except (KeyboardInterrupt, EOFError):
                print("\nAborted.")
                return 0

            if not user_choice or user_choice.lower() in ("quit", "exit", "cancel", "q"):
                print("\nClarification cancelled by user.")
                return 2

            # Check if user selected by index
            if available_options and user_choice.isdigit():
                choice_idx = int(user_choice) - 1
                if 0 <= choice_idx < len(available_options):
                    clarification = available_options[choice_idx]
                else:
                    clarification = user_choice
            else:
                clarification = user_choice

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

