"""Task G7 (research/g7-defaults.md): gemclean's gridder defaults as rang-core sees them."""

from rang import core_config, core_pipeline


def test_image_accuracy_default_is_coarse():
    assert core_config.SCHEMA["image"]["wgridder_accuracy"].default == 1e-4


def test_model_precision_follows_gemclean():
    single = core_pipeline._gridder_single
    assert single({"wgridder_accuracy": 1e-4}, [])
    assert not single({"wgridder_accuracy": 1e-6}, [])
    assert not single({"wgridder_accuracy": 1e-4}, ["-double"])
    assert single({"wgridder_accuracy": 1e-6}, ["-single"])
    assert not single({"wgridder_accuracy": 1e-4}, ["-single", "-double"])
