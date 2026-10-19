# Audit Baseline Execution Record

**Date**: 2026-10-19
**Branch**: `fix/full-audit` (branched from `backup/20261016-100500-pre-recovery` @ `b814267`)
**Environment**: Windows 11, Python 3.13.7, Java 21.0.12 LTS, Ollama daemon active on localhost:11434, Docker unavailable (`docker: command not found`).

---

## 1. `pip install -e ".[dev]"`

```
Obtaining file:///D:/Projects/MinecraftAI
  Installing build dependencies: started
  Installing build dependencies: finished with status 'done'
  Checking if build backend supports build_editable: started
  Checking if build backend supports build_editable: finished with status 'done'
  Getting requirements to build editable: started
  Getting requirements to build editable: finished with status 'done'
  Preparing editable metadata (pyproject.toml): started
  Preparing editable metadata (pyproject.toml): finished with status 'done'
Requirement already satisfied: pydantic>=2.0.0 in c:\users\dell\appdata\local\programs\python\python313\lib\site-packages (from minecraft-ai==1.0.0) (2.13.5)
Requirement already satisfied: python-dotenv>=1.0.0 in c:\users\dell\appdata\local\programs\python\python313\lib\site-packages (from minecraft-ai==1.0.0) (1.2.3)
Requirement already satisfied: ollama>=0.2.0 in c:\users\dell\appdata\local\programs\python\python313\lib\site-packages (from minecraft-ai==1.0.0) (0.6.2)
Requirement already satisfied: openai>=1.0.0 in c:\users\dell\appdata\local\programs\python\python313\lib\site-packages (from minecraft-ai==1.0.0) (3.10.0)
Requirement already satisfied: fastapi>=0.100.0 in c:\users\dell\appdata\local\programs\python\python313\lib\site-packages (from minecraft-ai==1.0.0) (0.124.4)
Requirement already satisfied: uvicorn>=0.20.0 in c:\users\dell\appdata\local\programs\python\python313\lib\site-packages (from minecraft-ai==1.0.0) (0.38.0)
Requirement already satisfied: jinja2>=3.1.0 in c:\users\dell\appdata\local\programs\python\python313\lib\site-packages (from minecraft-ai==1.0.0) (3.1.6)
Requirement already satisfied: httpx>=0.24.0 in c:\users\dell\appdata\local\programs\python\python313\lib\site-packages (from minecraft-ai==1.0.0) (0.28.1)
Requirement already satisfied: pytest>=7.0.0 in c:\users\dell\appdata\local\programs\python\python313\lib\site-packages (from minecraft-ai==1.0.0) (9.1.1)
...
Successfully installed minecraft-ai-1.0.0
```
**Exit Code**: 0

---

## 2. `python -m pytest -W error -q`

