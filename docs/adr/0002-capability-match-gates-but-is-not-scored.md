# Capability match gates assessment but is not a scored dimension

Capability match was being judged in two places by independent model calls (mandatory core requirements at scan, every requirement again in the report prose), with nothing keeping the two consistent. We decided every requirement a posting lists is judged once, at scan, and that judgment gates which opportunities are assessed and is displayed in the score report, but it is never turned into a fifth scored dimension.

The four dimensions measure how much the candidate wants a role; capability match estimates the chance of getting it. Those multiply rather than add. Under the recommendation rule (every dimension above 3, two above 4) a capability score could stand in for an attractiveness dimension and promote roles that are merely comfortable. Applying to a long shot is cheap and skipping a reachable role is expensive, so the chance term belongs in a lenient threshold: only a gap on a core mandatory requirement counts, and it takes two to exclude. A fine-grained score would read "adjacent" as a deduction and discourage reach applications, and it would discard the per-requirement verdicts that preparation actually uses.

## Considered Options

- **A fifth scored dimension.** Rejected for the reasons above.
- **Keep scan to core requirements and let the scoring stage add the rest.** Rejected: two sources for one table, and the same judgment split across two stages.

## Consequences

Scan output grows for every scanned posting, including those the gate excludes. The 87 opportunities excluded before this change keep their earlier core-only judgment and are not rescanned.
