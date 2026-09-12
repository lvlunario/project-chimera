"""Synthetic verification demo; no hardware or network access."""
from .engine import Task, run


def verify_link() -> None:
    observed_margin_db = 2.0
    required_margin_db = 3.0
    if observed_margin_db < required_margin_db:
        raise ValueError("Synthetic link margin 2.0 dB is below required 3.0 dB")


def main() -> None:
    tasks = [
        Task("ingest", lambda: "Synthetic fixture loaded"),
        Task("link-check", verify_link, ("ingest",)),
        Task("report", lambda: "All checks passed", ("link-check",)),
        Task("health", lambda: "Runner responsive"),
    ]
    for result in run(tasks).values():
        print(f"{result.task_id}: {result.status}" + (f" — {result.error}" if result.error else ""))


if __name__ == "__main__":
    main()
