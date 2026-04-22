"""
SENTINEL — Defence News Sensor
Scans military and defence publications for force posture changes,
arms deals, exercises, and capability developments.
"""

from sensors.base_sensor import BaseSensor
from config import DEFENCE_SOURCES, DEFENCE_KEYWORDS


class DefenceSensor(BaseSensor):

    def _sensor_name(self) -> str:
        return "defence"

    def _domain(self) -> str:
        return "Defence & Military Affairs"

    def _sources(self) -> list[str]:
        return DEFENCE_SOURCES

    def _keywords(self) -> list[str]:
        return DEFENCE_KEYWORDS
