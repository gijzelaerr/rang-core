"""beam_gate.py OUT.json CASE=GEMCLEAN_IMAGE.fits,WSCLEAN_IMAGE.fits ...

Gate B of research/g7-defaults.md, section 2: BMAJ and BMIN within 1e-3 (relative) and BPA
within 0.1 degree (modulo 180) of WSClean 3.7's header beam. Prints a table and writes OUT.json.
"""

import json
import sys

from astropy.io import fits


def beam(path):
    h = fits.getheader(path)
    return h["BMAJ"] * 3600.0, h["BMIN"] * 3600.0, float(h["BPA"])


def main():
    out, *cases = sys.argv[1:]
    rows = {}
    ok_all = True
    print("| case | GeMClean BMAJ × BMIN, PA | WSClean | BMAJ G/W − 1 | BMIN G/W − 1 | ΔPA (deg) | B |")
    print("| --- | --- | --- | ---: | ---: | ---: | --- |")
    for c in cases:
        name, pair = c.split("=", 1)
        g, w = pair.split(",")
        gb, wb = beam(g), beam(w)
        dmaj, dmin = gb[0] / wb[0] - 1.0, gb[1] / wb[1] - 1.0
        dpa = (gb[2] - wb[2] + 90.0) % 180.0 - 90.0
        ok = abs(dmaj) <= 1e-3 and abs(dmin) <= 1e-3 and abs(dpa) <= 0.1
        ok_all &= ok
        rows[name] = {
            "gemclean": g, "wsclean": w, "gemclean_beam_asec_deg": gb, "wsclean_beam_asec_deg": wb,
            "bmaj_rel": dmaj, "bmin_rel": dmin, "bpa_deg": dpa, "pass": ok,
        }  # fmt: skip
        print(
            f"| {name} | {gb[0]:.4f}″ × {gb[1]:.4f}″, {gb[2]:.3f}° | {wb[0]:.4f}″ × {wb[1]:.4f}″, {wb[2]:.3f}° "
            f"| {dmaj:.2e} | {dmin:.2e} | {dpa:.4f} | {'pass' if ok else 'FAIL'} |"
        )
    with open(out, "w") as f:
        json.dump({"cases": rows, "all_pass": ok_all}, f, indent=1)
        f.write("\n")


if __name__ == "__main__":
    main()
