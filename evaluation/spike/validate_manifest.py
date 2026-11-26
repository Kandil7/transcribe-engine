"""Check a dev manifest and print its counts.

Usage: python -m evaluation.spike.validate_manifest <manifest.jsonl> [--require-coverage]

Exit status: 0 when the file parses (and meets the coverage gate if asked), 1 otherwise.
Error output names the line and the rule, never the transcript text or the file name.
"""

import argparse
import sys
from pathlib import Path

from evaluation.spike.manifest import ManifestError, coverage_problems, load, summarize


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate an S00 dev manifest.")
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--require-coverage",
        action="store_true",
        help="also apply the S00 coverage gate (60 min, 5 speakers, required conditions)",
    )
    args = parser.parse_args(argv)
    try:
        summary = summarize(load(args.manifest))
    except ManifestError as exc:
        sys.stderr.write(f"invalid manifest: {exc}\n")
        return 1
    except OSError as exc:
        sys.stderr.write(f"cannot read manifest ({type(exc).__name__})\n")
        return 1

    lines = [
        f"turns: {summary.turns}",
        f"speakers: {summary.speakers}",
        f"minutes: {summary.total_ms / 60_000:.1f}",
        *(f"condition {name}: {count}" for name, count in summary.conditions.items()),
    ]
    problems = coverage_problems(summary) if args.require_coverage else []
    lines.extend(f"coverage: {problem}" for problem in problems)
    sys.stdout.write("\n".join(lines) + "\n")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
