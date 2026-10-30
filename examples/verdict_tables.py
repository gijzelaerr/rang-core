"""Tabulate every pre-registered call of the gain-TV flagging experiment (task L4).

Usage:
    python examples/verdict_tables.py            # print the tables
    python examples/verdict_tables.py --write    # also write the consolidated archive
    python examples/verdict_tables.py --check    # fail if the committed archive is stale

Reads only the committed archives under research/results (no visibilities, no
runs) and writes research/results/flagging-verdict.json: every pre-registered
call with its ratio, its rule, and the archive file and JSON path it comes from.
Each archived call is re-derived from its ratio with the frozen +/-1 % band and
must agree, so a transcription error stops the script.
"""

import argparse
import json
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1] / "research" / "results"
OUT = RESULTS / "flagging-verdict.json"
BETTER, WORSE = 0.99, 1.01

K = "core-k-luno-campaign.json"
L1 = "luno-array-campaign.json"
L2 = "luno-1830-campaign.json"
L1M = "l1-model-completeness.json"
C1 = "c1-closure-arm.json"
A1 = "a1-rfi-audit.json"
L5 = "l5-solver-science.json"
OCASA = "o-casa-crosscal.json"
FIXTURE = "gain-tv-flagging.json"
PROSPECTIVE = "gain-tv-next-prospective.json"
FIXTURE_CARACAL = "gain-tv-caracal.json"


def load(name):
    return json.loads((RESULTS / name).read_text())


def get(obj, path):
    for key in path.split("/"):
        obj = obj[int(key)] if isinstance(obj, list) else obj[key]
    return obj


def derive(ratio):
    if ratio is None:
        return "undecidable"
    if ratio <= BETTER:
        return "better"
    if ratio >= WORSE:
        return "worse"
    return "null"


class Calls:
    def __init__(self):
        self.rows = []
        self.cache = {}

    def archive(self, name):
        if name not in self.cache:
            self.cache[name] = load(name)
        return self.cache[name]

    def add(
        self,
        campaign,
        model,
        candidate,
        reference,
        rule,
        metric,
        source,
        path,
        dropped=None,
        dropped_path=None,
    ):
        node = get(self.archive(source), path)
        ratio, call = node["ratio"], node["call"]
        if derive(ratio) != call:
            sys.exit(f"{source}:{path}: call {call!r} does not follow from {ratio!r}")
        row = {
            "campaign": campaign,
            "model": model,
            "candidate": candidate,
            "reference": reference,
            "rule": rule,
            "metric": metric,
            "ratio": ratio,
            "call": call,
            "source": f"research/results/{source}",
            "path": path,
        }
        if dropped_path is not None:
            dropped = get(self.archive(source), dropped_path)
        if dropped is not None:
            row["dropped_test_samples"] = dropped
        self.rows.append(row)


def frozen(calls, campaign, model, source, base):
    """The frozen pairs (K's rule: MSE_test and residual RMS on all held-out cells)."""
    for i, pair in enumerate(get(calls.archive(source), base)):
        for metric in ("mse_test", "residual_rms"):
            calls.add(
                campaign,
                model,
                pair["candidate"],
                pair["reference"],
                "frozen",
                metric,
                source,
                f"{base}/{i}/{metric}",
            )


def matched(calls, campaign, model, source, base):
    """Amendment 1: MSE_test on held-out samples both arms predict."""
    for i, pair in enumerate(get(calls.archive(source), base)):
        drop = (
            f"{base}/{i}/dropped_test_cells" if "dropped_test_cells" in pair else None
        )
        calls.add(
            campaign,
            model,
            pair["candidate"],
            pair["reference"],
            "amendment-1 matched",
            "mse_test",
            source,
            f"{base}/{i}/mse_test",
            dropped_path=drop,
        )


