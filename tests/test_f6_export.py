"""F6 (research/f6-flagger.md): the weights file in the swap contract's form.
N5's network exported NCHW, Conv and Relu only, loads through
`rang.learned.load` (the contract's metadata and interpreter checks), and the
contract's reference runtime matches PyTorch."""

import numpy as np
import pytest
from rang import f5net, learned

torch = pytest.importorskip("torch")
pytest.importorskip("onnx")


def header(nplanes):
    return {
        "format": learned.FORMAT,
        "stage": "flag",
        "data_class": "calibrator",
        "telescope": "MeerKAT",
        "band": "L",
        "architecture": {
            "id": "f5-n5",
            "hyperparameters": {
                "inputs": nplanes,
                "hidden": 8,
                "dilations": [1, 2, 4, 8, 16],
                "stem": True,
            },
        },
        "inputs": {"planes": [nplanes, "T", "F"]},
        "outputs": {"logits": [1, "T", "F"]},
        "normalisation": {"planes": "asinh, F5 section 2"},
        "training": {"framework": "torch"},
        "gates": {},
        "envelope": {"channel_width_hz": [208984.375, 208984.375]},
        "licence": f5net.WEIGHTS_LICENCE,
        "source": "tests/test_f6_export.py; " + f5net.SARAO_ACKNOWLEDGEMENT,
    }


@pytest.mark.parametrize("stem", [True, False])
def test_export_loads_through_the_contract_and_matches_torch(tmp_path, stem):
    n = 33
    rng = np.random.default_rng(4)
    arrays = [
        (w, rng.normal(0, 0.1, b.shape).astype(np.float32))
        for w, b in f5net.init_arrays(6, n, stem)
    ]
    net = f5net.build(n, stem, arrays)
    path = f5net.export_onnx_nchw(net, tmp_path / "n5.onnx", header(n))
    w = learned.load(path)
    assert set(w.ops) <= {"Conv", "Relu"}
    assert w.header.licence == "CC-BY-4.0"
    assert "South African Radio Astronomy Observatory" in w.header.source
    x = rng.normal(0, 1, (2, n, 12, 64)).astype(np.float32)
    with torch.no_grad():
        want = net(
            torch.from_numpy(x.transpose(0, 2, 3, 1).copy())
        ).numpy()  # (N, T, F)
    got = learned.run_reference(w, x)
    assert got.shape == (2, 1, 12, 64)
    d = np.abs(got[:, 0] - want)
    assert np.quantile(d, 0.999) <= 1e-4 and d.max() <= 1e-3
