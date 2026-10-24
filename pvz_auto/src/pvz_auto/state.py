"""Immutable domain models at the perception and control boundary.

Board rows and columns are zero-based. ``board_x`` is measured in grid units,
with the left edge at 0 and the right edge at ``grid.columns``.
"""

from dataclasses import dataclass
from enum import Enum
import math


class ScreenState(str, Enum):
    ACTIVE_LAWN = "active_lawn"
    PAUSED = "paused"
    TRANSITION = "transition"
    UNKNOWN = "unknown"


class GameMode(str, Enum):
    ADVENTURE = "adventure"
    ENDLESS = "endless"


def _finite_nonnegative(value: float, name: str) -> None:
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and nonnegative")


def _confidence(value: float) -> None:
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("confidence must be finite and in [0, 1]")


def _nonnegative_integer(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")


@dataclass(frozen=True, slots=True)
class GridDimensions:
    rows: int
    columns: int

    def __post_init__(self) -> None:
        if (isinstance(self.rows, bool) or not isinstance(self.rows, int)
                or isinstance(self.columns, bool) or not isinstance(self.columns, int)
                or self.rows <= 0 or self.columns <= 0):
            raise ValueError("grid rows and columns must be positive integers")


@dataclass(frozen=True, slots=True)
class SelectedPlantCard:
    """A chosen plant card; slot numbering is zero-based."""

    slot: int
    plant_id: str
    cooldown_seconds: float | None = None
    ready: bool | None = None

    def __post_init__(self) -> None:
        _nonnegative_integer(self.slot, "card slot")
        if not isinstance(self.plant_id, str) or not self.plant_id:
            raise ValueError("plant_id must be a non-empty string")
        if self.cooldown_seconds is not None:
            _finite_nonnegative(self.cooldown_seconds, "cooldown_seconds")
        if self.ready is not None and not isinstance(self.ready, bool):
            raise ValueError("ready must be bool or None")


@dataclass(frozen=True, slots=True)
class DetectedPlant:
    plant_id: str
    row: int
    board_x: float
    confidence: float

    def __post_init__(self) -> None:
        if not isinstance(self.plant_id, str) or not self.plant_id:
            raise ValueError("plant_id must be a non-empty string")
        _nonnegative_integer(self.row, "row")
        _finite_nonnegative(self.board_x, "board_x")
        _confidence(self.confidence)


@dataclass(frozen=True, slots=True)
class DetectedThreat:
    threat_id: str
    row: int
    board_x: float
    confidence: float

    def __post_init__(self) -> None:
        if not isinstance(self.threat_id, str) or not self.threat_id:
            raise ValueError("threat_id must be a non-empty string")
        _nonnegative_integer(self.row, "row")
        _finite_nonnegative(self.board_x, "board_x")
        _confidence(self.confidence)


@dataclass(frozen=True, slots=True)
class GameState:
    """Best available observation; optional values preserve unknown readings."""

    screen: ScreenState = ScreenState.UNKNOWN
    mode: GameMode | None = None
    sun: int | None = None
    wave: int | None = None
    grid: GridDimensions | None = None
    selected_cards: tuple[SelectedPlantCard, ...] = ()
    plants: tuple[DetectedPlant, ...] = ()
    threats: tuple[DetectedThreat, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.screen, ScreenState):
            raise ValueError("screen must be a ScreenState")
        if self.mode is not None and not isinstance(self.mode, GameMode):
            raise ValueError("mode must be a GameMode or None")
        for name, value in (("sun", self.sun), ("wave", self.wave)):
            if value is not None:
                _nonnegative_integer(value, name)
        if self.wave is not None and self.wave < 1:
            raise ValueError("wave must be at least 1 when known")
        if self.grid is not None:
            for entity in (*self.plants, *self.threats):
                if entity.row >= self.grid.rows or entity.board_x > self.grid.columns:
                    raise ValueError("detected entity is outside the known grid")
        if not all(isinstance(items, tuple) for items in
                   (self.selected_cards, self.plants, self.threats)):
            raise ValueError("selected_cards, plants, and threats must be tuples")
        if len({card.slot for card in self.selected_cards}) != len(self.selected_cards):
            raise ValueError("selected card slots must be unique")
