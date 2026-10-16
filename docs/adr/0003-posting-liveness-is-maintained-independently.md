# Maintain posting liveness independently of evaluation

Periodic liveness checks will persist source evidence and observations for unsubmitted opportunities still in the candidate pool, including already scored opportunities. Dashboard and evaluation will consume the same current liveness observations, because evaluation-triggered checks leave scored opportunities with outdated status.

A specific posting is active only when evidence establishes that it accepts applications. Readable job descriptions alone do not establish liveness; login walls, challenges, timeouts and inconclusive results leave it uncertain. Posting closure does not imply rejection of an existing application, so submitted opportunities and opportunities whose pursuit has ended are outside the initial periodic scope.

Evaluation and other opportunity workflows will consume maintained liveness observations without repeating a liveness network check. Obtaining missing or unusable job-description evidence remains necessary for evaluation and is a separate responsibility; a failed liveness check alone must not invalidate usable job-description evidence.

Checks will run twice daily at 06:00 and 18:00 Asia/Shanghai. Active observations are valid for 24 hours; older observations are displayed as uncertain with their last confirmation time. A newer inconclusive check also makes the current status uncertain rather than retaining an earlier active verdict.

Liveness is nonblocking: missing, stale, inconclusive or failed checks must not block, cancel, or downgrade evaluation, material preparation, notifications, or any other workflow for that opportunity. They only affect liveness display and check diagnostics. This supersedes the earlier agreement to wait for a valid active observation. An uncertain display must not silently become an eligibility or recommendation gate.

The user chose deletion of explicitly closed postings because they no longer wish to track them, superseding the suggested policy of retaining them in a closed state. Inconclusive checks do not authorize deletion; submitted opportunities remain outside this automatic policy. Closure requires evidence tied to the specific posting, rather than a failed request, absence from search results, or a missing application button alone.

Deletion includes the opportunity's related business records, execution records and exclusively owned scores, reports, application drafts and source captures. Shared company research, candidate source documents and artifacts referenced by other opportunities are retained. A minimal closed-URL discovery outcome is retained using the existing deduplication mechanism so discovery does not recreate the same posting; a new posting URL remains eligible for discovery. Reopening the same URL requires explicit manual rechecking.

Failed checks retry at the next regular run; manual checking remains available. Each posting's result is saved independently, and failure of one posting must not prevent other checks or workflows from proceeding. No separate retry schedule is needed.

## Implementation boundary

This records the design agreed on 2026-10-16. The [technical implementation proposal](../posting-liveness-implementation-plan.md) describes the affected code and validation; runtime implementation, deployment and schedule installation have not been requested. Initial automatic deletion must rely on newly collected, explicit closure evidence rather than historical uncertain or stale observations. Implementation must coordinate deletion with running tasks, recheck submitted status before deletion, and preserve shared artifact references.
