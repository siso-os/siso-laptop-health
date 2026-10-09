# halo-vps runs HALO's client work first

Shaan, 2 Oct 2026 (verbatim in `.agents/source/2026-10-02-1444-shaan-health-manager.md`): "the halo thing should be
running like we don't need to be building agents on there ... it's only if it's under allocated we'll use it ... right
now is a bad scenario because I think it's double allocated and that's supposed to be our client running stuff".

## The rule
- halo-vps (6 cores, 12 GB) is HALO's production box. Production always has first claim: the HALO CRM, the Oracle
  production workspace and its electron/convex-local, OME, cloudflared.
- Our build, test and agent work (DEV workspaces, soaks, readback/probe loops, builds, test browsers, Codex/omp
  workers) may run there only while the box is under-allocated:
  - load (5 min) under 4.5 (0.75 x cores), and
  - CPU pressure `some avg60` under 15%, and
  - 3 GB+ RAM available.
- If ours pushes it past load 9 (1.5 x cores) or pressure 30% for 5 minutes, ours yields: the owner pauses or moves
  it. HEALTH opens an issue and tells the owner; production units are never touched without A0.
- A production gate that must run on the real box (a go-live soak) is allowed, but it is scheduled, time-boxed,
  announced in the A0 inbox, and nothing else of ours runs beside it.

## Where our work goes instead
| Work | First choice | Then |
|---|---|---|
| builds, tsc, vitest, Playwright | siso-vps (`estate fleet pick build`) | the Mac mini |
| headless agents, workers | siso-vps, ovh-pool | the Mac mini |
| image runs (Luna) | the Mac mini | siso-vps |
| test loops that read HALO data | run from siso-vps against the API, with an end time | never an open-ended loop on halo-vps |
`estate fleet pick <kind>` (SISO_Agents/siso-estate) ranks these live; halo-vps is marked client-only there.

## Measured when the rule was written (2 Oct 14:44 +07, issue H-0001)
Load 15.4 / 12.7 / 11.8 on 6 cores (2.6x), CPU pressure 55%. Ours: DEV soak 229% CPU, a 5-day-old readback loop
spawning `npx convex data` twice every 8 s (~43%), the DEV workspace-host timer (2 s CPU every 15 s), convex-dev 26%.
Production: about 60%.