def all_calls():
    calls = Calls()
    # K: four stations, 1934-638, stored model.
    frozen(calls, "K", "stored", K, "hypotheses")
    # L1: whole array, 1934-638. The matched calls are not in L1's archive; C1
    # reproduced L1's run on every non-image field and archives them.
    frozen(calls, "L1", "stored", L1, "hypotheses")
    # Dropped = the first pass's unpredictable test samples (L1's own archive).
    fp_invalid = get(
        calls.archive(L1), "arms/tricolour-firstpass/metrics/invalid_predictions/test"
    )
    for i, pair in enumerate(calls.archive(C1)["l1_amendment_1_pairs"]):
        drop = fp_invalid if pair["reference"] == "tricolour-firstpass" else 0
        calls.add(
            "L1",
            "stored",
            pair["candidate"],
            pair["reference"],
            "amendment-1 matched",
            "mse_test",
            C1,
            f"l1_amendment_1_pairs/{i}/mse_test",
            dropped=drop,
        )
    # L2: whole array, 1830-211, two model arms.
    for model in ("stored", "scalar"):
        frozen(calls, "L2", model, L2, f"model_arms/{model}/hypotheses")
        matched(calls, "L2", model, L2, f"model_arms/{model}/amendment_1/pairs")
    # L1-M: L1's campaign under three calibrator models.
    for model in ("stored", "point", "field"):
        frozen(calls, "L1-M", model, L1M, f"models/{model}/hypotheses")
        matched(calls, "L1-M", model, L1M, f"models/{model}/amendment_1/pairs")
    # C1: closure-guided policy and closure-outlier mask, three rules each.
    for i, pair in enumerate(calls.archive(C1)["calls"]):
        cand, ref = pair["candidate"], pair["reference"]
        calls.add(
            "C1",
            "stored",
            cand,
            ref,
            "frozen",
            "mse_test",
            C1,
            f"calls/{i}/frozen/mse_test",
        )
        calls.add(
            "C1",
            "stored",
            cand,
            ref,
            "frozen",
            "residual_rms",
            C1,
            f"calls/{i}/frozen/residual_rms",
        )
        calls.add(
            "C1",
            "stored",
            cand,
            ref,
            "amendment-1 matched",
            "mse_test",
            C1,
            f"calls/{i}/matched/mse_test",
            dropped_path=f"calls/{i}/matched/dropped_test_cells",
        )
        calls.add(
            "C1",
            "stored",
            cand,
            ref,
            "A1 drop",
            "mse_test",
            C1,
            f"calls/{i}/a1_drop/mse_test",
            dropped_path=f"calls/{i}/a1_drop/dropped_test_cells",
        )
    return calls


def model_calls(calls):
    """L1-M's cross-model questions (calibration quality, not flagging)."""
    rows = []
    for pair in ("field vs stored", "field vs point"):
        for q, metric in (
            ("q1", "original_mse_test"),
            ("q2", "tv_at_stored_scale_and_support"),
        ):
            path = f"comparison/{q}/{pair}/{metric}"
            node = get(calls.archive(L1M), path)
            if derive(node["ratio"]) != node["call"]:
                sys.exit(f"{L1M}:{path}: inconsistent call")
            rows.append(
                {
                    "question": q,
                    "pair": pair,
                    "metric": metric,
                    "ratio": node["ratio"],
                    "call": node["call"],
                    "source": f"research/results/{L1M}",
                    "path": path,
                }
            )
    return rows


def loop_summary(records):
    guided = [r for r in records if r.get("policy") and r["policy"]["tv_weight"] > 0]
    solved = [r for r in guided if "objective" in r]
    return {
        "guided_trials": len(guided),
        "guided_distinct_solved": len(solved),
        "guided_accepted": sum(bool(r.get("accepted")) for r in solved),
        "guided_best_objective": min(
            (r["objective"] for r in solved if r["objective"] is not None), default=None
        ),
        "no_change_objective": 1.25,
    }


