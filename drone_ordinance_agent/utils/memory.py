"""
Session memory for a single ordinance generation run.
Holds all user inputs and generated outputs in one place.
"""

import json
import os
from datetime import datetime


class OrdinanceSession:
    """Holds inputs + all generated ordinance components for one project."""

    def __init__(self):
        self.created_at = datetime.utcnow().isoformat()
        self.inputs: dict = {}
        self.outputs: dict = {}

    # ------------------------------------------------------------------
    # Inputs
    # ------------------------------------------------------------------
    def set_inputs(
        self,
        state: str,
        airport_type: str,
        density: str,
        operational_scale: int,
        municipality: str = "",
        site_acreage: float = 0.0,
        wetland_nearby: bool = False,
        floodplain_nearby: bool = False,
        residential_proximity_ft: int = 0,
        notes: str = "",
    ):
        self.inputs = {
            "state": state,
            "airport_type": airport_type,
            "density": density,
            "operational_scale": operational_scale,
            "municipality": municipality,
            "site_acreage": site_acreage,
            "wetland_nearby": wetland_nearby,
            "floodplain_nearby": floodplain_nearby,
            "residential_proximity_ft": residential_proximity_ft,
            "notes": notes,
        }

    def get_inputs_summary(self) -> str:
        if not self.inputs:
            return "(no inputs set)"
        i = self.inputs
        return (
            f"State: {i.get('state')}\n"
            f"Airport Type: {i.get('airport_type')}\n"
            f"Density Context: {i.get('density')}\n"
            f"Operational Scale: {i.get('operational_scale')} ops/day\n"
            f"Municipality: {i.get('municipality', 'unspecified')}\n"
            f"Site Acreage: {i.get('site_acreage', 0.0)} acres\n"
            f"Wetland Nearby: {i.get('wetland_nearby', False)}\n"
            f"Floodplain Nearby: {i.get('floodplain_nearby', False)}\n"
            f"Nearest Residential: {i.get('residential_proximity_ft', 0)} ft\n"
            f"Additional Notes: {i.get('notes', 'none')}"
        )

    # ------------------------------------------------------------------
    # Outputs
    # ------------------------------------------------------------------
    def set_output(self, key: str, data: dict):
        self.outputs[key] = data

    def get_output(self, key: str) -> dict:
        return self.outputs.get(key, {})

    def all_complete(self) -> bool:
        required = [
            "tier_classification",
            "use_definitions",
            "zoning_language",
            "setback_recommendations",
            "approval_pathways",
            "environmental_triggers",
        ]
        return all(k in self.outputs for k in required)

    # ------------------------------------------------------------------
    # Serialise / export
    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "created_at": self.created_at,
            "inputs": self.inputs,
            "outputs": self.outputs,
        }

    def save(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2)

    @classmethod
    def load(cls, path: str) -> "OrdinanceSession":
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        session = cls()
        session.created_at = data.get("created_at", session.created_at)
        session.inputs = data.get("inputs", {})
        session.outputs = data.get("outputs", {})
        return session
