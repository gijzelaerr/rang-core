# Stimela 2.1.4: "There is no current event loop" on Python 3.14

Repository: caracal-pipeline/stimela (not under ratt-ru). Status: **not filed: outside the
declared support range.** Checked 2026-10-30. Found while scanning task files; not in
`upstream-notes.md`.

- Observation ([core-i-imaging-replay.md](../core-i-imaging-replay.md)): Stimela 2.1.4 on the
  system Python 3.14.4 loads and validates a recipe, then fails before running the cab with
  `RuntimeError: There is no current event loop in thread 'MainThread'` (the Python 3.14
  asyncio change); the same recipe passes in a uv Python 3.13 venv.
- Why not filed: the latest release 2.1.4 declares `Requires-Python: <3.14,>=3.9` on PyPI, so
  3.14 is unsupported by design; Python 3.14 support is a known topic upstream (closed #554,
  "Changing to uv created a subtle restriction for testing with python 3.14").
- Also in [core-h-recipes.md](../core-h-recipes.md): two rang recipes failed to load because an
  `info:` string contained `{clean,...}` inside a YAML flow mapping. That is valid YAML
  behaviour, rang's own error, not a Stimela defect.
