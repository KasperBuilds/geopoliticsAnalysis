"""
SENTINEL — Materials & Supply Chain Sensor
Scans critical minerals, semiconductor supply, energy markets,
shipping disruptions, and strategic material shortfalls.
"""

from sensors.base_sensor import BaseSensor
from config import MATERIALS_SUPPLY_CHAIN_SOURCES, MATERIALS_KEYWORDS


class MaterialsSensor(BaseSensor):

    def _sensor_name(self) -> str:
        return "materials"

    def _domain(self) -> str:
        return "Materials & Supply Chain Security"

    def _sources(self) -> list[str]:
        return MATERIALS_SUPPLY_CHAIN_SOURCES

    def _keywords(self) -> list[str]:
        return MATERIALS_KEYWORDS
