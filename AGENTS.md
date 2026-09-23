# Rang working conventions

## Start here and leave a trail

- Read `research/README.md` for the research index and `research/STATE.md` for
  the latest progress before starting work. The active experiment is MeerKAT
  L-band gain-TV-guided flagging; older pointing reports are separate history.
- Save meaningful progress, exact run paths, seeds/settings, provenance, checks,
  rejected/null outcomes and next steps in the repository as work proceeds.
  Distinguish proposed, implemented and measured work. Link compact result
  archives; raw observations and generated checkpoints belong in ignored outputs.
- The user authorizes regular pushes of verified checkpoints to origin/main so
  astronomers can follow progress. Run the full local checks before every commit;
  push normally, never force-push. Keep scientific status and handoff links current.

## Research scope

- Focus on MeerKAT. The current experiment is specified in `research/meerkat-scope.md`.
- Use simulations and comparisons to test research hypotheses; distinguish proposed methods, implemented methods and measured results.
- Preserve reproducible experiment settings, seeds, data provenance and relevant negative results.
- Inspect CARACAL's shipped MeerKAT strategies and flag-worker semantics when
  verifying flagging methods; a reduced kernel ablation is not a full CARACAL baseline.
- Novelty must target demonstrably higher calibration/imaging quality at comparable cost, or comparable quality with materially lower runtime/resource use than a relevant state-of-the-art method. Toy-baseline wins and software reimplementations alone do not establish novelty. Record matched accuracy/cost comparisons and negative results.

## Implementation languages

- Use public PyPI only for this project, never the Spotify package registry.
- The user explicitly requested JAX DFT prediction and automatic differentiation for the smooth pointing-solver reference path; retain the existing Rust baseline.

- Use Rust for computational kernels and performance-sensitive simulation and calibration work.
- Use Python for astronomer-facing interfaces, experiment scripting and pipeline orchestration.
- Validate numerical correctness before claiming performance or scientific improvements.

## Git attribution

- Always use `gijsmolenaar@gmail.com` for non-Spotify or public work, including this repository. Do not use a Spotify email for Rang commits.
- Commits use the user's Git identity. Do not substitute an agent or bot identity.
- Never add agent signatures, AI attribution, generated-by footers or co-author trailers to commit messages.
- Never name Codex or OpenAI as a co-author. Never include a Spotify email
  address in a Rang commit message, author or committer identity.
- Follow the user's global Git and pre-commit verification rules.
