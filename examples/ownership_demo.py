"""Synthetic ownership exercise; does not execute or recover interrupted tasks."""
from pathlib import Path
import tempfile

from chimera import DatabaseOwnership, EvidenceStore, OwnershipBusy


def main():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory, "evidence.sqlite")
        with EvidenceStore(path):
            pass
        with DatabaseOwnership(path) as owner:
            # Ordinary SQLite connection/transaction lifetime is independent.
            with EvidenceStore(path):
                pass
            owner.check()
            try:
                with DatabaseOwnership(path):
                    raise RuntimeError("Second owner was incorrectly admitted")
            except OwnershipBusy:
                print("PASS: second owner refused after SQLite connection closed")
        with DatabaseOwnership(path) as owner:
            owner.check()
            print("PASS: ownership available after explicit release")
    print("Temporary database removed; journaling/recovery still pending")


if __name__ == "__main__":
    main()
