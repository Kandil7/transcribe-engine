"""commit-msg hook: enforce `type(scope): summary` (see CONTRIBUTING.md).

Valid:  feat(S06): claim jobs with FOR UPDATE SKIP LOCKED
        test(S02): add transition table tests (xfail)
        chore(repo): bump ruff
Invalid: "fixed stuff", "feat: no scope", "feat(S6): bad slice id"
"""

import re
import sys
from pathlib import Path

TYPES = "feat|fix|test|refactor|docs|chore|perf|build|ci|revert|spike"
SCOPE = r"S\d{2}|repo|ci|deps|docs|eval|adr"
PATTERN = re.compile(rf"^({TYPES})\(({SCOPE})\)!?: \S.{{0,70}}$")
MERGE_OR_FIXUP = re.compile(r"^(Merge |Revert |fixup! |squash! )")


def main() -> int:
    first_line = Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()[0].strip()
    if MERGE_OR_FIXUP.match(first_line) or PATTERN.match(first_line):
        return 0
    print(
        "Commit message must be `type(scope): summary` (summary <= 72 chars).\n"
        f"  types:  {TYPES.replace('|', ', ')}\n"
        "  scopes: SXX slice id (e.g. S06), repo, ci, deps, docs, eval, adr\n"
        f"  got:    {first_line!r}"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
