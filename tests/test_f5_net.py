"""F5 (research/f5-flagger.md, section 2f): the PyTorch port of F3's and F4's
network against the Rust kernels (`f3flag_logits`, `f4flag_logits`), its
initialisation against `rang.f3net`'s, the weight counts, the flat-order round
trip and the ONNX export, on small synthetic scans."""

import numpy as np
import pytest
from rang import f3flag as f3
from rang import f3net, f5net
from rang import f4flag as f4

from tests.test_f4_flag import synthetic

torch = pytest.importorskip("torch")


def _torch_logits(net, x):
    with torch.no_grad():
        return net(torch.from_numpy(np.ascontiguousarray(x, np.float32))).numpy()


def _check(zr, zt, eligible):
    d = np.abs(zr - zt)[eligible]
    assert np.quantile(d, 0.999) <= 1e-4
    assert d.max() <= 1e-3
    assert np.mean((zr > 0)[eligible] != (zt > 0)[eligible]) <= 1e-5


def test_weight_counts():
    assert f5net.weight_count(15, False) == 3433
    assert f5net.weight_count(23, False) == 4009
    assert f5net.weight_count(33, True) == 3201
    net = f5net.build(33, True)
    assert sum(p.numel() for p in net.parameters()) == 3201


def test_init_is_f3nets_and_round_trips():
    for nplanes in (15, 23):
        a = f5net.init_arrays(5, nplanes, False)
        b = f3net.init_params(5, nplanes)
        assert all(
            np.array_equal(x, y) and np.array_equal(u, v)
            for (x, u), (y, v) in zip(a, b, strict=True)
        )
        assert np.array_equal(f5net.flat_from_arrays(a), f3net.flat_weights(b))
    for stem in (False, True):
        a = f5net.init_arrays(7, 33, stem)
        flat = f5net.flat_from_arrays(a)
        net = f5net.build(33, stem, f5net.arrays_from_flat(flat, 33, stem))
        assert np.array_equal(f5net.flat_from_arrays(f5net.to_arrays(net)), flat)


@pytest.mark.parametrize("kind", ["f3", "f4"])
def test_port_matches_the_rust_kernels(kind):
    scan = synthetic(phases=True)
    flagged = scan["input_flags"].any(-1)
    ix = f3.index(scan)
    sel = np.arange(len(ix["ubl"]))
    mod, nplanes = (f3, 15) if kind == "f3" else (f4, 23)
    arrays = f5net.init_arrays(11, nplanes, False)
    # Non-zero biases, so the bias order is checked too.
    rng = np.random.default_rng(1)
    arrays = [(w, rng.normal(0, 0.1, b.shape).astype(np.float32)) for w, b in arrays]
    x = mod.rust_features(scan, flagged, sel)
    zt = _torch_logits(f5net.build(nplanes, False, arrays), x)[ix["bl"], ix["t"]]
    zr = mod.rust_logits(scan, flagged, f5net.flat_from_arrays(arrays))
    _check(zr, zt, ~flagged)


def test_stem_is_a_linear_1x1_map():
    rng = np.random.default_rng(2)
    a = f5net.init_arrays(3, 33, True)
    net = f5net.build(33, True, a)
    x = rng.normal(0, 1, (2, 5, 40, 33)).astype(np.float32)
    w, b = a[0]
    h = x @ w + b  # (2, 5, 40, 8)
    rest = f5net.build(8, False, a[1:])
    _check(_torch_logits(rest, h), _torch_logits(net, x), np.ones((2, 5, 40), bool))


def test_bce_ignores_minus_one():
    z = torch.tensor([[2.0, -1.0, 0.5]])
    y = torch.tensor([[1, -1, 0]], dtype=torch.int8)
    want = (np.log1p(np.exp(-2.0)) + (0.5 + np.log1p(np.exp(-0.5)))) / 2
    assert abs(float(f5net.bce(z, y)) - want) < 1e-6


def test_onnx_export_carries_the_header(tmp_path):
    onnx = pytest.importorskip("onnx")
    from onnx.reference import ReferenceEvaluator

    net = f5net.build(33, True, seed=4)
    path = tmp_path / "n5.onnx"
    f5net.export_onnx(net, path, {"stage": "flag", "architecture": "f5-n5"})
    model = onnx.load(str(path))
    onnx.checker.check_model(model)
    meta = {p.key: p.value for p in model.metadata_props}
    assert '"architecture": "f5-n5"' in meta["rang.learned"]
    x = np.random.default_rng(5).normal(0, 1, (1, 6, 64, 33)).astype(np.float32)
    (zo,) = ReferenceEvaluator(model).run(None, {"planes": x})
    _check(zo, _torch_logits(net, x), np.ones((1, 6, 64), bool))
