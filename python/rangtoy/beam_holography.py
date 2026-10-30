"""MeerKAT L-band holography beams as rang's reference beam (B1-0).

research/b1-beam-pointing.md freezes the product: SARAO's 2023 holography
release (de Villiers 2023, AJ 165, 78; data DOI 10.48479/wdb0-h061, licence
CC BY-NC 4.0), read by HTTP range from the stored (not deflated)
`MeerKAT_L_band_primary_beam.npz`: complex64 voltage Jones maps (pol HH, HV,
VH, VV; antennas m000-m063 and `array_average`; 1024 channels; 128 x 128
pixels of 0.0625 deg, centre index 64). Nothing from the release is
redistributed here; the product lives under `outputs/`.

One sampler interface serves the predictor's per-component beam:
`jones(antenna, x_deg, y_deg, freq_hz) -> (..., 2, 2)` and `power_i(...)`,
both normalised per frequency so that the Stokes I power beam is 1 at the
beam-coordinate origin. katbeam and EIDOS sit behind the same interface as
controls. Beam coordinates are antenna-frame degrees: x cross-elevation,
y elevation; sky (l, m) to (x, y) is the caller's parallactic rotation.

Interpolation (frozen): cubic spline in space on the real and imaginary
parts of each Jones element, linear in frequency between product channels,
no extrapolation.
"""

import ast
import hashlib
import json
import struct
import time
import urllib.request
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy import ndimage, optimize

HOLOGRAPHY_BASE = (
    "https://archive-gw-1.kat.ac.za/public/repository/10.48479/wdb0-h061/data/"
)
L_BAND_URL = HOLOGRAPHY_BASE + "MeerKAT_L_band_primary_beam.npz"
L_BAND_METRICS_URL = HOLOGRAPHY_BASE + "MeerKAT_L_band_primary_beam_metrics.npz"
CITATION = (
    "de Villiers M. S. (2023), MeerKAT Holography Measurements in the UHF, L, "
    "and S bands, V1, South African Radio Astronomy Observatory, "
    "doi:10.48479/wdb0-h061; AJ 165, 78"
)
LICENCE = "CC BY-NC 4.0"
POLS = ("HH", "HV", "VH", "VV")
NANT = 65
ARRAY_AVERAGE = 64
NCHAN = 1024
NPIX = 128
PIXEL_DEG = 0.0625
CENTRE_INDEX = 64
# Product channels (frozen): every 11th native channel plus the top one.
PRODUCT_CHANNELS = tuple(range(0, NCHAN, 11)) + (NCHAN - 1,)
COMPARISON_BAND_HZ = (900e6, 1650e6)


# --------------------------------------------------------------------------
# Remote stored-npz access by HTTP range


def _http_range(url, start, length, retries=6):
    """`length` bytes of `url` from byte `start`."""
    error = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(
                url, headers={"Range": f"bytes={start}-{start + length - 1}"}
            )
            with urllib.request.urlopen(request, timeout=300) as response:
                data = response.read()
            if len(data) == length:
                return data
            error = ValueError(f"short read {len(data)} of {length}")
        except OSError as exc:
            error = exc
        time.sleep(min(2**attempt, 30))
    raise OSError(f"range {start}+{length} of {url} failed: {error!r}")


def _http_size(url):
    request = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(request, timeout=60) as response:
        return int(response.headers["Content-Length"]), dict(response.headers)


def file_reader(path):
    """A `read(start, length)` callable over a local file."""
    path = Path(path)

    def read(start, length):
        with path.open("rb") as stream:
            stream.seek(start)
            data = stream.read(length)
        if len(data) != length:
            raise OSError(f"short read of {path}")
        return data

    read.size = path.stat().st_size
    return read


def http_reader(url):
    """A `read(start, length)` callable over HTTP range requests."""

    def read(start, length):
        return _http_range(url, start, length)

    read.size, read.headers = _http_size(url)
    return read


