# Stimela: Python 3.14 (event loop, forkserver scatter workers, requires-python)

Repository: caracal-pipeline/stimela. Status: **filed 2026-10-30 (task U2),
https://github.com/caracal-pipeline/stimela/issues/619**, after the user allowed CARACal and
Stimela reports. Earlier status (U1): not filed because 2.1.4 declares `<3.14`; `master`
(9747611) and 2.2.0rc1 now declare `<=3.14` (PR #555 "Relax python version", after #554).

PR: https://github.com/caracal-pipeline/stimela/pull/620 (branch `python314-event-loop`,
commit 8f39567). CI: 3.10-3.14 pass; 3.9 fails at "Set up Python 3.9" (not available on the
Ubuntu 26.04 runner; unrelated to the change).

Checked on stimela 2.1.4 and 2.2.0rc1 (PyPI, the latter = `master` for these lines), Python
3.14.8 and 3.13.16 (uv). Origin: [core-i-imaging-replay.md](../core-i-imaging-replay.md).

- Reproduction: a one-step recipe with a native `echo` cab (`stimela run echo.yml hello`).
  3.14.8 + 2.1.4 and 3.14.8 + 2.2.0rc1: exit 1, `RuntimeError: There is no current event loop
  in thread 'MainThread'` from `asyncio.get_event_loop()` in `utils/xrun_asyncio.py:116`
  (2.6-3.8 s). 3.13.16 + 2.2.0rc1: exit 0 (2.9 s).
- `requires-python = ">=3.9,<=3.14"` admits 3.14.0 only: `pip install --pre stimela==2.2.0rc1`
  on 3.14.8 refuses it; uv installs it anyway (also 2.1.4 despite `<3.14`).
- Found while fixing: `tests/test_recipe.py::test_scatter` fails on 3.14 because the default
  start method on Linux is now `forkserver`; its workers cannot unpickle the classes that
  `stimela.config` creates at run time (`AttributeError: ... no attribute 'StimelaLibrary'`,
  `BrokenProcessPool`).
- Fix (PR): get-or-create-and-set the loop in `xrun` and `loop.create_task` for the reporter;
  `mp_context=get_context("fork")` for the scatter pool on Linux; `requires-python <3.15`;
  3.14 in the CI matrix. New test runs `xrun` in a fresh thread (no loop on any version):
  fails on 3.13.16 and 3.14.8 before, passes after. Full suite: 72 passed on both.
- Also in [core-h-recipes.md](../core-h-recipes.md): two rang recipes failed to load because an
  `info:` string contained `{clean,...}` inside a YAML flow mapping. That is valid YAML
  behaviour, rang's own error, not a Stimela defect.
