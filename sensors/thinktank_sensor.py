"""
SENTINEL — Think Tank & OSINT Sensor
Scans research institutions, policy think tanks, and open-source
intelligence outlets for deep strategic analysis.
"""

from sensors.base_sensor import BaseSensor
from config import THINKTANK_SOURCES, THINKTANK_KEYWORDS


class ThinktankSensor(BaseSensor):

    def _sensor_name(self) -> str:
        return "thinktank"

    def _domain(self) -> str:
        return "Strategic Analysis & OSINT"

    def _sources(self) -> list[str]:
        return THINKTANK_SOURCES

    def _keywords(self) -> list[str]:
        return THINKTANK_KEYWORDS
