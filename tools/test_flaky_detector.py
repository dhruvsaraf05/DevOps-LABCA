"""Unit tests for the detector, using small synthetic JUnit XML files."""

import json
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

import pytest

from tools import flaky_detector as fd

STABLE_ID = "tests/test_a.py::test_stable"
FLAKY_ID = "tests/test_a.py::test_flaky"
BROKEN_ID = "tests/test_a.py::test_broken"


def write_run(results_dir, number, outcomes):
    """Write results_dir/run-<number>.xml. outcomes: {node id: 'pass'|'fail'|'error'|'skip'}."""
    suite = ET.Element("testsuite", name="pytest")
    for node_id, outcome in outcomes.items():
        path, name = node_id.split("::", 1)
        classname = path.removesuffix(".py").replace("/", ".")
        case = ET.SubElement(suite, "testcase", classname=classname, name=name)
        if outcome == "fail":
            ET.SubElement(case, "failure", message="assert False")
        elif outcome == "error":
            ET.SubElement(case, "error", message="boom")
        elif outcome == "skip":
            ET.SubElement(case, "skipped", message="skipped")
    root = ET.Element("testsuites")
    root.append(suite)
    results_dir.mkdir(exist_ok=True)
    ET.ElementTree(root).write(results_dir / f"run-{number}.xml")


def write_runs(results_dir, per_run_outcomes):
    for number, outcomes in enumerate(per_run_outcomes, start=1):
        write_run(results_dir, number, outcomes)


def write_quarantine(path, ids):
    path.write_text(json.dumps({"version": 1, "tests": [{"id": i} for i in ids]}))


def run_cli(tmp_path, quarantine_ids=()):
    """Run the detector CLI on tmp_path/results; return (exit code, report, new quarantine)."""
    quarantine = tmp_path / "quarantine.json"
    write_quarantine(quarantine, quarantine_ids)
    code = fd.main(
        [
            "--results", str(tmp_path / "results"),
            "--quarantine", str(quarantine),
            "--out-json", str(tmp_path / "report.json"),
            "--out-md", str(tmp_path / "report.md"),
            "--write-quarantine", str(tmp_path / "quarantine.new.json"),
            "--commit", "abc1234def",
        ]
    )  # fmt: skip
    report = json.loads((tmp_path / "report.json").read_text())
    new_path = tmp_path / "quarantine.new.json"
    new_quarantine = json.loads(new_path.read_text()) if new_path.exists() else None
    return code, report, new_quarantine


def by_id(report):
    return {t["id"]: t for t in report["tests"]}


def mixed_runs(flaky_fails=(0, 1, 2)):
    """10 runs: STABLE always passes, FLAKY fails in some runs, BROKEN always fails."""
    return [
        {
            STABLE_ID: "pass",
            FLAKY_ID: "fail" if i in flaky_fails else "pass",
            BROKEN_ID: "fail",
        }
        for i in range(10)
    ]


# ---------------------------------------------------------------- classification


def test_classify():
    assert fd.classify(passed=10, failed=0) == fd.STABLE
    assert fd.classify(passed=0, failed=10) == fd.BROKEN
    assert fd.classify(passed=7, failed=3) == fd.FLAKY
    assert fd.classify(passed=1, failed=9) == fd.FLAKY
    assert fd.classify(passed=0, failed=0) == fd.NOT_RUN


def test_stable_flaky_broken_are_classified_with_flake_rate(tmp_path):
    write_runs(tmp_path / "results", mixed_runs())
    _, report, _ = run_cli(tmp_path)
    tests = by_id(report)
    assert tests[STABLE_ID]["status"] == "stable"
    assert tests[FLAKY_ID]["status"] == "flaky"
    assert tests[FLAKY_ID]["flake_rate"] == 0.3
    assert (tests[FLAKY_ID]["passed"], tests[FLAKY_ID]["failed"]) == (7, 3)
    assert tests[BROKEN_ID]["status"] == "broken"
    assert tests[BROKEN_ID]["flake_rate"] == 1.0


def test_error_element_counts_as_failure(tmp_path):
    write_runs(tmp_path / "results", [{STABLE_ID: "error"}, {STABLE_ID: "pass"}])
    _, report, _ = run_cli(tmp_path)
    assert by_id(report)[STABLE_ID]["status"] == "flaky"


