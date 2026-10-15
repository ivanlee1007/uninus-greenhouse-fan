# UNiNUS Greenhouse Fan 0.5.6

The four **expanded global-card threshold sliders** now adjust in whole **1 °C / 1 %** steps. Newly edited values display as integers without `.0`. Native `input_number`, Shared policy Options, service precision and sensor-reading formatting are unchanged.

The approved button-icon demo A is now shipped: **▶ 開啟** and **■ 關閉**, using 16px SVG icons before the text. Icons inherit the existing button color; manual-hold behavior and authoritative output feedback are unchanged.

Home Assistant integration with a Lovelace card based on the approved global-policy-above-grid v8 design. Repository-only development build: no deployment, release, live HA restart or physical fan operation is performed by these tests.

## Lock readings to the right (0.5.3)

The global native editor checkbox **溫濕度固定在風扇右側** applies to every displayed fan. It is off by default, preserving existing responsive geometry. Enable it to keep temperature/humidity beside the fan animation even on narrow fixed-two-column cards, reducing the previously stacked hero height. It is independent of **顯示控制模式與診斷訊息**; badges, buttons, diagnostic safety gates and backend policy remain unchanged.

```yaml
lock_readings_right: true  # optional; only literal boolean true enables, default false
```

Use unquoted YAML `true`/`false`; strings (`"true"`, `"false"`), numbers, null, arrays and objects do not enable it. This setting only changes display configuration, emits typed booleans, and makes no backend writes. Dashboard Save/reopen retains it. The opt-in `.readings-right` class overrides the legacy fixed-two narrow stacking, with hero-local container units scaling the complete animation group and bounded 13–21px readings. No whole-card overflow hiding is used. Verified card widths: **320, 390, 500, 630, 720, 1080 CSS px**, layouts auto/1/2, both themes and both details settings. **320px is the supported tested minimum**, not a promise of arbitrary sub-320px fixed-two fit; unusually long/unbounded numerical readings are not a supported fixed-two-width contract.

`tests/verify_readings_browser.py` is the seventh browser gate. It checks actual reading/animation rectangles, full negative-temperature and 100.0% values/units and unavailable dashes, fixed-two columns and overflow, typed editor Save/reopen false→true→false, and enabled-mode node/focus/animation identity across three polls plus 18 hass updates. `docs/verification/0.5.3-readings-red.json` records the failing exact 0.5.2 baseline; `docs/verification/0.5.3-frontend.json` records actual full-gate results, measured height reductions, shipped hashes and the working-tree fingerprint. The editor test uses a synthetic Dashboard Save host, not live HA storage UI. Existing six browser gates, the unchanged approved-A fixture and both isolated actual HA runtime suites remain mandatory.

## Compact device details and stable refresh (0.5.2)

The card editor checkbox **顯示控制模式與診斷訊息** applies to every displayed fan. It defaults to checked for old YAML. Unchecking emits the typed boolean `show_device_details: false`; Dashboard Save retains it. Only the complete per-fan `.device-details` region (control mode / pending-report line and reason/diagnostic paragraph) is omitted from the DOM. No empty reserved space remains. Headers, status badges, current readings, fan buttons, global policy strip and the outer card note remain visible. This is display-only: no binding, policy or output command is sent.

```yaml
show_device_details: false  # optional; only literal false hides, default true
```

Healthy five-second refreshes now use the current authoritative snapshot without temporarily marking controls as loading. A minimal keyed DOM patch updates changed values/attributes without remounting unchanged fan articles, rotating elements, manual buttons or the global switch. Threshold ranges and Save/Cancel remain continuously connected; dirty drafts retain their original policy revision. Initial loading, read errors, unloaded/missing scopes and actual pending commands still fail closed. Polls coalesce while a read is outstanding; newer explicit reads/actions and scope/disconnect invalidate stale completions, and disconnect cancels the polling timer.

