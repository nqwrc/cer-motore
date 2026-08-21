# status

state: active
remote: github-public
updated: 2026-08-21
stale-after-days: 30

## kpi
None. docs/ROADMAP.md is this project's own declared source of truth for work status;
a second number here would duplicate it worse. Declared deviation from the 1-3 KPI rule.

## now
Spike / pre-v0.1 calculation engine for Italian energy communities (CER) on documented mock
GSE data, formulas verified verbatim against the GSE rules and ARERA TIAD (188 test
functions). 15 of 16 roadmap items closed. Fourth mock scenario `cumulo` added 2026-08-21:
closes a standing review finding (roadmap items 6/8 lineage) that
`condivisione.partiziona_esente_fattore_f` and the 45%-threshold `InsiemeIncentivato.
cumulo_conto_capitale` insieme were written and unit-tested but had no real caller — the demo
now routes a capital-contribution plant through the partition and both incentivized-insiemi
end-to-end. The three prior scenarios are unchanged byte-for-byte. Install gate verified
2026-08-20 on a fresh public clone (Windows, Python 3.13, 3 scenarios at the time), README
path followed verbatim: clone+venv+install+tests+demo in ~32 s against the 15-minute gate,
184 tests green then, demo wrote the twelve expected files under data/ (now sixteen, with the
fourth scenario) — re-verification against the current file count is pending, not blocking.
Doc drift reconciled: ROADMAP item 10's residuals were both already resolved (single-source
version policy in CHANGELOG; private vulnerability reporting enabled), and SECURITY.md no
longer claims the factor-F partition is missing (item 13 shipped it). Item 9 (real GSE export
adapter) remains the only open item, blocked on a file from a CER, not on this repo.

## backlog
- see docs/ROADMAP.md and the repo's open issues for the technical backlog
- roadmap item 9, the adapter for a real GSE export, is the only one still open: it is
  blocked on obtaining a real export file from a CER, not on this repo's own state. The
  interface that adapter must satisfy is specified in docs/ADAPTER-GSE.md
