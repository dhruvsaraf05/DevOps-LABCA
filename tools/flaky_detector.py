#!/usr/bin/env python3
"""Flaky test detector: classify tests from N repeated pytest runs and apply the CI gate.

Input : a directory of JUnit XML files, one per run (results/run-1.xml ... run-N.xml).
Output: report.json, report.md and (optionally) an updated quarantine file.

Classification (PLAN.md section 4.3), counted over the runs where the test actually ran:
    never failed        -> stable
    failed every time   -> broken
    otherwise           -> flaky   (flake_rate = failed / runs)

Gate:
    broken and not quarantined  -> exit 1 (build blocked)
    flaky and not quarantined   -> "newly quarantined", does NOT block
    already quarantined         -> never blocks, always listed in the report

Exit codes: 0 = gate passed, 1 = gate failed, 2 = bad input (no results, unreadable XML,
a test missing from some runs, malformed quarantine file). Standard library only.
"""

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

PASSED, FAILED, SKIPPED = "passed", "failed", "skipped"  # outcome of one test in one run
STABLE, FLAKY, BROKEN, NOT_RUN = "stable", "flaky", "broken", "not-run"  # verdict over all runs


@dataclass
class TestStat:
    __test__ = False  # not a pytest test class, despite the name

    id: str
    passed: int
    failed: int
    skipped: int
    missing: int  # runs in which this test does not appear at all
    status: str
    quarantined: bool = False
    newly_quarantined: bool = False
    blocking: bool = False

    @property
    def runs(self) -> int:
        """Runs in which the test really executed (skipped runs do not count)."""
        return self.passed + self.failed

    @property
    def flake_rate(self) -> float:
        return round(self.failed / self.runs, 4) if self.runs else 0.0


# ---------------------------------------------------------------- parsing JUnit XML


def make_test_id(classname: str, name: str) -> str:
    """Turn JUnit (classname, name) into a pytest node id.

    pytest writes classname="tests.test_flaky" for a module-level test, or
    "tests.test_x.TestClass" for a method. The first dotted part that looks like a test
    module (test_*) ends the file path; anything after it is a class name.
    """
    parts = [p for p in classname.split(".") if p]
    for i, part in enumerate(parts):
        if part.startswith("test_") or part.endswith("_test"):
            file_path = "/".join(parts[: i + 1]) + ".py"
            return "::".join([file_path, *parts[i + 1 :], name])
    return f"{classname}::{name}" if classname else name


def parse_run(path: Path) -> dict[str, str]:
    """Read one JUnit file and return {test id: passed | failed | skipped}."""
    outcomes: dict[str, str] = {}
    for case in ET.parse(path).getroot().iter("testcase"):
        test_id = make_test_id(case.get("classname", ""), case.get("name", ""))
        if case.find("failure") is not None or case.find("error") is not None:
            outcome = FAILED
        elif case.find("skipped") is not None:
            outcome = SKIPPED
        else:
            outcome = PASSED
        if outcomes.get(test_id) != FAILED:  # a failure (e.g. in teardown) always wins
            outcomes[test_id] = outcome
    return outcomes


def load_runs(results_dir: Path) -> tuple[list[dict[str, str]], list[str]]:
    """Parse every *.xml in the directory. Returns (runs, errors)."""
    runs, errors = [], []
    files = sorted(results_dir.glob("*.xml")) if results_dir.is_dir() else []
    if not files:
        errors.append(f"No JUnit XML files found in '{results_dir}'.")
    for file in files:
        try:
            runs.append(parse_run(file))
        except (ET.ParseError, OSError) as exc:
            errors.append(f"Could not read '{file.name}': {exc}")
    return runs, errors


# ---------------------------------------------------------------- classification + gate


def classify(passed: int, failed: int) -> str:
    if passed + failed == 0:
        return NOT_RUN
    if failed == 0:
        return STABLE
    if passed == 0:
        return BROKEN
    return FLAKY