def selections(calls):
    """What the TV policy loop selected in each campaign run."""
    out = []

    def one(campaign, model, source, arms, cands):
        arm = get(calls.archive(source), f"{arms}/tv-policy")
        row = {
            "campaign": campaign,
            "model": model,
            "selected_policy": arm["policy"],
            "additions": arm["additions"],
            "source": f"research/results/{source}",
            "path": f"{arms}/tv-policy",
        }
        row.update(loop_summary(get(calls.archive(source), f"{cands}/tv-policy")))
        out.append(row)

    one("K", "stored", K, "arms", "candidates")
    one("L1", "stored", L1, "arms", "candidates")
    for m in ("stored", "scalar"):
        one("L2", m, L2, f"model_arms/{m}/arms", f"model_arms/{m}/candidates")
    q2 = calls.archive(C1)["questions"]["q2"]["selection"]
    out.append(
        {
            "campaign": "C1",
            "model": "stored",
            "loop": "closure-tv-policy",
            "selected_policy": q2["policy"],
            "additions": q2["additions"],
            "guided_trials": q2["guided_trials"],
            "guided_distinct_solved": q2["guided_solved"],
            "guided_accepted": q2["guided_accepted"],
            "source": f"research/results/{C1}",
            "path": "questions/q2/selection",
        }
    )
    for m in ("stored", "point", "field"):
        sel = calls.archive(L1M)["comparison"]["q3"][m]["tv_policy"]
        out.append(
            {
                "campaign": "L1-M",
                "model": m,
                "selected_policy": {
                    "threshold": sel["threshold"],
                    "tv_weight": sel["tv_weight"],
                },
                "additions": sel["additions"],
                "source": f"research/results/{L1M}",
                "path": f"comparison/q3/{m}/tv_policy",
            }
        )
    return out


def costs(calls):
    """The cost clause (TV chain against the first-pass port), as archived."""
    out = []

    def one(campaign, model, source, path, note):
        c = get(calls.archive(source), path)
        out.append(
            {
                "campaign": campaign,
                "model": model,
                "note": note,
                "tv_chain_seconds": c["tv_chain_seconds"],
                "firstpass_seconds": c["tricolour_firstpass_seconds"],
                "ratio": c["ratio"],
                "comparable": c["comparable"],
                "source": f"research/results/{source}",
                "path": path,
            }
        )

    one("K", "stored", K, "cost_clause", "four stations, single-threaded kernels")
    one(
        "L1",
        "stored",
        L1,
        "cost_clause",
        "whole array, single-threaded kernels, contended host",
    )
    for m in ("stored", "scalar"):
        one(
            "L2",
            m,
            L2,
            f"model_arms/{m}/cost_clause",
            "parallel kernels, load average 46-97",
        )
    for m in ("stored", "point", "field"):
        one(
            "L1-M",
            m,
            L1M,
            f"models/{m}/cost_clause",
            "parallel kernels, 4 threads, load 3-7",
        )
    st = calls.archive(C1)["l1_stages"]
    tv = st["solve_original"] + st["tv_loop"]
    fp = st["flag_tricolour-firstpass"]
    out.append(
        {
            "campaign": "C1 (L1 rerun)",
            "model": "stored",
            "note": "parallel kernels, 4 threads, load 1-2; derived from l1_stages",
            "tv_chain_seconds": tv,
            "firstpass_seconds": fp,
            "ratio": tv / fp,
            "comparable": tv / fp <= 3.0,
            "source": f"research/results/{C1}",
            "path": "l1_stages/{solve_original,tv_loop,flag_tricolour-firstpass}",
        }
    )
    return out