The real Chromium regression failed against exact `eac6a1d` / 0.5.1: across three controlled five-second polls plus 18 `hass` updates, original control subtrees were removed, focus was lost, and 24 disabled-attribute mutations were observed. The fixed gate requires **zero original-control removals and zero disabled-attribute mutations**, identical connected nodes and CSS animation objects, retained focus/open/scroll state, updated readings and no idle writes. Deferred reads additionally test coalescing, command invalidation, real pending disable, live server diagnostics/colors/mode, failure/unload, new scope and disconnect. `docs/verification/0.5.2-refresh-red.json` records the baseline; `docs/verification/0.5.2-frontend.json` contains actual full-gate results, both HA runtime fingerprints and browser evidence.

The checkbox test clicks the actual custom editor control and reopens saved false/true/false configs through a synthetic Dashboard Save host, checking refresh persistence and both themes at 390/500/720px fixed-two layout. This is **not** a test of live HA's dashboard storage dialog. Baseline reproduction: extract `git show eac6a1d:www/uninus-greenhouse-fan-card.js` to a local file, then set `CARD_TEST_SOURCE` to its absolute path when running `python tests/verify_refresh_browser.py` (expected assertion failure). Run without that variable for the fixed bundle. Existing slider pointer/keyboard and manual-mode gates remain required; CI includes both new browser scripts. No polling or changed-state rendering is disabled to hide flicker.

## Device settings: one save in the integration

1. **Settings → Devices & services → Add integration → UNiNUS Greenhouse Fan**. Name the control group and choose shared temperature/humidity on/off limits and required duration.
2. Open the group's **Configure / Options** menu. **Configured devices** shows names/outputs; **Add device**, **Edit device**, **Remove device** manage an unlimited-length inventory. **Shared policy** retains the group-wide threshold form.
3. **Add device** opens a native form: name, existing output entity (`fan.*` or `switch.*`), optional temperature sensor (temperature device class, °C) and humidity sensor (humidity class, %).
4. Leave **both sensors blank** for manual-only control; automatic control requires a **complete pair**. Clearing both on an existing device clears its binding. A partial pair produces a field error with your input retained.
5. Submit once (**Save/Submit**, depending on HA frontend language) to save the complete record. **Cancel/close writes nothing**. Validation/storage errors preserve inputs. A concurrent settings change requires cancel/reopen/review; there are no revision or internal-ID fields.
6. **Edit device** selects a named configured record then opens the same form. **Remove device** requires explicit unchecked-by-default confirmation, stops automation and clears its hold, but **does not switch the physical output**. Arrange its physical state first if necessary.

### Ownership and control safety

- Each output can belong to one configured device/group. Duplicate outputs are rejected within and across loaded groups. If **another group is unloaded**, its ownership cannot be proven: device assignment/editing and manual/automatic control are conservatively blocked until **all groups load**. Removal and shared policy edits remain possible.
- Sensor-source changes reset automatic duration timers and preserve manual holds. A name-only edit leaves timers intact.
- Output replacement retains the opaque device identity, but **does not transfer the old hold/timers**. It does not actuate the old output. The new output starts automatic evaluation with fresh timers only under global Auto if complete healthy sources exist; a zero-duration policy permits action on its next evaluation. Review this before saving.
- Explicit manual on/off/resume requires an owned existing canonical `fan.*`/`switch.*` output reporting **`on`, `off`, or `unknown`**, **not sensors**. Missing, `unavailable`, invalid states/domains, unowned outputs and stale/unloaded scopes are rejected before saving and rechecked after awaited durable persistence. A durable hold is saved before dispatch, survives restart and remains held if the service fails. **Resume automatic** clears the hold without immediate actuation; manual-only devices remain automatically inactive. An `unknown` output may receive explicit manual commands, but automatic evaluation stays paused until valid `on`/`off` feedback returns. Successful commands update hold mode only; they never fabricate feedback or animate blades optimistically.
- Auto remains fail-closed for missing/unavailable/mislabeled/non-finite readings. On: temperature above limit **OR** humidity above limit. Off: temperature at/below off limit **AND** humidity at/below off limit. Conditions must last the required duration.

## Global Auto / Manual control (0.3.0)

The compact switch lives **inside the existing global policy strip**, not in the editor or a new row. It controls **every configured device in the selected group**, including devices hidden from this card, offline outputs and manual-only outputs. Only administrators can change it. The switch is disabled while pending and reflects the **authoritative backend snapshot**, never an optimistic selection; click/keyboard activation does not expand the policy disclosure.

