from dataclasses import FrozenInstanceError

import pytest

from pvz_auto.state import (
    DetectedPlant,
    DetectedThreat,
    GameMode,
    GameState,
    GridDimensions,
    ScreenState,
    SelectedPlantCard,
)


def test_unknown_measurements_are_explicit_and_state_is_immutable():
    state = GameState()
    assert state.screen is ScreenState.UNKNOWN
    assert state.mode is state.sun is state.wave is state.grid is None
    with pytest.raises(FrozenInstanceError):
        state.sun = 50


def test_state_carries_mode_cards_and_detections_without_fixed_asset_catalog():
    state = GameState(
        screen=ScreenState.ACTIVE_LAWN,
        mode=GameMode.ENDLESS,
        sun=125,
        wave=3,
        grid=GridDimensions(rows=5, columns=9),
        selected_cards=(SelectedPlantCard(0, "hybrid_future_plant", 2.5, False),),
        plants=(DetectedPlant("another_new_plant", 1, 2.25, 0.92),),
        threats=(DetectedThreat("unlisted_zombie", 1, 7.5, 0.71),),
    )
    assert state.selected_cards[0].ready is False
    assert state.plants[0].board_x == 2.25
    assert state.threats[0].threat_id == "unlisted_zombie"


@pytest.mark.parametrize("grid", [(0, 9), (5, -1), (1.5, 9), (True, 9)])
def test_grid_dimensions_must_be_positive_integers(grid):
    with pytest.raises(ValueError):
        GridDimensions(*grid)


@pytest.mark.parametrize("confidence", [-0.01, 1.01, float("nan"), float("inf")])
def test_detection_confidence_must_be_finite_and_bounded(confidence):
    with pytest.raises(ValueError, match="confidence"):
        DetectedThreat("zombie", 0, 1.0, confidence)


@pytest.mark.parametrize("cooldown", [-1.0, float("nan"), float("inf")])
def test_card_cooldown_must_be_finite_and_nonnegative(cooldown):
    with pytest.raises(ValueError, match="cooldown"):
        SelectedPlantCard(0, "plant", cooldown)


def test_state_rejects_invalid_counts_duplicate_slots_and_out_of_grid_detections():
    with pytest.raises(ValueError, match="sun"):
        GameState(sun=-1)
    with pytest.raises(ValueError, match="wave"):
        GameState(wave=0)
    with pytest.raises(ValueError, match="unique"):
        GameState(selected_cards=(SelectedPlantCard(1, "a"), SelectedPlantCard(1, "b")))
    with pytest.raises(ValueError, match="outside"):
        GameState(grid=GridDimensions(5, 9), plants=(DetectedPlant("p", 5, 2, 1),))
