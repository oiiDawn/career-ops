# Codex public employer research experiment

Status: completed, including source review. This is a single-arm feasibility experiment, not a production migration or an A/B benchmark.

## Confirmed decisions

- Replace the research and summarization loop only for this isolated experiment. Do not run the current self-built baseline.
- Research uses public employer and job information only. Candidate preferences affect scoring, never research. No CV, private preferences, score rubric, existing research answers, or scores enter the research inputs.
- One Codex task researches company, culture, and compensation for each job. Codex selects sources and reading depth autonomously using live search; the old retrieval/summarization tool is not used.
- Use the existing ChatGPT CLI login, `gpt-6-astra`, medium reasoning, fresh isolated working directories, and no additional agents.
- Return the existing `profiles / facts / gaps / conflicts` structure. Every fact includes claim, date, kind, applicability, limitations, and an original source URL. Profile IDs in this experiment are the three dimension names; they are not production scope keys.
- Test Microsoft Software Engineer 2—M365 UIPilot (opportunity 9), NVIDIA Senior Performance Software Engineer—Deep Learning Libraries (24), and Climind Full-Stack Engineer (176). Preserve multi-location and unknown-level scope.
- Each job has a 15-minute external deadline covering all three dimensions. Preserve partial artifacts and label a timed-out task incomplete.
- The research phase makes no Jev calls. A separately authorized scoring follow-up is recorded below. Neither phase writes the business database or changes the production workflow.

## Assessment

Measure wall-clock time, completion, structural validity, reported token usage, observed tool events, and fact counts by dimension. Report subscription usage without inventing a currency cost. Missing provider usage stays unknown.

Check each material claim against its cited source, especially employer identity, region, grade, financial period, compensation components, and employer statements versus observed practice. Unknowns may be valid outcomes, but a sparse output is not automatically useful. Inspect missing research coverage separately from false statements.

There is no relative speedup threshold because the user removed the baseline. The cancelled historical Microsoft diagnostic is context only. Three samples cannot establish stable latency or broad reliability.

## Artifacts

Frozen public inputs, prompts, schema, command arguments, raw JSONL events, stderr, final fact arrays, and timing/usage metrics are retained under `data/experiments/codex-research-2026-10-09/`. The retained `run.py` runs one sample and refuses to overwrite a completed attempt.

The first Microsoft startup failed before model execution because the outer filesystem sandbox prevented CLI initialization. Its artifacts are retained under `microsoft/startup-attempt-1/`; the approved retry permits CLI initialization while the inner research task retains a read-only sandbox.

## Results

All three runs completed within two minutes, produced valid fact arrays, and used only web tools in their observed execution events. No research output was edited after generation. Times cover research execution, including CLI startup, but exclude the supervising agent's subsequent citation audit.

| Sample | Seconds | Company facts | Culture facts | Compensation facts | Web tool invocations |
| --- | ---: | ---: | ---: | ---: | ---: |
| Microsoft | 116.97 | 4 | 5 | 3 | 5 |
| NVIDIA | 94.91 | 4 | 4 | 2 | 4 |
| Climind | 110.63 | 4 | 2 | 0 | 6 |

Combined research execution: 322.50 seconds; median: 110.63 seconds. A web invocation may batch several searches or page operations and is not an individual HTTP request or billable credit.

### Usage

| Sample | Input tokens, including cached | Cached subset | Uncached input | Output tokens |
| --- | ---: | ---: | ---: | ---: |
| Microsoft | 247,918 | 183,680 | 64,238 | 3,068 |
| NVIDIA | 188,716 | 131,968 | 56,748 | 2,699 |
| Climind | 320,610 | 248,064 | 72,546 | 2,518 |
| Total | 757,244 | 563,712 | 193,532 | 8,285 |

The CLI reported these aggregate token counts. Repeated context contributes to input usage; cached input is not added again. No invoice or currency cost was available from the existing ChatGPT login, and per-model-request counts were not exposed in the retained events. Fast completion did not mean negligible token consumption.

### Citation and quality review

The supervising agent reviewed all 28 fact entries. Twenty-seven were supported as attributed by reopened original sources or the frozen public JD; one was supported by indexed homepage text only. No major factual error was observed in this sample. This is source-support review, not independent verification of company marketing, anonymous employee reports, or every fact available on the web. Recall was not measured.