- **Manual:** persist a group-wide automation gate, cancel all pending duration state and **maintain current physical output**. No turn-on/turn-off service is called by the mode command. Explicit individual manual on/off remains available for healthy or `unknown` output feedback; individual Resume is not rendered and backend requests are still rejected with instructions to switch the group to Auto first.
- **Auto:** in one transaction clear **all** individual manual holds, reset pending duration state and resume every configured device. No immediate actuation occurs in the mode handler. The next normal periodic evaluation starts fresh durations; a zero-duration policy can actuate on that next evaluation. Sources/feedback must still be valid.
- The global gate survives reload, device additions/replacements/source/name edits and explicit per-device manual commands. Historical storage without `control_mode` migrates to `auto`, preserving stable identities, bindings and existing holds. Invalid stored mode flags fail closed. Per-device manual holds while global Auto remain independent until explicit individual Resume or global Auto.
- All mutation paths retain the flag. Group/device/registry locks serialize mode changes against manual commands, device CRUD and evaluation. Verified persistence failures preserve the previous complete modes and pending timers; indeterminate failures quarantine the group. Unload/stopping checks occur before and after awaited persistence, and disposed UI completions are ignored.

Temperature and humidity readings gain **separate underlined high-contrast warning colors only in effective Auto mode** when their finite native °C/% value is strictly greater than its own on-threshold. Exact equality, missing/invalid/mislabeled readings, individual holds and global Manual do not warn. No alert rows were added; output blade colors still reflect actual feedback only.

Measured collapsed four-device heights (CSS px), identical in light/dark themes; baseline is `fea58d4`:

| Layout | Width | Before | 0.3.0 | Reduction |
|---|---:|---:|---:|---:|
| fixed 2 | 390 | 886.09375 | 834.09375 | 52 |
| fixed 2 | 500 | 919.109375 | 825.109375 | 94 |
| fixed 2 | 720 / 1080 | 848.171875 | 737.671875 | 110.5 |
| auto | 390 | 1481.15625 | 1309.15625 | 172 |
| auto | 500 | 1478.171875 | 1275.171875 | 203 |
| auto | 720 / 1080 | 848.171875 | 737.671875 | 110.5 |

All 16 measured cases preserve 44×44px minimum control targets, zero horizontal overflow and unclipped reason/readout text. These are local real-Edge synthetic fixtures, not live dashboard measurements. Full measurements, computed colors and gate counts: `docs/verification/0.3.0-control-mode.json` (reruns also produce `tests/evidence/control-mode-layout.json`).

## Shared threshold sliders (introduced in 0.4.0, approved A)

Expand the existing global strip to edit temperature and humidity in **two group boxes** (side-by-side wide, stacked narrow). Each group puts Start above Stop. The card editor and Dashboard Save still change only display configuration.

- Sliders create a local draft only. **取消修改** discards it and reloads the saved policy; **儲存門檻** saves all four thresholds together. Only an administrator with a loaded selected group can save. Saved summary, warning colors and automatic control keep the saved policy until verified success. Pending saves block another Save, Cancel and other card writes.
- Card-only default display ranges are temperature **0–50 °C**, humidity **0–100 %**, step **1**. Only the changed finite numeric draft field is rounded to an integer. Untouched legacy fractions remain exact in the saved policy, adjacent output and all-four Save payload; opening, polling, dragging and Cancel do not write them. Native range thumbs/DOM values necessarily snap to the nearest whole tick at step 1; the output still shows the true legacy fraction (for example **37.7 °C**) until that particular control is edited. There is no silent migration or display-only rounding of saved fractions.
- Valid historical temperatures outside the default range expand to whole-number tick anchors using floor/ceil: **−10.5 / 70.5** remains unchanged, with range **−11–71** in initial markup and live controls. Backend limits remain **−20–80 °C / 0–100 %**, with Stop ≤ Start; invalid/non-finite/boolean/string values are rejected. Invalid existing policy displays an error and disables editing rather than overwriting it. Native helpers retain step **0.1**, described separately below.
- The existing verified registry Store is the **only durable policy authority**, including native **Shared policy** Options and duration. Initial migration uses historical entry options over entry data over defaults, preserving identities, sources, holds and global mode. Once saved in the registry, stale entry options cannot restore an old policy. Native Options may edit duration; card Save preserves it.
- A separate internal policy revision changes only when policy changes. Ordinary polls never rebase a dirty draft. A conflict or save failure retains the draft and old effective policy/timers; use Cancel/reload (or cancel/reopen native Options) to review current values. There are no revision inputs. Successful changed policies reset duration state while retaining manual holds and global mode; **the save handler never actuates equipment**. Normal periodic evaluation may act later, including the next tick for zero duration.
- Expanded state, the exact focused slider node and a pointer drag survive live `hass` and snapshot updates. Old scope/detached operation results are ignored. Quarantine disables control; follow [verified-store recovery](docs/PERSISTENCE.md), not repeated Save.