def context(calls):
    """Numbers quoted in the verdict outside the call tables."""
    ocasa = calls.archive(OCASA)["comparison"]["arms"]["sh"]
    l5 = calls.archive(L5)["sweeps"]["array"]["arms"]
    fx = calls.archive(FIXTURE)["final_whitened_reserved"]
    seed109 = calls.archive(PROSPECTIVE)["raw_result_projection"]["cases"][2]
    fixture_caracal = calls.archive(FIXTURE_CARACAL)["result"]["controls"]
    return {
        "fixture_baseline": {
            "tv": fx["baseline"]["tv"],
            "losses": fx["baseline"]["losses"],
            "selected_policy": fx["selected_policy"],
            "path": f"research/results/{FIXTURE}:final_whitened_reserved",
        },
        "fixture_seed109_injected": {
            "selected_residual": seed109["selected"]["residual"],
            "selected_tv": seed109["selected"]["tv"],
            "baseline_test_mse": seed109["baseline"]["losses"]["test"],
            "path": f"research/results/{PROSPECTIVE}:raw_result_projection/cases/2",
        },
        "fixture_caracal_controls": [
            {
                "strategy": c["strategy"],
                "label": c["native"]["label"],
                "added_fraction": c["metrics"]["added_fraction"],
                "objective": c["objective"],
                "guard_pass": c["guard_pass"],
            }
            for c in fixture_caracal
        ],
        "o_casa_sh": {
            k: ocasa[k]
            for k in (
                "mse_test",
                "mse_test_parallel_casa",
                "mse_test_parallel_core",
                "mse_test_cross_casa",
                "mse_test_cross_core",
                "core_mse_test_same_cells",
            )
        },
        "o_casa_flagdata": calls.archive(OCASA)["flagdata"],
        "l5_array": {
            k: {
                f: l5[k][f]
                for f in ("iterations", "converged_fraction", "losses", "polar_tv")
            }
            for k in ("D", "anderson-3", "transposed-anderson-3")
        },
        "c1_q1_trace": calls.archive(C1)["questions"]["q1"]["by_family"]["trace"],
        "a1_emptied": {
            c: calls.archive(A1)["campaigns"][c]["arms"]["tricolour-firstpass"][
                "emptied_station_bins"
            ]
            for c in ("l1", "l2")
        },
        "l1m_model_calls": model_calls(calls),
    }


def build():
    calls = all_calls()
    return {
        "schema_version": 1,
        "task": "L4 verdict: gain-TV-guided flagging (research/flagging-verdict.md)",
        "rule": "ratio candidate/reference <= 0.99 better, >= 1.01 worse, else null; "
        "missing value undecidable",
        "generated_by": "examples/verdict_tables.py",
        "calls": calls.rows,
        "tv_policy_selections": selections(calls),
        "cost_clause": costs(calls),
        "context": context(calls),
        "summary": {
            "calls": len(calls.rows),
            "by_call": {
                c: sum(r["call"] == c for r in calls.rows)
                for c in ("better", "worse", "null", "undecidable")
            },
        },
    }


def fmt(x, digits=6):
    return "–" if x is None else f"{x:.{digits}f}"


def print_tables(data):
    print("| Campaign | Model | Candidate | Reference | Rule | Metric | Ratio | Call |")
    print("| --- | --- | --- | --- | --- | --- | ---: | --- |")
    for r in data["calls"]:
        drop = r.get("dropped_test_samples")
        rule = r["rule"] + (f" ({drop} dropped)" if drop else "")
        print(
            f"| {r['campaign']} | {r['model']} | {r['candidate']} | {r['reference']} "
            f"| {rule} | {r['metric']} | {fmt(r['ratio'])} | {r['call']} |"
        )
    print()
    print("| Campaign | Model | TV chain (s) | First pass (s) | Ratio | Comparable |")
    print("| --- | --- | ---: | ---: | ---: | --- |")
    for c in data["cost_clause"]:
        print(
            f"| {c['campaign']} | {c['model']} | {c['tv_chain_seconds']:.1f} "
            f"| {c['firstpass_seconds']:.1f} | {c['ratio']:.2f} | {c['comparable']} |"
        )
    print()
    print(json.dumps(data["summary"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    data = build()
    text = json.dumps(data, indent=1, sort_keys=False) + "\n"
    if args.check:
        if OUT.read_text() != text:
            sys.exit(f"{OUT} is stale; rerun with --write")
        print(f"{OUT}: up to date ({data['summary']['calls']} calls)")
        return
    print_tables(data)
    if args.write:
        OUT.write_text(text)
        print(f"wrote {OUT} ({len(text)} bytes)")


if __name__ == "__main__":
    main()