def test_skipped_runs_are_not_counted(tmp_path):
    runs = [{STABLE_ID: "pass"}, {STABLE_ID: "skip"}, {STABLE_ID: "pass"}]
    write_runs(tmp_path / "results", runs)
    code, report, _ = run_cli(tmp_path)
    test = by_id(report)[STABLE_ID]
    assert (test["status"], test["passed"], test["skipped"], test["runs"]) == ("stable", 2, 1, 2)
    assert code == 0


def test_always_skipped_test_has_no_verdict_and_does_not_block(tmp_path):
    write_runs(tmp_path / "results", [{STABLE_ID: "skip"}] * 3)
    code, report, _ = run_cli(tmp_path)
    assert by_id(report)[STABLE_ID]["status"] == "not-run"
    assert code == 0


# ---------------------------------------------------------------- gate


def test_unquarantined_broken_test_blocks_the_build(tmp_path):
    write_runs(tmp_path / "results", mixed_runs())
    code, report, _ = run_cli(tmp_path)
    assert code == 1
    assert report["gate"] == "fail"
    assert by_id(report)[BROKEN_ID]["blocking"] is True


def test_broken_but_quarantined_does_not_block_and_is_listed(tmp_path):
    write_runs(tmp_path / "results", mixed_runs())
    code, report, _ = run_cli(tmp_path, quarantine_ids=[BROKEN_ID])
    assert code == 0
    assert by_id(report)[BROKEN_ID]["blocking"] is False
    assert by_id(report)[BROKEN_ID]["quarantined"] is True
    assert "Already quarantined" in (tmp_path / "report.md").read_text()


def test_new_flaky_test_does_not_block_and_is_newly_quarantined(tmp_path):
    runs = [{STABLE_ID: "pass", FLAKY_ID: "fail" if i < 4 else "pass"} for i in range(10)]
    write_runs(tmp_path / "results", runs)
    code, report, new_quarantine = run_cli(tmp_path)
    assert code == 0
    assert by_id(report)[FLAKY_ID]["newly_quarantined"] is True
    assert report["summary"]["newly_quarantined"] == 1
    assert [t["id"] for t in new_quarantine["tests"]] == [FLAKY_ID]


def test_already_quarantined_flaky_test_is_not_newly_quarantined_again(tmp_path):
    runs = [{FLAKY_ID: "fail" if i < 3 else "pass"} for i in range(10)]
    write_runs(tmp_path / "results", runs)
    code, report, new_quarantine = run_cli(tmp_path, quarantine_ids=[FLAKY_ID])
    assert code == 0
    assert by_id(report)[FLAKY_ID]["newly_quarantined"] is False
    assert [t["id"] for t in new_quarantine["tests"]] == [FLAKY_ID]  # no duplicate


def test_quarantined_test_that_is_now_stable_is_still_listed(tmp_path):
    write_runs(tmp_path / "results", [{STABLE_ID: "pass"}] * 5)
    code, report, _ = run_cli(tmp_path, quarantine_ids=[STABLE_ID])
    assert code == 0
    assert by_id(report)[STABLE_ID]["quarantined"] is True
    assert report["summary"]["quarantined"] == 1


def test_all_stable_passes(tmp_path):
    write_runs(tmp_path / "results", [{STABLE_ID: "pass"}] * 10)
    code, report, new_quarantine = run_cli(tmp_path)
    assert (code, report["gate"]) == (0, "pass")
    assert new_quarantine["tests"] == []


# ---------------------------------------------------------------- quarantine file


def test_new_quarantine_keeps_existing_entries_and_adds_metadata(tmp_path):
    runs = [{FLAKY_ID: "fail" if i < 3 else "pass", STABLE_ID: "pass"} for i in range(10)]
    write_runs(tmp_path / "results", runs)
    old = tmp_path / "quarantine.json"
    old.write_text(json.dumps({"version": 1, "tests": [{"id": "tests/old.py::test_old"}]}))
    fd.main(
        ["--results", str(tmp_path / "results"), "--quarantine", str(old),
         "--write-quarantine", str(tmp_path / "new.json"), "--commit", "abc1234def"]
    )  # fmt: skip
    tests = json.loads((tmp_path / "new.json").read_text())["tests"]
    assert [t["id"] for t in tests] == ["tests/old.py::test_old", FLAKY_ID]
    entry = tests[1]
    assert (entry["flake_rate"], entry["runs"], entry["commit"]) == (0.3, 10, "abc1234def")
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", entry["detected_at"])
    assert entry["reason"]