Local browser gate compares the frozen approved A fixture with production at 390/500/720/1080px in both themes and auto/fixed-two layouts. It checks group/slider and whole-card composition, overflow, real pointer/keyboard editing, Save/Cancel, validation, permissions, conflicts, failures and lifecycle races. Production deliberately replaces demo-only saved messages with verified-backend/pending/conflict guidance and dynamic native duration; demo host controls are not shipped.

The ninth browser gate, `tests/verify_integer_sliders_browser.py`, checks all four real pointer/keyboard controls, integer draft/output values, whole tick anchors, exact untouched legacy fractions, Save payload/CAS/duration, unverified-save rejection, and zero writes on drag/Cancel. Existing geometry, conflict, permission, refresh and lifecycle gates and both frozen approved fixtures remain unchanged. `docs/verification/0.5.6-integer-sliders-red.json` records the real 0.5.5 baseline failure (`step=0.1`, expected `1`); `docs/verification/0.5.6-frontend.json` records the actual complete gate, runtime/source hashes and working-tree fingerprint. Historical refresh/readings RED references remain `0.5.2-refresh-red.json` and `0.5.3-readings-red.json`. These are isolated fixtures, not live HA or hosted-CI verification.

## Native threshold entities (0.5.1)

Architecture and compatibility boundary: [native threshold entities](docs/NATIVE_THRESHOLD_ENTITIES.md).

0.5.1 fixes the actual HA 2026.10.1 NumberEntity-based input_number API:
policy saves no longer commit and then fail on removed `_minimum` fields,
and native set_value/increment/decrement all enter the same validated durable
policy transaction. Legacy HA 2025.12.0 remains covered in a separate runtime.
Four helper publication plans and registry IDs are prepared before persistence;
a subsequent state-publication fault is reported as **saved, display failed**,
with control disabled and a reload instruction—not a second stale draft Save.
The card renders backend failure guidance once. Static-route retry after
partial registration is also covered by a real HA HTTP regression.

Local verification is isolated Windows HA/Chromium, not a live installation or
hosted CI run. CI defines Ubuntu/Windows × HA 2025.12.0/2026.10.1; see the
versioned verification report for executed counts, interpreter paths and
source/dependency/worktree fingerprints.

Creating a greenhouse group automatically creates **exactly four native
`input_number.*` entities**, one for each shared policy threshold:
`temperature_on`, `temperature_off`, `humidity_on`, `humidity_off`. Existing
groups receive them on load. They are actual HA `InputNumber` entities, not
`number.*` replacements or state-machine-only placeholders. Names include the
group's friendly title; opaque unique IDs use the persistent group identity,
not its name or list position. Same-name groups are allowed and get distinct
entities. EntityRegistry-selected entity IDs and user renames survive reload.

Find their current friendly names and IDs under **Settings → Devices & services
→ UNiNUS Greenhouse Fan → Configure → Threshold entities (names and entity
IDs)**, or in that integration's Entities list. The read-only public group
snapshot exposes `threshold_entities`, keyed by the four policy field names;
read this mapping rather than constructing an entity ID from a group name.
The native more-info/entity slider and standard `input_number.set_value`,
`input_number.increment`, and `input_number.decrement` work from the frontend
or automations under the caller's ordinary HA entity-control permissions.
The card's existing all-four Save and native Shared policy form remain
admin-only/unchanged and synchronize all four entity values.

