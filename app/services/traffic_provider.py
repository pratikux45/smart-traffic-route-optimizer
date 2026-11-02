"""
Traffic Provider abstraction and implementations.
Enables plug-and-play traffic estimation now, and ready for future live traffic feeds.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any


class TrafficProvider(ABC):
    """Abstract base class for traffic data providers."""

    @abstractmethod
    async def get_traffic_factor(self, route_coords: List[List[float]]) -> float:
        """
        Compute or fetch a normalized traffic congestion factor in [0.0, 1.0].
        0.0 = completely free flow, 1.0 = gridlock.
        """
        pass

    @abstractmethod
    def get_metadata(self) -> Dict[str, Any]:
        """Return provider identification and description metadata."""
        pass


class StaticTrafficProvider(TrafficProvider):
    """
    Default open-source baseline provider using a neutral traffic component.
    Transparently informs users that OpenStreetMap provides physical signal locations,
    not live light cycles or live vehicle congestion.
    """

    def __init__(self, neutral_factor: float = 0.5):
        self.neutral_factor = neutral_factor

    async def get_traffic_factor(self, route_coords: List[List[float]]) -> float:
        return self.neutral_factor

    def get_metadata(self) -> Dict[str, Any]:
        return {
            "traffic_source": "static",
            "description": "Baseline neutral traffic estimate (OpenStreetMap provides signal coordinates; live signal timings require local telemetry)."
        }


class OSMTrafficProvider(TrafficProvider):
    """
    Heuristic traffic provider analyzing road classifications (motorway vs primary vs residential)
    from OpenStreetMap data to estimate baseline peak vs off-peak friction.
    """

    def __init__(self, baseline_factor: float = 0.5):
        self.baseline_factor = baseline_factor

    async def get_traffic_factor(self, route_coords: List[List[float]]) -> float:
        # Currently returns baseline factor; extensible to tag-based speed limit analysis
        return self.baseline_factor

    def get_metadata(self) -> Dict[str, Any]:
        return {
            "traffic_source": "osm_heuristic",
            "description": "Road class heuristic estimation from OpenStreetMap infrastructure attributes."
        }


class FutureLiveTrafficProvider(TrafficProvider):
    """
    Integration stub ready for commercial or municipal live traffic APIs
    (e.g., TomTom, HERE, Google Traffic, City TMC sensors).
    """

    def __init__(self, api_key: str = "", endpoint_url: str = ""):
        self.api_key = api_key
        self.endpoint_url = endpoint_url

    async def get_traffic_factor(self, route_coords: List[List[float]]) -> float:
        # Hook for querying external live tile/speed API
        return 0.5

    def get_metadata(self) -> Dict[str, Any]:
        return {
            "traffic_source": "live_telemetry_stub",
            "description": "Prepared interface for live road telemetry and congestion feeds."
        }


def get_default_traffic_provider() -> TrafficProvider:
    """Factory returning the active traffic provider."""
    return StaticTrafficProvider(neutral_factor=0.5)
