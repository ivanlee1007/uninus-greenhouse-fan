# Persistence transactions and recovery

Device inventory, sensor bindings, revision and manual holds are one durable record.
The integration constructs the real HA `Store` with `atomic_writes=True`. A write
interrupted before the atomic replacement leaves the previous record intact.

Before every candidate write (including migration), the integration atomically
writes and verifies `<storage file>.pending`. Its `previous` field contains the
previous record in HA's complete JSON envelope (`version`, `minor_version`, `key`,
`data`), or `null` if no record existed. The candidate is written through the real
Store and checked with at most three direct disk reads, bypassing Store caches.

- A transient read failure followed by an exact match is a successful save.
- An unsuccessful write or three unsuccessful verification reads trigger rollback.
  The prior bytes are either verified already intact or restored atomically and
  verified. Only then is a normal retry-safe Save failure returned.
- If rollback, verification, or journal release fails, the group stops controlling
  equipment, keeps the journal as durable quarantine, and logs its exact path at
  critical level. Native forms retain input and show a distinct quarantine error,
  not an invitation to retry. Setup refuses the journal before loading Store, even
  with a new HA process, so an indeterminate replacement output or cleared hold
  cannot silently become automatic after restart.
- Cancellation waits for the actual underlying writer to finish, then verifies
  rollback while the registry/group locks remain held. Repeated cancellation does
  not abandon cleanup. If cleanup fails, quarantine remains. No canceled manual
  command is dispatched. Unload during a successful manual save may persist the
  hold, but never dispatches; the hold survives reload. Writes are rejected before
  Store can schedule final-write when HA is already stopping. Shutdown during an
  already-started write may finish saving the hold, but cannot dispatch afterward.
- Setup and unload share a persistent per-entry lifecycle lock. Unload first stops
  timers/control and closes the old registry to queued/new mutations, then drains
  the group and registry mutation locks before removing the runtime. This covers
  transactions before the journal executor even starts, not just existing journals.
  Setup cannot load the old disk record while a prior save can still publish.
  Repeated cancellation of unload is deferred until drain finishes; only then is
  cancellation propagated and setup permitted. Indeterminate writes retain the
  restart-visible quarantine described above. An OS-level hung write deliberately
  keeps unload and subsequent setup waiting rather than enabling stale control.
- Journal removal at successful commit is deliberately one synchronous filesystem
  unlink with no intervening await before runtime publication. All writes, fsyncs,
  readback, and rollback work run in the executor. A crash while the journal remains
  conservatively requires recovery, even if the candidate happened to reach disk.

## Explicit recovery from quarantine

Do **not** merely delete `.pending` or retry Save: the primary file could contain
an unacknowledged new output, missing hold, or corrupt data. Quarantine itself does
not turn off physical equipment; use independent controls if necessary.

1. Keep the affected integration unloaded (or stop HA before editing its storage).
   Resolve the filesystem/read/write fault first. Back up both the primary storage
   file and its `.pending` journal before editing anything.
2. Read the journal's `previous` field. If it is an object, restore that **whole
   envelope**, not just `data`, to the primary path using atomic replacement. If it
   is `null`, restore the previous absence by removing only the primary file.
3. Independently read and parse the restored primary file and compare the complete
   envelope with `previous` (or confirm absence). Check equipment, bindings and
   manual holds. If the journal is unreadable, restore a known-good backup; do not
   infer ownership from the uncertain new record.
4. Only after the prior state is verified, remove the `.pending` journal, then
   reload the group. Confirm its inventory and holds before submitting the desired
   change again. Other groups may conservatively block control while this one is
   unloaded, because cross-group ownership cannot be established.

This recovery is intentionally explicit, not automatic adoption of uncertain
settings. Disk read retries are bounded by count, not by elapsed time; an OS-level
hung I/O can still block. Full filesystem/device failure or external deletion of
both storage and the journal is outside this transaction's protection. The tests
exercise real HA Store and atomic writer APIs in an isolated temporary HA directory;
no live HA restart, configuration mutation, or hardware actuation is required.
