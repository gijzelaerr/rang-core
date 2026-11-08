"""merge_edits.py : the semantic edits of G9's merge of main 3defaae (G6/W6), after the textual
conflicts are resolved: G6's model writing and -predict refused for polarisations other than
Stokes I (a follow-up, not a finished task), in gemclean and in rang-core; E2-B's expected refusal
set after both G9 and W6."""

W = "/home/gijsm/Worktrees/rang/fp-g9-stokes/"


def edit(path, pairs):
    p = W + path
    s = open(p).read()
    for old, new in pairs:
        assert s.count(old) == 1, (path, old[:70])
        s = s.replace(old, new, 1)
    open(p, "w").write(s)


edit(
    "core/src/bin/gemclean.rs",
    [
        (
            """    if a.join_pols && a.pols.len() < 2 {""",
            """    if a.pols != [Pol::I] && (a.predict || a.update_model) {
        return Err(
            "MODEL_DATA (-predict, and the model update after imaging) is written for Stokes I \\
             only; a model of other polarisations is a follow-up of research/g9-stokes.md, not \\
             implemented: add -no-update-model-required"
                .into(),
        );
    }
    if a.join_pols && a.pols.len() < 2 {""",
        ),
    ],
)

edit(
    "python/rang/core_config.py",
    [
        (
            """            if img["join_polarizations"] and len(pols) < 2:""",
            """            if img["write_model"] and pols != ["I"]:
                out.append(
                    Refusal(
                        "image.write_model",
                        "",
                        "MODEL_DATA is written for Stokes I only; a model of "
                        f"pol: {img['pol']!r} is a follow-up of research/g9-stokes.md, "
                        "not implemented",
                    )
                )
            if img["join_polarizations"] and len(pols) < 2:""",
        ),
    ],
)

p = W + "tests/test_w2_commands.py"
s = open(p).read()
start = s.index("<<<<<<< HEAD\n")
end = s.index(">>>>>>> 3defaae\n") + len(">>>>>>> 3defaae\n")
s = (
    s[:start]
    + """    # extendflags; since task W6 (research/w6-imaging-inputs.md) data.scans and
    # data.weights: uniform reach gemclean (-scans, -unit-weights), and since
    # task G9 (research/g9-stokes.md) IQUV with joined polarisations: nothing
    # is left.
    assert _tasks(DATA / "e2b.yaml") == set(
"""
    + s[end:]
)
open(p, "w").write(s)
