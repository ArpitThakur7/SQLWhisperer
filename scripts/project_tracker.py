"""SQLWhisperer — Project Tracker & Development Notes Manager.

This script tracks project progress, verifies repository health, records
timestamped development activity logs in PROJECT_NOTES.md, and provides
quick visibility into what has been done, what is in progress, and what is next.

Usage:
    python -m scripts.project_tracker                     # Show dashboard
    python -m scripts.project_tracker --status            # Detailed repo inspection
    python -m scripts.project_tracker --log "Worked on X" # Add entry to PROJECT_NOTES.md
    python -m scripts.project_tracker --set-task "Task"   # Update current in-progress task
    python -m scripts.project_tracker --check-tests       # Run test suite
"""

import argparse
import datetime
import os
import re
import subprocess
import sys
from pathlib import Path

# Paths
ROOT_DIR = Path(__file__).resolve().parent.parent
NOTES_FILE = ROOT_DIR / "PROJECT_NOTES.md"
SRC_DIR = ROOT_DIR / "src"
TESTS_DIR = ROOT_DIR / "tests"

# Expected milestone files to monitor
EXPECTED_CORE_FILES = [
    # Chains
    "src/chains/schema_retriever.py",
    "src/chains/text2sql.py",
    "src/chains/validator.py",
    "src/chains/executor.py",
    "src/chains/inspector.py",
    "src/chains/explainer.py",
    "src/chains/pipeline.py",
    # Memory
    "src/memory/few_shot_store.py",
    "src/memory/feedback.py",
    # DB
    "src/db/connector.py",
    "src/db/models.py",
    "src/db/history.py",
    # API & Frontend
    "src/api/app.py",
    "src/api/routes.py",
    "src/schemas/request.py",
    "src/schemas/response.py",
    "streamlit_app/app.py",
    # Scripts & Docker
    "scripts/init_db.sql",
    "scripts/seed_db.py",
    "scripts/seed_few_shots.py",
    "docker-compose.yml",
    "run.bat",
    "stop.bat",
]

OPEN_SOURCE_CHECKLIST_FILES = [
    ("LICENSE", "License file (MIT/Apache)"),
    ("pyproject.toml", "PEP 621 Python packaging"),
    ("CONTRIBUTING.md", "Contributor guidelines"),
    ("CODE_OF_CONDUCT.md", "Contributor Code of Conduct"),
    ("SECURITY.md", "Security disclosure policy"),
    (".github/workflows/ci.yml", "GitHub Actions CI pipeline"),
    (".github/ISSUE_TEMPLATE/bug_report.md", "Bug report template"),
    (".github/ISSUE_TEMPLATE/feature_request.md", "Feature request template"),
]


def inspect_repository() -> dict:
    """Analyze the repository state and calculate completion metrics."""
    core_present = [f for f in EXPECTED_CORE_FILES if (ROOT_DIR / f).is_file()]
    core_missing = [f for f in EXPECTED_CORE_FILES if not (ROOT_DIR / f).is_file()]

    oss_present = [f for f, _ in OPEN_SOURCE_CHECKLIST_FILES if (ROOT_DIR / f).is_file()]
    oss_missing = [(f, desc) for f, desc in OPEN_SOURCE_CHECKLIST_FILES if not (ROOT_DIR / f).is_file()]

    # Count total code files
    python_files = list(ROOT_DIR.glob("**/*.py"))
    test_files = list(TESTS_DIR.glob("**/test_*.py")) if TESTS_DIR.exists() else []

    # Check env file
    has_env = (ROOT_DIR / ".env").is_file()
    has_env_example = (ROOT_DIR / ".env.example").is_file()

    return {
        "core_count": len(core_present),
        "core_total": len(EXPECTED_CORE_FILES),
        "core_percent": int((len(core_present) / len(EXPECTED_CORE_FILES)) * 100),
        "core_missing": core_missing,
        "oss_count": len(oss_present),
        "oss_total": len(OPEN_SOURCE_CHECKLIST_FILES),
        "oss_percent": int((len(oss_present) / len(OPEN_SOURCE_CHECKLIST_FILES)) * 100),
        "oss_missing": oss_missing,
        "python_files_count": len(python_files),
        "test_files_count": len(test_files),
        "has_env": has_env,
        "has_env_example": has_env_example,
    }


