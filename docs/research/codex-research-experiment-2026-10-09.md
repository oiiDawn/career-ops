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
- No Jev calls, business database writes, or production workflow changes.

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
