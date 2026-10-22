"""ActiveSite — Autonomous QM/MM Assistant (Open Agent Hackathon 2026 - Track 02)"""
import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ActiveSite: Autonomous QM/MM Assistant with Explainable Scientific Reasoning"
    )
    parser.add_argument("--version", action="version", version="ActiveSite 0.1.0")
    parser.add_argument("--sample-mode", action="store_true", help="Run in offline sample evaluation mode")
    args = parser.parse_args()

    print("ActiveSite 0.1.0 initialized.")
    if args.sample_mode:
        print("Sample mode active (offline evaluation).")


if __name__ == "__main__":
    main()
