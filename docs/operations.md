# Local operations

Install dependencies with `uv sync --locked` and `npm ci`. The root `.venv`
is the Career Ops Python environment. Run `.venv/bin/python -B -m career_ops
--help`; each command has its own `--help`.

| Command | Purpose |
| --- | --- |
| `discover [global]` | Collect configured sources or sweep public ATS directories |
| `evaluate ID` | Scan and score a retained opportunity |
| `apply` | Prepare materials; record confirmed events, replies and salary; communication and prefill |
| `interview` | Preparation plans, skill gaps, stories and durable sessions |
| `cv` | Preview, confirm, recover and check candidate facts |
| `show ID` | Show an opportunity and its retained results |
| `list --view VIEW` | Opportunities (default), scores, decisions, applications or followups |
| `insights` | Aggregate retained evidence |
| `task` | Start explicit inputs; inspect, resume, run and cancel tasks |
| `dashboard` | Local page of scanned, scored and applied jobs; its only writes start `apply prepare` or a re-score of the retained JD (`--port`, default 8765) |
| `system` | Doctor, portal maintenance, liveness, company resolution, advance and notify |

Daily commands derive inputs from the opportunity ID:

```bash
.venv/bin/python -B -m career_ops list
.venv/bin/python -B -m career_ops evaluate 123
.venv/bin/python -B -m career_ops apply prepare 123
.venv/bin/python -B -m career_ops interview preparation-plan 123
.venv/bin/python -B -m career_ops interview jd-skill-gap 123
.venv/bin/python -B -m career_ops task show TASK_ID
.venv/bin/python -B -m career_ops task resume TASK_ID --decision confirm
```

Use `task start scan|score|apply ID INPUT` for explicit input imports. Business
commands emit JSON by default. Put global sweep options after `discover global`.
`discover --throttle MS` takes milliseconds; zero disables the delay.
`system resolve-company` previews by default; `--write` and `--dry-run` cannot
be combined. Application events retain confirmation, source attribution and
idempotency requirements; preparing materials never records submission.

`--directory PATH` before the command selects the business store directory;
its default is `data/`. Interview context maps it to `opportunities.db`.
Read-only file tools do not use a business directory. Application preparation
never submits an application. New model calls and external sends require the
appropriate user authorization.

Personal data belongs in `inputs/`: `cv.md`, `profile.yml`, `targeting.md`,
`portals.yml`, `voice.md`, optional `article-digest.md`, `documents/`, `stories/`,
and `writing-samples/`. Copy example profile and fact constraints from
`docs/examples/` when setting up a fresh checkout; copy `portals.yml` there
to `inputs/portals.yml` for source configuration. `CAREER_OPS_INPUT_ROOT` may
select another input directory. Its sibling `rules/` holds scoring and workflow
policies. Inherited environment settings take priority over `.env`.

`rules/scoring.md`, domain policies, shared contract, and market rules retain
their existing bytes. Their historical path and command labels are stable
source labels in persisted inputs, not executable entrypoints. The context
manifest is also preserved as a record of those labels. Use this document and
the agent router for current command paths; editing frozen policies intentionally
invalidates affected results and waiting confirmations.

`data/opportunities.db` owns business facts, including CV task previews and
confirmations. `workflow-checkpoints.db` owns scan/score/apply/interview/delivery
execution progress; `cv-checkpoints.db` owns CV preview progress. Completed
business commits remain idempotent even if a process stops before checkpoint
save. CV file application verifies the confirmed preview, locks updates, and
recovers the same task after interruption.

Reports, captured sources, frozen payloads, PDFs, package manifests, and stored
absolute artifact references retain their existing physical locations and bytes.
They are not moved into a cosmetic new layout. Historical working directories
remain where referenced by checkpoint state or manifests. New operation paths
must not overwrite those artifacts.

Hermes invokes `scripts/career-ops-scan.sh` and `scripts/career-ops-score.sh`;
installed copies under `~/.hermes/scripts/` must match. Scan collects discovery;
score advances existing evaluation tasks and uses the previously authorized
notification policy. Check `system doctor --json` and the offline suite before enabling
changed wrappers. Neither doctor nor offline fixtures send candidate data.

`evaluate ID` and `system advance` trace one opportunity as `job-evaluation`,
with `prescreen` and `score` stages under the same root. A scheduled run continues
from a completed prescreen into scoring; exclusions or waiting conditions stop it.
The persisted task module `scan` identifies the prescreen stage and retains its
existing checkpoint and evidence keys. Batch source collection is `discovery`.

