# Native threshold entity boundary (0.5.1)

## Implementation choice

The input_number domain owns its standard entity services. Its native
`EntityComponent` registers `set_value`, `increment`, and `decrement`, invoking
entity methods through HA's ordinary permission-aware entity-service handler.
The integration never re-registers or overrides those services.

A dedicated `EntityPlatform` is constructed with domain `input_number`,
platform name `uninus_greenhouse_fan`, and the greenhouse config entry. The
public `async_prepare`/`async_add_entities`/`async_destroy` lifecycle is used.
No mutation of the native component's platform map is needed: HA's
`EntityPlatform` constructor places every platform's `domain_entities` in a
shared domain index, which is the same index the native `EntityComponent`
holds for its registered services. This was checked against HA 2025.12.0 and
2026.10.1 and exercised with actual native input_number setup and actual ServiceRegistry
calls, not fake state registrations.

This low-level HA entity-platform boundary is intentionally version-tested.
It is not a promise that all future HA versions retain the same shared-index
contract. The CI pin in `tests_ha/requirements.txt` and native discovery suite
must be updated/tested when changing supported HA versions.

The wrapper subclasses real `InputNumber`, overriding only its three value
mutation methods and integrating availability/state publication. Native
restoration initializes with an explicit saved policy value, so unrelated
restored state cannot supersede the authoritative group policy. Each helper
uses an opaque UUID derived from group entry ID and semantic threshold key.
Registry identity is `(input_number, uninus_greenhouse_fan, opaque_unique_id)`;
pre-existing rows must also have the exact greenhouse config-entry association.
A mismatch fails closed rather than adopting another owner's registry row.
Native registry allocation resolves entity-name collisions normally. The
public snapshot rereads current registry IDs on every call, including renames.

## Durable mutation/lifecycle

All value updates merge into the authoritative registry policy inside the
existing group lock. Increment/decrement derive from that policy, not from a
helper value sampled before acquiring the lock. The complete candidate is
validated and saved with the existing verified group journal/atomic HA Store
before controller or helper publication. Synchronization changes only native
entity values; there is no state-event feedback listener and no helper-service
call during synchronization. Equal values do not emit additional helper
state events. Controller policy updates reset pending timers while preserving
manual gates/holds, without invoking an output service.

Group setup depends on input_number, creates and verifies four actual entity
states, then publishes runtime and starts control. HA can log and swallow an
individual entity add failure, so counting the platform's dictionary alone is
not sufficient: actual published state is verified as well. Failure destroys
the temporary owned platform and removes only newly created matching registry
rows. Retry preserves pre-existing owned IDs.

Unload gates control/availability immediately and closes new/queued registry
mutations. A shielded drain holds group then registry locks until in-flight
writes settle and the owned entity platform is destroyed. Registry rows are
retained; HA may leave unavailable restored states. Removal uses that same
lifecycle lock/drain and removes only the four matching platform/unique-ID/
config-entry registry records. Native config-entry removal is tested through
HA's real FlowManager/ConfigEntries removal machinery; only integration
loader/setup routing and static-resource registration are isolated seams.
Queued native service writes cannot recreate helper states after deletion.

## Native management limitation

These are native-domain entities managed by this integration, not records in
input_number's storage-backed `NumberStorageCollection`. No hidden bound
WebSocket callback is scraped, no native collection is monkeypatched, and no
`.storage/input_number` or YAML file is written. Consequently `editable` is
false and `input_number/list` does not enumerate them as user-created helpers.
Use the integration Options read-only list or HA's Entities page for names/IDs,
and native entity value controls or input_number services for values. Native
min/max/step helper editing is not supported. Live native frontend management
was not exercised; repository browser gates cover the shipped card only.

## Native numeric service compatibility

