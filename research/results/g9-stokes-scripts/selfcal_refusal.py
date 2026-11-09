"""selfcal_refusal.py : with main a2450aa's C5, self-calibration images through image.* and predicts
`<name>-model.fits`, a Stokes I model; refuse selfcal when image.pol is not I (a follow-up of
research/g9-stokes.md), and test it (merge edit)."""

W = "/home/gijsm/Worktrees/rang/fp-g9-stokes/"
p = W + "python/rang/core_config.py"
s = open(p).read()
old = """    if "selfcal" in stages:
        sc = config["selfcal"]
"""
new = """    if "selfcal" in stages:
        sc = config["selfcal"]
        if config["image"]["pol"] != "I":
            out.append(
                Refusal(
                    "image.pol",
                    "",
                    "self-calibration predicts a Stokes I model; selfcal with "
                    f"pol: {config['image']['pol']!r} is a follow-up of "
                    "research/g9-stokes.md, not implemented",
                )
            )
"""
assert s.count(old) == 1
s = s.replace(old, new, 1)
open(p, "w").write(s)

t = W + "tests/test_w2_commands.py"
s = open(t).read()
old = """    raw = core_config.load(DATA / "e2b.yaml")
    config, errors = core_config.resolve(raw)
    assert errors == []
    assert not ["""
new = """    config, errors = core_config.resolve(
        {"version": 1, "image": {**image, "join_polarizations": False}}
    )
    assert errors == []
    assert "image.pol" in {r.path for r in core_config.refusals(config, ["selfcal"])}
    raw = core_config.load(DATA / "e2b.yaml")
    config, errors = core_config.resolve(raw)
    assert errors == []
    assert not ["""
assert s.count(old) == 1
s = s.replace(old, new, 1)
open(t, "w").write(s)