Each native entity slider (not the card's global sliders) uses step **0.1**, units **°C** or **%**, temperature bounds normally
**0–50**, humidity **0–100**. Saved legacy temperatures outside 0–50 are retained
by extending the corresponding helper's bounds (the canonical policy still
accepts −20–80). Initial values always come from the saved authoritative policy,
never from restored helper state or old entry options. Every write merges into
the latest policy under the group lock, validates the complete on/off pair,
and durably verifies the existing group journal/Store transaction before
publishing any changed helper values. Invalid pairs, nonfinite values and
failed writes leave the prior effective policy and timers unchanged; quarantine
makes the helpers unavailable and stops control. Successful changes restart
policy timers, preserve global/individual manual holds, and never immediately
switch an output. There are no helper state-change-to-policy listeners.

**Management boundary:** these are integration-managed native entities, not
user-created records in HA's native helper storage collection. They advertise
`editable: false`; use the integration's Shared policy form for configuration.
Min/max/step are integration-owned and cannot be edited through the native
helper configuration dialog; no record is added to `input_number/list`, and
the Helpers configuration page need not list them. Entity IDs/friendly names
can be customized in the Entities page, and native more-info/dashboard entity
controls can change their values. No YAML files or native helper store are
written and HA's domain services are not replaced.

**Unload versus delete:** unloading removes this group's runtime helper
objects (HA may retain unavailable restored states) but preserves its four
owned registry records so reload retains IDs/customizations. Removing the
actual greenhouse group automatically drains queued/in-flight writes and
removes its four runtime entities **and owned EntityRegistry records**.
Ownership checks require both integration platform/unique ID and group
association; unrelated user helpers and other groups are untouched. Missing
helpers are safely recreated on the next group load. Partial creation cleans
newly created owned entries and refuses to start the group.

**Known native-service limitation, not a completed strict-boolean guarantee:**
HA 2025.12's original `input_number.set_value` schema uses `Coerce(float)`.
It converts a boolean to `1.0`/`0.0` *before* calling the entity, so the unchanged
native service cannot distinguish it from a numeric value. Direct entity,
WebSocket and native Shared policy writes reject booleans; the native service
rejects nonfinite/invalid numeric candidates but may accept coerced booleans
when the numeric candidate is valid. Strict native-service boolean rejection
would require an upstream schema change or relaxing the no-global-override
constraint. The real-HA tests explicitly reproduce this limitation.

Automation example (replace the quoted placeholder with the **actual**
`temperature_on` ID shown in the read-only list or current snapshot mapping;
no entity ID below is claimed to exist):

```yaml
actions:
  - action: input_number.set_value
    target:
      entity_id: "<actual temperature_on entity ID from Threshold entities>"
    data:
      value: 35.0
```

After the action, read that entity's state and the group's public snapshot:
its `policy.temperature_on` must agree and `threshold_entities.temperature_on`
must still point to the current entity ID. Adjust an off threshold first if
lowering an on threshold would otherwise violate the pair. Dashboard Save
still only saves display configuration; use the expanded card's explicit
policy Save to atomically change four thresholds.

## Dashboard: display-only editor

1. Add the **UNiNUS Greenhouse Fan** card. The integration serves/registers its bundled module in storage-resource mode. YAML-managed resources need `/uninus_greenhouse_fan/card.js?v=0.5.6` manually as a module.
2. A unique loaded group resolves automatically. With several groups choose the friendly **control group** dropdown **in the card editor only**, then Save. The displayed runtime card never shows a group selector. Missing, multiple, unloaded and query-failed groups show noninteractive guidance to edit the card or open Settings; saved missing/unloaded references are never silently switched.
3. Add display items and select from **only this group's configured devices**. Configured offline devices are included and marked offline. No arbitrary output picker is offered for device selection (the display-only subtitle picker below accepts any domain). If none exists, follow the integration settings link and Add device, then refresh.
4. Set display names/order, card title and subtitle, theme and automatic/one/two-column layout. Dashboard **Save** persists only view settings. There are **no sensor fields, Apply, Discard, revision fields or backend writes** in this editor. Removing a display item neither deletes the device nor actuates it.
5. New choices store opaque `device_id`, independent of name/output, so they follow output edits. A deleted stable reference cannot fall back to a different output. Refresh and scope/disconnect races cannot replace new inventory or show stale manual results.

