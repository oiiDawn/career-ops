# Ponytail review: posting liveness

What this change does: It checks whether stored jobs accept applications. Clear
closure evidence can delete an unsubmitted job; access failures remain uncertain
and do not block other work.

Reviewed the `685f6860` changes and their connected collectors, classifier,
maintenance/deletion boundary, callers, tests, README and operations guide.
Expected load: one local user, 209 current candidates, twice daily, alongside
discovery and scoring. This is a focused review, not a whole-repository audit.

## Must fix

1. **Closure judgement can lose its evidence** (`liveness-core.mjs`, `liveness-browser.mjs`).
   - **What this is:** The classifier decides closure, while the browser separately searches for a narrower set of closure phrases.
   - **Problem:** `Job posting has expired` is classified closed but the browser returns an empty excerpt. Maintenance then downgrades it to uncertain.
   - **Fix:** Return the matched excerpt from the classifier and preserve it in the browser observation. Remove the second phrase matcher. Keep generic missing-page messages and closure dates without a posting-specific assertion inconclusive.
   - **If we skip it:** Recognized closures remain tracked, and every phrase change risks disagreement between classification and deletion evidence.

2. **Waiting misses a late application button inside a frame** (`liveness-browser.mjs`).
   - **What this is:** A posting can be embedded in a same-origin child page.
   - **Problem:** The old frame wait stops once that child contains `Loading`. Later retries reread only the main page and overwrite application controls while retaining stale child text. A child button appearing after 2.5 seconds stays unseen.
   - **Fix:** Read the main page and all same-origin posting frames together on each bounded attempt. Use one wait loop and return the URL and evidence from that snapshot.
   - **If we skip it:** Live embedded postings stay uncertain even though the checker waits long enough for their buttons to appear.

## Should fix

3. **A brand name stands in for a control's meaning** (`liveness-browser.mjs`).
   - **What this is:** A Mercedes-Benz hostname branch adds its custom button tag to the DOM selector.
   - **Problem:** The observed button already has an application link and accessible label. Naming the brand adds a special case for a normal actionable element.
   - **Fix:** Read linked, labelled elements through the common selector. Keep visibility and disabled-state checks. Retain LinkedIn and SmartRecruiters attributes where they provide real application semantics independent of the displayed label.
   - **If we skip it:** Another equivalent custom element would require another hostname branch.

## Verification and final review

Findings 1 and 2 were reproduced with a real Chromium test before the changes.
Both pass after the changes. Existing localized controls, disabled/hidden controls,
contradictory signals, SmartRecruiters API identity and permission-error cases pass.
Business checks cover localized deletion, submitted/shared protection, cleanup
recovery, historical evaluation inputs and isolated check failures. The required
workflow-scan check and syntax checks for 707 `.mjs` files passed.

The design has three responsibilities: collect source evidence, classify it once,
then persist or delete under the existing business protections. No scheduler,
configuration, dependency, compatibility layer or LLM path was added. The browser
now has one document reader and one bounded snapshot loop; the second frame wait,
stale frame accumulation, duplicate closure matcher and Mercedes-specific branch
are removed. Generic `Applications closed` and `Closed on DATE` phrases alone no
longer establish posting closure.

Verdict: Ship.

Lean: 82 source lines removed net across the browser reader and classifier.

Not checked: unrelated repository workflows were not audited; live acceptance is
recorded separately from these isolated regression checks.
