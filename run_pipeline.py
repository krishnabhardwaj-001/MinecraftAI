import argparse
import os
import sys
from pathlib import Path
from typing import Any, Callable, List, Optional

from pipeline import run_minecraft_pipeline
from ai.version_registry import get_version_registry, get_default_version
from ai.provider import (
    is_ollama_unreachable_error,
    get_ollama_diagnostic_message,
    classify_provider_error,
)
from security.input_security import (
    validate_prompt,
    InputValidationError,
)


def create_cli_parser() -> argparse.ArgumentParser:
    """Creates the standard argument parser for the MinecraftAI CLI."""
    parser = argparse.ArgumentParser(
        prog="run_pipeline.py",
        description="MinecraftAI - Transform natural-language requests into validated Minecraft Java Edition datapacks."
    )
    parser.add_argument(
        "--version",
        dest="version",
        default=None,
        help="Target Minecraft version (e.g. 1.21.11, 1.21.1)"
    )
    parser.add_argument(
        "--request",
        dest="request",
        default=None,
        help="Natural-language request for datapack generation"
    )
    parser.add_argument(
        "words",
        nargs="*",
        default=[],
        help="Positional words of the natural-language request"
    )
    return parser


def run_cli(
    args: Optional[List[str]] = None,
    input_fn: Callable[[str], str] = input,
    pipeline_fn: Callable[..., Any] = run_minecraft_pipeline
) -> int:
    """
    Executes the MinecraftAI CLI with interactive clarification support.
    Returns exit code (0 for success, 1 for error/failure, 2 for aborted clarification).
    """
    cli_args = list(sys.argv[1:] if args is None else args)

    parser = create_cli_parser()
    try:
        parsed = parser.parse_args(cli_args)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else (0 if e.code is None else 1)

    # Validate selected version against VersionRegistry
    selected_version = parsed.version.strip() if parsed.version else get_default_version()
    registry = get_version_registry()
    if not registry.is_supported(selected_version):
        supported = ", ".join(registry.get_supported_versions())
        print(f"Error: Unsupported Minecraft version '{selected_version}'. Officially supported version(s): {supported}")
        return 1

    # Extract raw request from --request or positional words
    has_cli_request_args = (parsed.request is not None) or bool(parsed.words)
    parts = []
    if parsed.request:
        parts.append(parsed.request.strip())
    if parsed.words:
        joined_words = " ".join(parsed.words).strip()
        if joined_words:
            parts.append(joined_words)

    raw_request = " ".join(parts).strip()

    if not raw_request:
        if has_cli_request_args:
            print("Error: Request cannot be empty.")
            return 1
        try:
            raw_request = input_fn("\nEnter Minecraft natural-language request: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            return 0

    if not raw_request:
        print("Error: Request cannot be empty.")
        return 1

    # Security validation of input prompt
    try:
        request = validate_prompt(raw_request)
    except InputValidationError as e:
        print(f"Error: {e}")
        return 1

    version_meta = registry.get(selected_version)
    print("=" * 70)
    print("MinecraftAI - End-to-End Datapack Pipeline")
    print(f"Target: Minecraft Java Edition {selected_version} | Data Pack Version {version_meta.data_pack_version or version_meta.pack_format}")
    print("=" * 70)

    clarification_history: List[Dict[str, str]] = []
    clarification_round = 0
    original_prompt = request

    while True:
        print()
        try:
            result = pipeline_fn(
                request=original_prompt,
                minecraft_version=selected_version,
                provider=os.getenv("LLM_PROVIDER", "ollama"),
                create_zip=True,
                verbose=True,
                clarification_history=clarification_history,
                clarification_round=clarification_round
            )
        except Exception as e:
            if is_ollama_unreachable_error(e):
                print("\n" + "=" * 70)
                print("[!] OLLAMA SERVICE UNREACHABLE")
                print("=" * 70)
                print(get_ollama_diagnostic_message(exc=e))
                print("=" * 70)
                return 1
            print(f"\n[-] Unexpected pipeline execution error: {e}")
            return 1

        if result.status == "error":
            if result.error_code in ("provider_unreachable", "provider_auth") or result.diagnostic:
                print("\n" + "=" * 70)
                print(f"[!] {result.error_code.upper() if result.error_code else 'PROVIDER ERROR'}")
                print("=" * 70)
                print(result.diagnostic or (result.errors[0] if result.errors else "Provider error"))
                print("=" * 70)
                return 1
            print("\n" + "=" * 70)
            print("PIPELINE EXECUTION ERROR")
            print("=" * 70)
            print(result.summary())
            return 1

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

            # Add to structured history
            clarification_history.append({
                "question": result.clarification or "Clarification required",
                "answer": clarification
            })
            clarification_round += 1

            # Generic prompt refinement matching web/app.js pattern
            composed_request = f"{original_prompt} Specifically: {clarification}."
            try:
                validate_prompt(composed_request)
            except InputValidationError as e:
                print(f"\n[-] Error: Clarified request validation failed: {e}")
                return 1
            print(f"\n[+] Refining request with clarification: '{clarification}' (Round {clarification_round}/2)")
            continue

        elif result.status == "unsupported":
            print("\n[-] REQUEST UNSUPPORTED BY VANILLA MINECRAFT:")
            for err in result.errors:
                print(f"    - {err}")
            return 1
        elif result.is_success:
            print(f"\n[+] SUCCESS: Validated Datapack Ready for Minecraft {selected_version}!")
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

