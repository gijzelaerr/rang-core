# How-to guides for astronomers

Task pages for a MeerKAT L-band Measurement Set. They assume rang installed
from source ({doc}`../installation`; 0.1.0 on PyPI lacks the chain) and the
{doc}`../quickstart` done once.

| Guide | Covers |
| --- | --- |
| {doc}`image-your-ms` | the configuration for your fields, `config check`, `run`, resume, the run directory, `gemclean` directly |
| {doc}`calibrate` | CARACal's 1GC terms (K, G, B, A, F), polarisation (Gpol, KCROSS, Xf, Df), apply, self-calibration, memory |
| {doc}`flag` | the Tricolour port, strategies, static masks, flag versions and restore |
| {doc}`check-results` | receipts, stage summaries, tables, images, and how to compare with CARACal or WSClean |
| {doc}`../limits` | what rang does not do and where it differs from the tools it was checked against |

```{warning}
rang-core is a tested research demonstrator, not an operational
calibrator. The v0.2.0 gates on real data have not reported
({doc}`../limits`). Compare against your usual pipeline before relying on an
image, and report what differs ({doc}`../contributing`).
```

With an agent: the procedure {doc}`../agents/image-a-meerkat-ms` takes an
agent through the same steps on your MS and ends in a short run record.

```{toctree}
:hidden:

image-your-ms
calibrate
flag
check-results
```
