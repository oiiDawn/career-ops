# Architecture

A high-level map of how career-ops is put together. For the precise system/user file boundary, see [DATA_CONTRACT.md](DATA_CONTRACT.md); for contribution mechanics, see [CONTRIBUTING.md](CONTRIBUTING.md); for runtime flow diagrams (evaluation steps, batch processing), see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Principles

Career-ops is built on three commitments that every design decision serves:

- **Local-first.** Everything runs on your machine against your files. No account required, no server in the loop for the core tool.
- **AI-agnostic.** The logic lives in Markdown prompt files under `modes/`, executed by whatever AI coding CLI you use (Claude Code, Codex, OpenCode, Gemini, Qwen, Grok, Antigravity) or by standalone Node scripts. No single model is hardcoded.
- **Human-in-the-loop.** The tool prepares and evaluates; the human reviews and clicks. It never submits applications on your behalf.

## The two layers (the data contract)

The single most important architectural rule: **system files** and **user files** are strictly separated.

- **System layer** — the tool itself: `modes/`, scripts (`*.mjs`), templates. These are versioned and updated by `update-system.mjs`. Listed in `SYSTEM_PATHS`.
- **User layer** — your data: `cv.md`, `config/profile.yml`, `modes/_profile.md`, `data/`, `reports/`, `jds/`, etc. The updater **never** touches these. Listed in `USER_PATHS`.

`DATA_CONTRACT.md` is the source of truth for this boundary, and `updater-migration-tests.mjs` enforces that no system path ever overlaps a user path.

## Files are canonical — databases are derived

Settled doctrine ([#918](https://github.com/santifer/career-ops/issues/918)): the human-readable, git-diffable files (`data/applications.md`, `reports/`, `data/pipeline.md`) are the **permanent source of truth**. SQLite exists only as a derived index (fast queries, reindex-on-delete) and will never become a primary store — not even opt-in. The reason is ecosystem-wide: CLI tools, community plugins, and fork scripts all read the files; a second canonical store would force every reader to support two modes forever. Performance work is welcome **on the derived layer**; the files stay the brain.

## Why the flat root

The repo keeps its ~70 scripts at the root deliberately ([#1386](https://github.com/santifer/career-ops/issues/1386)). Path stability is a feature here, not an accident: the updater's `SYSTEM_PATHS` allowlist, community plugins, docs, guides, and the muscle memory of thousands of users (`node scan.mjs`) all reference these paths. A cosmetic reorganization would break forks and plugins for no functional gain. The conventions that keep the flat root navigable: one script = one job, `*.test.mjs` sits next to what it tests, and every script is registered in `SYSTEM_PATHS` (enforced in CI by the coverage guard).

## Component map

The product surface is two modules. Internal names remain stable for existing
scripts and prompts:

1. **A — 机会搜寻与评估:** Discover/scan → Verify/Liveness → Pre-screen/Stage 0 → Evaluate/Stage 1 → Shortlist/Scored.
2. **B — 申请准备与投递:** Select → Prepare/Preparation Plan → Tailor/Reactive Resume → Review/Drafter-Reviewer → Verify/PDF-ATS → Submit (user only).

`pipeline` is the internal module-A orchestrator. `data/pipeline.md` is its
human-readable opportunity inbox/database, not the product-level workflow.

```
AI coding CLI  ─┐
(or scripts)    │  reads prompt files
                ▼
   modes/*.md  ──────────────►  the "brain": scoring, evaluation,
   (_shared.md = scoring core)   apply, scan, interview, etc. prompts
                │
   ┌────────────┼─────────────────────────────────────────────┐
   ▼            ▼                  ▼               ▼            ▼
 scan        evaluate          generate         track       update
 scan.mjs    oferta.md         PDFs/CVs/        data/        update-
 providers/  (+eval scripts)   cover letters    reports/     system.mjs
```

### Discovery — `scan.mjs` + `providers/`
Finds jobs from **open, no-auth public sources**. `scan.mjs` is zero-token: it calls public ATS APIs (Greenhouse, Ashby, Lever, BambooHR, Teamtailor, Workday, Breezy) and RSS/JSON boards via per-board modules in `providers/`. Auth-gated/login-required sources are intentionally out of core (they belong in the plugin layer). Results land in `data/pipeline.md`.

### Evaluation — `modes/oferta.md` + `modes/_shared.md`
The heart of the tool. `oferta.md` defines the A–H evaluation blocks (H is conditional, on scores of 4.5 and above); `_shared.md` defines the 1–5 scoring system, archetype detection, posting-legitimacy signals, and global rules. The AI reads these plus your `cv.md` and produces a structured report.

**Standalone evaluators** let you run the same scoring without an interactive CLI, against cheaper/local models: `gemini-eval.mjs` (Google free tier), `ollama-eval.mjs` (fully local), and `openai-eval.mjs` (any OpenAI-compatible endpoint).

### Application preparation — PDFs, CVs, cover letters
`generate-pdf.mjs` (Playwright HTML→PDF), `generate-latex.mjs` / `build-cv-latex.mjs`, `generate-cover-letter.mjs`. ATS-safe templates live in `templates/` and `fonts/`.

### Tracking — `data/` + `reports/` + tracker scripts
Every evaluated offer is registered. `data/applications.md` is the canonical tracker table; `reports/{NNN}-{company}-{date}.md` holds full evaluations. `tracker.mjs`, `merge-tracker.mjs`, `dedup-tracker.mjs`, `normalize-statuses.mjs` keep it consistent (atomic writes + a SQLite index). Report numbers are claimed atomically via `reserve-report-num.mjs`.

### Liveness — 岗位存活核验
`node check-liveness.mjs` 默认只读检查 Pending 和 Scored，复用 `liveness-*.mjs` 的公共 API / Playwright 检测链。过期条目退出可选池；待确认保留原状态；已评分且仍有效的岗位不重复评估。

### Self-update — `update-system.mjs`
Safely pulls new system files from upstream without touching user data. It backs up, fetches, re-execs the target updater (resolving its import closure so a new import can't break the upgrade), then checks out only `SYSTEM_PATHS`. `BOOTSTRAP_PATHS` covers very old installs.

### Multi-CLI entry files
Each CLI reads its own entry file, all of which point at the canonical `AGENTS.md`: `CLAUDE.md` (full), and thin `@AGENTS.md` redirect wrappers `OPENCODE.md`, `CODEX.md`, `GEMINI.md`, plus the `.agents/skills/` skill entrypoints. This is the [open agent skill standard](https://agentskills.io).

## Data flow (a typical run)

```
Discover/scan → Verify/Liveness → Pre-screen/Stage 0 → Evaluate/Stage 1
       │                                                     │
       └──────── data/pipeline.md inbox/database ─────→ Shortlist/Scored
                                                              │ user selects
                                                              ▼
Select → Prepare → Tailor → Review → Verify/PDF-ATS → Submit (user only)
```

## Quality gates

- `test-all.mjs` — the full suite (500+ checks across scoring, scan, tracker, PDF, security, updater).
- `updater-migration-tests.mjs` — enforces the system/user boundary and safe cross-version upgrades.
- CI: `test` + CodeQL are required; CodeRabbit reviews every PR; Renovate keeps deps current.

## Where to start reading

- The boundary → `DATA_CONTRACT.md`
- The scoring → `modes/_shared.md` + `modes/oferta.md`
- Adding a job source → [`providers/README.md`](providers/README.md)
- The updater → `update-system.mjs`
