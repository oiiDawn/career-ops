# OII-397 DeepAgents migration — 2026-10-09

## Implemented behavior

The formal company research path now uses `deepagents==0.7.23` / `langchain==1.4.4`. Company, culture and compensation retain separate research contexts, summaries, Jev requests and reusable company archives. Direction remains job-specific.

Cumulative research and summary model tokens are uncapped. The score orchestration no longer has a total 900-second deadline. Individual provider timeouts, finite retries, native model output limits and a 10,000-step technical recursion guard remain. Tavily permits 60 conservative credits per dimension (previously 20); exhaustion blocks further network dispatch but preserves material for local reading and summary.

DeepAgents offloads large tool output, compacts context and saves SQLite checkpoints. Original model requests/responses, provider bodies, tool-returned ranges and evicted conversation history are retained. Resume binds the same public input and validity window. No exact summary/original matching or semantic hash gate was added.

Research models receive public company identity, applicability scopes and public source material. The previously authorized Jev endpoint receives rubric/private salary thresholds and public evidence. CV, candidate identity, contact details and candidate experience are excluded from company research and Jev.

## First live trial

A fresh isolated store runs Microsoft: global company, China culture, and China SDE2 software-engineering annual-total compensation. It uses the existing real job 9 and three existing seed URLs. It does not write business scores or promote its company profiles to production.

The first live process started with a 12K compaction trigger and 3K retained context. Observed repeated compaction/read cycles led to a 32K/6K final configuration and formatted tool-result JSON for readable offloads. Atomic ledger writes and per-dimension source-tool serialization were added after a concurrent ledger-read anomaly. The live process retains its initially imported configuration; final fixes are verified separately. The company process was paused after a repeated offload lookup/compaction loop and resumed from the same SQLite checkpoint, original public prompt/system, validity window and capture using the corrected 32K/6K configuration. Completed culture/compensation archives and Jev scores were reused. One interrupted in-flight model usage remains unknown and conservatively reserved. It is a mixed-configuration recovery trial, not an exact-final-configuration cold benchmark.

Research stages completed. Configured provider model was `deepseek-v4.1-flash`, research reasoning `xhigh`; compaction/structured summaries use `low`. No provider/model substitution was made.

| Dimension | Reported research tokens | Unknown reservation | Model attempts / compactions | Compaction reported tokens | Tavily conservative / reported credits | Captured/read bodies | Research seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| company | 935,694 | 41,334 | 68 / 26 | 400,282 | 11 / 7 | 4 / 4 | 2,297 |
| culture | 357,978 | 0 | 26 / 10 | 160,203 | 20 / 12 | 8 / 8 | 858 |
| compensation | 249,659 | 0 | 23 / 5 | 73,571 | 9 / 3 | 7 / 7 | 348 |

Total reported research usage: 1,543,331 tokens; unknown reservation: 41,334; 117 research/compaction model attempts. 41 compactions consumed 634,056 reported tokens (41.1% of research). 19 captured/read provider bodies across the three agents (some overlapping URLs). All raw request/response counts reconcile with ledgers: culture 26/26, compensation 23/23, company 68/67 plus the interrupted request. The earlier concurrent JSON-read anomaly did not leave a settled ledger/raw-count mismatch.

The initial company summary failed after its one repair because `date:null` and object-valued applicability conflicted with the text-only contract. The prompt did not explicitly declare field types, and repair feedback omitted the actual validation failure. Commit `f000d17e` makes types explicit and returns specific field errors to the model. Tests reproduce unknown-date repair. The pipeline regenerated summaries from retained material without another research run or Tavily dispatch.

| Summary phase | Company tokens / calls | Culture tokens / calls | Compensation tokens / calls |
| --- | ---: | ---: | ---: |
| Initial, including failed company summary | 57,224 / 4 | 63,819 / 5 | 26,630 / 3 |
| Corrected contract, source reuse | 78,518 / 5 | 38,460 / 4 | 30,049 / 4 |

