# Heavy-lock backfill (2026-11-16)

Status: **implemented and unit-tested** on branch `lock-backfill`; not yet on
the live queue (it takes effect for new tickets once merged and pulled into the
main checkout, whose `tools/heavy_lock.py` every session calls).

## The incident

On 2026-11-16 the queue was strict first come, first served. The head was a
shared ticket for 4 slots and 46 GB. One running 6 GB hold left 42 of 48 GB,
so the head did not fit, and every ticket behind it waited for about an hour
with 14 of 16 slots free, 1-slot 2 GB jobs included. An exclusive ticket at
the head blocks the queue in the same way while it drains the shared jobs
(research/next-session.md, "Exclusive holds"; ts-p1's T6 ticket on the same day).

## The rule

`tools/heavy_lock.py`, function `decide`, evaluated at every poll and again
under the mutex from a fresh read of the queue and the holds before a waiter
starts:

1. The head starts as soon as it fits, as before (an oversized shared job still
   runs alone; an exclusive ticket waits for every shared job).
2. A shared ticket further back may **backfill** while the head does not fit,
   if it fits the slots and memory free right now, strictly (no
   oversized-job-runs-alone exception). Earlier backfill-aware shared tickets
   that fit get their room reserved first, in queue order, so backfillers do
   not overtake each other.
3. **Drain limit.** Backfill past the head stops once the head has waited its
   limit, counted from the time in its ticket name (the critical offset added
   back; the mtime is refreshed every poll). The running jobs then drain and
   the head starts. The limit is the head's own: `run --drain MIN`, written
   into its ticket as `drain_s`; default `RANG_HEAVY_DRAIN_MIN`, 15 minutes;
   `--drain 0` is strict first come, first served. For a ticket written by an
   older copy of the helper (no `drain_s`) the backfiller's default applies.
4. **Exclusive.** An exclusive head is backfilled past until its limit, then
   drains. Exclusive tickets never backfill themselves.
5. **Critical.** No ticket backfills past a critical head, so `--priority
   critical` keeps its meaning: served first, never preempting.
6. A backfilled hold carries `"backfill": true` in its slot file; `status`
   marks it `backfilled`, prints every ticket's wait, and on the head says
   whether later tickets may backfill or the queue is draining.

The rule is stateless: a ticket that becomes head after waiting longer than its
limit behind an earlier head is draining at once, which is intended (it has
waited long enough).

Known limit: a backfilled job can still delay the head by its whole runtime,
since the lock has no runtime estimates; the drain limit only stops new
backfills. A job that must not be delayed asks `--drain 0`, or, on the
release's critical path, `--priority critical`.

## Compatibility with running waiters

Waiters already running an older copy keep strict FIFO for themselves: they
start only at the head and never backfill. Their tickets have no `drain_s`, so
new waiters reserve no room for them while they wait further back. New files go
nowhere that old copies glob; the new keys in tickets and slot files are
ignored by them.

## Tests

`tests/test_heavy_lock_backfill.py` (11 tests; temporary lock directories only):
the incident replayed through `decide` and through real waiters; no backfill
past the drain limit (the head's own limit, the environment default for an
older ticket); reservation order; an exclusive head backfilled past then
drained; exclusive tickets never backfill; a critical head holding back a
ticket that would fit; the CLI option and the variable.
`tests/test_heavy_lock_queue.py::test_exclusive_waits_for_shared_and_blocks_later_shared`
now pins `drain_s=0`, the behaviour it asserted before; the #30/#31 tests
(ticket order, a reader on a ticket, the mutex re-check) are unchanged and pass.
The five `RANG_HEAVY_*` variables are now in `rang.core.ENVIRONMENT`, and
`tests/test_w4_1_receipts.py` scans `tools/heavy_lock.py`.
