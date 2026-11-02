# Live demo script (10 minutes)

Scenarios A → B → C → D from `PLAN.md` section 5, Phase 7. Everything below was run once end to
end; the screenshots in `docs/screenshots/` are the fallbacks.

| Item | URL |
|---|---|
| Repository | https://github.com/dhruvsaraf05/DevOps-LABCA |
| Actions (all runs) | https://github.com/dhruvsaraf05/DevOps-LABCA/actions |
| naive-ci runs | https://github.com/dhruvsaraf05/DevOps-LABCA/actions/workflows/naive-ci.yml |
| PR 3 (real bug, must stay a blocked draft) | https://github.com/dhruvsaraf05/DevOps-LABCA/pull/3 |
| Live app | https://quarantine-flaky-ci.vercel.app/version |
| GHCR package | https://github.com/users/dhruvsaraf05/packages/container/package/devops-labca |
| Vercel project (logged in) | https://vercel.com/dhruvsaraf05s-projects/quarantine-flaky-ci |

## Who presents what

| Person | Part | Time |
|---|---|---|
| **Person 1** (app + detector) | Problem, classification rules, the detector, the probability math (why 10 runs). Scenario A and the detector part of B. | about 3.5 min |
| **Person 2** (pipeline) | Architecture diagram, the `ci.yml` jobs, the gate, quarantine PR, GHCR, Vercel deploy, smoke test. Scenarios C and D. | about 4 min |
| **Person 3** (demo + report) | Opens each page, clicks, drives the browser, handles fallbacks, wraps up with results and limitations. Answers viva questions on the report. | about 2.5 min plus Q&A |

Person 3 drives the screen the whole time; Persons 1 and 2 talk.

## Timeline

| Time | What |
|---|---|
| 0:00 | One-paragraph pitch, architecture diagram (README) |
| 1:00 | **A** Before: naive-ci |
| 2:30 | **B** Detection: merge the new-flaky PR, then the bot PR |
| 5:00 | **C** Real bug: PR 3 blocked |
| 7:00 | **D** Delivery: merge the harmless PR, show live `/version` |
| 9:00 | Results, limitations, questions |

The main-branch run after a merge takes about 2.5 minutes, so B's and D's merges are timed to
finish while the next scenario is being talked through.

## Prepare the night before (once)

The branches `demo/new-flaky` and `demo/harmless-change` were deleted when they were merged, so
make fresh ones. Do this from a clean `main` (`git pull`), then push and open PRs.

**B: a new flaky test.** `import random` and `flake_rate()` already exist in `tests/test_flaky.py`.
Add one more test function, with a new name each time (a test already in `quarantine.json` would
not be "new"):

```python
def test_flaky_demo_second_new_test():
    """INTENTIONALLY FLAKY (demo scenario B): fails with probability FLAKE_RATE."""
    assert random.SystemRandom().random() >= flake_rate()
```

```bash
git checkout -b demo/new-flaky-2
git commit -am "test: add another new flaky test (demo scenario B)"
git push -u origin demo/new-flaky-2
gh pr create --base main --head demo/new-flaky-2 --title "demo: add another flaky test (scenario B)" --body "Demo scenario B."
```

**D: a harmless change.** Edit the `description=` text in `app/main.py`, then:

```bash
git checkout -b demo/harmless-change-2
git commit -am "docs: tweak API description (demo scenario D)"
git push -u origin demo/harmless-change-2
gh pr create --base main --head demo/harmless-change-2 --title "demo: harmless change (scenario D)" --body "Demo scenario D."
```

Both PRs should show green `lint` and `analyze` before the demo. If a flaky test happens to pass
all 10 runs, the PR has nothing "new" to show: push an empty commit to re-run it.

## Pre-demo checklist (15 minutes before)

- [ ] Open https://quarantine-flaky-ci.vercel.app/version once to warm up the serverless function.
- [ ] Confirm PR 3 is still an open **draft** and shows "Merging is blocked" (logged in).
- [ ] The two prepared PRs (B and D) show green `lint` and `analyze`.
- [ ] No CI run is still in progress on `main` (Actions tab). Runs on `main` queue, so a pending
      run would delay B or D.
- [ ] Logged in to GitHub in the demo browser, with admin rights (needed for the bot PR).
- [ ] Tabs open, in this order: (1) README, (2) naive-ci runs, (3) the B PR, (4) PR 3, (5) the D PR,
      (6) live `/version`, (7) GHCR package, (8) Vercel dashboard deployments.
- [ ] A terminal in the repo with the venv active, for the local detector run (Person 1).
- [ ] `docs/screenshots/` open in a file viewer, as the fallback.
- [ ] Phones on silent, hotspot ready.

## A: Before (about 1.5 min). Person 1 talks, Person 3 drives

1. Open the **naive-ci runs** tab. It lists runs of the same code on the same commit, some red and
   some green.
2. Click **Run workflow** → **Run workflow** on `main`. Say that you will check it at the end.
3. Open one red run and show that the failing test is one of the `test_flaky_*` tests.