The unchanged HA 2025.12 native `set_value` schema uses `vol.Coerce(float)`.
`True` becomes `1.0` and `False` becomes `0.0` before entity dispatch. A subclass
cannot recover the original type. Rejecting numeric 0/1 instead would wrongly
reject valid thresholds. The integration therefore rejects booleans at direct
entity/policy/WS/native Options boundaries; the native service retains HA's
standard float coercion and applies full numeric bounds and pair validation.
Use numeric values in automations. The dedicated real-native test proves this
behavior. No global schema override or event-hook workaround is installed.
Strict rejection of pre-coercion booleans is not a user requirement; this native
compatibility behavior is recorded as a limitation, not a release blocker.
The verification report derives `acceptance_complete` from the actual feature
regression gates rather than claiming changes to the native service schema.

## Primary source audit

Audited HA 2025.12 source paths (also inspected in the installed pinned runtime):

- `homeassistant/components/input_number/__init__.py`: native setup, service
  schemas, `InputNumber` state/config and mutation methods.
- `homeassistant/helpers/entity_component.py`: shared domain entity index and
  native entity service registration.
- `homeassistant/helpers/entity_platform.py`: domain index sharing, registry
  association, entity allocation/rename/removal and public lifecycle methods.
- `homeassistant/helpers/service.py`: user/permission lookup and dispatch.
- `homeassistant/config_entries.py`: native removal, unload and cleanup.

## 0.5.1: actual HA 2026.10.1 compatibility

HA 2026.10.1 `InputNumber` subclasses `NumberEntity`; native `set_value`
dispatches `async_set_native_value`. Its public native value/bounds and
`_attr_native_*` attributes replace the old `_config`, `_current_value`,
`_minimum` and `_maximum` representation. The 0.5.0 wrapper therefore both
bypassed policy validation on native service writes and raised AttributeError
when publishing a policy that the verified journal had already committed.
This explains a saved policy revision alongside unchanged helper values and a
subsequent stale-draft conflict: the conflict was not the first failure.

The capability-based adapter defines only the appropriate setter for its
native generation. Modern execution never reads/writes the legacy fields;
legacy execution remains an explicit branch. Snapshot IDs and all four helper
publication plans are computed before persistence. A later HA state-publication
fault returns `save_status=committed_publication_failed` with the committed
policy/revision and a clear warning, disables control, and logs the traceback;
it is not reported as an uncommitted storage failure. Verified journal readback,
rollback and quarantine gates remain unchanged. Lifecycle unload/delete still
gates and drains in-flight services, forbidding post-unload publication.

A real HA HTTP regression also confirmed that static route creation happens
before CORS setup, so a CORS failure leaves GET registered while the old success
flag stays unset. Retry now verifies exact route ownership, completes CORS,
and avoids duplicate route registration; concurrent setup is serialized.

`tests_ha/reproduce_050_modern.py` intentionally executes the unchanged 0.5.0
source from baseline commit `411fce8` against actual modern InputNumber and
HA Store/journal. Its RED evidence records persisted humidity **88.1**, policy
revision **1**, unchanged helper **93.4**, then the exact `_minimum` AttributeError.
The detached entities isolate that root cause from the separate modern HA
warning about an entity's reserved `group` attribute; production now uses
`_fan_group`. Native EntityPlatform/ServiceRegistry RED separately proves the
old native setter bypass. No replacement/fake modern InputNumber is used.

Verified locally: Windows 10, HA **2025.12.0 / Python 3.13.14** and HA
**2026.10.1 / Python 3.14.5**, in separate environments. The installed modern
input_number source is byte-identical to the official 2026.10.1 tag, SHA256
`125533042f60e6e3a58d31f971b85d3ba4df42a7c47f5eccc4a9f26ed52927d2`.
The real native Options HTTP schema serializer is exercised for each version;
modern HA's probatio serializer accepts the existing flow schemas. CI now has
both HA versions on Windows and Ubuntu, but hosted CI/Ubuntu has not been run
locally or claimed as verified. Full counts, dependency/source hashes and
worktree fingerprint are in `verification/0.5.1-thresholds.json`.

No live Home Assistant, credentials, hardware, deployment, restart, commit,
push, tag or release is used by these tests.
