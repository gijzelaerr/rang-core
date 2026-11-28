# SPDX-License-Identifier: MIT
"""rang passes data.memory_limit_gb to gemclean as -memory-limit (issue #34,
research/gemclean-memlimit.md); the binary's own check is tested in
core/tests/gemclean_memlimit.rs."""

from rang import core_config
from rang import core_pipeline as pipe


def _config(extra=""):
    raw = core_config.loads("version: 1\nimage: {size: 64, scale: 2asec}\n" + extra)
    config, errors = core_config.resolve(raw)
    assert errors == []
    return config


def test_no_limit_no_option():
    img = _config()["image"]
    args = pipe.gemclean_arguments(img, "DATA", 0, "x/image", "x.ms")
    assert "-memory-limit" not in args


def test_limit_before_the_extra_arguments():
    config = _config("data: {memory_limit_gb: 12.5}\n")
    config["image"]["extra_args"] = ["-memory-report"]
    limit = pipe._memory_limit(config)
    assert limit == 12.5
    args = pipe.gemclean_arguments(
        config["image"], "DATA", 0, "x/image", "x.ms", (), False, limit
    )
    i = args.index("-memory-limit")
    assert args[i + 1] == "12.5"
    assert args.index("-no-update-model-required") < i < args.index("-memory-report")
    assert args[-1] == "x.ms"


def test_default_limit_is_passed_whole():
    config = _config("data: {processes: 4}\n")
    assert pipe._memory_limit(config) == 8.0