def npz_members(read):
    """Members of a zip (npz) through `read(start, length)` with `read.size`:
    name -> {method, size, data_offset, npy header and array_offset}.

    Handles zip64. Only stored (method 0) members get an npy header, since
    only those can be range-read; the npy header is parsed with
    `ast.literal_eval` (no pickle)."""
    size = read.size
    tail_length = min(size, 65536 + 22)
    tail = read(size - tail_length, tail_length)
    at = tail.rfind(b"PK\x05\x06")
    if at < 0:
        raise ValueError("no end-of-central-directory record")
    count = struct.unpack("<H", tail[at + 10 : at + 12])[0]
    cd_size, cd_offset = struct.unpack("<II", tail[at + 12 : at + 20])
    locator = tail.rfind(b"PK\x06\x07")
    if locator >= 0:
        record_offset = struct.unpack("<Q", tail[locator + 8 : locator + 16])[0]
        record = read(record_offset, 56)
        count, cd_size, cd_offset = struct.unpack("<QQQ", record[32:56])
    directory = read(cd_offset, cd_size)
    members, p = {}, 0
    for _ in range(count):
        if directory[p : p + 4] != b"PK\x01\x02":
            raise ValueError("bad central-directory entry")
        method = struct.unpack("<H", directory[p + 10 : p + 12])[0]
        csize, usize = struct.unpack("<II", directory[p + 20 : p + 28])
        name_length, extra_length, comment_length = struct.unpack(
            "<HHH", directory[p + 28 : p + 34]
        )
        local = struct.unpack("<I", directory[p + 42 : p + 46])[0]
        name = directory[p + 46 : p + 46 + name_length].decode()
        extra = directory[p + 46 + name_length : p + 46 + name_length + extra_length]
        q = 0
        while q + 4 <= len(extra):
            tag, length = struct.unpack("<HH", extra[q : q + 4])
            if tag == 1:
                values, k = extra[q + 4 : q + 4 + length], 0
                if usize == 0xFFFFFFFF:
                    usize = struct.unpack("<Q", values[k : k + 8])[0]
                    k += 8
                if csize == 0xFFFFFFFF:
                    csize = struct.unpack("<Q", values[k : k + 8])[0]
                    k += 8
                if local == 0xFFFFFFFF:
                    local = struct.unpack("<Q", values[k : k + 8])[0]
            q += 4 + length
        header = read(local, 30)
        local_name, local_extra = struct.unpack("<HH", header[26:30])
        data_offset = local + 30 + local_name + local_extra
        entry = {"method": method, "size": usize, "data_offset": data_offset}
        if method == 0 and usize >= 10:
            head = read(data_offset, min(usize, 4096))
            if head[:6] == b"\x93NUMPY":
                if head[6] == 1:
                    length, start = struct.unpack("<H", head[8:10])[0], 10
                else:
                    length, start = struct.unpack("<I", head[8:12])[0], 12
                meta = ast.literal_eval(head[start : start + length].decode("latin1"))
                entry.update(
                    descr=meta["descr"],
                    fortran_order=bool(meta["fortran_order"]),
                    shape=tuple(meta["shape"]),
                    array_offset=data_offset + start + length,
                )
        members[name] = entry
        p += 46 + name_length + extra_length + comment_length
    return members


def read_member(read, member):
    """A whole small stored npy member as an array (no pickle)."""
    dtype = np.dtype(member["descr"])
    if dtype.hasobject or member["fortran_order"]:
        raise ValueError("object or Fortran-order members are refused")
    count = int(np.prod(member["shape"]))
    raw = read(member["array_offset"], count * dtype.itemsize)
    return np.frombuffer(raw, dtype=dtype).reshape(member["shape"])


