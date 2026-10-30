"""Read-only boundary validation before any copied prepared-MS flag writes.

Verbatim extract of the frozen `rangtoy.flagging_prepared` (big plan task P11,
research/p11-extract.md): the definitions the live chains use, copied
byte for byte in source order from python/rangtoy/flagging_prepared.py at commit
2da566c (now history/python/flagging_prepared.py),
sha256 8c1878cdaa3259ca2e5416b78df2a89544a87cea86aa1b47099eaf4b3d96e8ab.
Only import statements differ: frozen modules are replaced by their core
extracts. tests/test_p11_extract.py checks every definition against the
history copy.
"""

from pathlib import Path


def reject_nested_paths(run_dir, prepared_dir):
    """Reject either ancestor relationship, including equality, before mkdir."""
    output, source = Path(run_dir).resolve(), Path(prepared_dir).resolve()
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError("prepared input and output paths must not be nested")
    return output, source
