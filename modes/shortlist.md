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

1. Read `data/pipeline.md` and locate the `## Scored（已评分 · 可手动启动申请）`
   section (accept the localized/legacy header as needed).
2. For each `- [~] #NNN | URL | Company | Role | Score/5 | Report: path` row,
   render a compact table sorted by score descending.
3. Highlight the **推荐申请 (≥4.0)** tier; group the rest by band
   (3.5–3.9 可考虑, <3.5 不建议).
4. Do not liveness-check or re-evaluate roles here — that is module A's job on
   the next run. If a report link is missing, list the row with `报告: —` rather
   than inventing a path.
5. Optionally show counts: total scored, count ≥4.0, count by band.

## Explicitly not done

- No scoring, no re-evaluation, no pre-screen.
- No row moves (no Processed, no discard, no status change).
- No Stage-2 artifacts (no preparation plan, CV, PDF, cover letter, tracker write).
- No application submission of any kind.

## Output language

Follow `profile.yml language.output` (zh-CN default). Keep the report compact
and table-first with no filler prose.