def map_offset(member, pol, antenna, channel):
    """Byte offset of the (pol, antenna, channel) map in the beam member."""
    npol, nant, nchan, ny, nx = member["shape"]
    itemsize = np.dtype(member["descr"]).itemsize
    if not (0 <= pol < npol and 0 <= antenna < nant and 0 <= channel < nchan):
        raise IndexError("map index outside the beam cube")
    return member["array_offset"] + ((pol * nant + antenna) * nchan + channel) * (
        ny * nx * itemsize
    )


def read_maps(read, member, pol, antenna, first, count):
    """`count` consecutive channels of one (pol, antenna), one range read."""
    _, _, nchan, ny, nx = member["shape"]
    dtype = np.dtype(member["descr"])
    if first + count > nchan:
        raise IndexError("channel range outside the beam cube")
    raw = read(
        map_offset(member, pol, antenna, first), count * ny * nx * dtype.itemsize
    )
    return np.frombuffer(raw, dtype=dtype).reshape(count, ny, nx)


def fetch_product(out_dir, url=L_BAND_URL, antennas=range(64), threads=16, log=print):
    """Fetch the frozen B1-0 product into `out_dir` (see the protocol):
    `array_average_native.npy` (4, 1024, 128, 128), `antennas_sampled.npy`
    (4, len(antennas), len(PRODUCT_CHANNELS), 128, 128), `small.npz` and
    `manifest.json` with SHA256 of every (pol, antenna) block and file."""
    import concurrent.futures

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    read = http_reader(url)
    members = npz_members(read)
    beam = members["beam.npy"]
    small = {
        name[:-4]: read_member(read, members[name])
        for name in ("pols.npy", "antnames.npy", "freq_MHz.npy", "margin_deg.npy")
    }
    np.savez(out / "small.npz", **small)
    antennas = list(antennas)
    manifest = {
        "url": url,
        "size": read.size,
        "last_modified": read.headers.get("Last-Modified"),
        "etag": read.headers.get("ETag"),
        "licence": LICENCE,
        "citation": CITATION,
        "layout": {k: v for k, v in beam.items() if k != "fortran_order"},
        "channels_sampled": list(PRODUCT_CHANNELS),
        "antennas_sampled": antennas,
        "blocks": {},
    }
    started = time.perf_counter()
    average = np.lib.format.open_memmap(
        out / "array_average_native.npy", "w+", "<c8", (4, NCHAN, NPIX, NPIX)
    )
    piece = 64
    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        jobs = {
            pool.submit(read_maps, read, beam, p, ARRAY_AVERAGE, f, piece): (p, f)
            for p in range(4)
            for f in range(0, NCHAN, piece)
        }
        for job in concurrent.futures.as_completed(jobs):
            p, f = jobs[job]
            average[p, f : f + piece] = job.result()
    average.flush()
    log(f"array average {time.perf_counter() - started:.1f} s")
    sampled = np.lib.format.open_memmap(
        out / "antennas_sampled.npy",
        "w+",
        "<c8",
        (4, len(antennas), len(PRODUCT_CHANNELS), NPIX, NPIX),
    )
    with concurrent.futures.ThreadPoolExecutor(threads) as pool:
        jobs = {
            pool.submit(read_maps, read, beam, p, a, f, 1): (p, i, k)
            for p in range(4)
            for i, a in enumerate(antennas)
            for k, f in enumerate(PRODUCT_CHANNELS)
        }
        for job in concurrent.futures.as_completed(jobs):
            p, i, k = jobs[job]
            sampled[p, i, k] = job.result()[0]
    sampled.flush()
    for p in range(4):
        manifest["blocks"][f"pol{p}_ant{ARRAY_AVERAGE}_native"] = hashlib.sha256(
            np.ascontiguousarray(average[p]).tobytes()
        ).hexdigest()
        for i, a in enumerate(antennas):
            manifest["blocks"][f"pol{p}_ant{a}_sampled"] = hashlib.sha256(
                np.ascontiguousarray(sampled[p, i]).tobytes()
            ).hexdigest()
    for name in ("array_average_native.npy", "antennas_sampled.npy", "small.npz"):
        manifest[name] = {
            "sha256": sha256_file(out / name),
            "bytes": (out / name).stat().st_size,
        }
    manifest["wall_s"] = time.perf_counter() - started
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return manifest


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 24), b""):
            digest.update(block)
    return digest.hexdigest()