def analyze(runs: list[dict[str, str]], quarantined_ids: set[str]) -> list[TestStat]:
    """Classify every test seen in any run and apply the gate rules to it."""
    stats = []
    for test_id in sorted({tid for run in runs for tid in run}):
        outcomes = [run.get(test_id) for run in runs]  # None = test absent from that run
        passed, failed = outcomes.count(PASSED), outcomes.count(FAILED)
        stat = TestStat(
            id=test_id,
            passed=passed,
            failed=failed,
            skipped=outcomes.count(SKIPPED),
            missing=outcomes.count(None),
            status=classify(passed, failed),
            quarantined=test_id in quarantined_ids,
        )
        stat.blocking = stat.status == BROKEN and not stat.quarantined
        stat.newly_quarantined = stat.status == FLAKY and not stat.quarantined
        stats.append(stat)
    return stats


def find_consistency_errors(stats: list[TestStat], run_count: int) -> list[str]:
    return [
        f"'{s.id}' is missing from {s.missing} of {run_count} runs."
        for s in stats
        if s.missing
    ]


# ---------------------------------------------------------------- quarantine file


def load_quarantine(path: Path) -> dict:
    """Read quarantine.json. A missing file means nothing is quarantined yet."""
    if not path.exists():
        return {"version": 1, "tests": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("tests"), list):
        raise ValueError("expected an object with a 'tests' list")
    return data


def build_new_quarantine(
    existing: dict, stats: list[TestStat], commit: str, now: datetime
) -> dict:
    """Existing entries are kept untouched; newly flaky tests are appended."""
    timestamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    added = [
        {
            "id": s.id,
            "flake_rate": s.flake_rate,
            "runs": s.runs,
            "detected_at": timestamp,
            "commit": commit,
            "reason": "mixed results across repeated runs",
        }
        for s in stats
        if s.newly_quarantined
    ]
    return {"version": existing.get("version", 1), "tests": [*existing["tests"], *added]}


# ---------------------------------------------------------------- reporting


def build_report(stats: list[TestStat], run_count: int, errors: list[str], commit: str) -> dict:
    blocking = [s for s in stats if s.blocking]
    if errors:
        gate, exit_code = "error", 2
    elif blocking:
        gate, exit_code = "fail", 1
    else:
        gate, exit_code = "pass", 0

    def count(status: str) -> int:
        return sum(1 for s in stats if s.status == status)

    return {
        "commit": commit,
        "runs": run_count,
        "gate": gate,
        "exit_code": exit_code,
        "errors": errors,
        "summary": {
            "total": len(stats),
            "stable": count(STABLE),
            "flaky": count(FLAKY),
            "broken": count(BROKEN),
            "not_run": count(NOT_RUN),
            "quarantined": sum(1 for s in stats if s.quarantined),
            "newly_quarantined": sum(1 for s in stats if s.newly_quarantined),
            "blocking": len(blocking),
        },
        "tests": [
            {
                "id": s.id,
                "status": s.status,
                "passed": s.passed,
                "failed": s.failed,
                "skipped": s.skipped,
                "runs": s.runs,
                "flake_rate": s.flake_rate,
                "quarantined": s.quarantined,
                "newly_quarantined": s.newly_quarantined,
                "blocking": s.blocking,
            }
            for s in stats
        ],
    }


def _table(tests: list[dict]) -> list[str]:
    lines = [
        "| Test | Status | Pass / Fail | Flake rate | Quarantined? |",
        "|---|---|---|---|---|",
    ]
    for t in tests:
        test_id = t["id"].replace("|", "\\|")
        quarantined = "yes" if t["quarantined"] else ("newly" if t["newly_quarantined"] else "no")
        lines.append(
            f"| `{test_id}` | {t['status']} | {t['passed']} / {t['failed']} "
            f"| {t['flake_rate']:.0%} | {quarantined} |"
        )
    return lines


