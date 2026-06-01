"""
all.py — Launch both Backend (FastAPI) and Frontend (Vite) together.

Usage:
    python all.py

This starts:
  1. Backend  →  http://localhost:8000  (FastAPI + DuckDB + LangGraph)
  2. Frontend →  http://localhost:5173  (React + Vite dev server)

Press Ctrl+C to stop both.
"""

import subprocess
import sys
import os
import signal
import time
from pathlib import Path

ROOT = Path(__file__).parent
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"

# ── Colors for terminal output ──────────────────────────────────────
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

processes: list[subprocess.Popen] = []


def log(label: str, color: str, msg: str):
    print(f"{color}{BOLD}[{label}]{RESET} {msg}")


def check_npm():
    """Ensure npm is available and node_modules exist."""
    if not (FRONTEND_DIR / "node_modules").exists():
        log("SETUP", YELLOW, "Installing frontend dependencies (first run)...")
        subprocess.run(
            ["npm", "install"],
            cwd=str(FRONTEND_DIR),
            shell=True,
            check=True,
        )
        log("SETUP", GREEN, "Frontend dependencies installed.")


def start_backend():
    """Start the FastAPI backend with uvicorn."""
    log("BACKEND", CYAN, f"Starting FastAPI on http://localhost:8000")

    env = os.environ.copy()
    env["DATA_DIR"] = str(ROOT / "data")
    env.setdefault("OLLAMA_BASE_URL", "http://192.168.1.206:11434")
<<<<<<< HEAD
    env.setdefault("OLLAMA_MODEL", "RogerBen/qwen3.5-35b-opus-distill:latest")
=======
    env.setdefault("OLLAMA_MODEL", "qwen3:30b")
>>>>>>> beb14c1332f889001101e643b18fcfda2885c8f6

    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "main:app",
            "--host", "0.0.0.0",
            "--port", "8000",
            "--reload",
        ],
        cwd=str(BACKEND_DIR),
        env=env,
    )
    processes.append(proc)
    return proc


def start_frontend():
    """Start the Vite dev server."""
    log("FRONTEND", GREEN, f"Starting Vite on http://localhost:5173")

    proc = subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=str(FRONTEND_DIR),
        shell=True,
    )
    processes.append(proc)
    return proc


def shutdown(*args):
    """Gracefully terminate all child processes."""
    print()
    log("ALL", YELLOW, "Shutting down...")
    for proc in processes:
        try:
            proc.terminate()
        except Exception:
            pass
    # Wait briefly for graceful exit
    for proc in processes:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    log("ALL", GREEN, "All services stopped.")
    sys.exit(0)


def main():
    print()
    print(f"{CYAN}{BOLD}{'═' * 56}{RESET}")
    print(f"{CYAN}{BOLD}  Marassi Smart City — Public Safety Agent{RESET}")
    print(f"{CYAN}{BOLD}{'═' * 56}{RESET}")
    print()

    # Handle Ctrl+C
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Pre-flight checks
    if not (BACKEND_DIR / "main.py").exists():
        log("ERROR", RED, f"Backend not found at {BACKEND_DIR}")
        sys.exit(1)

    if not (FRONTEND_DIR / "package.json").exists():
        log("ERROR", RED, f"Frontend not found at {FRONTEND_DIR}")
        sys.exit(1)

    data_dir = ROOT / "data"
    csv_count = len(list(data_dir.glob("*.csv"))) if data_dir.exists() else 0
    log("DATA", CYAN, f"Found {csv_count} CSV files in {data_dir}")

    if csv_count == 0:
        log("WARNING", YELLOW, "No CSV data files found! Place them in the data/ folder.")

    # Install frontend deps if needed
    check_npm()

    print()

    # Launch both services
    backend_proc = start_backend()
    time.sleep(2)  # Let backend start before frontend
    frontend_proc = start_frontend()

    print()
    log("READY", GREEN, "Both services starting...")
    print()
    print(f"  {BOLD}Backend  →{RESET}  http://localhost:8000       (API docs: /docs)")
    print(f"  {BOLD}Frontend →{RESET}  http://localhost:5173       (Dashboard)")
    print(f"  {BOLD}Ollama   →{RESET}  http://192.168.1.206:11434  (remote LLM server)")
    print()
    print(f"  {YELLOW}Press Ctrl+C to stop all services{RESET}")
    print()

    # Wait for either process to exit
    while True:
        for proc in processes:
            retcode = proc.poll()
            if retcode is not None:
                name = "Backend" if proc == backend_proc else "Frontend"
                log("EXIT", RED if retcode != 0 else YELLOW, f"{name} exited with code {retcode}")
                shutdown()
        time.sleep(1)


if __name__ == "__main__":
    main()
