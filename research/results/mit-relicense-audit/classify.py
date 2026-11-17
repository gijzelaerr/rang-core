# SPDX-License-Identifier: MIT
"""Per-file provenance classes of the shipped sources (research/mit-relicense-audit.md).

Writes files.csv beside this script and prints the totals per class and per
upstream. Files not listed in CLASSES are class a (own original). Line counts
are the line counts of the tracked files in the working tree.

    python research/results/mit-relicense-audit/classify.py
"""

import csv
import subprocess
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent

# path: (class, upstream, upstream licence, upstream files and version, derived lines estimate)
CLASSES = {
    # imaging outside GeMClean
    "core/src/wgridder.rs": (
        "b-copyleft",
        "ducc0",
        "GPL-2.0-or-later",
        "ducc0 0.42.0 (42ce8ab5) wgridder_impl.h, gridding_kernel.{h,cc} (KernelDB rows verbatim), gl_integrator.*; fft.h good_size_cmplx (BSD-3-Clause OR GPL-2.0-or-later)",
        3550,
    ),
    "core/src/grid.rs": (
        "b-copyleft",
        "WSClean",
        "GPL-3.0 (wstackinggridder.h: 'GPL 3 license', no or-later)",
        "WSClean 3.6-1 wstackinggridder.{cpp,h}, wsmsgridder.cpp, msgridderdata.h, msprovidercollection.cpp, wsclean.cpp",
        850,
    ),
    "core/src/weights.rs": (
        "b-copyleft",
        "WSClean",
        "GPL-3.0; schaapcommon GPL-3.0-or-later",
        "WSClean 3.6 structures/imageweights.*, 3.7 Set*Taper; schaapcommon reordering.cc (549bc69f); aocommon polarization.h",
        560,
    ),
    "core/src/gpu/shader.rs": (
        "b-copyleft",
        "WSClean",
        "GPL-3.0 (through grid.rs); fdlibm constants (Sun, permissive)",
        "AddDataSample, projectOnImageAndCorrect as in grid.rs",
        180,
    ),
    "python/rang/core_grid.py": (
        "b-copyleft",
        "WSClean",
        "GPL-3.0",
        "makeKaiserBesselKernel transcription (kernel_reference); Stokes I reader",
        60,
    ),
    "python/rang/formats/sky.py": (
        "b-copyleft",
        "Tigger",
        "GPL-2.0-or-later",
        "Tigger ModelClasses.renderAttrMarkup, ModelHTML.save (writer); readers c-src from Tigger, Crystalball 0.4.3, DDFacet 1.0, killMS 3.3.0 (GPL-2.0); two regexes from codex-africanus 0.4.4 (BSD-3-Clause)",
        170,
    ),
    "core/src/predict.rs": (
        "b-permissive",
        "codex-africanus",
        "BSD-3-Clause",
        "0.4.4 rime/wsclean_predict.py, model/wsclean/spec_model.py",
        180,
    ),
    "core/src/correct.rs": (
        "c-src",
        "WSClean",
        "GPL-3.0-or-later (schaapcommon)",
        "schaapcommon reordering.cc Stokes I rule",
        10,
    ),
    "python/rang/core_weights.py": (
        "c-src",
        "WSClean",
        "GPL-3.0",
        "aocommon BandData wavelengths; WSClean angle parser",
        10,
    ),
    "python/rang/core_model.py": (
        "c-src",
        "WSClean",
        "GPL-3.0",
        "WSClean 3.6 msprovider.cpp row and cell rules",
        15,
    ),
    "core/src/gpu/fft.rs": (
        "c",
        "-",
        "-",
        "Stockham FFT from a published description",
        0,
    ),
    # GeMClean
    "core/src/gemclean.rs": (
        "b-copyleft",
        "schaapcommon",
        "GPL-3.0-or-later; WSClean GPL-3.0",
        "schaapcommon b553fd25 gaussianfitter.cc Fit2DGaussianCentred; WSClean 3.7 imageoperations.cpp FitBeamSize; radler Perform glue (c-src)",
        65,
    ),
    "core/src/gemclean/multiscale.rs": (
        "b-copyleft",
        "radler",
        "LGPL-3.0-only",
        "radler 76fe4474 multiscale_algorithm.cc, subminor_loop.cc, multiscale_transforms.h; WSClean 3.7 and 53e25d59 CalculateMsLimits",
        800,
    ),
    "core/src/gemclean/mask.rs": (
        "b-copyleft",
        "radler",
        "LGPL-3.0-only; aocommon GPL-3.0",
        "radler 76fe4474 radler.cc Perform, gain_calculations.h; aocommon aa4d6a47 image.h MedianAndStdDevFromMAD",
        220,
    ),
    "core/src/gemclean/stokes.rs": (
        "b-copyleft",
        "aocommon",
        "GPL-3.0; radler LGPL-3.0-only; schaapcommon GPL-3.0-or-later",
        "aocommon aa4d6a47 polarization.h ParseList; radler image_set.h; schaapcommon reordering.cc",
        165,
    ),
    "core/src/gemclean/input.rs": (
        "b-copyleft",
        "schaapcommon",
        "GPL-3.0-or-later",
        "schaapcommon b553fd25 reordering.cc ExtractData, ExtractWeights (stokes_cell); WSClean selection rules c-src",
        24,
    ),
    "core/src/gemclean/cli.rs": (
        "c-src",
        "WSClean",
        "GPL-3.0",
        "WSClean 3.7 commandline.cpp, wsclean.cpp, settings.cpp behaviour (option names: interface; help text own; one error phrase)",
        300,
    ),
    "core/src/gemclean/joined.rs": (
        "c-src",
        "radler",
        "LGPL-3.0-only",
        "radler generic_clean.cc, subminor_loop.cc, image_set.cc flow (v030-fix header: AND LGPL-3.0-only)",
        60,
    ),
    "core/src/gemclean/predict.rs": (
        "c-src",
        "WSClean",
        "GPL-3.0",
        "WSClean 3.6 msprovider.cpp, 3.7 FillModelColumn behaviour",
        50,
    ),
    "core/src/gemclean/spectral.rs": (
        "c-src",
        "schaapcommon",
        "GPL-3.0-or-later",
        "schaapcommon spectralfitter.cc conventions; WSClean channel split",
        40,
    ),
    # calibration
    "core/src/cal/fluxscale.rs": (
        "b-copyleft",
        "CASA",
        "LGPL-2.0-or-later",
        "casa6 9269a52 and 6.7.6.14 SolvableVisCal.cc fluxscale; casacore 3.7.1 LSQFit.cc, median",
        350,
    ),
    "core/src/cal/reference.rs": (
        "b-copyleft",
        "CASA",
        "LGPL-2.0-or-later",
        "casa6 9269a52 SolvableVisCal.cc applyRefAnt, verifyConstraints",
        185,
    ),
    "core/src/cal/bandpass.rs": (
        "b-copyleft",
        "CASA",
        "LGPL-2.0-or-later",
        "casa6 9269a52 StandardVisCal.cc BJones::fillChanGapArray",
        90,
    ),
    "core/src/cal/apply.rs": (
        "b-copyleft",
        "CASA",
        "LGPL-2.0-or-later",
        "RIorAParray.cc trackPhase (fragment); rest c-src from Jones.cc, VisCal.cc, CTPatchedInterp.cc, CTTimeInterp1.cc, casacore Interpolate1D",
        30,
    ),
    "core/src/cal/crosshand.rs": (
        "b-copyleft",
        "CASA",
        "LGPL-2.0-or-later",
        "KJones.cc DelayFFT::searchPeak (fragment); rest c-src from KcrossJones, XJones, VisEquation",
        27,
    ),
    "python/rang/cal_pol.py": (
        "b-copyleft",
        "casacore",
        "LGPL-2.0-or-later",
        "casacore measures MCDirection.cc, MeasMath.cc, MeasTable.cc, MSDerivedValues.cc (parallactic_angle_casa; v030-fix notice: a translation of the steps and constants); XJones, VisEquation c-src",
        70,
    ),
    "python/rang/cal_refant.py": (
        "b-copyleft",
        "CARACal",
        "GPL-2.0 (only or or-later unstated); msutils GPL-2.0",
        "CARACal 8f7bb363 get_refant (c-src); msutils 1.2.0 wgs84_to_ecef operation by operation",
        20,
    ),
    "python/rang/beam_holography.py": (
        "b-copyleft",
        "EIDOS",
        "GPL-3.0",
        "EIDOS 1.1.2 recon_par (_reconstruct), a comparison control",
        24,
    ),
    "core/src/cal/leakage.rs": (
        "c-src",
        "CASA",
        "LGPL-2.0-or-later",
        "DJones.cc guessPar, Jones GenLinear",
        0,
    ),
    "core/src/cal/diag.rs": (
        "c-src",
        "CASA",
        "LGPL-2.0-or-later; QuartiCal MIT",
        "QuartiCal 0.2.7 diag kernels (b-permissive, about 1,000 lines); CASA VisCalSolver2 SNR formula (823-905)",
        80,
    ),
    "core/src/caltable.rs": (
        "c-src",
        "CASA",
        "LGPL-2.0-or-later",
        "NewCalTable writeToDisk sequence",
        0,
    ),
    "python/rang/applycal.py": (
        "c-src",
        "CASA",
        "GPL-2.0-or-later (Calibrater.cc)",
        "Calibrater.cc, CTPatchedInterp.cc, VisJones::updateWt2 rules",
        0,
    ),
    "python/rang/cal_bandpass.py": (
        "c-src",
        "CASA",
        "LGPL-2.0-or-later",
        "StandardVisCal, Calibrater::genericGatherAndSolve",
        0,
    ),
    "python/rang/cal_delay.py": (
        "c-src",
        "CASA",
        "LGPL-2.0-or-later",
        "KJones.cc, Calibrater.cc rules",
        0,
    ),
    "python/rang/cal_fluxscale.py": (
        "c-src",
        "CASA",
        "GPL-2.0-or-later",
        "Calibrater::fluxscale, SolvableVisJones::fluxscale",
        0,
    ),
    "python/rang/cal_gain.py": (
        "c-src",
        "CASA",
        "LGPL-2.0-or-later",
        "VisEquation collapse2, divideCorrByModel, SolveDataBuffer enforceAPonData",
        0,
    ),
    "python/rang/cal_selfcal.py": (
        "c-src",
        "CARACal",
        "GPL-2.0",
        "CARACal selfcal worker; CubiCal semantics",
        0,
    ),
    "python/rang/cal_apply.py": (
        "c-src",
        "CARACal",
        "GPL-2.0",
        "CARACal 8f7bb363 interpolation table",
        0,
    ),
    "python/rang/cal_chain.py": (
        "c-src",
        "CARACal",
        "GPL-2.0",
        "CARACal crosscal and polcal worker order",
        0,
    ),
    "python/rang/calmodels.py": (
        "c-src",
        "CASA",
        "LGPL-2.0-or-later",
        "CASA Imager.cc sjy_setmanualflux; casacore SpectralIndex, SkyCompRep, Flux, Polynomial; CARACal nrao_xcal.yml values",
        0,
    ),
    "python/rang/formats/caltable.py": (
        "c-src",
        "CASA",
        "LGPL-2.0-or-later",
        "CTPatchedInterp, RIorAParray, CTTimeInterp1, KJones, DJones, XJones",
        0,
    ),
    "core/src/solve.rs": (
        "b-permissive",
        "QuartiCal",
        "MIT",
        "QuartiCal 0.2.7 complex kernel and flagging",
        2000,
    ),
    "core/src/cal/delay.rs": (
        "b-permissive",
        "QuartiCal",
        "MIT",
        "QuartiCal 0.2.7 delay",
        1000,
    ),
    "core/src/cal/delay_offset.rs": (
        "b-permissive",
        "QuartiCal",
        "MIT",
        "QuartiCal 0.2.7 delay_and_offset",
        1000,
    ),
    "core/src/fluxstd.rs": (
        "c",
        "-",
        "-",
        "Perley and Butler 2017, Baars 1977 coefficients (papers)",
        0,
    ),
    "python/rang/fluxstd.py": (
        "c",
        "-",
        "-",
        "papers; PB2010, SR2016 and Baars fitted to setjy outputs",
        0,
    ),
    # flagging and table IO
    "core/src/ms_write.rs": (
        "b-copyleft",
        "casacore",
        "LGPL-2.0-or-later",
        "casacore 3.8.1 SSMBase, SSMIndex, SSMStringHandler, StManArrayFile, FilebufIO, BucketCache, TSMCube (L927-4754); the rest c-src",
        3830,
    ),
    "core/src/ism.rs": (
        "b-copyleft",
        "casacore",
        "LGPL-2.0-or-later",
        "casacore 3.8.1 ISMBase, ISMBucket, ISMColumn, ISMIndColumn, ISMIndex, BucketCache (step for step)",
        2100,
    ),
    "core/src/multifile.rs": (
        "b-copyleft",
        "casacore",
        "LGPL-2.0-or-later",
        "casacore MultiFile, MultiFileBase",
        600,
    ),
    "core/src/tiled.rs": (
        "b-copyleft",
        "casacore",
        "LGPL-2.0-or-later",
        "casacore 3.8.1 TiledStMan::makeTileShape, TSMCube::adjustTileShape",
        230,
    ),
    "core/src/flag_extend.rs": (
        "b-copyleft",
        "CASA",
        "LGPL-2.1-or-later",
        "casa6 9269a52 FlagAgentExtension.cc computeAntennaPairFlags",
        125,
    ),
    "core/src/ms_schema.rs": (
        "d",
        "casacore",
        "LGPL-2.0-or-later (schema strings)",
        "MS v2 and NewCalTable column names, comments and keywords from table.dat written by casacore 3.8.1 and CASA 6.7.6 (interface data)",
        2130,
    ),
    "core/src/ms.rs": (
        "c-src",
        "casacore",
        "LGPL-2.0-or-later",
        "casacore 3.8.1 table format sources (core-e-ms-reader.md)",
        0,
    ),
    "core/src/aipsio.rs": (
        "c-src",
        "casacore",
        "LGPL-2.0-or-later",
        "AipsIO.cc, TypeIO.cc, RecordDesc.cc, RecordRep.cc",
        0,
    ),
    "core/src/ms_desc.rs": (
        "c-src",
        "casacore",
        "LGPL-2.0-or-later",
        "BaseTable, TableDesc, ColumnSet::putFile",
        0,
    ),
    "core/src/ms_create.rs": (
        "c-src",
        "casacore",
        "LGPL-2.0-or-later",
        "SetupNewTable::bindCreate, MeasurementSet::createDefaultSubtables",
        0,
    ),
    "python/rang/formats/_aipsio.py": (
        "c-src",
        "casacore",
        "LGPL-2.0-or-later",
        "through the Rust parser",
        0,
    ),
    "python/rang/flag_extend.py": (
        "c-src",
        "CASA",
        "LGPL-2.0-or-later",
        "casacore MSIter MSInterval::comp, BaseTabIter; CASA FlagDataHandler, FlagMSHandler",
        30,
    ),
    "python/rang/formats/killms.py": (
        "c-src",
        "killMS",
        "GPL-2.0",
        "killMS 3.3.0 kMS.py, MergeSols.py field list",
        0,
    ),
    "core/src/sumthreshold.rs": (
        "b-permissive",
        "Tricolour",
        "BSD-3-Clause",
        "Tricolour 0.2.1 and katsdpsigproc twodflag.py",
        1330,
    ),
    "core/src/blosc.rs": (
        "b-permissive",
        "c-blosc",
        "BSD-3-Clause",
        "c-blosc 1.21.6 blosc_d, shuffle-sse2.c (notice missing)",
        150,
    ),
    "python/rang/meerkat.py": (
        "b-permissive",
        "katdal",
        "BSD-3-Clause",
        "katdal 0.23 test helpers, flags.py (BSD text missing)",
        230,
    ),
    "python/rang/core_flag.py": (
        "b-permissive",
        "Tricolour",
        "BSD-3-Clause",
        "Tricolour 0.2.1 defaults, load_mask (SPDX line GPL only)",
        45,
    ),
    "python/rang/flagdata.py": (
        "c",
        "-",
        "-",
        "CASA flagdata documentation and probes",
        0,
    ),
    "python/rang/tfcrop.py": ("c", "-", "-", "CASA tfcrop documentation and probes", 0),
    "python/rang/listobs.py": ("c", "-", "-", "CASA listobs output layout", 0),
    "python/rang/oracles/casa_listobs.py": ("c", "-", "-", "CASA listobs output", 0),
    "python/rang/formats/h5parm.py": (
        "c-src",
        "losoto",
        "GPL-3.0-or-later",
        "losoto 2.7.1 sdist read for the H5parm layout (dfio-formats.md:37); attribute values from a losoto-made file",
        0,
    ),
    "python/rang/formats/flagversions.py": (
        "c",
        "-",
        "-",
        "CASA flagmanager on-disk layout",
        0,
    ),
    "python/rang/formats/quartical_store.py": (
        "c",
        "-",
        "-",
        "QuartiCal and dask-ms layout",
        0,
    ),
    # orchestration
    "python/rang/core_pipeline.py": (
        "c-src",
        "CARACal",
        "GPL-2.0",
        "CARACal 8f7bb363 crosscal, polcal and selfcal worker recipe",
        310,
    ),
    "python/rang/core_config.py": (
        "c-src",
        "CARACal",
        "GPL-2.0",
        "CARACal 8f7bb363 selfcal_worker image(), schema defaults",
        60,
    ),
    # tests
    "tests/test_e0_refant_extend.py": (
        "b-copyleft",
        "CASA",
        "LGPL-2.1-or-later",
        "FlagAgentExtension.cc loops transcribed (casa_cube)",
        40,
    ),
    "tests/test_cal_fluxscale.py": (
        "c-src",
        "CASA",
        "LGPL-2.0-or-later",
        "SolvableVisJones::fluxscale rules in NumPy",
        56,
    ),
    "tests/test_a3_casa_phase_weights.py": (
        "c-src",
        "CASA",
        "LGPL-2.0-or-later",
        "divideCorrByModel in NumPy",
        27,
    ),
}

