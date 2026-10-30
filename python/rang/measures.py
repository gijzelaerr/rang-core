"""Parallactic and feed angles for B1-2 (research/b1-2-identifiability.md).

Frozen convention (research/b1-beam-pointing.md, "Measures convention"):
the **geodetic** parallactic angle q with **astropy** as the reference. q is
the position angle of the zenith seen from the source, measured from north
through east in the ICRS frame of the (J2000) phase direction. The zenith is
the geodetic one of `EarthLocation.from_geocentric`, at the observing time;
casacore's `AZEL` frame would use the geocentric horizon instead.

The feed's RECEPTOR_ANGLE is read from the MS FEED table and recorded; the
holography beam is measured in the dish (H/V) frame, so it is not added to
the beam rotation (the protocol). `feed_angle` returns q plus the receptor
angle for callers that need the polarisation-basis angle.

Sky (l, m) to the antenna frame (x cross-elevation toward increasing
azimuth, y elevation toward the zenith): x = -l cos q + m sin q,
y = l sin q + m cos q (`sky_to_beam`).

No network: astropy's IERS auto-download is switched off; the bundled IERS
tables serve the 2019-2020 epochs of the B1 data.
"""

import numpy as np

MJD_SECONDS = 86400.0


def _astropy():
    from astropy import units
    from astropy.coordinates import AltAz, EarthLocation, SkyCoord
    from astropy.time import Time
    from astropy.utils import iers

    iers.conf.auto_download = False
    return units, AltAz, EarthLocation, SkyCoord, Time


def location(itrf_xyz_m):
    """astropy EarthLocation of an ITRF position (m), e.g. the array centre."""
    units, _, EarthLocation, _, _ = _astropy()
    x, y, z = np.asarray(itrf_xyz_m, float)
    return EarthLocation.from_geocentric(x, y, z, unit=units.m)


def parallactic_angle(times_mjd_s, ra_rad, dec_rad, itrf_xyz_m):
    """Geodetic parallactic angle q (rad) at MS TIME values (MJD seconds, UTC).

    The astropy reference: the zenith (alt 90 deg) at each time, transformed
    to ICRS, and the ICRS position angle from the source to it."""
    units, AltAz, _, SkyCoord, Time = _astropy()
    times = np.atleast_1d(np.asarray(times_mjd_s, float))
    when = Time(times / MJD_SECONDS, format="mjd", scale="utc")
    site = location(itrf_xyz_m)
    source = SkyCoord(ra_rad * units.rad, dec_rad * units.rad, frame="icrs")
    zenith = SkyCoord(
        alt=np.full(times.shape, 90.0) * units.deg,
        az=np.zeros(times.shape) * units.deg,
        frame=AltAz(obstime=when, location=site),
    ).transform_to("icrs")
    angle = source.position_angle(zenith).wrap_at(180 * units.deg).rad
    return np.asarray(angle, float)


def parallactic_angle_closed_form(times_mjd_s, ra_rad, dec_rad, itrf_xyz_m):
    """The hour-angle formula on astropy's apparent (TETE) place and apparent
    sidereal time, with the geodetic latitude: the fast path that the test
    checks against `parallactic_angle` (frozen tolerance 0.01 deg). The
    apparent-place angle is rotated to ICRS north at the source (the
    precession-nutation since J2000 turns north by 0.2 deg at ESO137 in
    2019)."""
    units, _, _, SkyCoord, Time = _astropy()
    times = np.atleast_1d(np.asarray(times_mjd_s, float))
    when = Time(times / MJD_SECONDS, format="mjd", scale="utc")
    site = location(itrf_xyz_m)
    apparent = SkyCoord(ra_rad * units.rad, dec_rad * units.rad, frame="icrs")
    from astropy.coordinates import TETE

    apparent = apparent.transform_to(TETE(obstime=when, location=site))
    lst = when.sidereal_time("apparent", longitude=site.lon).rad
    hour = lst - apparent.ra.rad
    phi = site.lat.rad
    dec = apparent.dec.rad
    q_apparent = np.arctan2(
        np.sin(hour), np.tan(phi) * np.cos(dec) - np.sin(dec) * np.cos(hour)
    )
    # Rotate from apparent north to ICRS north at the source: the ICRS
    # position angle of a point 1 arcsec toward apparent north.
    north = SkyCoord(
        ra=apparent.ra, dec=apparent.dec + 1 * units.arcsec, frame=apparent.frame
    ).transform_to("icrs")
    source = SkyCoord(ra_rad * units.rad, dec_rad * units.rad, frame="icrs")
    eta = source.position_angle(north).wrap_at(180 * units.deg).rad
    return np.angle(np.exp(1j * (q_apparent + eta)))


def feed_angle(parallactic_rad, receptor_angle_rad):
    """q plus the FEED RECEPTOR_ANGLE (rad): the polarisation-basis angle."""
    return np.asarray(parallactic_rad, float) + float(receptor_angle_rad)


def sky_to_beam(l, m, q):
    """Antenna-frame (x, y) of sky direction cosines (l, m) at parallactic
    angle q (all broadcast): x toward increasing azimuth, y toward zenith."""
    l, m, q = np.broadcast_arrays(*(np.asarray(v, float) for v in (l, m, q)))
    c, s = np.cos(q), np.sin(q)
    return -l * c + m * s, l * s + m * c


def array_centre(positions_itrf_m):
    """Mean ITRF position of the antennas (m)."""
    return np.asarray(positions_itrf_m, float).mean(axis=0)


__all__ = [
    "array_centre",
    "feed_angle",
    "location",
    "parallactic_angle",
    "parallactic_angle_closed_form",
    "sky_to_beam",
]
