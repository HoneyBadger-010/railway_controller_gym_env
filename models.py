"""
Railway Traffic Controller Models.

Pydantic models for actions, observations, and state.
"""

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class SignalState(str, Enum):
    """Signal states for track segments."""
    RED = "red"      # Stop
    YELLOW = "yellow"  # Caution/slow down
    GREEN = "green"   # Go


class TrainStatus(str, Enum):
    """Status of a train."""
    WAITING = "waiting"      # Waiting at signal
    MOVING = "moving"        # Moving on track
    ARRIVED = "arrived"      # Reached destination
    DELAYED = "delayed"      # Behind schedule


class TrainState(BaseModel):
    """State of a single train."""
    train_id: str = Field(..., description="Unique train identifier")
    current_segment: str = Field(..., description="Current track segment ID")
    destination: str = Field(..., description="Destination station ID")
    status: TrainStatus = Field(default=TrainStatus.MOVING)
    speed: float = Field(default=0.0, ge=0.0, le=1.0, description="Current speed (0-1)")
    scheduled_arrival: int = Field(..., description="Scheduled arrival time (step)")
    delay: int = Field(default=0, ge=0, description="Delay in steps")
    priority: int = Field(default=1, ge=1, le=3, description="Train priority (1=normal, 2=express, 3=high-speed)")
    train_type: str = Field(default="regular", description="Train type: regular, express, high-speed")
    
    def get_priority_name(self) -> str:
        """Get human-readable priority name."""
        return {3: "high-speed", 2: "express", 1: "regular"}.get(self.priority, "regular")


class TrackSegment(BaseModel):
    """A track segment in the railway network."""
    segment_id: str = Field(..., description="Unique segment identifier")
    length: float = Field(..., description="Segment length (travel time units)")
    signal_state: SignalState = Field(default=SignalState.GREEN)
    occupied_by: Optional[str] = Field(default=None, description="Train ID occupying this segment")
    next_segments: List[str] = Field(default_factory=list, description="Connected segment IDs")
    is_junction: bool = Field(default=False, description="Whether this is a junction point")
    station_name: Optional[str] = Field(default=None, description="Station name if this is a station")


class RailwayObservation(BaseModel):
    """Observation returned by the railway environment."""
    trains: Dict[str, TrainState] = Field(default_factory=dict, description="All trains in the network")
    track_segments: Dict[str, TrackSegment] = Field(default_factory=dict, description="Track network state")
    current_step: int = Field(default=0, ge=0)
    max_steps: int = Field(default=50, ge=1)
    collisions: int = Field(default=0, ge=0, description="Number of collisions occurred")
    message: str = Field(default="", description="Status message")


class RailwayControllerAction(BaseModel):
    """
    Action for controlling the railway network.
    
    The controller can:
    1. Set signal states for track segments
    2. Hold trains at stations
    3. Route trains at junctions
    """
    action_type: str = Field(..., description="Type of action: 'set_signal', 'hold_train', 'release_train', 'route_train'")
    target_id: str = Field(..., description="Target segment or train ID")
    value: Optional[str] = Field(default=None, description="Value for the action (signal state, route, etc.)")
    reason: Optional[str] = Field(default=None, description="Reason for the action (for logging)")


class RailwayState(BaseModel):
    """Internal state of the railway environment."""
    episode_id: str = Field(default="")
    step_count: int = Field(default=0)
    total_reward: float = Field(default=0.0)
    trains_arrived: int = Field(default=0)
    trains_delayed: int = Field(default=0)
    collisions_avoided: int = Field(default=0)
    task_name: str = Field(default="basic_control")
    difficulty: str = Field(default="easy")


class TaskResult(BaseModel):
    """Result of a task evaluation."""
    task_name: str
    score: float = Field(ge=0.0, le=1.0)
    trains_arrived: int
    trains_delayed: int
    collisions: int
    avg_delay: float
    message: str