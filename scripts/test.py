#!/usr/bin/env python3
"""Smart test runner: quiet first pass, detailed on failure."""

import subprocess
import sys


def main():
    full_suite = "--full" in sys.argv

    # Pass 1: Quick check
    cmd = ["pytest", "--tb=no", "-q", "--no-header"]
    if not full_suite:
        cmd.append("--affected-only")

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        summary = result.stdout.strip().split("\n")[-1] if result.stdout.strip() else "All tests passed"
        print(f"✓ {summary}")
        return 0

    # Pass 2: Detailed on failure (only failed tests)
    summary = result.stdout.strip().split("\n")[-1] if result.stdout.strip() else "Tests failed"
    print(f"✗ {summary}")
    print("\nRe-running failed tests with detail...")

    subprocess.run(["pytest", "--last-failed", "--tb=short", "-v"])
    return 1


if __name__ == "__main__":
    sys.exit(main())
