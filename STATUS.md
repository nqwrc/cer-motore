# status

state: active
remote: github-public
updated: 2026-08-22
stale-after-days: 30

## kpi
None. docs/ROADMAP.md is this project's own declared source of truth for work status;
a second number here would duplicate it worse. Declared deviation from the 1-3 KPI rule.

## now
Spike / pre-v0.1 calculation engine for Italian energy communities (CER) on documented mock
GSE data, formulas verified verbatim against the GSE rules and ARERA TIAD (190 test
functions). 15 of 16 roadmap items closed. 2026-08-22: closed the last silent-money hole
left open by items 13/16 - a truncated `prelievi` perimeter inflated the factor-F exempt
energy without tripping any invariant. Completeness itself is not checkable here (no
registry), but its consequence is: EC = min(injected; withdrawn) over the whole
configuration, so an hour's shared energy can never exceed that hour's total withdrawal.
Measured on the `cumulo` scenario: dropping one non-exempt point overstated the premium
tariff by +19.54 EUR (+5.05%), and dropping the largest exempt point wiped 50.19 EUR
(-12.96%) off it - the previous guard silent in all 720 hours in both cases, the new one
firing in 346 and 378. Both sides of the comparison are quantized to the same grid: two
adversarial review passes were needed, the first because comparing quantized EC against
raw withdrawals accused complete perimeters, the second because quantizing only the
withdrawals mirrored the defect. Zero false positives across 720 combinations (four
scenarios, every plant, twelve months, six resolutions, both admissible input series). Not a
completeness check - a truncation that never crosses the line still passes. Install gate
verified 2026-08-20 on a fresh public clone (~32 s against the 15-minute gate). Item 9
(real GSE export adapter) remains the only open item, blocked on a file from a CER.

## backlog
- see docs/ROADMAP.md and the repo's open issues for the technical backlog
- roadmap item 9, the adapter for a real GSE export, is the only one still open: it is
  blocked on obtaining a real export file from a CER, not on this repo's own state. The
  interface that adapter must satisfy is specified in docs/ADAPTER-GSE.md
