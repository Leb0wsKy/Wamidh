# ADR 0003: public alerts by Cell Broadcast to population zones, confirmed by the dispatcher

- **Status:** accepted (2026-10-05)
- **Supersedes:** the "resident opt-in SMS" of CLAUDE.md §1, §8 (`resident_subscription`, SMS service) and §9.4.

## Context

When a fire is confirmed, the people living near it must be warned quickly and in their language.
The original plan was an opt-in service: residents register their phone number and receive an
SMS. That only reaches those who signed up beforehand, and it means storing personal data
(phone numbers).

Emergency services elsewhere warn the public by **Cell Broadcast**: every phone under the
selected towers receives the alert, without registration. Examples are EU-Alert in Europe and
Wireless Emergency Alerts in the US. The authority sends a standard **CAP** (Common Alerting
Protocol, OASIS 1.2) message describing the area; the mobile operators broadcast it from their
towers.

## Decision

- **No opt-in, no phone numbers.** Public alerts go by Cell Broadcast to everyone in the
  threatened area.
- **Alert zones are clusters of where people live,** built offline from OpenStreetMap building
  footprints. Each has a name, an estimated population (WorldPop 2020, 100 m) and a fire-risk
  level from the placement model's susceptibility map.
- **Each zone is linked to the cell towers that probably serve it,** from the OpenCelliD open
  database.
- **A fire concerns the zones within a configured radius** of its estimated origin (to be
  refined by the fire-spread forecast).
- **A human confirms every broadcast.** The system proposes the alert (zones, people, towers,
  text); the dispatcher confirms. Nothing is broadcast automatically, so a false detection
  never alarms a whole valley. Who confirmed, and when, goes in the incident's audit log.
- **The alert is a CAP 1.2 message in Arabic** (short Modern Standard Arabic). It is targeted
  by the zones' outlines (CAP `<area>` polygons); known towers, when there are any, are added
  as a hint (`cell_ids` parameter). The wording is a template in config, **to be validated with
  Civil Protection**.
- **Delivery goes through an interface.** The prototype uses a **simulated** broadcast (shown on
  a simulated phone, CAP `status` = `Exercise`). A real operator Cell Broadcast Centre can be
  plugged in once an agreement exists.

## Limits, stated honestly

- **OpenCelliD** is crowdsourced. Tower positions are approximate, and the "range" is an
  estimate from measurements, not the operator's coverage. In a real deployment the operators
  choose the cells from the CAP polygon; our tower list is indicative.
- **Measured on 2026-10-06: OpenCelliD lists no cell in the pilot zone.** The MCC 605 export
  holds 1,958 cells for all of Tunisia. None lies within 30 km of Kroumirie, and the nearest
  three are 43–47 km away near Béja, two of them seen once. The OpenStreetMap extract maps
  one telecom mast in the area. So the prototype targets alerts by zone outline only, which
  is how operational Cell Broadcast works anyway (EU-Alert, US WEA): the authority sends
  polygons, and the operator, who alone knows its cells, selects those covering them. The
  map shows no tower layer rather than invented ones. Field logging with an OpenCelliD
  client, or operator data, would fill the gap.
- **WorldPop** population is a modelled estimate (CC BY 4.0), not a census count.
- **Distance** is a first approximation of "concerned": wind and terrain matter. The spread
  engine will replace it.
- **Alert text** is a draft until Civil Protection approves it.

## Alternatives considered

| Option | Why not |
|---|---|
| **Opt-in SMS (the original plan)** | Reaches only those who registered; stores phone numbers; slower to reach everyone. |
| **Opt-in and Cell Broadcast together** | Chosen against by the team: one public channel, no personal data. |
| **Administrative areas (imadas, delegations) as zones** | Too coarse: one imada mixes safe villages with villages next to the fire. |
| **CAP polygon only, no tower data** | Matches how operators work, but leaves the "zone → cells" link invisible; the team chose to show it. |
| **Automatic broadcast on detection** | A false alarm would warn thousands; a human in the loop is the ethical default. |
