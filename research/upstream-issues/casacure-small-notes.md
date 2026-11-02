# casacure: smaller differences from casacore

Repository: tmolteno/casacure. Status: **filed 2026-11-02 (U4), https://github.com/tmolteno/casacure/issues/26**. From `non-ratt-observations.md`,
checked by U4 on 3.8.36. Left out: TiledDataStMan (open as #18), `info` (open as #23), undefined
cell values (#8, by design), macOS x86_64 wheels (README: deliberately not built).

<!-- issue-title: Smaller differences from casacore: getvarcol numbering, iscelldefined, MemoryStMan and MultiFile opens, cp310 macOS wheel -->
<!-- issue-body -->
A few smaller things I noticed on casacure 3.8.36 against python-casacore 3.8.1. None is urgent. Happy to split any of them out.

- **`getvarcol` keys with a start row.** `getvarcol("V", 1, 2)` gives keys `r1`, `r2`; python-casacore gives `r2`, `r3` (numbered from row 0 of the table).
- **`iscelldefined`.** The Python table has no `iscelldefined`. Given that undefined cells read as defaults (#8), a caller cannot tell the two apart.
- **MemoryStMan.** Opening a table written with `MemoryStMan` and reading a column raises `storage error: unsupported data-manager type MemoryStMan`. The message is clear; I mention it only for completeness.
- **MultiFile.** A table written with `table.storage.option: multifile` (it holds `table.mf`) fails with `storage error: .../mf.tab/table.f0: No such file or directory (os error 2)`. A message naming MultiFile would help.
- **Wheels.** The README lists macOS aarch64 for Python 3.10 to 3.14, but PyPI has no cp310 macOS wheel for 3.8.36, and `publish-python.yml` has macOS jobs for 3.11 to 3.14 only.
<!-- /issue-body -->
