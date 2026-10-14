# UNiNUS Greenhouse Fan 0.2.1

Home Assistant integration with a Lovelace card based on the approved global-policy-above-grid v8 design. Repository-only development build: no deployment, release, live HA restart or physical fan operation is performed by these tests.

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
- Output replacement retains the opaque device identity, but **does not transfer the old hold/timers**. It does not actuate the old output. The new output starts automatic evaluation with fresh timers if complete healthy sources exist; a zero-duration policy permits action on its next evaluation. Review this before saving.
- Manual on/off requires an owned available output, **not sensors**. A durable hold is saved before dispatch, survives restart and remains held if the service fails. **Resume automatic** clears the hold without immediate actuation; manual-only devices remain automatically inactive. The backend can clear an offline target's hold, while visible card buttons require availability.
- Auto remains fail-closed for missing/unavailable/mislabeled/non-finite readings. On: temperature above limit **OR** humidity above limit. Off: temperature at/below off limit **AND** humidity at/below off limit. Conditions must last the required duration.

## Dashboard: display-only editor

1. Add the **UNiNUS Greenhouse Fan** card. The integration serves/registers its bundled module in storage-resource mode. YAML-managed resources need `/uninus_greenhouse_fan/card.js?v=0.2.1` manually as a module.
2. A unique loaded group resolves automatically. With several groups choose the friendly **control group** dropdown **in the card editor only**, then Save. The displayed runtime card never shows a group selector. Missing, multiple, unloaded and query-failed groups show noninteractive guidance to edit the card or open Settings; saved missing/unloaded references are never silently switched.
3. Add display items and select from **only this group's configured devices**. Configured offline devices are included and marked offline. No arbitrary HA entity picker is offered. If none exists, follow the integration settings link and Add device, then refresh.
4. Set display names/order, card title, theme and automatic/one/two-column layout. Dashboard **Save** persists only view settings. There are **no sensor fields, Apply, Discard, revision fields or backend writes** in this editor. Removing a display item neither deletes the device nor actuates it.
5. New choices store opaque `device_id`, independent of name/output, so they follow output edits. A deleted stable reference cannot fall back to a different output. Refresh and scope/disconnect races cannot replace new inventory or show stale manual results.

The policy strip stays above the grid. Automatic layout uses the card's own width: 390/720/1080/1380px show 1/2/3/4 columns. Animation/readings follow real entity state, not optimistic toggles. Blades/hub are red and rotate only when the available output reports `on`, even with missing/unavailable sensors or manual-only configuration; other output states are neutral gray and paused. Reduced-motion disables animation, not running color.

Disabled output diagnostics distinguish an entity absent from HA from reported `unknown`/`unavailable`, include the authoritative configured output ID/state and Settings guidance. Deleted stable selections explicitly require reselection in the card editor; stale YAML is never substituted. Manual gating already supports configured `fan.*`/`switch.*` outputs without sensors; regression fixtures include `switch.uss_p130_f5_relay0`. These synthetic tests do not establish that switch's live state or permissions.

After updating resources, hard-refresh/reopen all dashboard tabs: a previously registered custom element cannot be replaced by merely fetching a newer JS file. Verify the **loaded** module in browser DevTools with `customElements.get('uninus-greenhouse-fan-card').buildVersion` (expected `'0.2.1'`); the editor class exposes the same marker. A served-file version alone does not prove the active browser element is current.

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
node --test tests/test_card.mjs
python -m compileall -q custom_components/uninus_greenhouse_fan
node --check www/uninus-greenhouse-fan-card.js
node --check custom_components/uninus_greenhouse_fan/card.js
python -c "from pathlib import Path; assert Path('www/uninus-greenhouse-fan-card.js').read_bytes() == Path('custom_components/uninus_greenhouse_fan/card.js').read_bytes()"
git diff --check
python tests/verify_card_browser.py
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

Before production use, review target HA version/permissions and verify native Options and Lovelace dialogs in an isolated authenticated HA instance. Devices with complete healthy sources may automatically act under the policy **even without a dashboard card**. Live HA .223 is unauthenticated here; its installed compatibility, native frontend button wording and hardware behavior are **not live-verified**. No commit/push/tag/release/deploy/restart/fan operation is authorized by this repository task.