def render_markdown(report: dict) -> str:
    s, tests = report["summary"], report["tests"]
    verdict = {"pass": "PASSED", "fail": "BLOCKED", "error": "ERROR"}[report["gate"]]
    out = [
        "# Flaky test report",
        "",
        f"**Gate: {verdict}** | {s['total']} tests | {report['runs']} runs "
        f"| commit `{report['commit'][:7]}`",
        "",
        "| Stable | Flaky | Broken | Quarantined | Newly quarantined |",
        "|---|---|---|---|---|",
        f"| {s['stable']} | {s['flaky']} | {s['broken']} | {s['quarantined']} "
        f"| {s['newly_quarantined']} |",
        "",
    ]

    if report["errors"]:
        out += ["## Errors", "", *[f"- {e}" for e in report["errors"]], ""]

    broken = [t for t in tests if t["blocking"]]
    if broken:
        out += [
            "## Broken (blocking)",
            "",
            "These tests failed in every run and are not quarantined. The build is blocked.",
            "",
            *_table(broken),
            "",
        ]

    new = [t for t in tests if t["newly_quarantined"]]
    if new:
        out += [
            "## Newly quarantined",
            "",
            "Mixed results across runs. They do not block the build and will be added "
            "to `quarantine.json`.",
            "",
            *_table(new),
            "",
        ]

    old = [t for t in tests if t["quarantined"]]
    if old:
        out += [
            "## Already quarantined",
            "",
            "Quarantined tests never block the build but stay visible here. "
            "One that is now stable may be ready to un-quarantine.",
            "",
            *_table(old),
            "",
        ]

    out += [
        "<details><summary>All tests</summary>",
        "",
        *_table(sorted(tests, key=lambda t: (t["status"] == STABLE, t["id"]))),
        "",
        "</details>",
        "",
    ]
    return "\n".join(out)


# ---------------------------------------------------------------- command line


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Detect flaky tests from repeated JUnit runs.")
    p.add_argument("--results", required=True, type=Path, help="directory of JUnit XML files")
    p.add_argument("--quarantine", required=True, type=Path, help="current quarantine.json")
    p.add_argument("--out-json", type=Path, help="write the machine-readable report here")
    p.add_argument("--out-md", type=Path, help="write the Markdown report here")
    p.add_argument("--write-quarantine", type=Path, help="write the updated quarantine file here")
    p.add_argument("--commit", default="unknown", help="commit SHA recorded in new entries")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    runs, errors = load_runs(args.results)
    try:
        quarantine = load_quarantine(args.quarantine)
    except (ValueError, OSError) as exc:  # json.JSONDecodeError is a ValueError
        errors.append(f"Could not read quarantine file '{args.quarantine}': {exc}")
        quarantine = {"version": 1, "tests": []}

    quarantined_ids = {entry["id"] for entry in quarantine["tests"] if "id" in entry}
    stats = analyze(runs, quarantined_ids)
    errors += find_consistency_errors(stats, len(runs))

    report = build_report(stats, len(runs), errors, args.commit)
    if args.out_json:
        args.out_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.out_md:
        args.out_md.write_text(render_markdown(report), encoding="utf-8")
    if args.write_quarantine and not errors:
        new_quarantine = build_new_quarantine(
            quarantine, stats, args.commit, datetime.now(UTC)
        )
        args.write_quarantine.write_text(
            json.dumps(new_quarantine, indent=2) + "\n", encoding="utf-8"
        )

    s = report["summary"]
    print(
        f"gate={report['gate']} runs={report['runs']} stable={s['stable']} flaky={s['flaky']} "
        f"broken={s['broken']} newly_quarantined={s['newly_quarantined']} "
        f"blocking={s['blocking']}"
    )
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    for stat in stats:
        if stat.blocking:
            print(f"BLOCKING: {stat.id} failed {stat.failed}/{stat.runs} runs", file=sys.stderr)
    return report["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
