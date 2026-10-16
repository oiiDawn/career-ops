# Posting liveness fixes and one-round LLM comparison

The confirmed code gaps are fixed in `685f6860`. This experiment found no additional
supported determinations from the LLM on the same captured evidence. It produced
one unsupported closure judgement and six cases without a usable judgement.
Production liveness remains deterministic; no model fallback was installed.

## Implemented fixes

- SmartRecruiters: require matching posting identity, explicit `active=true`,
  `visibility=PUBLIC`, and an application URL for that posting. Ambiguous or
  inaccessible API responses fall back to the browser rather than authorizing deletion.
- LinkedIn: recognize the observed Chinese closure wording and posting-specific
  application controls regardless of their displayed language. Conflicting closure
  and application signals remain uncertain. Localized closure evidence is retained
  through Python's deletion validation.
- Browser controls: recognize SmartRecruiters application links and Mercedes-Benz
  `wb-button` elements; exclude hidden and disabled controls.
- Hydration: poll inconclusive pages for at most six additional seconds. A generic
  missing-page message remains uncertain, since Workday displayed it after its
  per-posting API returned `403 permission denied`.

The new real-Chromium layout test and isolated localized-closure maintenance test
passed. Existing LinkedIn API, core classification, liveness CLI, maintenance,
evaluation and opportunity-cleanup tests passed, as did the required workflow-scan
test and syntax checks for 706 `.mjs` files. The installed Hermes wrapper still
matches the repository wrapper. No production maintenance run was added for this experiment.

## Matched experiment

The cohort consists of all 43 original uncertain URLs plus four historical controls:
two active and two closed postings. All 47 were freshly captured read-only.
Code and LLM judgement use the same captured evidence, not separate live browsing
sessions. API responses, HTTP status, posting/final URL, rendered text and control
metadata were retained. API HTML is reduced to text and element attributes;
long fields are bounded to 20,000 characters, with head/tail retained. This is a
text/DOM experiment, without screenshots or model-operated browsing.

The LLM receives no previous code verdict, historical status, cohort label, reference
label, candidate document or scoring policy. It judges directly from public evidence
in a tool-free LangGraph node. The configured model is `deepseek-v4.1-flash` through
the existing project provider, with low reasoning, a 2,048-token output budget,
50-second per-case deadline and concurrency two. There is one pass per case, with
the existing bounded transport-retry policy; failed outputs were not repaired by
another model call. The first case was a preflight and was reused in the full batch.

Reference labels come from source-evidence review by the coding assistant. They are
not external human labels or independent ground truth about inaccessible postings.
In particular, uncertain means the captured evidence is insufficient, not that the
job is actually closed. Agreement with code alone is not treated as proof of accuracy.

## Results

For the original 43 URLs:

| Outcome | Fixed code | Pure LLM judgement |
| --- | ---: | ---: |
| Active | 15 | 13 |
| Closed | 1 | 2 |
| Uncertain | 27 | 22 |
| No usable judgement | 0 | 6 |

The LLM's extra closed judgement is unsupported by the agreed deletion standard.
None of its additional determinations was supported. Five truncation failures
and one timeout produced no usable judgement, including two postings whose captured
evidence the code correctly recognized as active. The 43-URL changes from the
initial run include access/rendering variability; they are not all attributable
to code fixes. ABB still lacked an application control in this capture despite
the bounded additional wait.

Across all 47 cases, the model produced 41 readable classifications: 40 matched
the evidence-review reference and one did not. All four controls received the
supported semantic classification. Only 37 responses passed the initial strict
metadata schema: another four used `null` for `uncertainty_cause`. Those four
classifications are counted as readable rather than incorrectly counted as model
judgement failures; nullable metadata is an interface compatibility issue.

Case `36` is the important disagreement. The Mercedes-Benz posting redirected to
`https://group.mercedes-benz.com/karriere/jobsuche/nicht-mehr-verfuegbar/`, which
returned HTTP 403. The model interpreted the German path as explicit posting-bound
closure, despite not seeing the destination content. The code and evidence review
retain uncertain. This does not establish that the job is open; it establishes
that the supplied evidence is insufficient for automatic deletion. Its literal
URL quote exists, illustrating that quote-presence validation alone cannot verify
the model's inference.

Case `0` had a supported active judgement but combined nonadjacent API fields into
a purported verbatim quote. Evidence correctness must be assessed separately from
classification and JSON validity.

## Time and usage

The full comparison batch took 467.9 seconds; the reused first-case preflight took
another 8.4 seconds. Median per-case elapsed time was 17.6 seconds. There were 48
attempt records for 47 cases: after one 50-second HTTP timeout, the retry was rejected
before dispatch because the deadline was exhausted. No additional judgement was
obtained through that retry.

Recorded usage totals 280,485 input and 38,572 output tokens, including reported
usage on truncated calls. Two attempt records have no usage, so these are not a
complete billing reconciliation. At the official Flash peak cache-miss reference
rates of $0.30/$1.20 per million input/output tokens, the recorded portion is about
$0.13. This is an illustrative equivalent, not the project's proxy-provider invoice;
cache discounts and unreported usage are not reconciled. See
[DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing/).

## Decision and retained evidence

Keep the code fixes and do not add this model configuration to the production
liveness schedule. Even allowing nullable metadata, this round showed no supported
incremental resolution, a closure inference below the deletion evidence threshold,
and additional latency/output-budget failures. This is evidence about one model,
prompt, budget and selected cohort, not a general claim that LLMs cannot help.

The experiment never writes observations, closes URLs or deletes opportunities.
The existing production schedules were not changed. Primary artifacts are under
`data/experiments/liveness-llm-20261016/`:

- `capture-*.json`, `manifest.json`: raw captures and cohort.
- `prompt.txt`, `experiment.json`, `input-*.json`: exact prompt, run configuration and inputs.
- `raw-*.txt`, `calls-*/*.json`, `result-*.json`, `results.json`: returned text,
  attempt usage/errors and original strict-schema results. Truncated/timeout calls
  retain diagnostics and available usage rather than a complete usable response.
- `reference.json`, `summary.json`: evidence-review reference and
  final audit, including metadata-only failures and the unsupported closure.

The four metadata-only failures are recovered from retained raw output during
offline analysis; no model call or production fallback is involved.

The completed one-off collector, comparison and summary scripts and their duplicate
progress logs were removed during local cleanup on 2026-10-16. Captures, inputs,
returned outputs and final analysis remain intact. The cleanup inventory and
removed-file hashes are retained in
`data/maintenance/liveness/local-cleanup-20261016.json`.