ORDER = ["a", "b-permissive", "b-copyleft", "c-src", "c", "d"]


def shipped():
    out = subprocess.run(
        [
            "git",
            "-C",
            str(ROOT),
            "ls-files",
            "core/src",
            "core/py/src",
            "src",
            "python/rang",
            "tests",
            "tools/check.py",
            "tools/wheel",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return [p for p in out if Path(p).suffix in {".rs", ".py", ".sh", ".wgsl"}]


def main():
    files = shipped()
    missing = set(CLASSES) - set(files)
    assert not missing, missing
    rows = []
    for p in files:
        n = len((ROOT / p).read_bytes().splitlines())
        cls, up, lic, what, derived = CLASSES.get(p, ("a", "-", "-", "-", 0))
        rows.append((p, n, cls, up, lic, what, derived))
    with open(HERE / "files.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(
            [
                "path",
                "lines",
                "class",
                "upstream",
                "licence",
                "upstream_files",
                "derived_lines_est",
            ]
        )
        w.writerows(rows)
    per = defaultdict(lambda: [0, 0, 0])
    perup = defaultdict(lambda: [0, 0, 0])
    for _, n, cls, up, _, _, d in rows:
        for acc in (per[cls], perup[(up, cls)] if up != "-" else [0, 0, 0]):
            acc[0] += 1
            acc[1] += n
            acc[2] += d
    print("| class | files | lines | derived lines (est.) |")
    for k in ORDER:
        print(f"| {k} | {per[k][0]} | {per[k][1]:,} | {per[k][2]:,} |")
    print(
        f"| total | {len(rows)} | {sum(r[1] for r in rows):,} | {sum(r[6] for r in rows):,} |"
    )
    print()
    print("| upstream | class | files | lines | derived lines (est.) |")
    for (up, cls), v in sorted(perup.items(), key=lambda kv: -kv[1][1]):
        print(f"| {up} | {cls} | {v[0]} | {v[1]:,} | {v[2]:,} |")


if __name__ == "__main__":
    main()
