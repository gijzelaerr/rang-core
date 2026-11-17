# Task procedures for agents

Written procedures for the tasks people most often bring to an agent in this
repository. They are plain markdown so that any agent (Claude, Codex or another)
can follow them: open the agent in a checkout and ask it to follow the
procedure. Claude Code also finds them as skills, through the thin wrappers in
`.claude/skills/<name>/SKILL.md`; each wrapper only points to the page here,
which is the one source.

Every procedure assumes the rules of `AGENTS.md`, Part 1. None of them merges
anything on its own: work that changes the repository ends in a pull request
(the route is in {doc}`../contributing`).

| Procedure | For | Ends in |
| --- | --- | --- |
| {doc}`answer-a-question` | a beginner asking about radio astronomy or rang | an answer that cites the notebooks, concepts pages and reports it rests on |
| {doc}`image-a-meerkat-ms` | an astronomer with a MeerKAT Measurement Set | a FITS image, its receipts and a short run record |
| {doc}`propose-and-measure` | an algorithm scientist with an idea | a frozen proposal note, a measurement against an oracle, and a pull request |
| {doc}`use-the-mcp-server` | an agent with rang-core's MCP server and a user's MS | read-only answers, and runs or images only after the user confirmed a plan |
| {doc}`check-and-ci` | any agent session with a changed branch | a quick local check, a pushed branch with a green CI run, and the oracle gates left to one full check |

```{toctree}
:hidden:

answer-a-question
image-a-meerkat-ms
propose-and-measure
check-and-ci
use-the-mcp-server
```
