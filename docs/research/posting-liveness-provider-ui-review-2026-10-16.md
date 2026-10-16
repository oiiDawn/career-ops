# Posting liveness provider and LinkedIn UI review

What this change does: It reads explicit HKSTP activity from the existing public
platform. It follows one trusted Eightfold application link and checks the ATS
job number against a visible heading and Apply control. It implements the user's
confirmed rule that a complete LinkedIn posting without a visible Apply control
is closed.

Looks good. Ship.

Checked the API registry, browser snapshot reader, pure classifier, streaming
collector, Python closure gate, maintenance deletion path and their callers.
The expected load is one local user, with two scheduled maintenance runs a day.
The existing per-posting locks, submission protections and independent failure
handling remain in place. No model, dependency, configuration switch, new
scheduler or retry layer was added.

The browser keeps one bounded hydration loop. The LinkedIn closure rule needs a
visible title and job description, a matching requested/final/canonical posting
number, a complete document, no visible login wall and no visible Apply control.
A dismissible LinkedIn sign-in prompt is closed through its own button before
reading the posting; a mandatory login wall stays uncertain.
A visible disabled Apply control stays uncertain. A late enabled Apply control
stays active. Missing guest-API markers trigger the browser; conflicting API
markers stay uncertain. The Python deletion gate validates the emitted evidence
again before allowing the existing cleanup path.

The application-page check reuses Eightfold's trusted tenant resolver and the
existing browser security and classification code. The destination is pinned to
the verified SuccessFactors application origin and path. The API job number,
URL job number and visible heading must agree. Redirected or mismatched pages
cannot turn the original posting active. The destination cannot resolve to an
Eightfold tenant, so the browser's application-page call is bounded to one hop.

Checked offline: explicit HKSTP status and publication dates; identity mismatch;
HTTP failures; trusted application URLs; matching, wrong and hidden ATS headings;
hidden and disabled Apply controls; late rendering; login walls; API missing vs
conflicting signals; isolated deletion and protection against incomplete closure
evidence; existing browser/frame regressions; liveness workflows; syntax and scan
handoff checks.

Not checked: Final application submission and employer-internal recruiting status.
The live diagnostic run is read-only; it is not a production state update.