*Talking points*
- Same code, different result: that is a flaky test, and it makes CI untrustworthy.
- The usual reaction is "re-run until green". Retrying hides the flakiness and slows every build.
- naive-ci has no detector and ignores quarantine, so it shows the "before" state.

*Fallback:* show `docs/screenshots/A-naive-ci-red-green-runs.png`.

## B: Detection (about 2.5 min). Person 1 then Person 2

1. Open the **B PR**. Show the checks: `lint`, `analyze` green and the 10 `test-matrix` jobs.
2. Open the **Actions run** → the **graph**: 10 parallel matrix jobs. Then the `analyze` job →
   **Summary**: the flaky-test table with the new test marked "newly".
3. Go to Person 1's terminal: `make test-n N=10`, then the detector command from the README.
   Show `report.md`. (If it is slow, skip and keep the Summary.)
4. Back on the PR: click **Merge**. Say that the main run now starts.
5. Move on to scenario C. After about 2 minutes, open the **Pull requests** tab: the bot PR
   "chore: quarantine 1 flaky test(s)" has appeared. Open it: its body is the report; the diff adds
   one entry to `quarantine.json`. Click **Merge pull request**. Tick **"Merge without waiting for
   requirements to be met (bypass branch protections)"**, because bot PRs get no checks.

*Talking points*
- 10 runs in parallel containers, random test order, quarantine ignored in these runs, so the
  results are raw.
- Flaky means mixed results. It does not block. It is recorded through a reviewable PR.
- The probability: at p = 0.3, 10 runs miss a flaky test only 2.8% of the time.
- Quarantined tests still run and stay listed in every report. Quarantine does not hide failures.

*Fallback:* `B-pr2-matrix-and-summary.png`, `B-job-summary-flaky-table.png`,
`B-bot-quarantine-pr.png`.

## C: Real bug (about 2 min). Person 2

1. Open **PR 3** (draft). Show the title: POST /notes returns 200 instead of 201.
2. Open its **Actions run**: the `analyze` job is red, the 10 matrix jobs are green. Open the
   Summary: two tests **broken, 0 / 10**, the quarantined flaky tests are listed but did not matter.
3. Go back to the PR: **"Merging is blocked"**. The release jobs never ran for it.
4. Optional: the Vercel dashboard shows no new deployment for this change.

*Talking points*
- A flaky test and a real bug look different: flaky is mixed, broken fails every run. The gate blocks
  only on broken.
- Branch protection requires `lint` and `analyze`, so the bug cannot reach `main` or production.
- **Do not click merge or mark PR 3 ready for review.**

*Fallback:* `C-pr3-run-broken-tests.png`, `C-pr3-merge-blocked.png`.

## D: Delivery (about 2 min). Person 2 talks, Person 3 drives

1. Wait until B's main run has finished (Actions tab, top run green). Then open the **D PR**
   and click **Merge**.
2. Open the new run on `main`. Walk through the graph left to right: `lint`, matrix, `analyze`,
   `build-push`, `deploy`, `smoke-test`. It takes about 2.5 minutes.
3. When it is green: open the **live `/version`** and compare it with the commit SHA of the run.
4. Open the **GHCR package**: the same SHA as a tag, plus `latest`.
5. Open the **Vercel deployments** page: all deployments come from the CLI, none from Git.

*Talking points*
- Only code that passed the gate is released. Image to GHCR, same commit to Vercel with the Vercel
  CLI.
- The smoke test does not just check that the site is up. It checks that `/version` returns this
  commit's SHA.
- Vercel does not run the Docker image. The GHCR image is the versioned release artifact.
- The Vercel project is not connected to Git, so CI is the only way to deploy.

*Fallback:* `D-release-chain-green.png`, `D-live-version.png`, `D-ghcr-package.png`,
`D-vercel-dashboard-cli-only.png`.

## Wrap-up (about 1 min). Person 3

- Results: 4 scenarios run on real runs; the numbers are in `docs/REPORT.md` section 8.
- Limitations: detection is probabilistic, the quarantine PR needs admin bypass, there is no
  persistent storage on Vercel, quarantine needs human follow-up.
- Offer the naive-ci run from scenario A as the closing contrast.

## If something goes wrong

| Problem | What to do |
|---|---|
| GitHub or Actions is slow or down | Use the fallback screenshots for the current scenario and keep talking; do not wait on a spinner. |
| A run is stuck in "queued" | The `main` run queue: another run is in progress. Show the screenshot and move on. |
| The new flaky test passes all 10 runs (no "newly quarantined") | Say that this is the 2.8% miss from the probability slide, then show `B-job-summary-flaky-table.png`. It is a real example of why detection is probabilistic. |
| The smoke test fails or `/version` is old | Wait one minute (Vercel alias update), reload. If still old, show `D-live-version.png` and say what the job checks. |
| Vercel's first request is slow | That is the serverless cold start. It is why the pre-demo checklist opens the URL first. |
