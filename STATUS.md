# status

state: active
remote: github-public
updated: 2026-08-20
stale-after-days: 30

## kpi
None. docs/ROADMAP.md is this project's own declared source of truth for work status
(CLAUDE.md: "resta la fonte di verità sullo stato del lavoro"); a second number here would
duplicate it worse. Declared deviation from the 1-3 KPI rule.

## now
Spike / pre-v0.1 calculation engine for Italian energy communities (CER) on documented mock
GSE data, formulas verified verbatim against the GSE rules and ARERA TIAD (183 test
functions). 14 of 15 roadmap items closed; pause lifted per maintainer decision, work resumed.

## backlog
- see docs/ROADMAP.md and the repo's open issues for the technical backlog
- roadmap item 9, the adapter for a real GSE export, is the only one still open: it is
  blocked on obtaining a real export file from a CER, not on this repo's own state. The
  interface that adapter must satisfy is specified in docs/ADAPTER-GSE.md
