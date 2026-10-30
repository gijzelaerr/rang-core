"""Compatibility module: the Tigger ASCII reader moved to `rang.formats.sky`
(research/dfio-formats.md). Everything `rang.lsm` exported is re-exported
unchanged, private helpers included, so that L1-M's callers and archives
keep working."""

from .formats import sky as _sky
from .formats.sky import (  # noqa: F401
    ANGLE_UNITS,
    DEFAULT_FORMAT,
    MAX_SPI_TERMS,
    Source,
    _dec,
    _extent,
    _float,
    _ra,
    components,
    direction_cosines,
    load,
    loads,
    parse_format,
    parse_line,
    summary,
)

__all__ = [
    "DEFAULT_FORMAT",
    "Source",
    "components",
    "direction_cosines",
    "load",
    "loads",
    "parse_format",
    "parse_line",
    "summary",
]

del _sky
