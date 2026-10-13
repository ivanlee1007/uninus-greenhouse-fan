# UNiNUS Greenhouse Fan

A Home Assistant custom integration and Lovelace card implementing the user-approved **C 方案 · 逐欄自動排列 v8** design. **Development repository — not released, installed, or live-verified.** No Home Assistant system or fan has been modified by this repository work.

## Approved interaction contract

- Collapsible global policy strip **above** the independent fan cards at every width; its collapsed view shows only temperature/humidity upper and lower thresholds.
- Auto columns based on the card's own device-grid width; with four devices the grid can display 1, 2, 3+1, or 4 in a row. Fixed 1- or 2-column choices remain distinct.
- Runtime card has per-device sensor readings and manual controls, not configuration forms.
- Editor exposes a fan entity, display name, temperature entity, and humidity entity **for each displayed fan**.
- Integration Options owns only shared thresholds and duration. The integration persists one authoritative per-fan sensor binding that both control and display read; the card editor explicitly applies a binding via a versioned WebSocket mutation. Ordinary Lovelace Save alone cannot commit backend mappings.

See [implementation contract](docs/CONTRACT.md). The approved offline design source and tests remain in `../uninus-greenhouse-fan-design/`; they are references, not deployed code.

## Status and safety

The card and integration are under initial implementation. This repository is private and contains no tokens. There is no published release, HACS installation, HA deployment, restart, dashboard change, or test fan actuation. Do not install against production equipment before the code has passed integration/security review and an explicitly authorized staged physical-device test.
