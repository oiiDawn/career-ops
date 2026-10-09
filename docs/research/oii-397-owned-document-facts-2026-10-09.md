# OII-397 owned document-fact research — 2026-10-09

## Implemented slice

Commit `44e9b70b` restores the owned LangGraph tool loop and removes DeepAgents/langchain and 14 exclusive installed dependencies. `uv pip check` confirms 61 compatible packages. Existing valid company archives remain reusable; old partial engine checkpoints are not resumed by the new engine.

Each company/culture/compensation researcher reads only public company identity, its applicability scopes and public sources. Its extraction tool freezes a full provider-returned document, immediately invokes a fresh same-dimension summary context, then returns a few useful facts with source IDs/URLs. Claims are instructed to be one or two sentences. The next research turn receives fact cards, not the document body. Failed document summaries retain bodies and usage but never fall back to returning raw bodies. Successful source digests are reused across duplicate retrieval and interrupted resume, including a durable digest completed before its parent checkpoint.

Research and summaries have no cumulative token cap or total deadline. Each dimension retains 60 conservative Tavily credits; all calls, retries and repairs count. Native 32768 output limits, per-request timeouts and finite retries remain. No semantic summary/original equality or hash-integrity acceptance gate was added. Source identifiers/cache fingerprints remain bookkeeping.

Direction is per job; company profiles and independent Jev ratings remain per company and exact applicability scope. The main researcher currently has two tools (search and extraction), and a final dimension LLM summary still precedes Jev. This is **not yet** the later proposed single research-tool Agent → stateless source summarizer → all facts directly to Jev architecture.

## Matched public-company experiments

Both isolated stores use the retained real Microsoft job 9, global company, China culture, and China SDE2 software-engineering annual-total compensation scoped to Beijing/Shanghai/Suzhou. No business SQLite scores were written or experimental archives promoted. The configured model remains `deepseek-v4.1-flash`; research uses configured `xhigh`, structured summaries request `low`.

The baseline restores the owned loop with improved research prompts but carries retrieved source sections in history. The treatment immediately compresses each document. These are exploratory runs on one company with different retrieved evidence, not a controlled accuracy benchmark. The live treatment used the initial fact-loop build; the unused extraction argument removal and durable-digest recovery improvements were verified offline afterward. Each run retains its frozen rubric; numeric scoring criteria were not redesigned for this comparison.

| Dimension | Baseline reported tokens | Document-fact reported tokens | Baseline calls → main/document/final calls | Complete dimension minutes, baseline → treatment | Provider bodies, baseline → treatment | Document fact cards | Treatment Tavily conservative / reported credits |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| company | 263,783 | 424,812 | 11 → 8/17/3 | 8.7 → 28.7 | 5 → 15 | 69 | 27 / 16 |
| culture | 691,192 | 349,989 | 17 → 8/8/1 | 12.6 → 13.8 | 13 → 8 | 31 | 25 / 17 |
| compensation | 978,830 | 635,789 | 21 → 13/20/1 | 14.4 → 18.6 | 11 → 12 | 29 | 35 / 19 |

Baseline: **1,933,805 reported tokens / 51 model attempts / 75 Tavily dispatches / 4 new Jev requests**. Treatment: **1,410,590 reported tokens / 79 model attempts / 71 Tavily dispatches / 4 new Jev requests**, with 35 provider bodies and 129 document fact cards. Model tokens fell **27.1%**, attempts rose **54.9%**, and completion time for the slowest dimension rose **14.4 → 28.7 minutes**. No unknown usage remains in either completed run. Tokens include both input and output; cache pricing/provider billing are unavailable, so these are not dollar-cost savings.

Company captures increased from 5 to 15, with more dated management/layoff/market coverage. Culture tokens fell 49.4%, but duration rose 12.6 → 13.8 minutes. Compensation tokens fell 35.0%, but duration rose 14.4 → 18.6 minutes. Sequential document summary/merge calls and the retained final summary explain why smaller research context does not guarantee faster completion. Company final summary alone made three calls using 88,930 reported tokens after research ended.

Result: direction **4.97** (confidence 0.98, sufficiency 0.85); company **3.46** (confidence 0.48, sufficiency 0.49); culture **4.16** (confidence 0.50, sufficiency 0.19); compensation **4.22** (confidence 0.65, sufficiency 0.14). Recommendation **deprioritize**. Jev confidence describes score-distribution concentration; evidence sufficiency remains informational and does not gate recommendation.

