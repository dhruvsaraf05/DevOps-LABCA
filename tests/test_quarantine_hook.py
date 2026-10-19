"""Tests for the quarantine hook in tests/conftest.py, run against a throwaway mini project."""

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFTEST = (Path(__file__).parent / "conftest.py").read_text(encoding="utf-8")
BAD_ID = "test_inner.py::test_bad"


@pytest.fixture
def project(pytester, monkeypatch):
    """A temp project with the real conftest, one failing test and one passing test."""
    monkeypatch.delenv("IGNORE_QUARANTINE", raising=False)
    pytester.syspathinsert(REPO_ROOT)  # the real conftest imports `app`
    pytester.makeconftest(CONFTEST)
    pytester.makepyfile(
        test_inner="""
        def test_bad():
            assert False

        def test_good():
            assert True
        """
    )
    return pytester


def quarantine(project, ids):
    entries = [{"id": i} for i in ids]
    project.makefile(".json", quarantine=json.dumps({"version": 1, "tests": entries}))


def test_quarantined_failing_test_becomes_xfail(project):
    quarantine(project, [BAD_ID])
    project.runpytest("-p", "no:randomly").assert_outcomes(passed=1, xfailed=1)


def test_ignore_quarantine_gives_raw_results(project, monkeypatch):
    quarantine(project, [BAD_ID])
    monkeypatch.setenv("IGNORE_QUARANTINE", "1")
    project.runpytest("-p", "no:randomly").assert_outcomes(passed=1, failed=1)


def test_unquarantined_failure_still_fails(project):
    quarantine(project, [])
    project.runpytest("-p", "no:randomly").assert_outcomes(passed=1, failed=1)


def test_missing_quarantine_file_is_fine(project):
    project.runpytest("-p", "no:randomly").assert_outcomes(passed=1, failed=1)