# --------------------------------------------------------------------------
# Samplers


def _prefilter(maps):
    """Cubic B-spline coefficients of every 2-D map in (..., ny, nx)."""
    maps = np.asarray(maps, float)
    flat = maps.reshape((-1,) + maps.shape[-2:])
    out = np.stack([ndimage.spline_filter(m, order=3) for m in flat])
    return out.reshape(maps.shape)


def stokes_i(jones):
    """Stokes I power response of an unpolarised source, 1/2 sum |E_ij|^2."""
    jones = np.asarray(jones)
    return 0.5 * np.sum(np.abs(jones) ** 2, axis=(-2, -1))


class _Sampler:
    """Common normalisation: the Stokes I power beam is 1 at the origin."""

    name = "beam"

    def _raw(self, antenna, x_deg, y_deg, freq_hz):  # pragma: no cover
        raise NotImplementedError

    def raw_jones(self, antenna, x_deg, y_deg, freq_hz):
        """Unnormalised Jones (..., 2, 2) at scalar `freq_hz`."""
        x, y = np.broadcast_arrays(np.asarray(x_deg, float), np.asarray(y_deg, float))
        return self._raw(antenna, x, y, float(freq_hz))

    def norm(self, antenna, freq_hz):
        centre = self.raw_jones(antenna, np.zeros(1), np.zeros(1), freq_hz)
        return float(np.sqrt(stokes_i(centre)[0]))

    def jones(self, antenna, x_deg, y_deg, freq_hz):
        """Voltage Jones (..., 2, 2), [[HH, HV], [VH, VV]], normalised so that
        the Stokes I power beam is 1 at (0, 0) at this frequency."""
        return self.raw_jones(antenna, x_deg, y_deg, freq_hz) / self.norm(
            antenna, freq_hz
        )

    def power_i(self, antenna, x_deg, y_deg, freq_hz):
        return stokes_i(self.jones(antenna, x_deg, y_deg, freq_hz))


