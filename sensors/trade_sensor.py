"""
SENTINEL — Trade & Economics Sensor
Scans trade flows, sanctions regimes, tariff actions, FDI shifts,
and economic coercion relevant to the Indo-Pacific.
"""

from sensors.base_sensor import BaseSensor
from config import TRADE_ECONOMICS_SOURCES, TRADE_KEYWORDS


class TradeSensor(BaseSensor):

    def _sensor_name(self) -> str:
        return "trade"

    def _domain(self) -> str:
        return "Trade & Economic Security"

    def _sources(self) -> list[str]:
        return TRADE_ECONOMICS_SOURCES

    def _keywords(self) -> list[str]:
        return TRADE_KEYWORDS