```
........................................................................ [  8%]
........................................................................ [ 17%]
........................................................................ [ 26%]
........................................................................ [ 35%]
........................................................................ [ 44%]
........................................................................ [ 53%]
........................................................................ [ 61%]
........................................................................ [ 70%]
.............................................................FF......... [ 79%]
........................................................................ [ 88%]
........................................................................ [ 97%]
.......................                                                  [100%]
================================== FAILURES ===================================
____________ TestStep22aPackaging.test_5_windows_launchers_content ____________

self = <test_step22a_packaging.TestStep22aPackaging testMethod=test_5_windows_launchers_content>

    def test_5_windows_launchers_content(self):
        """
        Verify that launch_cli.bat and launch_web.bat exist, use %~dp0, and verify Python.
        """
        cli_bat = BASE_DIR / "launch_cli.bat"
        web_bat = BASE_DIR / "launch_web.bat"
    
        self.assertTrue(cli_bat.exists(), "launch_cli.bat must exist")
        self.assertTrue(web_bat.exists(), "launch_web.bat must exist")
    
        cli_content = cli_bat.read_text(encoding="utf-8")
        web_content = web_bat.read_text(encoding="utf-8")
    
        for name, content in [("launch_cli.bat", cli_content), ("launch_web.bat", web_content)]:
            self.assertIn('%~dp0', content, f"{name} must resolve script directory with %~dp0")
>           self.assertIn('python --version', content, f"{name} must check Python availability")
E           AssertionError: 'python --version' not found in '@echo off\nsetlocal\ncd /d "%~dp0"\n\nif exist "start.bat" (\n    call start.bat %*\n    exit /b %ERRORLEVEL%\n)\n\npython run_web.py %*\nexit /b %ERRORLEVEL%\n' : launch_web.bat must check Python availability

test_step22a_packaging.py:118: AssertionError
___________ TestStep22aPackaging.test_6_windows_launchers_execution ___________

self = <test_step22a_packaging.TestStep22aPackaging testMethod=test_6_windows_launchers_execution>

    def test_6_windows_launchers_execution(self):
        """
        Verify that the Windows batch launchers execute correctly from the command line.
        """
        if sys.platform != "win32":
            self.skipTest("Batch launcher execution test is Windows-specific")
    
        cli_bat = str(BASE_DIR / "launch_cli.bat")
        web_bat = str(BASE_DIR / "launch_web.bat")
    
        # Test launch_web.bat with --help
        res_web = subprocess.run(
            ["cmd", "/c", web_bat, "--help"],
            capture_output=True,
            text=True,
            cwd=str(BASE_DIR)
        )
>       self.assertEqual(res_web.returncode, 0)
E       AssertionError: 255 != 0

test_step22a_packaging.py:138: AssertionError
=========================== short test summary info ===========================
FAILED test_step22a_packaging.py::TestStep22aPackaging::test_5_windows_launchers_content
FAILED test_step22a_packaging.py::TestStep22aPackaging::test_6_windows_launchers_execution
2 failed, 813 passed in 521.36s (0:08:41)
```
**Exit Code**: 1
**Findings**:
- 813 out of 815 tests passed.
- 2 failures in `test_step22a_packaging.py` (`test_5_windows_launchers_content` and `test_6_windows_launchers_execution`): `launch_web.bat` was changed to call `start.bat` which doesn't contain `python --version` directly in `launch_web.bat`, and `start.bat` exited with 255 when passed `--help`.
- Tests took 8 minutes 41 seconds because live pipeline tests (`test_pipeline.py`, `test_step16_planner.py::test_18_...`, `test_web_full.py`, etc.) and headless Minecraft server boot tests (`test_step20_golden.py`, `test_step24_multiversion.py`, `test_step25_5_final_verification.py`) executed against local Ollama and local Java.

---

## 3. `python -m eval.benchmark --summary-only` (with NO OLLAMA_API_KEY set)

```
============================================================================
MinecraftAI Automated Evaluation Benchmark Report (Step 22B)
============================================================================
Total Test Cases:            78
Passed Cases:                78 (100.0%)
Failed Cases:                0
Clarification Cases:         6
Validation Failures:         4
QA Failures:                 4
Intent Failures:             4
Repair Attempts:             0
Average Duration Per Case:   260.16 ms
----------------------------------------------------------------------------
Version Summary
----------------------------------------------------------------------------
VERSION 1.21.1
  Cases:   25
  Passed:  25 (100.0%)
  Failed:  0

VERSION 1.21.11
  Cases:   53
  Passed:  53 (100.0%)
  Failed:  0

----------------------------------------------------------------------------
Category                     Passed   Total    Accuracy   Avg Time (ms)
----------------------------------------------------------------------------
advancements                 4        4        100.0%     472.18
clarification_required       6        6        100.0%     0.27
compound_requests            4        4        100.0%     0.27
entity_specific_targets      4        4        100.0%     0.82
function_tags                5        5        100.0%     454.59
functions                    6        6        100.0%     451.89
invalid_unsupported          4        4        100.0%     3.63
mob_loot                     7        7        100.0%     465.34
predicates                   5        5        100.0%     495.53
property_absolute            4        4        100.0%     0.52
property_multipliers         5        5        100.0%     1.02
property_percentage          4        4        100.0%     0.47
property_relative            4        4        100.0%     2.19
recipes                      6        6        100.0%     491.90
scoreboard_operations        6        6        100.0%     449.18
state_machines               4        4        100.0%     499.86
============================================================================
```
**Exit Code**: 0 (passes 78/78 when default local Ollama host is used, but crashes with `RuntimeError: OLLAMA_API_KEY is required for Ollama Cloud` if `OLLAMA_HOST=https://ollama.com` is configured in environment without API key because `AutonomousQAReviewer()` instantiates `AIProvider` eagerly).

---

## 4. `git status --short`

```
 M ai/numeric_interpreter.py
 M ai/planner.py
?? .ai/AUDIT_BASELINE.md
?? test_phase3_property_generalization.py
```
*(Plus untracked outputs in `generated/` created during the test run before cleaning).*