class HolographyBeam(_Sampler):
    """The frozen B1-0 product: spline in space, linear in frequency.

    `antenna` is an index into the product's antennas (0..63 for m000..m063
    when all were fetched) or "array_average"; the array average uses the
    native channels, the antennas the product channels. `flip` is the
    vertical sign s of the protocol: y = flip * margin_deg[row].
    """

    name = "holography"

    def __init__(self, product_dir, flip=1, native_average=True):
        """`product_dir` holds `small.npz`, `manifest.json`,
        `array_average_native.npy` and optionally `antennas_sampled.npy`."""
        self.dir = Path(product_dir)
        small = np.load(self.dir / "small.npz", allow_pickle=False)
        self.freq_hz = np.asarray(small["freq_MHz"], float) * 1e6
        self.margin_deg = np.asarray(small["margin_deg"], float)
        self.antnames = [s.decode() for s in small["antnames"]]
        self.flip = int(flip)
        if self.flip not in (1, -1):
            raise ValueError("flip must be +1 or -1")
        step = np.diff(self.margin_deg)
        if not np.allclose(step, PIXEL_DEG) or self.margin_deg[CENTRE_INDEX] != 0:
            raise ValueError("unexpected holography grid")
        self.average = np.load(self.dir / "array_average_native.npy", mmap_mode="r")
        sampled = self.dir / "antennas_sampled.npy"
        self.sampled = np.load(sampled, mmap_mode="r") if sampled.exists() else None
        manifest = json.loads((self.dir / "manifest.json").read_text())
        self.product_channels = np.asarray(manifest["channels_sampled"], int)
        self.sampled_antennas = list(manifest.get("antennas_sampled", range(64)))
        self.native_average = native_average

    def channels_for(self, antenna):
        if antenna == "array_average" and self.native_average:
            return np.arange(self.average.shape[1])
        return self.product_channels

    def _maps(self, antenna, channel):
        """(2, 2, ny, nx) complex at a native channel index."""
        if antenna == "array_average":
            maps = self.average[:, int(channel)]
        else:
            k = int(np.searchsorted(self.product_channels, channel))
            if k >= len(self.product_channels) or self.product_channels[k] != channel:
                raise KeyError("channel not in the product")
            maps = self.sampled[:, self.sampled_antennas.index(int(antenna)), k]
        return np.asarray(maps).reshape(2, 2, NPIX, NPIX)

    @lru_cache(maxsize=512)  # noqa: B019
    def _coefficients(self, antenna, channel):
        maps = self._maps(antenna, channel)
        return (
            _prefilter(maps.real),
            _prefilter(maps.imag),
        )

    def pixel_coordinates(self, x_deg, y_deg):
        col = (np.asarray(x_deg) - self.margin_deg[0]) / PIXEL_DEG
        row = (self.flip * np.asarray(y_deg) - self.margin_deg[0]) / PIXEL_DEG
        limit = self.margin_deg[-1] - PIXEL_DEG / 2
        if np.any(np.abs(x_deg) > limit) or np.any(np.abs(y_deg) > limit):
            raise ValueError("beam coordinates outside the holography grid")
        return row, col

    def sample_channel(self, antenna, channel, x_deg, y_deg):
        """Spline-sampled Jones (..., 2, 2) at one native channel."""
        row, col = self.pixel_coordinates(x_deg, y_deg)
        coords = np.stack([row.ravel(), col.ravel()])
        real, imag = self._coefficients(antenna, int(channel))
        out = np.empty((row.size, 2, 2), complex)
        for i in range(2):
            for j in range(2):
                out[:, i, j] = ndimage.map_coordinates(
                    real[i, j], coords, order=3, prefilter=False, mode="nearest"
                ) + 1j * ndimage.map_coordinates(
                    imag[i, j], coords, order=3, prefilter=False, mode="nearest"
                )
        return out.reshape(row.shape + (2, 2))

    def bracket(self, antenna, freq_hz):
        channels = self.channels_for(antenna)
        freqs = self.freq_hz[channels]
        if not freqs[0] <= freq_hz <= freqs[-1]:
            raise ValueError("frequency outside the holography band")
        k = int(np.clip(np.searchsorted(freqs, freq_hz) - 1, 0, len(freqs) - 2))
        weight = (freq_hz - freqs[k]) / (freqs[k + 1] - freqs[k])
        return channels[k], channels[k + 1], float(weight)

    def _raw(self, antenna, x, y, freq_hz):
        low, high, weight = self.bracket(antenna, freq_hz)
        out = (1 - weight) * self.sample_channel(antenna, low, x, y)
        if weight > 0:
            out = out + weight * self.sample_channel(antenna, high, x, y)
        return out


class KatBeam(_Sampler):
    """katbeam `MKAT-AA-L-JIM-2020`: diagonal Jones (HH, VV), co-polar only."""

    name = "katbeam"

    def __init__(self):
        from katbeam import JimBeam

        self.model = JimBeam("MKAT-AA-L-JIM-2020")
        self.band_hz = (
            self.model.freqMHzlist[0] * 1e6,
            self.model.freqMHzlist[-1] * 1e6,
        )

    def _raw(self, antenna, x, y, freq_hz):
        if not self.band_hz[0] <= freq_hz <= self.band_hz[1]:
            raise ValueError("frequency outside the katbeam table")
        mhz = freq_hz / 1e6
        out = np.zeros(x.shape + (2, 2), complex)
        out[..., 0, 0] = self.model.HH(x, y, mhz)
        out[..., 1, 1] = self.model.VV(x, y, mhz)
        return out