The policy strip stays above the grid. Automatic layout uses the card's own width: 390/720/1080/1380px show 1/2/3/4 columns. Explicit **2 columns stays exactly two** at card widths 390/500/520/630/720px in both themes; compact stacked heroes/readings and smaller padding/fonts prevent overflow while buttons retain 44px minimum height. One display item occupies one of the two grid cells: no duplicate is fabricated. Animation/readings follow real entity state, not optimistic toggles. Blades/hub are red and rotate only when the available output reports `on`, even with missing/unavailable sensors or manual-only configuration; other output states are neutral gray and paused. Reduced-motion disables animation, not running color.

Disabled output diagnostics distinguish an absent entity from reported `unavailable`/invalid states and include the authoritative configured output ID/state and Settings guidance. `unknown` instead shows a warning: state unknown, explicit manual commands permitted, automatic paused until feedback. Its badge remains unknown and its blades neutral/stationary—not inferred off. Deleted stable selections explicitly require reselection in the card editor; stale YAML is never substituted. Manual gating already supports configured `fan.*`/`switch.*` outputs without sensors; regression fixtures include `switch.uss_p130_f5_relay0`. These synthetic tests do not establish that switch's live state or permissions.

After updating resources, hard-refresh/reopen all dashboard tabs: a previously registered custom element cannot be replaced by merely fetching a newer JS file. Verify the **loaded** module in browser DevTools with `customElements.get('uninus-greenhouse-fan-card').buildVersion` (expected `'0.5.6'`); the editor class exposes the same marker. A served-file version alone does not prove the active browser element is current.

## Display-only subtitle (introduced in 0.3.1)

The global switch is pinned to the **right** of the existing threshold strip: visible label **自動**, then a conventional switch track. Its outer button is transparent with no border/capsule. Threshold pairs wrap on the left at narrow widths; the toggle stays in that row with a 44px hit target. Global Manual renders **no individual Resume button**. Only individual on/off holds under global Auto show Resume; pending switches keep the previous authoritative mode until success.

The card editor offers **文字 / 實體** subtitle sources, with immediate escaped preview. Dashboard **Save** retains config and **Cancel** makes no backend writes. Old YAML keeps `各區獨立感測 · 同群組共用門檻` until a subtitle is supplied; explicit empty text or an empty entity hides the subtitle.

```yaml
# Static text; literal text only, no templates
subtitle_mode: text
subtitle_text: Greenhouse status
# subtitle_text: ''  # hide
```

```yaml
# One searchable native HA picker, unrestricted entity domains
subtitle_mode: entity
subtitle_entity: weather.home   # sensor.*, switch.*, input_text.*, etc. also supported
subtitle_attribute: temperature # optional; empty selects the entity state
subtitle_unit: true             # optional, defaults true; state unit only, never attributes
```

A missing entity/state, `unknown`, `unavailable`, null, non-finite scalar or missing selected attribute renders **—**. A missing attribute never falls back to the state. Numeric 0 and boolean false remain visible. Arrays/objects use safely escaped JSON bounded to 256 characters; failed serialization renders **—**. One entity or attribute only: no templates or text/entity composition. The picker emits config changes immediately on authoritative `value-changed`, including clears, and keeps active search mounted through state refreshes.

Historical subtitle verification: `docs/verification/0.3.1-frontend.json` records 50 offline Python, 42 native HA, 35 Node tests and all three browser scripts with zero skips. Current 0.5.3 results and fingerprints are in `docs/verification/0.5.3-frontend.json`. Local Chromium evidence: `tests/evidence/subtitle-layout.json` contains 36 source/attribute/unit cases and 48 theme/width/layout/mode cases at 390/500/720/1080px with right alignment, transparent borderless outer switch, 44px targets, Resume visibility and no overflow. Picker user-flow tests use an offline native-event-contract fixture, **not the live HA frontend picker**.

## Migration and old YAML

