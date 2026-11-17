# v030-mcp: an agent runs the chain through `rang-core mcp`

`chain.json` is the receipt of `tests/test_mcp_chain.py::test_agent_runs_the_chain_over_stdio`, written with
`RANG_MCP_CHAIN_RECEIPT=research/results/v030-mcp/chain.json` and `RANG_FIXTURE` pointing at the public
fixture (`outer_scans.zip`, SHA-256 pinned in `rang.notebook.data`), on the Windows host, 2026-11-17.

- A scripted client (no SDK, no network) speaks JSON-RPC 2.0 over the server's stdin and stdout:
  initialize, tools/list, listobs, run_status, config_check (all stages), run (the plan; nothing written),
  run with the plan's `confirm` token, run_status until the job is done, job_log, fits_stats, receipts.
- **The user's "yes" to the plan is played by the script**; a real agent must get it from the user
  (`docs/agents/use-the-mcp-server.md` section 2).
- Stages flag, calibrate, apply, image, selfcal all `done`; flag versions `rang_original` then one per
  writing stage; the final image 128², no NaN.
- The transcript keeps every message; the text copy of each structured tool result is left out, lists of
  more than 16 numbers are cut to four, and local paths are replaced by `<work>`, `<fixture>`, `<tmp>`,
  `<python>`, `<checkout>` and `~`.
- `commit` is the branch commit the test ran at. Configuration: in the receipt (`config`).