class EidosBeam(_Sampler):
    """EIDOS 1.1.2 MeerKAT holography model ('mh' coefficients): Jones maps
    reconstructed on its own 10 deg grid at the nearest coefficient channel
    (as EIDOS selects), spline-sampled. The grid follows EIDOS's unit disk:
    pixel i is at (i - npix/2) / (npix/2) * 5 deg, rows y, columns x, read
    with the same flip as the holography product."""

    name = "eidos"

    def __init__(self, npix=256, flip=1, thresh=20):
        import importlib
        import os

        create_beam = importlib.import_module("eidos.create_beam")
        filename = os.path.join(
            os.path.dirname(create_beam.__file__),
            "data",
            "meerkat_beam_coeffs_ah_zp_dct.npy",
        )
        self._params, self.freq_mhz = create_beam.zernike_parameters(
            filename, npix, 10.0, thresh
        )
        self._spatial = importlib.import_module("spatial")
        self.npix = npix
        self.flip = int(flip)
        self.band_hz = (self.freq_mhz[0] * 1e6, self.freq_mhz[-1] * 1e6)

    def _reconstruct(self, data):
        """EIDOS `recon_par` for one channel, re-expressed because EIDOS
        1.1.2 calls `np.sum` on a generator, which NumPy 2 refuses: the same
        Zernike basis, the same `thresh` largest coefficients per element,
        summed with Python's `sum`."""
        coeffs, nolls, npix, thresh = data
        zernike = self._spatial.Zernike(mode="none")
        zernike.unit_disk(npix)
        rho, phi, mask = zernike.grid_rho, zernike.grid_phi, zernike.grid_mask
        out = np.zeros((2, 2, npix, npix), complex)
        for part, unit in ((0, 1.0), (1, 1j)):
            for i in range(2):
                for j in range(2):
                    c = np.asarray(coeffs[part][i, j, :])
                    n = np.asarray(nolls[part][i, j, :])
                    keep = np.argsort(np.abs(c))[::-1][:thresh]
                    out[i, j] += unit * sum(
                        c[k] * zernike.zernikel(int(n[k]), rho, phi) * mask
                        for k in keep
                    )
        return out

    @lru_cache(maxsize=64)  # noqa: B019
    def _coefficients(self, channel):
        maps = self._reconstruct(self._params[channel, :])
        return (
            _prefilter(maps.real),
            _prefilter(maps.imag),
        )

    def _raw(self, antenna, x, y, freq_hz):
        if not self.band_hz[0] <= freq_hz <= self.band_hz[1]:
            raise ValueError("frequency outside the EIDOS coefficients")
        channel = int(np.argmin(np.abs(self.freq_mhz - freq_hz / 1e6)))
        scale = (self.npix / 2) / 5.0
        col = np.asarray(x) * scale + self.npix / 2
        row = self.flip * np.asarray(y) * scale + self.npix / 2
        coords = np.stack([row.ravel(), col.ravel()])
        real, imag = self._coefficients(channel)
        out = np.empty((row.size, 2, 2), complex)
        for i in range(2):
            for j in range(2):
                out[:, i, j] = ndimage.map_coordinates(
                    real[i, j], coords, order=3, prefilter=False, mode="nearest"
                ) + 1j * ndimage.map_coordinates(
                    imag[i, j], coords, order=3, prefilter=False, mode="nearest"
                )
        return out.reshape(row.shape + (2, 2))


# --------------------------------------------------------------------------
# Measurements on beams (gates and comparison)


def gaussian_2d(params, x, y):
    """Elliptical Gaussian: x0, y0, height, sigma_major, sigma_minor, angle
    (rad, major axis from +x towards +y)."""
    x0, y0, height, s1, s2, angle = params
    c, s = np.cos(angle), np.sin(angle)
    u = c * (x - x0) + s * (y - y0)
    v = -s * (x - x0) + c * (y - y0)
    return height * np.exp(-0.5 * ((u / s1) ** 2 + (v / s2) ** 2))


