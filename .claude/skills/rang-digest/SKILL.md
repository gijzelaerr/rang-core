---
name: rang-digest
description: Weekly ra-ng literature digest. Searches arXiv and release APIs for new work in RFI flagging, calibration, imaging, MeerKAT/SKA-Mid, LOFAR 2.0, pulsars/FRBs/GRBs, VLBI/EHT and agentic tools; writes research/digests/<date>.md and at most five proposal stubs in research/proposals/; never edits code; ends with a commit on a branch for the coordinator. Use when asked for "the digest", "this week's literature", or task V4.
---

# rang-digest: the weekly literature digest

Owner's cadence: one digest a week (2026-11-11). Skills propose and measure;
they never merge (research/vision.md section 6). This skill **writes markdown
only**.

## Allowed paths

Write only `research/digests/<YYYY-MM-DD>.md`, new files in
`research/proposals/`, the one "Weekly digests" line in `research/README.md`
"Start here" (update its link and date to the new digest; never add a second
line), and `outputs/status/rang-digest.md` (ignored,
under 15 lines). Never edit code, tests, `AGENTS.md`, `STATE.md`, existing
notes or an existing proposal file. Never overwrite a proposal slug that
exists; pick a new slug and link the old one.

## Steps

1. **Branch.** From `origin/main`:
   `git -C ~/Github/rang worktree add ~/Worktrees/rang/digest-<date> -b digest-<date> origin/main`.
   Work there. Read `AGENTS.md`, `research/vision.md`, the top block of
   `research/STATE.md` and `research/README.md`.
2. **Avoid repeats.** Read the newest file in `research/digests/` and list
   every arXiv ID and release already cited in `research/` (including
   subfolders):
   `grep -rhoE "arXiv:[0-9]{4}\.[0-9]{4,5}|arxiv.org/abs/[0-9]{4}\.[0-9]{4,5}" research | grep -oE "[0-9]{4}\.[0-9]{4,5}" | sort -u`.
   Drop those IDs from the new results. A release is repeated only if its
   version is unchanged.
   Both link forms matter: the 2026-11-11 digest missed two repeats by
   checking only `arXiv:NNNN`.
3. **Search papers (arXiv API).** `http://export.arxiv.org/api/query` with
   `search_query=(<query>) AND submittedDate:[YYYYMMDDHHMM TO YYYYMMDDHHMM]`
   (from the last digest's date to tomorrow), `sortBy=submittedDate`,
   `sortOrder=descending`, `max_results` 60, a generic User-Agent, at least
   3 s between requests. Add `AND cat:astro-ph.IM` to every query unless the
   area needs astro-ph.HE/GA (time domain, EHT), and then filter titles: bare
   names and acronyms (QuartiCal OR DDECal, R2D2, AIRI, DP3, LINC, Presto,
   Heimdall) otherwise pull in mathematics, robotics and databases. Avoid
   `au:` with a bare surname. Per area, keyword queries with `abs:` terms:
   - RFI: `"radio frequency interference" AND (flagging OR detection)`;
     `RFI AND "deep learning"`; `RFI AND MeerKAT`; `AOFlagger OR Tricolour`.
   - Calibration: `"direction-dependent" AND calibration`; `calibration AND
     (Bayesian OR differentiable) AND interferometer`; `"self-calibration" AND
     radio`; `QuartiCal OR DDECal OR hyperdrive`.
   - Imaging: `deconvolution AND "radio interferometric"`; `"radio
     interferometric imaging" AND ("deep learning" OR unrolled OR "neural
     network")`; `"radio interferometric" AND uncertainty`; `WSClean OR
     wgridder`; `gridding AND GPU AND radio`; `R2D2 AND imaging`.
   - MeerKAT / SKA-Mid: `MeerKAT AND pipeline`; `"SKA-Mid" OR "MeerKAT+"`;
     `SARAO AND pipeline`.
   - LOFAR: `"LOFAR 2.0"`; `LOFAR AND calibration`; `LOFAR AND
     "direction-dependent"`.
   - Time domain: `dedispersion AND GPU`; `"single pulse" AND search`; `"fast
     radio burst" AND ("machine learning" OR "real-time")`; `MeerTRAP OR
     TRAPUM`; `"image-plane" AND transient`; `"gamma-ray burst" AND radio AND
     MeerKAT`; `Heimdall OR PRESTO` (filter out non-astronomy namesakes).
   - VLBI / EHT: `"fringe fitting"`; `"Event Horizon Telescope" AND imaging`;
     `VLBI AND calibration`.
   - Agents: `"large language model" AND cat:astro-ph.IM`; `agent AND LLM`;
     `"large language model" AND radio`.
   - Proceedings: `co:ADASS`, `co:URSI`, `co:SPIE AND abs:radio` (the
     comments field), filtered by title.
   Save raw results to the session scratchpad, not the repo.
4. **Search software (release APIs).** GitHub `repos/<r>/releases`:
   ratt-ru/QuartiCal, ratt-ru/pfb-imaging, ratt-ru/tricolour, mreineck/ducc
   (tags), caracal-pipeline/caracal, saopicc/DDFacet, scottransom/presto,
   MWATelescope/mwa_hyperdrive, achael/eht-imaging, ptiede/Comrade.jl,
   MPoL-dev/MPoL, CMBAgents/cmbagent, ska-sa/katdal (tags). GitLab v4
   `projects/<id>/releases`: gitlab.com aroffringa/wsclean and
   aroffringa/aoflagger; git.astron.nl RD/idg, RD/DP3, RD/EveryBeam,
   RD/rapthor, RD/LINC. Use web search only for news without an API (SKAO,
   SARAO) and say so.
5. **Read.** Fetch each candidate's **full** abstract (not a truncated
   snippet) or release notes. Nothing from memory: every item must have been
   fetched in this run, and every detail in its "what it does" line (code
   base, telescope, real or simulated data) must be in what was fetched.
   Tag **[abs]**, **[repo]** or **[page]**.
   Before writing a proposal, grep `research/` for the method and tool
   names: an existing note (for example DF5-O already froze pfb-imaging)
   or an owner decision in `research/finish-plan.md` section 7 changes the
   proposal.