Total summary usage across both phases: 294,700 reported tokens / 25 calls. Total isolated trial research plus summaries: **1,838,031 reported tokens**, plus **41,334 unknown token reservations**. All 142 model attempts (including compaction and the interrupted call), 29 returned Tavily requests, and 6 new Jev HTTP calls are distinct counts. This accounting excludes the separate formal warm verification below. There were no provider failures reported by the captured research model calls; summary validation failures and the operational interruption are included.

Final isolated result: direction **4.98**, company **3.99**, culture **3.59**, compensation **4.45**; company version `scored`, recommendation **deprioritize**. Each of the three dimensions has a separate completed summary, Jev request and persisted rating. Direction reused its earlier completed request. Formatting clarification and re-summarization changed culture 3.49→3.59 and compensation 4.41→4.45 without new research, so these changes are not quality evidence.

A final warm run under the final implementation reused all three company archives and all four ratings: **0 new model calls, 0 Tavily dispatches, 0 Jev HTTP calls**, with 4 cached scoring units. Retained result files: `data/experiments/deepagents-migration-2026-10-09/summary-recovery/scores/results.json` and `.../warm/scores/results.json`. Usage reservations must not be presented as billed tokens. Tavily conservative reservations (40 total) and provider-reported credits (22 total) are distinct; no dollar estimate is asserted without actual provider billing.

Compensation completed with research usage 249,659 tokens, summary usage 26,630 tokens, 9 conservative / 3 reported Tavily credits and score 4.41. It still lacks an official applicable salary band, variable-pay guarantees, payout criteria, vesting terms, Beijing/Suzhou-specific figures and concrete offer data. More budget has not resolved these gaps.

Culture completed research with 357,978 tokens, initial summary usage 63,819 tokens (including one repaired structural-validation problem), 20 conservative / 12 reported Tavily credits and scored 3.49. These figures do not establish improved accuracy against the old system. Final culture evidence still lacks current China-specific net hours, rest-day policy, leave amounts, overtime policy and social-insurance/fund bases and rates; employee execution mainly comes from a 2020 Suzhou account. Company evidence still lacks dated/confirmed China layoff scale, management changes, stock reaction and complete regional engineering-investment data. Missing facts remain gaps, not silently assumed benefits.

The migration establishes functional headroom, independent recoverability and no-cost reuse after successful capture. It does **not** establish a favorable cold cost/time/accuracy trade-off: repeated early compaction dominated model cost, and substantially higher usage left important evidence gaps. The corrected 32K configuration has live checkpoint-continuation evidence and offline checks, but no complete fresh-company comparative benchmark. More Tavily allowance alone is not demonstrated necessary (each dimension stayed below the previous 20-credit conservative ceiling except culture, which reached it).

## Formal verification

Formal job 9 re-evaluation completed as task `8650618c-8e90-42a3-bd3d-66f44c1ff4b3`, and its `results.payload` was read back from SQLite. Scores: direction 4.97, company 4.07, culture 3.95, compensation 4.28; recommendation `deprioritize` because culture is below 4. This run reused three valid company archives; it verifies integration and publication, not fresh formal research quality. No evidence-sufficiency recommendation gate is used.

Offline checks exercise the real DeepAgents harness with deterministic models: offload/readback, compaction, interrupted checkpoint recovery without repeat network requests, completion reuse, independent ready-to-score dimensions, and uncapped accounting above 200K. Formal scoring, company preparation/summary, adaptive tool credit ceilings, model deadlines, CLI and recovery checks pass. `uv pip check` reports 77 compatible packages. Required syntax and workflow-scan checks pass.

## Operational state

Migration committed as `37968a22`. Score cron `9ff33a7a6d12` was resumed and `hermes cron list` verified it active alongside unchanged scan cron `504a0b3c252c`. No push or unrelated local changes are included. The summary-repair fix is `f000d17e`; this report captures the separate experiment evidence.