def print_dashboard():
    """Print an executive progress summary to terminal."""
    repo = inspect_repository()

    print("=" * 68)
    print(" [*] SQLWhisperer -- Repository Progress & Status Tracker")
    print("=" * 68)
    print(f" Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f" Workspace: {ROOT_DIR}\n")

    # Core System Health
    print(f"[Core Components Health]    [{'#' * (repo['core_percent'] // 5)}{'.' * (20 - (repo['core_percent'] // 5))}] {repo['core_percent']}%")
    print(f"   - Core Architecture Files: {repo['core_count']}/{repo['core_total']} verified")
    print(f"   - Total Python Source Files: {repo['python_files_count']}")
    print(f"   - Test Modules Discovered:   {repo['test_files_count']}")
    print(f"   - Environment Config:        {'.env present' if repo['has_env'] else 'Missing .env (use .env.example)'}")

    if repo["core_missing"]:
        print("\n   [!] Missing Core Files:")
        for f in repo["core_missing"]:
            print(f"      - {f}")

    print("\n" + "-" * 68)
    # Open Source Readiness
    print(f"[Open-Source Readiness]     [{'#' * (repo['oss_percent'] // 5)}{'.' * (20 - (repo['oss_percent'] // 5))}] {repo['oss_percent']}%")
    print(f"   - OSS Standards Files:     {repo['oss_count']}/{repo['oss_total']} verified")

    if repo["oss_missing"]:
        print("   [ ] Pending Open-Source Items:")
        for f, desc in repo["oss_missing"]:
            print(f"      [ ] {f:<36} ({desc})")
    else:
        print("   [OK] All open-source community standards present!")

    print("\n" + "-" * 68)
    print("Commands:")
    print('   python -m scripts.project_tracker --log "Add description of your work"')
    print('   python -m scripts.project_tracker --set-task "Description of active task"')
    print('   python -m scripts.project_tracker --check-tests')
    print("=" * 68)


def log_activity(message: str, event_name: str = "Dev Update", status: str = "Completed"):
    """Append a timestamped log to the table in PROJECT_NOTES.md."""
    if not NOTES_FILE.is_file():
        print(f"Error: {NOTES_FILE} not found.")
        return

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    new_entry = f"| {now_str} | {event_name} | {status} | {message} |\n"

    content = NOTES_FILE.read_text(encoding="utf-8")
    table_header = "| Timestamp | Event / Action | Status | Notes |\n| :--- | :--- | :--- | :--- |"

    if table_header in content:
        # Append right after table header
        parts = content.split(table_header, 1)
        updated_content = parts[0] + table_header + "\n" + new_entry + parts[1].lstrip("\n")
        NOTES_FILE.write_text(updated_content, encoding="utf-8")
        print(f"[OK] Successfully logged activity to PROJECT_NOTES.md:\n   {new_entry.strip()}")
    else:
        # Append to end of file
        with open(NOTES_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n{new_entry}")
        print("[OK] Appended log entry to PROJECT_NOTES.md")


def set_active_task(task_description: str):
    """Update the 'Current Work (In Progress)' section in PROJECT_NOTES.md."""
    if not NOTES_FILE.is_file():
        print(f"Error: {NOTES_FILE} not found.")
        return

    content = NOTES_FILE.read_text(encoding="utf-8")
    pattern = r"(## 🎯 Current Work \(In Progress\)\n\n)(.*?)(?=\n##|\Z)"

    replacement = f"\\1* {task_description}\n"
    new_content, count = re.subn(pattern, replacement, content, flags=re.DOTALL)

    if count > 0:
        NOTES_FILE.write_text(new_content, encoding="utf-8")
        print(f"[OK] Updated Active Task in PROJECT_NOTES.md to:\n   * {task_description}")
    else:
        print("[!] Could not locate 'Current Work' section in PROJECT_NOTES.md")


def run_tests():
    """Execute pytest test suite."""
    print("[*] Running pytest test suite...\n")
    cmd = [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"]
    try:
        subprocess.run(cmd, cwd=str(ROOT_DIR), check=True)
    except subprocess.CalledProcessError as e:
        print(f"\n[FAIL] Tests failed with exit code {e.returncode}")
    except FileNotFoundError:
        print("[FAIL] pytest command not found in current environment.")


def main():
    parser = argparse.ArgumentParser(description="SQLWhisperer Project Progress Tracker")
    parser.add_argument("--status", action="store_true", help="Display full repository dashboard")
    parser.add_argument("--log", type=str, help="Add a timestamped log entry to PROJECT_NOTES.md")
    parser.add_argument("--event", type=str, default="Dev Update", help="Event title for the log entry")
    parser.add_argument("--status-col", type=str, default="Completed", help="Status column for the log entry")
    parser.add_argument("--set-task", type=str, help="Set the current in-progress task in PROJECT_NOTES.md")
    parser.add_argument("--check-tests", action="store_true", help="Run project test suite")

    args = parser.parse_args()

    if args.log:
        log_activity(args.log, event_name=args.event, status=args.status_col)
    elif args.set_task:
        set_active_task(args.set_task)
    elif args.check_tests:
        run_tests()
    else:
        print_dashboard()


if __name__ == "__main__":
    main()
