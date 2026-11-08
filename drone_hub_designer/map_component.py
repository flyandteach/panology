"""The site map: a Leaflet map in a Streamlit custom component (hub/site_map/index.html).

The component needs no build step: index.html speaks Streamlit's component
message protocol directly and loads a bundled copy of Leaflet 1.9.4.
"""

from __future__ import annotations

from pathlib import Path

import streamlit.components.v1 as components

_site_map = components.declare_component("hub_site_map", path=str(Path(__file__).parent / "hub" / "site_map"))


def site_map(*, geometry: dict, overlay: dict | None, osm_query: str | None, osm_url: str,
             min_overflight_defaults: dict, cesium_base_url: str, measure: dict, key: str):
    return _site_map(geometry=geometry, overlay=overlay, osm_query=osm_query, osm_url=osm_url,
                     min_overflight_defaults=min_overflight_defaults, cesium_base_url=cesium_base_url,
                     measure=measure, key=key, default=None)