def fit_main_lobe(power, x_deg, y_deg, level=0.5):
    """Fit `gaussian_2d` to a power map above `level` of its peak, inside
    the connected region around the maximum. Returns centroid (deg), power
    FWHM major and minor (deg) and angle (deg)."""
    power = np.asarray(power, float)
    peak = np.unravel_index(np.argmax(power), power.shape)
    above = power >= level * power[peak]
    labels, _ = ndimage.label(above)
    region = labels == labels[peak]
    xs, ys, values = x_deg[region], y_deg[region], power[region]
    guess = [x_deg[peak], y_deg[peak], power[peak], 0.4, 0.4, 0.0]

    def residual(p):
        return gaussian_2d(p, xs, ys) - values

    fit = optimize.least_squares(residual, guess, method="lm")
    x0, y0, _, s1, s2, angle = fit.x
    s1, s2 = abs(s1), abs(s2)
    if s2 > s1:
        s1, s2, angle = s2, s1, angle + np.pi / 2
    angle = (np.degrees(angle) + 90) % 180 - 90
    fwhm = 2 * np.sqrt(2 * np.log(2))
    return {
        "x0_deg": float(x0),
        "y0_deg": float(y0),
        "fwhm_major_deg": float(fwhm * s1),
        "fwhm_minor_deg": float(fwhm * s2),
        "angle_deg": float(angle),
        "pixels": int(region.sum()),
    }


def radial_profile(power, x_deg, y_deg, step_deg=PIXEL_DEG / 2, rmax_deg=3.5):
    """Azimuthal mean of a map in annuli of `step_deg` about the origin."""
    r = np.hypot(x_deg, y_deg).ravel()
    edges = np.arange(0, rmax_deg + step_deg, step_deg)
    which = np.digitize(r, edges) - 1
    keep = (which >= 0) & (which < len(edges) - 1)
    sums = np.bincount(which[keep], power.ravel()[keep], len(edges) - 1)
    counts = np.bincount(which[keep], minlength=len(edges) - 1)
    with np.errstate(invalid="ignore"):
        mean = sums / counts
    return 0.5 * (edges[1:] + edges[:-1]), mean


def lobe_radii(radius, profile):
    """Half-power radius, first and second minimum and first-sidelobe peak
    of an azimuthal profile normalised to 1 at the origin."""
    ok = np.isfinite(profile)
    radius, profile = radius[ok], profile[ok]
    below = np.nonzero(profile < 0.5)[0][0]
    r_hp = float(
        np.interp(
            0.5,
            profile[below - 1 : below + 1][::-1],
            radius[below - 1 : below + 1][::-1],
        )
    )
    minima = [
        i
        for i in range(1, len(profile) - 1)
        if profile[i] <= profile[i - 1]
        and profile[i] < profile[i + 1]
        and radius[i] > r_hp
    ]
    n1 = minima[0]
    n2 = next(
        (i for i in minima if i > n1 and radius[i] > radius[n1] + 0.2), minima[-1]
    )
    side = n1 + int(np.argmax(profile[n1 : n2 + 1]))
    return {
        "r_half_power_deg": r_hp,
        "r_first_null_deg": float(radius[n1]),
        "r_second_null_deg": float(radius[n2]),
        "r_first_sidelobe_deg": float(radius[side]),
        "first_sidelobe_level": float(profile[side]),
    }


def grid(half_width_deg, step_deg):
    axis = np.arange(-half_width_deg, half_width_deg + step_deg / 2, step_deg)
    y, x = np.meshgrid(axis, axis, indexing="ij")
    return x, y


def gradient_magnitude(power, step_deg):
    gy, gx = np.gradient(power, step_deg)
    return np.hypot(gx, gy)
