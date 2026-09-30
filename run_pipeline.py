import os
import sys
from pathlib import Path
from typing import Any, Callable, List, Optional

from pipeline import run_minecraft_pipeline
from ai.version_registry import get_version_registry, get_default_version


def is_ollama_unreachable_error(exc: Optional[BaseException]) -> bool:
    """
    Determines whether an exception indicates that the Ollama service
    is offline, unreachable, not running, or failed to connect.
    """
    if exc is None:
        return False

    exc_name = type(exc).__name__
    if exc_name in (
        "ConnectError",
        "ConnectTimeout",
        "ConnectionRefusedError",
        "RequestError",
        "ReadTimeout",
    ):
        return True

    try:
        import httpx
        if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
            return True
    except ImportError:
        pass

    try:
        import ollama
        if hasattr(ollama, "RequestError") and isinstance(exc, ollama.RequestError):
            return True
    except ImportError:
        pass

    if isinstance(exc, (ConnectionRefusedError, ConnectionError)):
        return True

    msg = str(exc).lower()
    indicators = [
        "connection refused",
        "connecterror",
        "failed to connect",
        "11434",
        "winerror 10061",
        "all connection attempts failed",
        "target machine actively refused",
        "is ollama running",
        "no such host",
    ]
    if any(ind in msg for ind in indicators):
        return True

    if exc.__cause__ and is_ollama_unreachable_error(exc.__cause__):
        return True
    if exc.__context__ and is_ollama_unreachable_error(exc.__context__):
        return True

    return False


def get_ollama_diagnostic_message(endpoint: Optional[str] = None) -> str:
    """
    Returns an actionable diagnostic message explaining that Ollama is unreachable,
    displaying the endpoint, explaining how to start Ollama, and noting external
    provider alternatives.
    """
    resolved_endpoint = endpoint or os.getenv("OLLAMA_HOST") or "http://localhost:11434"
    return (
        f"The AI provider (Ollama) is unreachable or not running at {resolved_endpoint}.\n\n"
        "To resolve this issue:\n"
        "  1. Ensure Ollama is installed (https://ollama.com).\n"
        "  2. Start the Ollama service by running:\n"
        "       ollama serve\n"
        "     or launch the Ollama desktop application.\n"
        "  3. Ensure the required model is pulled (e.g. 'ollama pull llama3.1:8b').\n"
        "  4. Alternatively, configure an external AI provider if supported "
        "(such as setting the OPENAI_API_KEY environment variable for OpenAI)."
    )


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

    # Parse optional --version flag
    selected_version = get_default_version()
    filtered_args = []
    i = 0
    while i < len(cli_args):
        arg = cli_args[i]
        if arg == "--version" or arg.startswith("--version="):
            if "=" in arg:
                selected_version = arg.split("=", 1)[1].strip()
            elif i + 1 < len(cli_args):
                selected_version = cli_args[i + 1].strip()
                i += 1
            else:
                print("Error: --version requires a version argument.")
                return 1
        elif arg == "--request" or arg.startswith("--request="):
            if "=" in arg:
                filtered_args.append(arg.split("=", 1)[1].strip())
            elif i + 1 < len(cli_args):
                filtered_args.append(cli_args[i + 1].strip())
                i += 1
        else:
            filtered_args.append(arg)
        i += 1

    # Validate selected version against VersionRegistry
    registry = get_version_registry()
    if not registry.is_supported(selected_version):
        supported = ", ".join(registry.get_supported_versions())
        print(f"Error: Unsupported Minecraft version '{selected_version}'. Officially supported version(s): {supported}")
        return 1

    version_meta = registry.get(selected_version)
    print("=" * 70)
    print("MinecraftAI - End-to-End Datapack Pipeline")
    print(f"Target: Minecraft Java Edition {selected_version} | Data Pack Version {version_meta.data_pack_version or version_meta.pack_format}")
    print("=" * 70)

    if filtered_args:
        request = " ".join(filtered_args).strip()
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
        try:
            result = pipeline_fn(
                request=request,
                minecraft_version=selected_version,
                provider="ollama",
                create_zip=True,
                verbose=True
            )
        except Exception as e:
            if is_ollama_unreachable_error(e):
                print("\n" + "=" * 70)
                print("[!] OLLAMA SERVICE UNREACHABLE")
                print("=" * 70)
                print(get_ollama_diagnostic_message())
                print("=" * 70)
                return 1
            print(f"\n[-] Unexpected pipeline execution error: {e}")
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

            # Generic prompt refinement matching web/app.js pattern
            request = f"{request} Specifically: {clarification}."
            print(f"\n[+] Refining request with clarification: '{request}'")
            continue

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

