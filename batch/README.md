# Batch Processing

Process multiple job offers in parallel via headless workers. Each worker runs canonical Stage 0 and, for survivors, writes a Stage 1 A-G report. CV/PDF/application/tracker artifacts wait for explicit per-role `Proceed`. See the **Headless / Batch Mode** table in `AGENTS.md` for the correct command per CLI.

## Quick Start

1. **Add offers** to `batch-input.tsv` (tab-separated: `id`, `url`, `source`, `notes`):

   ```tsv
   id	url	source	notes
   1	https://jobs.example.com/role-a	LinkedIn	
   2	https://greenhouse.io/company/role-b	Greenhouse	priority
   ```

2. **Dry run** to preview what will be processed:

   ```bash
   ./batch/batch-runner.sh --dry-run
   ```

3. **Run the batch**:

   ```bash
   ./batch/batch-runner.sh
   ```

4. **Results** remain in `batch-state.tsv` and `reports/` for the confirmation review. The runner does not mutate `data/applications.md` or create Stage 2 artifacts.

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--parallel N` | `1` | Number of concurrent headless workers |
| `--dry-run` | off | Preview pending offers without processing |
| `--retry-failed` | off | Only retry offers marked as `failed` in state |
| `--resume-paused` | off | Resume offers paused after a Claude session/rate limit |
| `--start-from N` | `0` | Skip offers with ID below N |
| `--limit N` | `0` | Max number of offers to process in this run (0 = no limit) |
| `--max-retries N` | `2` | Max retry attempts per offer before giving up |
| `--rate-limit-sleep N` | `300` | Seconds to wait before retrying a transient rate-limited worker; use `0` to pause the batch immediately |

## Directory Layout

```
batch/
  batch-runner.sh          # Orchestrator script
  batch-prompt.md          # Prompt template sent to each worker
  batch-input.tsv          # Input offers (you create this)
  batch-state.tsv          # Processing state (auto-managed, resumable)
  logs/                    # Per-offer worker logs ({report_num}-{id}.log)
```

## How It Works

1. **batch-runner.sh** reads `batch-input.tsv` and `batch-state.tsv` to determine which offers need processing.
2. For each pending offer, it launches a headless worker with `batch-prompt.md`; a temporary report-number reservation is released for Stage 0 failures.
3. Each worker runs/reuses `prescreen.mjs`. `fail` records an auditable skip; `incomplete` is retried; `pass`/`uncertain` produce a Stage 1 report with a confirmation checklist.
4. After all workers finish, review the reports and choose `Proceed`, `Reject`, or `Provide more evidence` per role. Only `Proceed` enables the existing Reactive Resume Stage 2 flow.

## Resumability

`batch-state.tsv` tracks the status of every offer (`pending`, `processing`, `completed`, `failed`, `skipped`, `rate_limited`, `paused_rate_limit`). If the batch is interrupted, re-running `batch-runner.sh` picks up where it left off -- completed offers are skipped automatically. `rate_limited` is a non-completed state used while the runner waits before retrying, so interrupted rate-limited jobs are eligible on the next normal run.

`paused_rate_limit` is different: it means a worker hit a Claude session/usage limit, so the runner stopped scheduling new offers and preserved the retry count. Resume those rows explicitly after the limit resets:

```bash
./batch/batch-runner.sh --resume-paused
```

A PID-based lock file (`batch-runner.pid`) prevents concurrent batch runs. If a previous run crashed, the stale lock is detected and removed automatically.

## Prerequisites

- Your CLI in PATH (see **Headless / Batch Mode** table in `AGENTS.md`)
- Node.js >= 18, Playwright chromium installed (`npm run doctor` to verify)
- `batch-input.tsv` with at least one offer