def test_build_new_quarantine_uses_given_timestamp():
    stat = fd.TestStat(FLAKY_ID, passed=7, failed=3, skipped=0, missing=0, status=fd.FLAKY)
    stat.newly_quarantined = True
    now = datetime(2026, 10, 14, 10, 22, tzinfo=UTC)
    result = fd.build_new_quarantine({"version": 1, "tests": []}, [stat], "abc", now)
    assert result["tests"][0]["detected_at"] == "2026-10-14T10:22:00Z"


def test_missing_quarantine_file_means_nothing_quarantined(tmp_path):
    write_runs(tmp_path / "results", [{STABLE_ID: "pass"}] * 3)
    code = fd.main(["--results", str(tmp_path / "results"), "--quarantine", str(tmp_path / "nope")])
    assert code == 0


def test_malformed_quarantine_file_is_an_error(tmp_path):
    write_runs(tmp_path / "results", [{STABLE_ID: "pass"}] * 3)
    bad = tmp_path / "quarantine.json"
    bad.write_text("{not json")
    assert fd.main(["--results", str(tmp_path / "results"), "--quarantine", str(bad)]) == 2


# ---------------------------------------------------------------- bad input


def test_empty_results_dir_is_an_error(tmp_path):
    (tmp_path / "results").mkdir()
    code, report, _ = run_cli(tmp_path)
    assert code == 2
    assert report["gate"] == "error"
    assert "No JUnit XML files" in report["errors"][0]


def test_nonexistent_results_dir_is_an_error(tmp_path):
    write_quarantine(tmp_path / "quarantine.json", [])
    code = fd.main(
        ["--results", str(tmp_path / "missing"), "--quarantine", str(tmp_path / "quarantine.json")]
    )
    assert code == 2


def test_test_missing_from_some_runs_is_an_error(tmp_path):
    runs = [{STABLE_ID: "pass", FLAKY_ID: "pass"}] * 4 + [{STABLE_ID: "pass"}] * 2
    write_runs(tmp_path / "results", runs)
    code, report, new_quarantine = run_cli(tmp_path)
    assert code == 2
    assert any(FLAKY_ID in e and "missing from 2 of 6" in e for e in report["errors"])
    assert new_quarantine is None  # input is untrustworthy: quarantine is not rewritten


def test_unparseable_xml_is_an_error(tmp_path):
    write_runs(tmp_path / "results", [{STABLE_ID: "pass"}] * 2)
    (tmp_path / "results" / "run-3.xml").write_text("<testsuites><oops")
    code, report, _ = run_cli(tmp_path)
    assert code == 2
    assert any("run-3.xml" in e for e in report["errors"])


# ---------------------------------------------------------------- ids and reports


@pytest.mark.parametrize(
    ("classname", "name", "expected"),
    [
        ("tests.test_flaky", "test_x", "tests/test_flaky.py::test_x"),
        ("tests.test_a.TestThing", "test_y", "tests/test_a.py::TestThing::test_y"),
        ("tests.sub.test_b", "test_z[a-1]", "tests/sub/test_b.py::test_z[a-1]"),
        ("", "tests.test_flaky", "tests.test_flaky"),  # e.g. a collection error
    ],
)
def test_make_test_id(classname, name, expected):
    assert fd.make_test_id(classname, name) == expected


def test_markdown_report_has_expected_sections(tmp_path):
    write_runs(tmp_path / "results", mixed_runs())
    run_cli(tmp_path)
    md = (tmp_path / "report.md").read_text()
    assert "**Gate: BLOCKED**" in md
    assert "## Broken (blocking)" in md
    assert "## Newly quarantined" in md
    assert f"`{FLAKY_ID}` | flaky | 7 / 3 | 30% | newly" in md
    assert "## Already quarantined" not in md


def test_report_json_summary_counts(tmp_path):
    write_runs(tmp_path / "results", mixed_runs())
    _, report, _ = run_cli(tmp_path)
    assert report["runs"] == 10
    assert report["commit"] == "abc1234def"
    assert report["summary"] == {
        "total": 3, "stable": 1, "flaky": 1, "broken": 1, "not_run": 0,
        "quarantined": 0, "newly_quarantined": 1, "blocking": 1,
    }  # fmt: skip
