"""
SENTINEL — Geopolitics Sensor
Scans diplomatic shifts, territorial disputes, alliance dynamics,
and great-power competition in the Indo-Pacific.
"""

from sensors.base_sensor import BaseSensor
from config import GEOPOLITICS_SOURCES, GEOPOLITICS_KEYWORDS


class GeopoliticsSensor(BaseSensor):

    def _sensor_name(self) -> str:
        return "geopolitics"

    def _domain(self) -> str:
        return "Geopolitics & Diplomacy"

    def _sources(self) -> list[str]:
        return GEOPOLITICS_SOURCES

    def _keywords(self) -> list[str]:
        return GEOPOLITICS_KEYWORDS
