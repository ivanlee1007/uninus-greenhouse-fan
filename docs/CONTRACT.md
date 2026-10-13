# Greenhouse fan v8 implementation contract

The approved design is `../uninus-greenhouse-fan-design/sketches-v8/card.html` and `SPEC-v8.md`; it is an **offline design reference**, not production code. Preserve its global-above-grid C composition, fan image/readings/buttons, collapsed global limits, and natural automatic 1→2→3→4+ columns (3+1 is valid). The product card has **no width control**. Runtime and visual editor are distinct.

## Ownership and persistence

- One integration config entry represents a control group. Its group policy has `temperature_on`, `temperature_off`, `humidity_on`, `humidity_off`, `duration_seconds`. Integration Options edits only this policy (no per-fan sensor form).
- The integration is the **only authoritative** mapping store, keyed by fan Entity ID: `{fan_entity: {temperature_entity, humidity_entity}}`. Revision is an integer. Persist via HA Store per config entry. No implicit sensor guesses.
- Card editor item has `fan_entity` and `name`. It displays **temperature and humidity Entity selectors** for the selected fan by reading the integration's authoritative mapping. "Apply sensor sources" submits to the integration immediately, with observed `revision`; Home Assistant's later Lovelace Save only stores view selection/name/theme/layout. If backend apply fails, retain editor draft and show failure; do not claim Save commits backend.
- Multiple cards selecting the same fan read the same authoritative mapping. Revision mismatch rejects changes and lets user refresh/reconcile. Removing an item from one card does not remove the binding or stop other cards.
- Unbound/invalid/unavailable readings must not cause automatic control actions. When source or policy changes, reset any pending duration timers. Periodic evaluation must never bypass `duration_seconds`.

## WebSocket contract

- `uninus_greenhouse_fan/get` with `{entry_id}` returns `{entry_id, revision, policy, bindings, runtime}`. `runtime` keyed by fan Entity ID includes `mode`, `pending`, `reason` (and may include on/off). Authenticated users can read.
- `uninus_greenhouse_fan/bind` with `{entry_id, expected_revision, fan_entity, temperature_entity, humidity_entity}` validates admin privileges, entity domains (`fan`, `sensor`, `sensor`), exact existing IDs, conflicts, then persists and returns a fresh snapshot. On stale revision, reject without mutation. Bind one fan at a time; editor refreshes revision after each success. Do not make card-YAML copies of sources.
- `uninus_greenhouse_fan/manual` with `{entry_id, fan_entity, mode}` where `mode` is `on`, `off`, or `auto`; admin-only. Manual mode holds automation until resumed. Device actuator calls only through HA fan services, never in demo/tests.
- Config entry options changes are integration-only; no duplicate sensor selectors there.

## Safety/release gates

- Work is repository-only until the user authorizes deployment. No existing Home Assistant config, fan Entity, dashboard, automation, HACS installation, or release may be modified.
- Do not tag/release or deploy before both layers and interaction/regression tests pass. Verify GitHub remote exact commit after push.
