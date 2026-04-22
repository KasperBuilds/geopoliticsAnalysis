"""
SENTINEL — Singapore-Specific Sensor
Scans Singapore defence, foreign affairs, and domestic policy
with geostrategic implications. Covers SAF, MINDEF, MFA, and local media.
"""

from sensors.base_sensor import BaseSensor
from config import SINGAPORE_SOURCES, SINGAPORE_KEYWORDS


class SingaporeSensor(BaseSensor):

    def _sensor_name(self) -> str:
        return "singapore"

    def _domain(self) -> str:
        return "Singapore Defence & Foreign Policy"

    def _sources(self) -> list[str]:
        return SINGAPORE_SOURCES

    def _keywords(self) -> list[str]:
        return SINGAPORE_KEYWORDS