6. **Write the digest** `research/digests/<date>.md`: a "How this was made"
   section (window, queries, counts, tags, wall time by the host clock);
   then per area the 3-8 most relevant items: title, authors and year, link,
   one line on what it does, one line on its relevance to ra-ng naming a
   concrete rang file or task. Say plainly when an area has nothing new.
   Respect closed lines (gain-TV flagging, pointing, F2, F3; see STATE): an
   item that would reopen one says so and needs an owner decision.
7. **Proposal stubs** (at most five, ranked), each `research/proposals/<slug>.md`
   with: status line (proposed, date, rank, nothing built); hypothesis; the
   oracle (pinned versions); the data (existing truth sets and held-out
   sets first: A1, F-SIM, C5, S1-S3 and H1-H4, LUNO, the pilot); the
   tolerance to freeze (success, null, cost bound); expected cost; the matched
   comparison against the state of the art the AGENTS.md novelty rule needs,
   including a tuned strongest baseline, not a weak one; owner decisions.
   Do not repeat an open proposal; extend it in a new file if needed.
8. **Verify.** Extract every arXiv ID from the new files and re-query with
   `id_list`; compare title and first author; fix or drop mismatches. Check
   every relative link resolves.
9. **Checks**, with the main checkout's venv
   (`~/Github/rang/.venv/Scripts/python` on Windows):
   `python -m pytest tests/test_w4_8_docs.py tests/test_w4_5_release.py`
   must pass (the research index and its links). The broader
   `python -m pytest tests -k "index or readme or research"` fails to
   collect about 21 modules in a fresh worktree because `rang._core` is not
   built there; that is not a digest failure, so say so in the hand-back.
   `python -m ruff check python examples tests` (the project's paths; a bare
   `ruff check .` reports hundreds of unrelated errors).
10. **Commit** on the branch with the owner's identity
    (`gijsmolenaar@gmail.com`), message `digest <date>: ...`, **no
    co-author trailer or AI footer**. Do not push to main. Hand back in at most
    15 lines, numbers first: item count per area, the ranked proposals one
    line each, the branch name.

## Not in this skill

- Scheduling. A weekly trigger is an owner decision (follow-up).
- Acting on a proposal: that is the improve skill, and only on a proposal the
  owner approved.