The final-build warm run used the cold run's frozen rubric and exact store/scopes: **0 new LLM calls, 0 Tavily dispatches, 0 Jev HTTP calls**, 4 cached scoring units. Evidence stages were cached and new per-agent logs recorded zero usage. This verifies reuse, not cold research quality.

## Quality review and architectural findings

Compensation source facts contain China-wide and Beijing/Shanghai SDE2 crowd-sourced annual benchmarks and components, plus third-party bonus/performance descriptions. They do not establish a concrete offer, official city/grade salary band, guaranteed variable pay or applicable vesting contract. Suzhou numeric data remains absent from the captured source material. Culture relies partly on 2015/2020/2021 recollections and role-specific postings; current China net hours, rest-day policy, official leave rules and insurance/fund bases/rates remain unresolved. An empty extracted dynamic table is not proof that its website contains no salary data.

Final compensation summary has an observable contradiction: facts include Beijing/Shanghai base/stock/bonus breakdowns, while gaps say no such breakdown is provided for the requested cities. The generated artifact is retained unchanged. This is a final-summary failure, not evidence that more sources or higher scores improve accuracy. Removing the second LLM summarization would eliminate this error stage, while source-summary omissions/errors and conflicting source claims would remain reviewable risks.

Search responses still accumulate in the main research history: culture's eighth/last research call used **62,667 input tokens** even though full documents were compressed. A focused research-tool Agent could keep search results and navigation history in its own fresh task context, returning only facts and provenance. The main dimension Agent should manage overall gaps and convergence; the tool Agent should handle only its assigned information task. All tool invocations must share the dimension's source caches and 60-credit allowance. Document summaries need scope/date information but no personal scoring thresholds or candidate materials. Fact arrays should be persisted and programmatically collected for Jev; document-specific missing fields must not become company-wide absence claims. The three-layer proposal has not been benchmarked in this slice.

## Discarded source-index experiment and full-turn accounting

A targeted compensation source-index variant was superseded by the user's immediate-document-summary clarification. Its research finished; the process was terminated during final summary. Retained accounting: **407,988 research + 4,715 returned summary = 412,703 reported tokens**, plus **48,767 unknown in-flight reservation**; 17 model attempts (one usage unknown), 19 Tavily dispatches, 23 conservative / 13 reported credits, no Jev request. Its incomplete result is not compared as a completed trial or billed at the reservation.

All paid isolated work in this slice: **3,757,098 reported model tokens + 48,767 unknown reservation; 147 model attempts, 165 Tavily dispatches, 8 new Jev requests**. Conservative Tavily credits total 205; provider-reported credits total 130. Earlier DeepAgents experiments and offline deterministic checks are excluded from these totals.

The prior mixed-configuration DeepAgents trial used 1,838,031 reported tokens + 41,334 unknown reservation / 142 attempts, including 41 compactions consuming 634,056 research tokens. It did not establish an accuracy benefit sufficient to justify the extra framework. Its recovery/configuration differences prevent a clean wall-time comparison.

## Verification and operations

Passed: owned document-fact recovery (no body in next research requests, usage beyond 200K, duplicate/durable digest reuse, failed-summary isolation); tool credit/cache checks; independent company pipeline and scope persistence; formal cold scoring, warm company reuse and resume; summary batching/types/repair; workflow recovery; model deadline; CLI. Required `node scripts/check-syntax.mjs` checked 233 files; workflow-scan passed. `git diff --check` passed.

Score cron `9ff33a7a6d12` was resumed and verified active alongside scan `504a0b3c252c`. No push. Unrelated local `scripts/experiments/jev-score.py` changes and the upstream-migration assessment were preserved.

Retained artifacts: `data/experiments/owned-research-tuning-2026-10-09/company-profiles`, `cold`, `fact-company-profiles`, `fact-cold`, `fact-warm`, and incomplete `context-company-profiles`. Source bodies, every model/provider request and response, summaries, usage and scores remain available for review. Company research receives no CV, identity, contact or candidate experience. Only the previously authorized Jev destination receives private scoring standards and public evidence; this report contains no private salary thresholds.