- Microsoft: financial amounts, China pay components and dated Suzhou employee statements matched the sources. One minor scope omission: the US return-to-office statement says employees near Puget Sound, omitting the original 50-mile threshold. The output correctly prevents applying that US rule to China. The 61/62 pay entries remain reference levels, not established grade mappings for this opening. Sources: [financial release](https://www.microsoft.com/en-us/investor/earnings/fy-2026-q4/press-release-webcast), [China salary table](https://www.levels.fyi/companies/microsoft/salaries/software-engineer/locations/china), [Suzhou reviews](https://www.glassdoor.co.in/Reviews/Microsoft-Suzhou-Jiangsu-Reviews-EI_IE1651.0,9_IL.10,24_IC2677883.htm), [office policy](https://blogs.microsoft.com/blog/2025/09/09/flexible-work-update/).
- NVIDIA: financial amounts and pay components matched; conflicting overtime accounts were retained as unverified secondhand statements. Culture evidence includes an old internship account and unspecified departments, so current team practice remains unresolved. IC3/IC4 figures are not the job's confirmed grade or offer. Sources: [quarterly report](https://investor.nvidia.com/files/doc_financials/2027/NVDA-2027-Q2-10Q-Final-including-exhibits.pdf), [China salary table](https://www.levels.fyi/en-gb/companies/nvidia/salaries/software-engineer/locations/china), [employee account](https://www.indeed.com/cmp/Nvidia/reviews?fcountry=CN&ftopic=wlbalance), [overtime discussion](https://linux.do/t/topic/924737).
- Climind: institutional profiles and job descriptions supported the claims, and the older posting's Shenzhen/Hong Kong location conflict was correctly kept separate from the target job. Compensation was left empty rather than filled with another employer's pay or an unsupported denial. The homepage fact has a provenance weakness: direct web open returned zero lines and direct HTML was a JavaScript shell; independently retrieved search-index text supported the statement, but the output did not label it as indexed evidence. Culture consists of employer statements, not independently observed employee experience. Sources: [homepage](https://www.climind.co/), [InvestHK case study](https://www.startmeup.hk/case-studies/climinda-climate-ripe-for-innovation/), [university profile](https://kto.hkbu.edu.hk/content/dam/kto-assets/our-services/entrepreneurship/start-up-profiles/booklet/hkbu-startup-booklet-en.pdf), [older posting](https://hk.linkedin.com/jobs/view/software-engineer-fullstack-at-climind-4339966841).

Per-fact audit outcomes and scope caveats are in each sample's `citation-audit.json`. Raw outputs remain unchanged in `facts.json`; aggregate measurements and hashes are in `summary.json`.

### Interpretation

This experiment supports using Codex as a candidate replacement for the research loop: all three jobs yielded structured, source-linked findings in 95–117 seconds, with useful uncertainty handling. It does not establish a causal speedup, superior recall, unattended reliability, or lower monetary cost compared with the current implementation.

Before production integration, the remaining concrete gap is evidence retention: the CLI JSONL preserves tool metadata and source references/snippets, not complete immutable source bodies. A source URL and valid JSON alone do not establish that original page content was acquired. Preserve that distinction when connecting results to existing evidence storage and scoring; do not pass reference-level salary figures as verified job-level offers. Candidate preferences remain exclusively in scoring.

## Facts-to-Jev follow-up

The user explicitly authorized sending the three employers' public facts and the complete existing rubric, including personal preferences, to `https://api.typesafe.ai/v1/systemone` for eight dimension calls and three independent culture repeats. The retained runner and all requests/responses are under `data/experiments/codex-research-2026-10-09/jev/`. Research was not rerun. Jev used `jev-1.13.0` and the frozen `first/rubric.md`.

The adapter reused `summary_profiles`, `company_request`, `evaluate`, and the existing Jev transport/validation. It mapped experimental dimension IDs to explicit scope keys without changing any facts, gaps, conflicts or source URLs. Research provenance hashes refer to the actual Codex prompt/schema and original output, not the previous research implementation. Region scopes preserve the target locations; unknown corporate grades remain unknown, with the public role title retained. These declared target scopes do not establish that every fact applies to them. All stores are isolated; no production database or dashboard publication was tested.

All 11 calls succeeded on their first HTTP attempt. The initial eight calls took 6.17 seconds in aggregate; the three repeats took 2.22 seconds, for 8.39 seconds of recorded call time. Replaying the identical bundle reused all eight profiles with zero HTTP attempts and identical retained ratings. Empty Climind compensation facts produced no profile and no Jev call. A company status of `scored` means its supplied profiles were scored, not that all three dimensions are available.

| Employer | Dimension | Score, 1–5 | Raw confidence | Evidence sufficiency |
| --- | --- | ---: | ---: | ---: |
| Microsoft | company | 4.22 | 0.64 | 0.32 |
| Microsoft | culture | 2.82 | 0.52 | 0.14 |
| Microsoft | compensation | 4.21 | 0.69 | 0.17 |
| NVIDIA | company | 4.40 | 0.52 | 0.36 |
| NVIDIA | culture | 3.20 | 0.56 | 0.12 |
| NVIDIA | compensation | 4.18 | 0.59 | 0.14 |
| Climind | company | 2.97 | 0.93 | 0.07 |
| Climind | culture | 3.05 | 0.51 | 0.09 |

Independent culture repeats returned Microsoft 2.87, NVIDIA 3.23, and Climind 3.00: absolute changes of 0.05, 0.03, and 0.05. Their sufficiency values stayed at 0.14, 0.12, and 0.09. One repeat per employer demonstrates only this sample's small variation, not general repeatability or correctness.

The transport and evidence-preservation checks passed, but scoring quality is not established. All eight sufficiency values are low (0.07–0.36); no pass threshold is introduced. In particular, Climind company confidence 0.93 coexists with sufficiency 0.07, and Microsoft compensation scores 4.21 despite uncertain grade applicability and sufficiency 0.17. The numerical culture results around 3 must not be interpreted as evidence of ordinary working conditions. The API returns distributions and sufficiency, not an explanatory rationale; the exact causes of each number cannot be inferred from the response alone.

The research prompt also omits explicit coverage of several current rubric topics, including actual weekly hours, paid leave and local social-insurance/housing-fund terms. The original source audit established claim support, not enough coverage to score confidently. Extend the public research checklist using objective evidence questions, without exposing private preference thresholds, before claiming useful scoring quality. Preserve the current raw scores and uncertainty; do not invent corrections or silently change recommendation policy.

An existing rubric inconsistency remains outside this experiment: its opening paragraph recommends using all four numerical scores without sufficiency gates, while its later sufficiency/recommendation section says unsupported high scores cannot provide positive grounds. This experiment does not resolve that product decision or validate downstream recommendation behavior. Direction scoring, complete job assembly, SQLite publication and dashboard rendering were not exercised.

Verification: live fact/citation preservation assertions and cache replay passed; existing company-scope/cache and Jev response/retry tests passed. Syntax and workflow scan checks also passed. Original Codex outputs and all raw Jev responses remain unedited.

## Revised screening-reference rubric rerun

After reviewing the shared questions, the user authorized rescoring with the revised rules from commit `5ba23ef5`. The same frozen input bundle, including all facts, scopes, gaps and conflicts, was passed through the current shared Jev adapter. No new research or editing of evidence occurred. The changed variables are the rubric and request instructions, including the definition of sufficiency. The model remains `jev-1.13.0`. Outputs, the frozen revised rubric and `comparison.json` are in `data/experiments/codex-research-2026-10-09/jev/screening-reference-results/`; raw requests and responses are in the adjacent `screening-reference-store/`. The retained `rescore.py` runs this experiment and refuses to overwrite its output.

All eight calls succeeded on the first HTTP attempt, taking 8.08 seconds in aggregate. Actual outbound requests were checked against the original bundle: facts, gaps, conflicts and scopes remained unchanged for all eight profiles. Empty Climind compensation remains unscored. No business database writes or recommendation publication occurred.

| Employer | Dimension | Score before → after | Sufficiency before → after | Confidence before → after |
| --- | --- | --- | --- | --- |
| Microsoft | company | 4.22 → 4.39 | 0.32 → 0.89 | 0.64 → 0.57 |
| Microsoft | culture | 2.82 → 2.94 | 0.14 → 0.79 | 0.52 → 0.59 |
| Microsoft | compensation | 4.21 → 4.47 | 0.17 → 0.90 | 0.69 → 0.57 |
| NVIDIA | company | 4.40 → 4.54 | 0.36 → 0.90 | 0.52 → 0.62 |
| NVIDIA | culture | 3.20 → 3.32 | 0.12 → 0.71 | 0.56 → 0.57 |
| NVIDIA | compensation | 4.18 → 4.46 | 0.14 → 0.87 | 0.59 → 0.54 |
| Climind | company | 2.97 → 2.99 | 0.07 → 0.72 | 0.93 → 0.97 |
| Climind | culture | 3.05 → 3.05 | 0.09 → 0.54 | 0.51 → 0.53 |

The unchanged evidence produces markedly different sufficiency under the revised decision question, while attraction scores change by 0.00–0.28. This supports question framing as a material contributor to the previously low readings; those readings alone did not establish inadequate research. It does not show improved evidence or better-calibrated predictions: sufficiency now concerns bounded screening usefulness rather than stronger applicability/completeness requirements. The two columns describe different assessment targets and must not be presented as an improvement in research coverage or accuracy.

Microsoft/NVIDIA financial and same-employer salary evidence can now serve as references despite unresolved target-role details. Climind culture, consisting of employer statements, remains the lowest sufficiency at 0.54; that number is not a validated pass threshold or proof of actual working conditions. Company or salary reference usefulness does not establish a specific offer or team experience. There is one revised run per profile, no new repeatability study, no labeled calibration set and no per-answer rationale. All raw scores and uncertainties remain available for review.
