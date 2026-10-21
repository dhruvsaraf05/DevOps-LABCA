# Architecture

## 1. Pipeline flow (`ci.yml`)

`needs` edges are real job dependencies. Jobs marked "main only" run on push to `main`, not on pull
requests. `test-matrix` is 10 parallel jobs.

```mermaid
flowchart TD
    A[push / pull request to main] --> L[lint<br/>ruff + pytest tools/]
    A --> B[build-test-image<br/>docker build --target test<br/>save image artifact]
    B --> M[test-matrix 1..10<br/>docker run test image<br/>IGNORE_QUARANTINE=1<br/>junit-N.xml]
    M --> AN[analyze<br/>flaky_detector.py over 10 XMLs<br/>report.md to job summary]
    AN -->|exit 1: a non-quarantined<br/>test is broken| RED[build blocked]
    AN -->|exit 0| OK[gate passed]

    OK -->|main only, new flaky tests| Q[quarantine-pr<br/>PR bot/quarantine updates<br/>quarantine.json]
    OK -->|main only| BP[build-push<br/>image :sha and :latest to GHCR]
    L -->|main only| BP
    BP --> D[deploy<br/>write SHA to app/_version.py<br/>vercel deploy --prod]
    D --> S[smoke-test<br/>/version == commit SHA<br/>/health 200, POST /notes 201]
```

Deploys are never triggered by Vercel's Git integration. Only the `deploy` job, after the gate,
can release to production.

## 2. Classification and quarantine state diagram

The state of a test as seen by the detector and the repository over time.

```mermaid
stateDiagram-v2
    [*] --> Counted: 10 runs finished
    Counted --> Stable: failed = 0
    Counted --> Broken: passed = 0
    Counted --> Flaky: mixed results
    Counted --> NotRun: skipped in every run

    Stable --> [*]: nothing to do
    NotRun --> [*]: no verdict, never blocks

    Broken --> Blocking: not in quarantine.json
    Broken --> Listed: already quarantined
    Flaky --> NewlyQuarantined: not in quarantine.json
    Flaky --> Listed: already quarantined

    Blocking --> [*]: gate exits 1
    NewlyQuarantined --> QuarantinePR: main only, bot PR opened
    QuarantinePR --> Listed: human merges the PR
    Listed --> [*]: never blocks, always shown in the report
```

Rules, as implemented in `tools/flaky_detector.py`:

| Condition | Result | Exit code |
|---|---|---|
| Broken and not quarantined | Blocks the build | 1 |
| Flaky and not quarantined | "Newly quarantined", does not block | 0 |
| Already quarantined (any status) | Listed in the report, never blocks | 0 |
| Empty results, unreadable XML, a test missing from some runs, malformed quarantine file | Error report, quarantine file not rewritten | 2 |

## 3. Where each environment fits

```mermaid
flowchart LR
    SRC[commit on main] --> T[Docker test image<br/>10 matrix runs]
    SRC --> RT[Docker runtime image]
    SRC --> V[Vercel build from source]
    RT --> G[(GHCR<br/>versioned release artifact)]
    V --> LIVE[Vercel live URL<br/>serverless function]
    G -.->|docker compose / any container host| LOCAL[local or other hosts]
```

Vercel does not run Docker images. The image in GHCR is the portable, SHA-tagged release artifact.
Vercel builds the same commit from source. Both carry the same SHA, baked into `app/_version.py`
before each build.

## 4. Docker stages

```mermaid
flowchart LR
    base[base<br/>python:3.12-slim<br/>runtime deps + app/] --> test[test<br/>+ dev deps, tests/, quarantine.json<br/>CMD pytest]
    base --> runtime[runtime<br/>non-root user<br/>CMD uvicorn :8000]
```

`runtime` builds from `base`, not from `test`, so pytest, ruff and httpx never reach the release
image.
