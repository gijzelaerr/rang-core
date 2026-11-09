"""resolve_g5.py : resolve G9's merge of main f3ab57d (G5 multiscale) additively, and refuse
-multiscale with several polarisations (a follow-up, research/g9-stokes.md section 12)."""

W = "/home/gijsm/Worktrees/rang/fp-g9-stokes/"


def hunks(text):
    """Split into [str | (ours, theirs)] pieces."""
    out, ours, theirs, state, plain = [], [], [], None, []
    for line in text.splitlines(keepends=True):
        if line.startswith("<<<<<<< "):
            out.append("".join(plain))
            plain, ours, theirs, state = [], [], [], "o"
        elif line.startswith("=======") and state == "o":
            state = "t"
        elif line.startswith(">>>>>>> ") and state == "t":
            out.append(("".join(ours), "".join(theirs)))
            state = None
        elif state == "o":
            ours.append(line)
        elif state == "t":
            theirs.append(line)
        else:
            plain.append(line)
    out.append("".join(plain))
    return out


def resolve(path, fns):
    p = W + path
    parts = hunks(open(p).read())
    k, res = 0, []
    for x in parts:
        if isinstance(x, tuple):
            res.append(fns[k](*x))
            k += 1
        else:
            res.append(x)
    assert k == len(fns), (path, k)
    open(p, "w").write("".join(res))


both = lambda o, t: o + t  # noqa: E731
none = lambda o, t: ""  # noqa: E731


def usage(o, t):
    assert o.rstrip().endswith('";') and t.rstrip().endswith('";')
    return o.rstrip()[:-2] + "\n\n" + t


def checks(o, t):
    return (
        o
        + "    }\n"
        + """    if ms_on && a.pols.len() > 1 {
        return Err(
            "-multiscale with several polarisations is not implemented (a follow-up of \\
             research/g9-stokes.md, section 12); image one polarisation at a time"
                .into(),
        );
    }
"""
        + t
    )


resolve("core/src/bin/gemclean.rs", [usage, checks])


def config_refusals(o, t):
    ours = o.splitlines(keepends=True)
    theirs = t.splitlines(keepends=True)
    # ours: G5's line (gone on main), "):", the loop (2 lines), then G9's try block,
    # left open before the shared closing ")" of its last out.append.
    assert ours[0].strip().startswith('("multiscale"')
    head = ours[1:4]
    g9 = ours[4:]
    i = g9.index('            if img["join_polarizations"] and len(pols) < 2:\n')
    g9 = (
        g9[:i]
        + [
            '            if img["multiscale"] and len(pols) > 1:\n',
            "                out.append(\n",
            "                    Refusal(\n",
            '                        "image.multiscale",\n',
            '                        "",\n',
            '                        "multiscale with several polarisations is a follow-up of "\n',
            '                        "research/g9-stokes.md, not implemented",\n',
            "                    )\n",
            "                )\n",
        ]
        + g9[i:]
        + ["                )\n"]
    )
    # theirs: G9's line (gone here), "):", the loop, G9's pol refusal (gone here), then G5's
    # multiscale block, left open before the same shared ")".
    j = next(
        n
        for n, line in enumerate(theirs)
        if line.startswith('        if not img["multiscale"]')
    )
    return "".join(head + g9 + theirs[j:])


resolve("python/rang/core_config.py", [none, config_refusals])
resolve("python/rang/core_pipeline.py", [both])
resolve("CHANGELOG.md", [both])
resolve("research/tool-timings.md", [both])
