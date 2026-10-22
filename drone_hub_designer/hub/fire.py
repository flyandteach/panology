"""Lithium-ion battery fire-risk screening for the charging / spare-pack area.

The only code figure used here is the 20 kWh lithium-ion threshold at which
NFPA 855 (Standard for the Installation of Stationary Energy Storage Systems)
starts to apply. Whether a rack of spare drone packs on chargers is regulated
as an ESS, as battery storage under the adopted fire code, or both, is a call
for the authority having jurisdiction. Everything else is a design flag, not a
code requirement.
"""

from __future__ import annotations

from dataclasses import dataclass, field

NFPA_855_LI_ION_THRESHOLD_KWH = 20.0


@dataclass
class FireResult:
    stored_energy_kwh: float
    exceeds_nfpa855_threshold: bool
    separated: bool
    suppression: bool
    conditioned: bool
    flags: list[str] = field(default_factory=list)


def assess_fire(
    stored_energy_kwh: float,
    separation_m: float,
    suppression: bool,
    conditioned: bool,
    min_separation_m: float = 3.0,
) -> FireResult:
    flags = []
    over = stored_energy_kwh > NFPA_855_LI_ION_THRESHOLD_KWH
    if over:
        flags.append(
            f"{stored_energy_kwh:.0f} kWh of lithium-ion packs on site is above the 20 kWh level at which "
            "NFPA 855 applies to lithium-ion ESS. Confirm with the AHJ which provisions govern spare-pack "
            "charging and storage, and whether a hazard mitigation analysis is required."
        )
    separated = separation_m >= min_separation_m
    if not separated:
        flags.append(
            "Battery charging/storage is not physically separated from the operations area and pads; a thermal "
            "runaway event spreads directly to people, aircraft and the store's parking."
        )
    if not suppression:
        flags.append("No detection/suppression or deflagration venting provided for the battery area.")
    if not conditioned:
        flags.append(
            "Battery area is not temperature-controlled; charging in heat or cold shortens pack life and, in "
            "heat, raises thermal-runaway risk."
        )
    return FireResult(
        stored_energy_kwh=stored_energy_kwh,
        exceeds_nfpa855_threshold=over,
        separated=separated,
        suppression=suppression,
        conditioned=conditioned,
        flags=flags,
    )
