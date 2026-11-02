# Tigger: ModelHTML.load calls eval on mdlval

Repository: ratt-ru/tigger-lsm. Status: **filed 2026-11-02 (U4), https://github.com/ratt-ru/tigger-lsm/issues/56**. Security policy checked first
(2026-11-02): no `SECURITY.md` in the repository, no organisation `.github` repository,
GitHub private vulnerability reporting disabled, nothing in the README; so a public issue,
as the owner approved. Reproduced by U4 on 1.8.0 with a harmless arithmetic expression only
([../u4-upstream-files/tigger_repro.py](../u4-upstream-files/tigger_repro.py)); `master`
11131bec has the same line.

<!-- issue-title: ModelHTML.load uses eval on mdlval; ast.literal_eval would cover the values Tigger writes -->
<!-- issue-body -->
In astro-tigger-lsm 1.8.0, and on `master` (11131bec), `Tigger/Models/Formats/ModelHTML.py` line 134 evaluates the `mdlval` attribute of each element when a `.lsm.html` file is loaded:

```python
obj = typeobj(eval(mdlval))
```

`mdlval` comes straight from the file, so a crafted `.lsm.html` runs code when it is loaded. These files are often passed between people and pipelines. To confirm the path, I replaced `mdlval="2.0"` for a source's Stokes I with `mdlval="1+1+1"`, and `ModelHTML.load` returned I = 3.0.

`ast.literal_eval` looks like a direct replacement. All 76 `mdlval` values in a file written by `ModelHTML.save` for a two-source model (strings, numbers) parse with it. Non-finite floats (`nan`, `inf`) may need a small special case; I did not test those.

I found no security policy in the repository, so I am reporting this here. Happy to move it elsewhere if you prefer.
<!-- /issue-body -->