Model calls run inside the LangGraph nodes with settings from `.env`. When the
Langfuse settings are present, every top-level graph run becomes one trace in the
local Langfuse (`~/dev/langfuse`, http://localhost:3001) with full node inputs,
outputs and model prompts; nested scan/score/apply graphs appear inside their
task's trace. `scripts/check.py` disables tracing; an offline Langfuse never
blocks a workflow.

JD capture cache lives at `data/cache/scan-jds/` and is reused for at most 24 hours.
Retained source evidence belongs to the business store and referenced artifacts.
Unreferenced acceptance output, expired captures and old tracker-import batches
are removed without an archive.

The isolated four-dimension Jev entrypoint reads
`rules/evaluation/four-dimension.md` directly:

```bash
.venv/bin/python -B scripts/experiments/jev-score.py --input FROZEN_CASES.json --output NEW_EXPERIMENT_DIR --check
.venv/bin/python -B scripts/experiments/jev-score.py --input FROZEN_CASES.json --output NEW_EXPERIMENT_DIR
```

Cases contain a safe unique `id`, `sample_type` (`real_retained` or
`controlled_probe`), and frozen `evidence`; source selection and baseline
metadata may be retained locally. The API receives only the rubric, evidence,
and eight questions. Exclude generic-market compensation from the evidence
before calling. `--check` freezes requests without network access. The live run
uses the existing `.env` `TYPESAFE_API_KEY` and Jev 1.13.0 API protocol, keeps
raw responses and failed attempts, and resumes only identical inputs. Results
preserve decimal scores, original confidence and independent sufficiency;
recommendation uses the four dimension scores. This does not change production
evaluation, notifications, the business store or scheduling.

Company reuse is tested through a separate isolated entrypoint:

Formal scoring uses the same `career_ops/evaluation/company_pipeline.py`, `adaptive_research.py`
and `jev.py` modules. Run `.venv/bin/python -B -m career_ops task start score ID scan:ID --re-evaluate`
to score a retained active JD through the complete pipeline. A public-only planning node declares exact employer,
region and grade scopes; absent grade remains unknown. Invalid scope formatting gets one model repair,
with every attempt retained; invalid plans never dispatch company research. Three main Agents research in parallel,
then each calls Jev as soon as its organized facts are ready. Only direction is evaluated per job.
Formal source/response archives live in `data/company-profiles`; SQLite persists reusable company ratings and
per-result job references in the publication transaction. Archives expire by Sunday (at most seven days),
and that same window is part of input validity. Existing results remain historical.
Reports and Dashboard preserve four raw fractional scores, confidence and independent sufficiency.
Initial recommendations use scores only: all four dimensions must have scores of at least 4 for `focus`.
Lower or missing scores are `deprioritize`; confirmed hard failures remain `discard`. Confidence and
evidence sufficiency remain visible but do not block recommendations or trigger extra model review.
Three independent owned tool loops perform research with retained model history, tool caches and full provider bodies.
Cumulative model tokens and score-stage elapsed time have no hard cap. Research, retries and document-summary calls
retain usage. Each dimension has 60 conservative Tavily credits; exhausted allowance stops new network dispatch
and preserves facts for main-Agent organization. Single requests retain timeouts and finite transient retries.
Each retrieved document is frozen and immediately summarized by its dimension's model into a few useful facts,
each one or two sentences. Only facts, source pointers and operational status enter subsequent research turns. Successful document
summaries are reused on duplicate retrieval and resume; original bodies remain archived for review. The main Agent
organizes these facts directly for its independent Jev request. All document-summary calls count toward usage.
The stateless reader may stop a document whose explicit heading identifies another employer as its subject.
The target company cannot be filtered as another employer; uncertain or mixed documents continue. Source-subject
labels are model judgments, and original bodies remain available to inspect possible relevance mistakes.
Prompts prioritize applicable recent evidence, independent source families and unresolved gaps, skipping unrelated seeds.
Large summary inputs use 16K batches/32K merges and at most one JSON/length repair, with the configured native
output ceiling (currently 32768). Failed owned research resumes from saved messages and caches without repeating
successful network calls. Existing unexpired company archives remain reusable.

The following isolated CLI uses the same implementation with an experiment-only store:

```bash
.venv/bin/python -B scripts/experiments/company-score.py --input COMPANY_JOB_BUNDLE.json --store data/experiments/company-profiles --output NEW_RUN_DIR --check
.venv/bin/python -B scripts/experiments/company-score.py --input COMPANY_JOB_BUNDLE.json --store data/experiments/company-profiles --output NEW_RUN_DIR
.venv/bin/python -B scripts/experiments/adaptive-research.py --company-input PUBLIC_COMPANY_SCOPES.json --output NEW_COMPANY_RESEARCH_DIR
```

The input has `companies` and `jobs`. Each company declares `company_id`, `name`,
`identity_url`, `scopes` (dimension/scope pairs), `seed_urls` and `valid_until`;
jobs declare their public posting and exact company/scope references. No prepared
profiles or manual factual summaries are required. `--check` validates this public
input without running research or scoring. A live run collects missing company
scopes through three parallel independent dimension agents. Each agent collects
only its own company, culture or compensation topics and produces its own JSON-mode
LLM summary; the main process merges their profiles without another LLM summary. Summary-stage reasoning
is fixed to `low` (collection keeps its configured effort). Usable JSON, declared
company/profile scope and factual-field structure are checked before programs build
Jev profiles. Summaries retain source URLs or IDs for review alongside frozen original
responses and bodies; text equality, offsets and hash integrity are not acceptance gates.
Invalid fact profiles remain pending. A later CLI attempt resumes main-Agent research and document
summaries from retained material without fallback scoring.

Each dimension runs its own owned research loop and summary pipeline with cumulative model tokens and score-stage
time uncapped. The 60-credit Tavily allowance is per dimension, including multiple compensation scopes.
Search exhaustion prevents new network dispatch but leaves facts available for the main Agent to organize.
All research calls, retries and summaries retain usage; unknown usage is reserved conservatively and is not a bill.
Document summaries retain publication dates, applicability, source IDs and URLs.
Full provider-returned bodies, raw messages, summary responses and usage remain in
the isolated store. Valid exact scopes reuse archived summaries and ratings, including
for new jobs. New scopes collect only missing ranges; expiry or `--refresh` triggers
collection. Scoring rubric changes reevaluate Jev only; summary-rule changes reuse
frozen sources for renewed main-Agent research and organization. Old archives and failed summaries remain visible.
No effective per-scope validity can be silently extended by changing an input date.

Each dimension invokes its own Jev request as soon as its summary is ready; multiple
compensation scopes stay in one request with separate score/Noul questions. One failed
dimension does not delay scoring the others. Cache and raw failures are independent,
and final aggregation does not retry failed company requests. Company requests contain no JD; job requests evaluate direction, plus compensation
only for an explicit job quotation. Every rating retains its original request/response
and summary provenance. Unknown scopes remain pending. Each output directory is new.
`--company-input` is a standalone public collection check accepting identity, scopes and seed URLs;
it researches one company across the requested scopes without a job or candidate
payload or personal salary thresholds. Only the public research checklist is sent
to research providers; the scoring rubric remains in the authorized Jev scoring
requests. The validity dates are experiment inputs, not a production refresh policy.

Company research uses three parallel main Agents, one per shared dimension. Each has only
`collect_facts(query, urls)`: a fixed retrieval Agent executes the specified Tavily query/URLs,
then a stateless source-summary Agent extracts brief scoped facts without scoring instructions.
Only the main Agent decides follow-up research, consolidates facts and stops. Its final fact
profiles go directly to the dimension's Jev request. Unsuccessful searches do not establish
absence; unsupported denials are excluded. The shared allowance remains 60 conservative
Tavily credits per dimension, with no cumulative token or aggregate-time cap.
Every formal score attempt retains actual LLM request counts, per-attempt latency and reported
usage in its draft `model-calls/`; dimension ledgers count `collect_facts` invocations separately
from source-summary LLMs, Tavily and Jev requests. Missing provider usage remains unknown.

单篇长文分片摘要时，摘要 Agent 可基于明确文档标题声明其制度或年报属于其他雇主；首片没有目标公司相关事实时不再摘要该文剩余片段，完整 provider 正文仍保留供审阅。混合或未知归属、仅首片无事实均不触发此处理。该判断只辨认来源主体，不是制度不存在的事实，不新增搜索或评分自主性。
