# Carbon / Trust agent rules

Follow [root /CLAUDE.md](../CLAUDE.md) and
[the Trust roadmap](../docs/roadmaps/ROADMAP_TRUST_BLOCKCHAIN.md). Primary edit scope:
`carbon/` and `carbon/tests/`.

Before creating or updating a Pull Request, read and follow
`docs/common/07_PR_WORKFLOW.md` and `.github/pull_request_template.md` (root-relative).
Never push to `main` or perform a PR merge. One roadmap stage is one feature branch and
one Draft PR; after the stage, report and stop for consumer review.

- Authoritative inputs: `data/` and `doc/` only. Coefficients, baseline, prices and
  parameters come from `data/methodology/*.csv`, never from third-party repositories.
- Inputs: per-cell payload from RS (area, AGB and AGB_SD on both dates), request geometry
  parts, period, and the case parameters. Outputs: interval, baseline, units and claim
  comparison as typed frozen dataclasses, sealed into a canonical passport.
- `analyse` is the one composition point. The report builder and the passport read its
  result; neither recomputes a formula, so API, report and hashed content cannot diverge.
- Reuse the P0 canonical form (`rfc8785` + `"0x" + sha256`). Never invent a second one.
  Volatile fields (`created_at`, `run_id`) stay outside the content hash; the integrity
  manifest stays detached and never carries its own hash.
- Upstream shapes live only in `carbon/rs_adapter.py`. A fixture-backed result is labelled
  `PROVISIONAL_LOCAL_EXTRACTION` end to end and is never presented as an RS result.
- Keep the package pure: no FastAPI, web3, HTTP clients, ORM, React or cross-role imports.
  Backend composes the functions; `carbon` never calls Backend.
- Q is `floor(Radj × 0.85)` exactly as written in the statement. Never replace it with
  `floor(Radj − B)`, and never turn missing input into zero: `null` and `0` are different
  answers with different reasons.
- Wording stays inside what the case supports: scenario interval, scenario prices,
  potential units of the case. Do not state that a violation, a market outcome or an
  empirical calibration is established.
- The method (ρ_t, coverage factor, main dependence mode) is approved by the Team Lead
  before real Q values are published; record it in `METHOD_VERSION`.
- The research baseline is research only. The reported Q always comes from
  `data/methodology/baseline.csv`, and a variant never rewrites a passport.
- Golden results live in `carbon/tests/golden/results.json`. Regenerate with
  `python -m carbon.tests.golden.build_golden` only when a change is intended, and read
  the diff before committing it.
- Run `python -m pytest carbon -q` and the shared `python -m pytest -q`, then report
  changed files, commands, results, limitations and the next handoff.