Existing bindings **and persisted manual-only holds** migrate idempotently into configured devices, preserving exact mappings and holds. Migration persists without actuation; legacy IDs are deterministic and retained on reload. Old literal `fan_entity` YAML continues to select the matching configured output:

```yaml
type: custom:uninus-greenhouse-fan-card
name: Greenhouse fans
items:
  - fan_entity: fan.front
    name: Front
layout: auto
theme: dark
```

**Old display-only outputs with neither a binding nor a persisted hold were never in integration storage. They cannot be inferred from dashboard YAML: Add them through Integration Options before manual control is enabled.** Old selections can still display state with a setup warning, but unregistered targets cannot be controlled.

Stable `device_id` selections follow output replacements; legacy `fan_entity` stays attached to its literal output and needs reselection after replacement. The deprecated admin-only `bind` WebSocket remains for old clients but can only modify an already configured output; it cannot create arbitrary bindings. The new editor never calls it.

## Persistence and local verification

HA Store owns complete device records, bindings and holds per group, with atomic writes and a pre-write durable transaction journal. Readback retries reconcile transient failures; other failures must verify rollback before returning a retry-safe error. Unreconciled storage disables the group and quarantines it across restart. See [persistence semantics and explicit recovery](docs/PERSISTENCE.md); **never simply delete a quarantine journal or retry Save**. Device snapshots project only allowlisted scalar fields.

Existing workflow commands:

```sh
python -m unittest discover -s tests -p 'test_*.py' -v
node tests/test_card.mjs
python -m compileall -q custom_components/uninus_greenhouse_fan
node --check www/uninus-greenhouse-fan-card.js
node --check custom_components/uninus_greenhouse_fan/card.js
python -c "from pathlib import Path; assert Path('www/uninus-greenhouse-fan-card.js').read_bytes() == Path('custom_components/uninus_greenhouse_fan/card.js').read_bytes()"
git diff --check
python tests/verify_card_browser.py
python tests/verify_control_browser.py
python tests/verify_subtitle_browser.py
python tests/verify_threshold_browser.py
python tests/verify_refresh_browser.py
python tests/verify_details_browser.py
python tests/verify_readings_browser.py
python tests/verify_icons_browser.py
python tests/verify_integer_sliders_browser.py
python tests/run_release_gate.py  # set HA_TEST_PYTHON, HA_MODERN_TEST_PYTHON, BROWSER_TEST_PYTHON
```

Browser tests require Playwright and Chromium/Edge. They execute the shipped JS in a real DOM using synthetic HA state/WebSocket only: configured selection, no source-write UI, exact widths/overflow, discovery/missing/unloaded/error, manual-only relay clicks, stale reads and disconnected completions. No HA network or hardware is used.

Real HA tests **must run separately** from the old adapter suite, which injects fake HA modules:

```sh
uv venv --python 3.13 .venv-ha
uv pip install --python .venv-ha/bin/python -r tests_ha/requirements.txt
.venv-ha/bin/python -m unittest discover -s tests_ha -v
```

Windows: use `.venv-ha/Scripts/python.exe` and add `--override tests_ha/windows-overrides.txt` to install. HA pins `lru-dict==1.3.0`, requiring unavailable MSVC build tools on this host; local verification uses the real 1.4.1 wheel. **HA remains pinned 2025.12.0**. `pycares==4.11.0` avoids its incompatible transitive 5.x API. Linux CI needs no Windows override. Native tests use actual ConfigFlow/OptionsFlow/EntitySelector/StateMachine/Store—not fake `sys.modules`—and exercise both flow handlers and HA's OptionsFlowManager save/reopen/abort path (only integration discovery/bootstrap is mocked).

## HACS and deployment gate

HACS custom repository: `https://github.com/ivanlee1007/uninus-greenhouse-fan`, category **Integration**, normal `custom_components/uninus_greenhouse_fan` layout.

Before production use, review target HA version/permissions and verify native Options and Lovelace dialogs in an isolated authenticated HA instance. Devices with complete healthy sources may automatically act under the policy **even without a dashboard card**. Local tests do not validate live hardware operation; authenticated live inspection, if performed separately, is read-only. No commit/push/tag/release/deploy/restart/fan operation is authorized by this repository task.
