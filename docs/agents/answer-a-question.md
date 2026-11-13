# Answer a beginner's question

For: someone learning radio astronomy or rang who asks a question in plain
words ("what is a visibility?", "why does flagging matter?", "what did the
flagging experiment find?"). Ends in an answer grounded in the repository's
own material, with the sources named.

## 1. Find the material

Look in this order and stop when the question is covered:

1. The beginner pages: `docs/concepts/basics.md` (the chain in one page) and
   `docs/glossary.md`.
2. The introductory track, `notebooks/intro/i1-*.ipynb` to `i9-*.ipynb`
   (radio sky, visibilities, the MeerKAT array, the measurement equation, RFI,
   calibration, imaging, polarisation, time domain); `docs/learn/index.md`
   gives the route.
3. The concepts pages, `docs/concepts/`: ingest, flagging, gains, imaging.
4. The notebooks, `notebooks/00-ms-to-image.ipynb` (the whole chain),
   `notebooks/01-*.ipynb` to `05-*.ipynb` (tutorials on the public 45 MB
   MeerKAT fixture) and `notebooks/science/` (the two research questions).
   `docs/tutorials/index.md` says what each one covers.
5. The command line, `docs/cli.md`, and the how-to guides, `docs/howto/`, for
   "how do I run ..." questions.
6. The research reports, `research/README.md` (index) and
   `research/STATE.md` (status), for "does rang do / show ..." questions.

For basics the repository does not cover, answer from general knowledge and
say so, then point to the nearest notebook.

## 2. Answer

- Answer the question first, then name the files and notebook sections it
  rests on (path and heading).
- Keep the status straight: rang is a tested research demonstrator, not an
  operational calibrator; no novelty is claimed; gain-TV-guided flagging and
  beam and pointing are closed as null (`research/STATE.md` has the current
  list). Say "proposed", "implemented" or "measured" as the reports do.
- Quote numbers only from the reports or archives in `research/`, never from
  memory, and give the file they come from.
- When showing is better than telling, offer to run the relevant notebook cell
  on the fixture (`rang.notebook.data.download_fixture` fetches and verifies it)
  rather than writing new code.

## 3. Do not

- Edit the repository to answer a question. If the docs are wrong or missing
  something the question exposed, say so and offer a pull request
  (`docs/contributing.md`).
- Present an exploratory notebook replay as a result: the real results are
  read from the tracked archives in `research/results/`.
