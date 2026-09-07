# Architecture

This file describes the runtime flows. Design principles and the
system/user data-contract layers live in [../ARCHITECTURE.md](../ARCHITECTURE.md).

## System Overview

The user-facing system has two modules:

- **A — 机会搜寻与评估:** Discover/scan → Verify/Liveness → Pre-screen/Stage 0 → Evaluate/Stage 1 → Shortlist/Scored.
- **B — 申请准备与投递:** Select → Prepare/Preparation Plan → Tailor/Reactive Resume → Review/Drafter-Reviewer → Verify/PDF-ATS → Submit (user only).

`pipeline` is module A's internal orchestrator. `data/pipeline.md` is its
opportunity inbox/database. Stage 1 publishes Scored roles and stops; only a
later user selection starts Stage 2.

```
                    ┌─────────────────────────────────┐
                    │         AI Coding CLI Agent      │
                    │   (reads AGENTS.md + modes/*.md) │
                    └──────────┬──────────────────────┘
                               │
            ┌──────────────────┼──────────────────────┐
            │                  │                       │
     ┌──────▼──────┐   ┌──────▼──────┐   ┌───────────▼────────┐
     │ Single Eval  │   │ Portal Scan │   │   Batch Process    │
     │ (auto-pipe)  │   │  (scan.md)  │   │   (batch-runner)   │
     └──────┬──────┘   └──────┬──────┘   └───────────┬────────┘
            │                  │                       │
            │           ┌──────▼──────┐          ┌────▼─────┐
            │           │ pipeline.md │          │ N workers│
            │           │ (URL inbox) │          │ (headless)
            │           └─────────────┘          └────┬─────┘
            │                                          │
     ┌──────▼──────────────────────────────────────────▼──────┐
     │             Stage 0 + Stage 1 → Scored                 │
     │  ┌──────────────┐  ┌────────────┐  ┌───────────────┐  │
     │  │ Prescreen JSON│  │ Report.md  │  │ Confirmation  │  │
     │  │ + hash/cache  │  │ (A-G eval)│  │ eval checklist│  │
     │  └──────────────┘  └────────────┘  └───────────────┘  │
     └────────────────────────────────────────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │  data/applications.md │
                    │  (canonical tracker)  │
                    └──────────────────────┘
```

## Evaluation Flow (Single Offer)

1. **Input**: User pastes JD text or URL
2. **Extract**: Playwright/WebFetch extracts JD from URL
3. **Classify**: Detect archetype (1 of 6 types)
4. **Evaluate**: 7 blocks (A-G):
   - A: Role summary
   - B: CV match (gaps + mitigation)
   - C: Level strategy
   - D: Comp research (WebSearch)
   - E: CV personalization plan
   - F: Interview prep (STAR stories)
   - G: Posting legitimacy (scam / ghost-job signals)
5. **Score**: Weighted average across 5 dimensions (1-5)
6. **Report**: Save as `reports/{num}-{company}-{date}.md`
7. **Shortlist**: Publish the role as Scored and stop
8. **Stage 2**: After the user selects the role and invokes application preparation, build the plan and bundle; Reactive Resume remains the CV backend

## Batch Processing

The batch system processes multiple offers in parallel:

```
batch-input.tsv    →  batch-runner.sh  →  N × headless CLI workers
(id, url, source)     (orchestrator)       (self-contained prompt)
                           │
                    batch-state.tsv
                    (tracks progress)
```

Each worker is a headless AI CLI instance — the bundled `batch-runner.sh` currently runs `claude -p` workers only. See the Headless / Batch Mode table in `AGENTS.md`. Workers produce a canonical Stage 0 result and, for `pass`/`uncertain`, a Stage 1 report. They never produce Stage 2 artifacts; the user starts that module later for one selected Scored role.

The orchestrator manages parallelism, state, retries, and resume.

## Data Flow

```
cv.md                    →  Evaluation context
article-digest.md        →  Proof points for matching
config/profile.yml       →  Candidate identity
portals.yml              →  Scanner configuration
templates/states.yml     →  Canonical status values
templates/cv-template.html → PDF generation template
```

## File Naming Conventions

- Reports: `{###}-{company-slug}-{YYYY-MM-DD}.md` (3-digit zero-padded)
- User-invoked application bundles: `output/{report-company-role}/`

## Pipeline Integrity

Scripts maintain data consistency:

| Script | Purpose |
|--------|---------|
| `merge-tracker.mjs` | Merges batch TSV additions into applications.md |
| `verify-pipeline.mjs` | Health check: statuses, duplicates, links |
| `dedup-tracker.mjs` | Removes duplicate entries by company+role |
| `normalize-statuses.mjs` | Maps status aliases to canonical values |
| `cv-sync-check.mjs` | Validates setup consistency |

## Dashboard TUI

The `dashboard/` directory contains a standalone Go TUI application that visualizes the pipeline:

- Filter tabs: All, Evaluada, Aplicado, Entrevista, Top >=4, No Aplicar
- Sort modes: Score, Date, Company, Status
- Grouped/flat view
- Lazy-loaded report previews
- Inline status picker
