# Mode: shortlist — Read-only view of the current Scored pool

## Purpose

Show the current valid, scored roles from `data/pipeline.md`'s
`## Scored（已评分 · 可手动启动申请）` section — the module-A output pool that
feeds module-B application selection. This mode is **read-only**: it never
evaluates, never scores, never moves rows, and never generates any Stage-2
artifact.

## Context (module A → module B)

`shortlist` sits at the boundary between the two user-facing modules:

- **Module A — 机会搜寻与评估:** Discover/scan → Verify/Liveness →
  Pre-screen/Stage 0 → Evaluate/Stage 1 → **Shortlist/Scored**.
- **Module B — 申请准备与投递:** **Select** (from this shortlist) → Prepare →
  Tailor → Review → Verify → Submit (user only).

A role reaches the shortlist only after it has been fully auto-evaluated and
moved to `## Scored`. Roles that fail Stage 0 or expire are not part of the
shortlist.

## Behavior

1. Run `node scoring-decisions.mjs`. It reads Scored, validates reports and semantic reviews, and applies the current profile's decision policy.
2. Display `decisions` in returned order, grouped as apply (推荐申请), verify (优先补证), deprioritize (暂缓), discard (硬门槛不符). Show attractiveness range, coverage, company/role, and report link.
3. Display `needs_review` separately as 历史评分待重评, and `invalid` as 报告校验失败. Neither belongs to the recommendation pool.
4. Report counts by action. Reading this view does not verify current posting liveness or start reassessment.

## Explicitly not done

- No scoring, no re-evaluation, no pre-screen.
- No row moves (no Processed, no discard, no status change).
- No Stage-2 artifacts (no preparation plan, CV, PDF, cover letter, tracker write).
- No application submission of any kind.

## Output language

Follow `profile.yml language.output` (zh-CN default). Keep the report compact
and table-first with no filler prose.
