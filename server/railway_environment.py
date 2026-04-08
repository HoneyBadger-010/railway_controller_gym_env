"""
Railway Traffic Controller Environment Implementation.

A real-world simulation of railway traffic control where an AI agent
manages train movements, signals, and routing to ensure safe and
efficient operations.

Track Safety (Block Signaling):
- Each track segment is a "block" that can only hold ONE train at a time
- Trains must wait if the next segment is occupied (safe distance)
- Signals control entry into segments (RED = stop, GREEN = proceed)
- Collisions occur if two trains somehow enter the same block
"""

import random
import uuid
import sys
import os
from typing import Any, Dict, List, Optional, Set

from fastmcp import FastMCP

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openenv.core.env_server.mcp_environment import MCPEnvironment
from openenv.core.env_server.types import Action, Observation, State

from models import (
    RailwayControllerAction,
    RailwayObservation,
    RailwayState,
    SignalState,
    TaskResult,
    TrackSegment,
    TrainState,
    TrainStatus,
)


class RailwayControllerEnvironment(MCPEnvironment):
    """
    Railway Traffic Controller Environment.
    
    The agent acts as a central traffic controller managing a railway network.
    Multiple trains move through the network, and the agent must:
    - Control signals to prevent collisions
    - Manage train routing at junctions
    - Minimize delays while ensuring safety
    - Prioritize express trains
    
    Track Safety (Block Signaling):
    - Each segment is a "block" - only ONE train allowed per block
    - Trains automatically stop if next block is occupied
    - Controller must manage signals to control train flow
    - Collisions = critical failure (two trains in same block)
    
    Tasks (easy -> hard):
    1. basic_control: 2 trains, simple track, prevent collision
    2. junction_management: 4 trains, multiple junctions, optimize flow
    3. rush_hour: 6 trains, complex network, delays, prioritize express trains
    """
    
    # Task configurations
    TASK_CONFIGS = {
        "basic_control": {
            "difficulty": "easy",
            "num_trains": 2,
            "max_steps": 30,
            "has_junctions": False,
            "has_delays": False,
            "has_weather": False,
            "express_trains": 0,
        },
        "junction_management": {
            "difficulty": "medium",
            "num_trains": 4,
            "max_steps": 50,
            "has_junctions": True,
            "has_delays": False,
            "has_weather": False,
            "express_trains": 1,
        },
        "rush_hour": {
            "difficulty": "hard",
            "num_trains": 6,
            "max_steps": 80,
            "has_junctions": True,
            "has_delays": True,
            "has_weather": True,
            "express_trains": 2,
        },
        "express_priority": {
            "difficulty": "medium-hard",
            "num_trains": 5,
            "max_steps": 40,
            "has_junctions": True,
            "has_delays": False,
            "has_weather": False,
            "express_trains": 3,
        },
    }
    
    def __init__(self, task_name: str = "basic_control"):
        """Initialize the railway environment."""
        self._task_name = task_name
        self._config = self.TASK_CONFIGS.get(task_name, self.TASK_CONFIGS["basic_control"])
        
        # Create MCP server
        mcp = FastMCP("railway_controller")
        
        @mcp.tool
        def set_signal(segment_id: str, state: str) -> dict:
            """Set the signal state for a track segment.
            
            Args:
                segment_id: The track segment ID
                state: Signal state ('red', 'yellow', 'green')
            
            Returns:
                Result of the signal change
            """
            return self._set_signal(segment_id, state)
        
        @mcp.tool
        def hold_train(train_id: str, reason: str = "") -> dict:
            """Hold a train at its current position.
            
            Args:
                train_id: The train ID to hold
                reason: Reason for holding the train
            
            Returns:
                Result of the hold action
            """
            return self._hold_train(train_id, reason)
        
        @mcp.tool
        def release_train(train_id: str) -> dict:
            """Release a held train to continue moving.
            
            Args:
                train_id: The train ID to release
            
            Returns:
                Result of the release action
            """
            return self._release_train(train_id)
        
        @mcp.tool
        def route_train(train_id: str, via_segment: str) -> dict:
            """Route a train through a specific segment at a junction.
            
            Args:
                train_id: The train ID to route
                via_segment: The segment ID to route through
            
            Returns:
                Result of the routing action
            """
            return self._route_train(train_id, via_segment)
        
        @mcp.tool
        def get_status() -> dict:
            """Get the current status of the railway network.
            
            Returns:
                Current state of all trains and track segments
            """
            return self._get_status()
        
        @mcp.tool
        def get_collision_warnings() -> dict:
            """Get warnings about potential collisions.
            
            Returns:
                List of segments where two trains might collide
            """
            return self._get_collision_warnings()
        
        @mcp.tool
        def get_segment_occupancy() -> dict:
            """Get occupancy status of all track segments.
            
            Returns:
                Map of segment_id to train_id (or None if empty)
            """
            return self._get_segment_occupancy()
        
        @mcp.tool
        def get_control_suggestions() -> dict:
            """Get intelligent suggestions for train control.
            
            Analyzes the current state and suggests actions to:
            - Prevent collisions
            - Prioritize late/high-priority trains
            - Optimize traffic flow
            
            Returns:
                List of suggested actions with reasons
            """
            return self._get_control_suggestions()
        
        @mcp.tool
        def get_delay_status() -> dict:
            """Get delay status of all trains.
            
            Returns:
                Trains sorted by delay, with recommendations
            """
            return self._get_delay_status()
        
        super().__init__(mcp)
        
        # Initialize state
        self._state = State(episode_id=str(uuid.uuid4()), step_count=0)
        self._internal_state = RailwayState(
            episode_id=str(uuid.uuid4()),
            task_name=task_name,
            difficulty=self._config["difficulty"]
        )
        
        # Environment state
        self._trains: Dict[str, TrainState] = {}
        self._track_segments: Dict[str, TrackSegment] = {}
        self._train_routes: Dict[str, List[str]] = {}
        self._held_trains: set = set()
        self._collisions: int = 0
        self._collisions_this_step: int = 0
        self._arrived_trains: Set[str] = set()
        self._step_count: int = 0
        self._max_steps: int = self._config["max_steps"]
        self._weather_active: bool = False
        self._weather_speed_modifier: float = 1.0
        
        # Initialize the network
        self._initialize_network()
    
    def _initialize_network(self):
        """Initialize the railway network based on task configuration."""
        self._trains.clear()
        self._track_segments.clear()
        self._train_routes.clear()
        self._held_trains.clear()
        self._collisions = 0
        self._collisions_this_step = 0
        self._arrived_trains = set()
        self._step_count = 0
        self._weather_active = False
        self._weather_speed_modifier = 1.0
        
        if self._task_name == "basic_control":
            self._create_basic_network()
        elif self._task_name == "junction_management":
            self._create_junction_network()
        elif self._task_name == "rush_hour":
            self._create_complex_network()
        elif self._task_name == "express_priority":
            self._create_express_network()
        else:
            self._create_basic_network()
    
    def _create_basic_network(self):
        """Create a simple network with one shared intersection segment.
        
        Network Layout:
        
            Station A ----[A-J1]----> [J1-CROSS] ----[J1-B]----> Station B
                                          |
            Station D ----[D-J1]----> [J1-CROSS] ----[J1-C]----> Station C
        
        Two trains crossing at J1-CROSS - must coordinate!
        """
        segments = [
            # Eastbound track (A-J1 leads to the shared crossing)
            TrackSegment(segment_id="A-J1", length=3, next_segments=["J1-CROSS"], station_name="Station A"),
            TrackSegment(segment_id="J1-B", length=3, next_segments=[], station_name="Station B"),
            # Westbound track (D-J1 also leads to the shared crossing)
            TrackSegment(segment_id="D-J1", length=3, next_segments=["J1-CROSS"], station_name="Station D"),
            TrackSegment(segment_id="J1-C", length=3, next_segments=[], station_name="Station C"),
            # Cross track at junction (shared segment - critical!)
            TrackSegment(segment_id="J1-CROSS", length=2, next_segments=["J1-B", "J1-C"], is_junction=True),
        ]
        
        for seg in segments:
            self._track_segments[seg.segment_id] = seg
        
        # Create 2 trains that will cross paths at J1-CROSS
        self._trains["T1"] = TrainState(
            train_id="T1",
            current_segment="A-J1",
            destination="J1-B",
            status=TrainStatus.MOVING,
            speed=1.0,
            scheduled_arrival=8,
            priority=1,
            train_type="regular"
        )
        self._train_routes["T1"] = ["A-J1", "J1-CROSS", "J1-B"]
        self._track_segments["A-J1"].occupied_by = "T1"
        
        self._trains["T2"] = TrainState(
            train_id="T2",
            current_segment="D-J1",
            destination="J1-C",
            status=TrainStatus.MOVING,
            speed=1.0,
            scheduled_arrival=8,
            priority=1,
            train_type="regular"
        )
        self._train_routes["T2"] = ["D-J1", "J1-CROSS", "J1-C"]
        self._track_segments["D-J1"].occupied_by = "T2"
    
    def _create_junction_network(self):
        r"""Create a network with multiple junctions and 4 trains.
        
        Network Layout:
        
                    Station N1
                        |
                    [N1-J1]
                        |
                    [J1-CORE] (junction)
                   /    |    \
              [J1-E1] [J1-S1] [J1-W1]
                |       |       |
            [E1-E2]  [J2-CORE] [W1-W2]
            Stn E2   (junction) Stn W2
                    /    |
               [J2-E2] [J2-S1]
                 |       |
              [E1-E2]  Stn S1
        
        4 trains with crossing routes at J1 and J2 junctions.
        """
        segments = [
            # North entry
            TrackSegment(segment_id="N1-J1", length=2, next_segments=["J1-CORE"], station_name="Station N1"),
            # East entry
            TrackSegment(segment_id="E1-J1", length=2, next_segments=["J1-CORE"], station_name="Station E1"),
            # East exit from J1
            TrackSegment(segment_id="J1-E1", length=2, next_segments=["E1-E2"]),
            TrackSegment(segment_id="E1-E2", length=2, next_segments=[], station_name="Station E2"),
            # West entry
            TrackSegment(segment_id="W1-J1", length=2, next_segments=["J1-CORE"], station_name="Station W1"),
            # West exit from J1
            TrackSegment(segment_id="J1-W1", length=2, next_segments=["W1-W2"]),
            TrackSegment(segment_id="W1-W2", length=2, next_segments=[], station_name="Station W2"),
            # South entry (from S1 toward J2)
            TrackSegment(segment_id="S1-J2", length=2, next_segments=["J2-CORE"], station_name="Station S1"),
            # South exit from J2 (toward S1)
            TrackSegment(segment_id="J2-S1", length=2, next_segments=[], station_name="Station S1"),
            # Junction cores (CRITICAL - shared segments)
            TrackSegment(segment_id="J1-CORE", length=1, next_segments=["J1-E1", "J1-W1", "J1-S1"], is_junction=True),
            TrackSegment(segment_id="J2-CORE", length=1, next_segments=["J2-E2", "J2-S1"], is_junction=True),
            # Cross connections
            TrackSegment(segment_id="J1-S1", length=2, next_segments=["J2-CORE"]),
            TrackSegment(segment_id="J2-E2", length=2, next_segments=["E1-E2"]),
        ]
        
        for seg in segments:
            self._track_segments[seg.segment_id] = seg
        
        # Create 4 trains with intersecting routes
        # T1 and T3 both need J1-CORE — conflict!
        # T2 needs J1-CORE and J2-CORE — crosses both junctions
        trains_config = [
            ("T1", "N1-J1", "E1-E2", 12, 1, "regular", ["N1-J1", "J1-CORE", "J1-E1", "E1-E2"]),
            ("T2", "W1-J1", "J2-S1", 14, 2, "express", ["W1-J1", "J1-CORE", "J1-S1", "J2-CORE", "J2-S1"]),
            ("T3", "E1-J1", "W1-W2", 15, 1, "regular", ["E1-J1", "J1-CORE", "J1-W1", "W1-W2"]),
            ("T4", "S1-J2", "E1-E2", 16, 1, "regular", ["S1-J2", "J2-CORE", "J2-E2", "E1-E2"]),
        ]
        
        for tid, start, dest, arrival, priority, train_type, route in trains_config:
            self._trains[tid] = TrainState(
                train_id=tid,
                current_segment=start,
                destination=dest,
                status=TrainStatus.MOVING,
                speed=1.0,
                scheduled_arrival=arrival,
                priority=priority,
                train_type=train_type
            )
            self._train_routes[tid] = route
            self._track_segments[start].occupied_by = tid
    
    def _create_complex_network(self):
        """Create a complex network for rush hour scenario with 6 trains.
        
        Network Layout (Complex Rail Network):
        
                    Station A ----[A-J1]----> J1 ----[J1-B]----> Station B
                        |                          |                  |
                    [A-J2]                     [J1-J2]           [B-J3]
                        |                          |                  |
                        J2 ----[J2-C]----> Station C ----[C-J3]----> J3
                        |                                             |
                    [J2-D]                                        [J3-E]
                        |                                             |
                    Station D <---[D-J4]------ J4 <---[J4-E]----- Station E
                                                   |
                                              [J4-F]
                                                   |
                                              Station F
        
        6 trains with multiple crossing points at J1, J2, J3, J4.
        Express trains have priority routing.
        """
        segments = [
            # Main corridor (East-West)
            TrackSegment(segment_id="A-J1", length=2, next_segments=["J1-CORE"], station_name="Station A"),
            TrackSegment(segment_id="J1-B", length=2, next_segments=[], station_name="Station B"),
            # North-South corridor
            TrackSegment(segment_id="A-J2", length=2, next_segments=["J2-CORE"]),
            TrackSegment(segment_id="J2-C", length=2, next_segments=["C-J3"], station_name="Station C"),
            # South branch
            TrackSegment(segment_id="J2-D", length=2, next_segments=[], station_name="Station D"),
            TrackSegment(segment_id="D-J4", length=2, next_segments=["J4-CORE"], station_name="Station D"),
            # East branch
            TrackSegment(segment_id="B-J3", length=2, next_segments=["J3-CORE"]),
            TrackSegment(segment_id="J3-E", length=2, next_segments=[], station_name="Station E"),
            TrackSegment(segment_id="E-J4", length=2, next_segments=["J4-CORE"], station_name="Station E"),
            # South station
            TrackSegment(segment_id="J4-F", length=2, next_segments=[], station_name="Station F"),
            # Junction cores (CRITICAL - shared segments)
            TrackSegment(segment_id="J1-CORE", length=1, next_segments=["J1-B", "J1-J2"], is_junction=True),
            TrackSegment(segment_id="J2-CORE", length=1, next_segments=["J2-C", "J2-D", "J4-CORE"], is_junction=True),
            TrackSegment(segment_id="J3-CORE", length=1, next_segments=["J3-E", "J4-CORE"], is_junction=True),
            TrackSegment(segment_id="J4-CORE", length=1, next_segments=["J4-F", "J2-CORE"], is_junction=True),
            # Cross connections
            TrackSegment(segment_id="J1-J2", length=2, next_segments=["J2-CORE"]),
            TrackSegment(segment_id="C-J3", length=2, next_segments=["J3-CORE"]),
            # Opposite directions
            TrackSegment(segment_id="B-J1", length=2, next_segments=["J1-CORE"], station_name="Station B"),
            TrackSegment(segment_id="F-J4", length=2, next_segments=["J4-CORE"], station_name="Station F"),
        ]
        
        for seg in segments:
            self._track_segments[seg.segment_id] = seg
        
        # Create 6 trains with varying priorities and crossing routes
        trains_config = [
            # High-speed trains (priority 3) - need clear path
            ("HS1", "A-J1", "J1-B", 15, 3, "high-speed", ["A-J1", "J1-CORE", "J1-B"]),
            ("HS2", "F-J4", "J2-C", 18, 3, "high-speed", ["F-J4", "J4-CORE", "J2-CORE", "J2-C"]),
            # Express trains (priority 2)
            ("EX1", "A-J2", "J3-E", 20, 2, "express", ["A-J2", "J2-CORE", "J2-C", "C-J3", "J3-CORE", "J3-E"]),
            ("EX2", "B-J1", "J4-F", 22, 2, "express", ["B-J1", "J1-CORE", "J1-J2", "J2-CORE", "J4-CORE", "J4-F"]),
            # Regular trains (priority 1)
            ("R1", "D-J4", "J2-D", 25, 1, "regular", ["D-J4", "J4-CORE", "J2-CORE", "J2-D"]),
            ("R2", "E-J4", "J4-F", 28, 1, "regular", ["E-J4", "J4-CORE", "J4-F"]),
        ]
        
        for tid, start, dest, arrival, priority, train_type, route in trains_config:
            # Add random delays for rush hour
            delay = random.randint(0, 3) if self._config["has_delays"] else 0
            self._trains[tid] = TrainState(
                train_id=tid,
                current_segment=start,
                destination=dest,
                status=TrainStatus.MOVING,
                speed=1.0,
                scheduled_arrival=arrival,
                priority=priority,
                train_type=train_type,
                delay=delay
            )
            self._train_routes[tid] = route
            self._track_segments[start].occupied_by = tid
        
        # Activate weather effects for rush hour
        if self._config.get("has_weather", False):
            self._weather_active = True
            self._weather_speed_modifier = 0.75  # 25% chance of weather delay per train per step
    
    def _create_express_network(self):
        """Create a network for express priority scenario with 5 trains.
        
        Network Layout (3-Junction Chain):
        
            Station A ---[A-J1]---> J1 ---[J1-B]---> Station B
                                     |
                                  [J1-J2]
                                     |
            Station C ---[C-J2]---> J2 ---[J2-D]---> Station D
                                     |
                                  [J2-J3]
                                     |
            Station E ---[E-J3]---> J3 ---[J3-F]---> Station F
        
        5 trains with cascading conflicts at J1, J2, J3.
        Tight schedules — high-speed trains MUST arrive on time.
        Two trains start from the same station (A), creating immediate conflict.
        """
        segments = [
            # J1 area
            TrackSegment(segment_id="A-J1", length=2, next_segments=["J1-CORE"], station_name="Station A"),
            TrackSegment(segment_id="J1-B", length=2, next_segments=[], station_name="Station B"),
            TrackSegment(segment_id="J1-CORE", length=1, next_segments=["J1-B", "J1-J2"], is_junction=True),
            # J1-J2 link
            TrackSegment(segment_id="J1-J2", length=2, next_segments=["J2-CORE"]),
            # J2 area
            TrackSegment(segment_id="C-J2", length=2, next_segments=["J2-CORE"], station_name="Station C"),
            TrackSegment(segment_id="J2-D", length=2, next_segments=[], station_name="Station D"),
            TrackSegment(segment_id="J2-CORE", length=1, next_segments=["J2-D", "J2-J3"], is_junction=True),
            # J2-J3 link
            TrackSegment(segment_id="J2-J3", length=2, next_segments=["J3-CORE"]),
            # J3 area
            TrackSegment(segment_id="E-J3", length=2, next_segments=["J3-CORE"], station_name="Station E"),
            TrackSegment(segment_id="J3-F", length=2, next_segments=[], station_name="Station F"),
            TrackSegment(segment_id="J3-CORE", length=1, next_segments=["J3-F"], is_junction=True),
        ]
        
        for seg in segments:
            self._track_segments[seg.segment_id] = seg
        
        # 5 trains with cascading junction conflicts
        # HS1 & EX1 both start at Station A → immediate conflict at J1-CORE
        # HS2 & R2 both start at Station C → conflict at J2-CORE
        # EX1 passes through J1 AND J2 → cascading conflict with HS2/R2
        # HS2 passes through J2 AND J3 → cascading conflict with R1
        trains_config = [
            # High-speed (priority 3) — tight schedules, must arrive on time
            ("HS1", "A-J1", "J1-B", 6, 3, "high-speed",
             ["A-J1", "J1-CORE", "J1-B"]),
            ("HS2", "C-J2", "J3-F", 12, 3, "high-speed",
             ["C-J2", "J2-CORE", "J2-J3", "J3-CORE", "J3-F"]),
            # Express (priority 2) — crosses two junctions
            ("EX1", "A-J1", "J2-D", 12, 2, "express",
             ["A-J1", "J1-CORE", "J1-J2", "J2-CORE", "J2-D"]),
            # Regular (priority 1)
            ("R1", "E-J3", "J3-F", 10, 1, "regular",
             ["E-J3", "J3-CORE", "J3-F"]),
            ("R2", "C-J2", "J2-D", 10, 1, "regular",
             ["C-J2", "J2-CORE", "J2-D"]),
        ]
        
        for tid, start, dest, arrival, priority, train_type, route in trains_config:
            self._trains[tid] = TrainState(
                train_id=tid,
                current_segment=start,
                destination=dest,
                status=TrainStatus.MOVING,
                speed=1.0,
                scheduled_arrival=arrival,
                priority=priority,
                train_type=train_type
            )
            self._train_routes[tid] = route
            self._track_segments[start].occupied_by = tid
    
    def _calculate_route(self, start: str, dest: str) -> List[str]:
        """Calculate a route from start to destination using BFS."""
        if start not in self._track_segments:
            return [start]
        
        visited = set()
        queue = [(start, [start])]
        
        while queue:
            current, path = queue.pop(0)
            if current == dest:
                return path
            
            if current in visited:
                continue
            visited.add(current)
            
            segment = self._track_segments.get(current)
            if segment:
                for next_seg in segment.next_segments:
                    if next_seg not in visited:
                        queue.append((next_seg, path + [next_seg]))
        
        return [start]  # No route found
    
    def _set_signal(self, segment_id: str, state: str) -> dict:
        """Set signal state for a segment."""
        if segment_id not in self._track_segments:
            return {"success": False, "error": f"Segment {segment_id} not found"}
        
        try:
            signal_state = SignalState(state.lower())
        except ValueError:
            return {"success": False, "error": f"Invalid signal state: {state}"}
        
        self._track_segments[segment_id].signal_state = signal_state
        return {"success": True, "segment_id": segment_id, "new_state": state}
    
    def _hold_train(self, train_id: str, reason: str = "") -> dict:
        """Hold a train at its current position."""
        if train_id not in self._trains:
            return {"success": False, "error": f"Train {train_id} not found"}
        
        train = self._trains[train_id]
        if train.status == TrainStatus.ARRIVED:
            return {"success": False, "error": "Cannot hold arrived train"}
        
        self._held_trains.add(train_id)
        train.status = TrainStatus.WAITING
        train.speed = 0.0
        
        return {"success": True, "train_id": train_id, "reason": reason}
    
    def _release_train(self, train_id: str) -> dict:
        """Release a held train."""
        if train_id not in self._trains:
            return {"success": False, "error": f"Train {train_id} not found"}
        
        if train_id not in self._held_trains:
            return {"success": False, "error": f"Train {train_id} is not held"}
        
        self._held_trains.discard(train_id)
        train = self._trains[train_id]
        train.status = TrainStatus.MOVING
        train.speed = 1.0
        
        return {"success": True, "train_id": train_id}
    
    def _route_train(self, train_id: str, via_segment: str) -> dict:
        """Route a train through a specific segment."""
        if train_id not in self._trains:
            return {"success": False, "error": f"Train {train_id} not found"}
        
        if via_segment not in self._track_segments:
            return {"success": False, "error": f"Segment {via_segment} not found"}
        
        # Update train route
        current_route = self._train_routes.get(train_id, [])
        if via_segment not in current_route:
            # Insert via_segment into route
            train = self._trains[train_id]
            new_route = self._calculate_route(train.current_segment, train.destination)
            if via_segment in new_route:
                self._train_routes[train_id] = new_route
                return {"success": True, "train_id": train_id, "route": new_route}
            else:
                return {"success": False, "error": f"Cannot route {train_id} through {via_segment}"}
        
        return {"success": True, "train_id": train_id, "route": current_route}
    
    def _get_status(self) -> dict:
        """Get current network status."""
        return {
            "step": self._step_count,
            "max_steps": self._max_steps,
            "trains": {tid: train.model_dump() for tid, train in self._trains.items()},
            "segments": {sid: seg.model_dump() for sid, seg in self._track_segments.items()},
            "collisions": self._collisions,
            "held_trains": list(self._held_trains),
            "weather_active": self._weather_active,
        }
    
    def _get_collision_warnings(self) -> dict:
        """Get warnings about potential collisions.
        
        Checks if two trains are heading towards the same segment.
        """
        warnings = []
        
        for train_id, train in self._trains.items():
            if train.status in [TrainStatus.ARRIVED, TrainStatus.DELAYED]:
                continue
            if train_id in self._held_trains:
                continue
            
            route = self._train_routes.get(train_id, [])
            current_idx = route.index(train.current_segment) if train.current_segment in route else -1
            
            if current_idx >= 0 and current_idx < len(route) - 1:
                next_segment = route[current_idx + 1]
                next_seg = self._track_segments.get(next_segment)
                
                if next_seg and next_seg.occupied_by is not None:
                    warnings.append({
                        "type": "block_occupied",
                        "train_id": train_id,
                        "segment_id": next_segment,
                        "blocked_by": next_seg.occupied_by,
                        "message": f"Train {train_id} waiting - segment {next_segment} occupied by {next_seg.occupied_by}"
                    })
        
        # Check for trains heading to same junction
        junction_trains: Dict[str, List[str]] = {}
        for train_id, train in self._trains.items():
            if train.status in [TrainStatus.ARRIVED, TrainStatus.DELAYED]:
                continue
            if train_id in self._held_trains:
                continue
            
            route = self._train_routes.get(train_id, [])
            current_idx = route.index(train.current_segment) if train.current_segment in route else -1
            # Look at upcoming segments (not already visited ones)
            upcoming = route[current_idx + 1:] if current_idx >= 0 else []
            for seg_id in upcoming[:3]:  # Check next 3 upcoming segments
                seg = self._track_segments.get(seg_id)
                if seg and seg.is_junction:
                    if seg_id not in junction_trains:
                        junction_trains[seg_id] = []
                    junction_trains[seg_id].append(train_id)
                    break
        
        for junction_id, trains in junction_trains.items():
            if len(trains) > 1:
                warnings.append({
                    "type": "junction_conflict",
                    "segment_id": junction_id,
                    "trains": trains,
                    "message": f"Multiple trains {trains} heading to junction {junction_id}"
                })
        
        return {
            "warnings": warnings,
            "warning_count": len(warnings),
        }
    
    def _get_segment_occupancy(self) -> dict:
        """Get occupancy status of all track segments."""
        occupancy = {}
        for seg_id, seg in self._track_segments.items():
            occupancy[seg_id] = {
                "occupied_by": seg.occupied_by,
                "signal_state": seg.signal_state.value,
                "is_junction": seg.is_junction,
                "station_name": seg.station_name,
            }
        return {
            "occupancy": occupancy,
            "total_segments": len(self._track_segments),
            "occupied_count": sum(1 for s in self._track_segments.values() if s.occupied_by is not None),
        }
    
    def _get_control_suggestions(self) -> dict:
        """Get intelligent suggestions for train control.
        
        Analyzes current state and suggests optimal actions.
        """
        suggestions = []
        
        # 1. Check for potential collisions at junctions
        junction_conflicts: Dict[str, List[str]] = {}
        for train_id, train in self._trains.items():
            if train.status in [TrainStatus.ARRIVED, TrainStatus.DELAYED]:
                continue
            if train_id in self._held_trains:
                continue
            
            route = self._train_routes.get(train_id, [])
            current_idx = route.index(train.current_segment) if train.current_segment in route else -1
            upcoming = route[current_idx + 1:] if current_idx >= 0 else []
            for seg_id in upcoming[:3]:  # Check next 3 upcoming segments
                seg = self._track_segments.get(seg_id)
                if seg and seg.is_junction:
                    if seg_id not in junction_conflicts:
                        junction_conflicts[seg_id] = []
                    junction_conflicts[seg_id].append(train_id)
                    break
        
        for junction_id, trains in junction_conflicts.items():
            if len(trains) > 1:
                # Suggest holding lower priority train
                trains_sorted = sorted(trains, key=lambda t: self._trains[t].priority)
                low_priority_train = trains_sorted[0]
                high_priority_train = trains_sorted[-1]
                
                suggestions.append({
                    "type": "collision_prevention",
                    "priority": "high",
                    "action": "hold_train",
                    "train_id": low_priority_train,
                    "reason": f"Prevent collision at {junction_id}. Let {high_priority_train} (priority {self._trains[high_priority_train].priority}) pass first.",
                    "junction": junction_id,
                })
        
        # 2. Check for late trains that need priority
        late_trains = [
            (tid, train) for tid, train in self._trains.items()
            if train.delay > 0 and train.status not in [TrainStatus.ARRIVED, TrainStatus.DELAYED]
        ]
        late_trains.sort(key=lambda x: x[1].delay, reverse=True)
        
        for tid, train in late_trains[:2]:  # Top 2 late trains
            route = self._train_routes.get(tid, [])
            current_idx = route.index(train.current_segment) if train.current_segment in route else -1
            upcoming = route[current_idx + 1:] if current_idx >= 0 else []
            for seg_id in upcoming[:2]:
                seg = self._track_segments.get(seg_id)
                if seg and seg.occupied_by and seg.occupied_by != tid:
                    blocking_train = self._trains.get(seg.occupied_by)
                    if blocking_train and blocking_train.priority < train.priority:
                        suggestions.append({
                            "type": "priority_override",
                            "priority": "medium",
                            "action": "hold_train",
                            "train_id": seg.occupied_by,
                            "reason": f"Train {tid} is {train.delay} steps late (priority {train.priority}). Hold {seg.occupied_by} to let it pass.",
                        })
                        break
        
        # 3. Suggest signal changes for better flow
        for seg_id, seg in self._track_segments.items():
            if seg.is_junction and seg.occupied_by is None:
                for tid, train in self._trains.items():
                    if train.status == TrainStatus.WAITING and tid not in self._held_trains:
                        route = self._train_routes.get(tid, [])
                        current_idx = route.index(train.current_segment) if train.current_segment in route else -1
                        upcoming = route[current_idx + 1:] if current_idx >= 0 else []
                        if seg_id in upcoming[:2]:
                            if seg.signal_state == SignalState.RED:
                                suggestions.append({
                                    "type": "signal_optimization",
                                    "priority": "low",
                                    "action": "set_signal",
                                    "segment_id": seg_id,
                                    "state": "green",
                                    "reason": f"Clear signal for train {tid} to improve flow",
                                })
                            break
        
        # 4. Check for trains that should be released
        for tid in list(self._held_trains):
            train = self._trains.get(tid)
            if train:
                route = self._train_routes.get(tid, [])
                if route:
                    current_idx = route.index(train.current_segment) if train.current_segment in route else -1
                    if current_idx >= 0 and current_idx < len(route) - 1:
                        next_seg = self._track_segments.get(route[current_idx + 1])
                        if next_seg and next_seg.occupied_by is None:
                            suggestions.append({
                                "type": "release_train",
                                "priority": "medium",
                                "action": "release_train",
                                "train_id": tid,
                                "reason": f"Path is clear for train {tid}, can release",
                            })
        
        # 5. Weather advisory
        if self._weather_active:
            suggestions.append({
                "type": "weather_advisory",
                "priority": "low",
                "action": "info",
                "reason": "Weather conditions active - trains may experience random delays. Prioritize high-speed trains.",
            })
        
        return {
            "suggestions": suggestions,
            "suggestion_count": len(suggestions),
            "critical_count": sum(1 for s in suggestions if s["priority"] == "high"),
        }
    
    def _get_delay_status(self) -> dict:
        """Get delay status of all trains with recommendations."""
        train_delays = []
        
        for tid, train in self._trains.items():
            # Calculate current delay based on schedule vs current step
            current_delay = 0
            if train.status in [TrainStatus.ARRIVED, TrainStatus.DELAYED]:
                current_delay = train.delay
            elif self._step_count > train.scheduled_arrival:
                current_delay = self._step_count - train.scheduled_arrival
            
            # Calculate time remaining
            time_remaining = max(0, train.scheduled_arrival - self._step_count)
            
            # Determine status label
            if train.status in [TrainStatus.ARRIVED, TrainStatus.DELAYED]:
                status_label = "arrived" if train.delay == 0 else f"arrived_late"
            elif current_delay > 0:
                status_label = "running_late"
            elif time_remaining <= 3:
                status_label = "critical_time"
            else:
                status_label = "on_time"
            
            train_delays.append({
                "train_id": tid,
                "current_segment": train.current_segment,
                "destination": train.destination,
                "priority": train.priority,
                "priority_name": {3: "high-speed", 2: "express", 1: "regular"}.get(train.priority, "regular"),
                "scheduled_arrival": train.scheduled_arrival,
                "current_delay": current_delay,
                "time_remaining": time_remaining,
                "status": status_label,
                "is_held": tid in self._held_trains,
            })
        
        # Sort by delay (most delayed first), then by priority
        train_delays.sort(key=lambda x: (-x["current_delay"], -x["priority"]))
        
        # Summary
        on_time = sum(1 for t in train_delays if t["status"] == "on_time")
        late = sum(1 for t in train_delays if t["status"] == "running_late")
        arrived = sum(1 for t in train_delays if t["status"] in ["arrived", "arrived_late"])
        
        return {
            "trains": train_delays,
            "summary": {
                "on_time": on_time,
                "late": late,
                "arrived": arrived,
                "total": len(train_delays),
            },
            "recommendations": [
                t for t in train_delays 
                if t["status"] in ["running_late", "critical_time"] or t["is_held"]
            ][:3],  # Top 3 trains needing attention
        }
    
    def reset(
        self,
        seed: Optional[int] = None,
        episode_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Observation:
        """Reset the environment, optionally switching tasks."""
        if seed is not None:
            random.seed(seed)
        
        # Support task switching via kwargs
        task_name = kwargs.get("task_name", None)
        if task_name and task_name in self.TASK_CONFIGS:
            self._task_name = task_name
            self._config = self.TASK_CONFIGS[task_name]
            self._max_steps = self._config["max_steps"]
        
        self._state = State(
            episode_id=episode_id or str(uuid.uuid4()),
            step_count=0,
        )
        self._internal_state = RailwayState(
            episode_id=self._state.episode_id,
            task_name=self._task_name,
            difficulty=self._config["difficulty"]
        )
        
        self._initialize_network()
        
        return Observation(
            done=False,
            reward=0.0,
            metadata={
                "status": "ready",
                "message": f"Railway environment ready. Task: {self._task_name}",
                "config": self._config,
                "task_name": self._task_name,
                "trains": {tid: train.model_dump() for tid, train in self._trains.items()},
                "segments": {sid: seg.model_dump() for sid, seg in self._track_segments.items()},
            },
        )
    
    def _step_impl(
        self,
        action: Action,
        timeout_s: Optional[float] = None,
        **kwargs: Any,
    ) -> Observation:
        """Handle non-MCP actions."""
        return Observation(
            done=False,
            reward=0.0,
            metadata={
                "error": f"Unknown action type: {type(action).__name__}. "
                "Use MCP tools: set_signal, hold_train, release_train, route_train, get_status"
            },
        )
    
    def step(
        self,
        action: Action,
        timeout_s: Optional[float] = None,
        **kwargs: Any,
    ) -> Observation:
        """Execute a step in the environment."""
        self._state.step_count += 1
        self._step_count += 1
        self._collisions_this_step = 0
        
        # Let base class handle MCP actions
        result = super().step(action, timeout_s=timeout_s, **kwargs)
        
        # Simulate train movements after action
        self._simulate_trains()
        
        # Check for collisions
        self._check_collisions()
        
        # Calculate reward
        reward = self._calculate_reward()
        result.reward = reward
        
        # Check if episode is done
        done = self._is_done()
        result.done = done
        
        # Update metadata
        result.metadata["step"] = self._step_count
        result.metadata["max_steps"] = self._max_steps
        result.metadata["trains"] = {tid: train.model_dump() for tid, train in self._trains.items()}
        result.metadata["collisions"] = self._collisions
        result.metadata["collisions_this_step"] = self._collisions_this_step
        result.metadata["weather_active"] = self._weather_active
        
        return result
    
    async def step_async(
        self,
        action: Action,
        timeout_s: Optional[float] = None,
        **kwargs: Any,
    ) -> Observation:
        """Async step for WebSocket handler."""
        self._state.step_count += 1
        self._step_count += 1
        self._collisions_this_step = 0
        
        result = await super().step_async(action, timeout_s=timeout_s, **kwargs)
        
        self._simulate_trains()
        self._check_collisions()
        
        reward = self._calculate_reward()
        result.reward = reward
        
        done = self._is_done()
        result.done = done
        
        result.metadata["step"] = self._step_count
        result.metadata["max_steps"] = self._max_steps
        result.metadata["trains"] = {tid: train.model_dump() for tid, train in self._trains.items()}
        result.metadata["collisions"] = self._collisions
        result.metadata["collisions_this_step"] = self._collisions_this_step
        result.metadata["weather_active"] = self._weather_active
        
        return result
    
    def _simulate_trains(self):
        """Simulate train movements for one step with block signaling.
        
        Block Signaling Rules:
        1. Each segment can only hold ONE train at a time
        2. Train can only move to next segment if it's clear (not occupied)
        3. RED signal on next segment = train must stop before entering
        4. YELLOW signal on next segment = train waits 1 step
        5. GREEN signal = train can proceed if segment is clear
        
        Priority Rules:
        - Higher priority trains (3=high-speed, 2=express, 1=regular) move first
        - Late trains get slight priority boost to recover schedule
        """
        # Collect all trains that want to move this step
        trains_to_move = []
        
        for train_id, train in self._trains.items():
            if train.status == TrainStatus.ARRIVED or train.status == TrainStatus.DELAYED:
                continue
            
            if train_id in self._held_trains:
                continue
            
            # Get route for this train
            route = self._train_routes.get(train_id, [])
            current_idx = route.index(train.current_segment) if train.current_segment in route else -1
            
            if current_idx >= 0 and current_idx < len(route) - 1:
                next_segment_id = route[current_idx + 1]
                next_seg = self._track_segments.get(next_segment_id)
                current_seg = self._track_segments.get(train.current_segment)
                
                if next_seg is None or current_seg is None:
                    continue
                
                # BLOCK SIGNALING: Check if next segment is clear
                if next_seg.occupied_by is not None:
                    # BLOCK OCCUPIED - Train must wait (safe distance!)
                    train.status = TrainStatus.WAITING
                    train.speed = 0.0
                    continue
                
                # Check signal at NEXT segment (signals control entry to blocks)
                if next_seg.signal_state == SignalState.RED:
                    train.status = TrainStatus.WAITING
                    train.speed = 0.0
                    continue
                
                if next_seg.signal_state == SignalState.YELLOW:
                    # YELLOW = caution, train waits this step
                    train.status = TrainStatus.WAITING
                    train.speed = 0.5
                    # Auto-clear yellow to green for next step
                    next_seg.signal_state = SignalState.GREEN
                    continue
                
                # Calculate effective priority (base priority + delay bonus)
                delay_bonus = min(train.delay * 0.1, 0.5)
                effective_priority = train.priority + delay_bonus
                
                # Train wants to move - collect for processing
                trains_to_move.append((train_id, train, current_seg, next_seg, next_segment_id, effective_priority))
                
            elif current_idx == len(route) - 1:
                # Train is at the last segment in its route = destination reached
                current_seg = self._track_segments.get(train.current_segment)
                train.speed = 0.0
                if current_seg and current_seg.occupied_by == train_id:
                    current_seg.occupied_by = None
                
                # Calculate delay
                if self._step_count > train.scheduled_arrival:
                    train.delay = self._step_count - train.scheduled_arrival
                    train.status = TrainStatus.DELAYED
                else:
                    train.status = TrainStatus.ARRIVED
        
        # Process train movements (handle conflicts)
        # Priority: higher effective priority trains move first
        trains_to_move.sort(key=lambda x: x[5], reverse=True)
        
        # Apply weather effects: some trains randomly skip their move
        if self._weather_active:
            weather_delayed = []
            for item in trains_to_move:
                if random.random() <= self._weather_speed_modifier:
                    weather_delayed.append(item)
                else:
                    # Weather delay - train can't move this step
                    item[1].status = TrainStatus.WAITING
                    item[1].speed = 0.3
            trains_to_move = weather_delayed
        
        moved_segments: Set[str] = set()  # Track which segments were moved into this step
        
        for train_id, train, current_seg, next_seg, next_segment_id, _ in trains_to_move:
            # Double-check segment is still clear (another train may have taken it)
            if next_seg.occupied_by is not None or next_segment_id in moved_segments:
                # Segment taken - train must wait
                train.status = TrainStatus.WAITING
                train.speed = 0.0
                continue
            
            # BLOCK CLEAR - Train can move
            # Release current segment (only if we're the recorded occupant)
            if current_seg.occupied_by == train_id:
                current_seg.occupied_by = None
            
            # Occupy next segment
            train.current_segment = next_segment_id
            next_seg.occupied_by = train_id
            train.status = TrainStatus.MOVING
            train.speed = 1.0
            moved_segments.add(next_segment_id)
    
    def _check_collisions(self):
        """Check for train collisions (two trains in same block).
        
        This should NOT happen with proper block signaling,
        but we check for safety. Collision = critical failure.
        """
        segment_occupancy: Dict[str, List[str]] = {}
        
        for train_id, train in self._trains.items():
            if train.status not in [TrainStatus.ARRIVED, TrainStatus.DELAYED]:
                seg = train.current_segment
                if seg not in segment_occupancy:
                    segment_occupancy[seg] = []
                segment_occupancy[seg].append(train_id)
        
        for seg_id, trains in segment_occupancy.items():
            if len(trains) > 1:
                # COLLISION DETECTED - Two trains in same block!
                self._collisions += 1
                self._collisions_this_step += 1
                
                # Keep highest-priority train as segment occupant, hold others
                trains_sorted = sorted(trains, key=lambda t: self._trains[t].priority, reverse=True)
                for i, tid in enumerate(trains_sorted):
                    self._trains[tid].status = TrainStatus.WAITING
                    self._trains[tid].speed = 0.0
                    if i == 0:
                        self._track_segments[seg_id].occupied_by = tid
                    else:
                        self._held_trains.add(tid)
                
                print(f"[COLLISION] Trains {trains} collided at segment {seg_id}", flush=True)
    
    def _calculate_reward(self) -> float:
        """Calculate reward for current step.
        
        Only rewards/penalizes NEW events this step to avoid cumulative drift.
        """
        reward = 0.0
        
        # Penalty for NEW collisions this step only
        reward -= self._collisions_this_step * 0.5
        
        # Reward for NEWLY arrived trains (not already rewarded)
        for tid, train in self._trains.items():
            if train.status in [TrainStatus.ARRIVED, TrainStatus.DELAYED] and tid not in self._arrived_trains:
                self._arrived_trains.add(tid)
                if train.delay == 0:
                    reward += 0.2 * train.priority
                else:
                    reward -= 0.05 * min(train.delay, 5)
        
        # Small penalty for trains waiting (encourages flow)
        waiting = sum(1 for t in self._trains.values() if t.status == TrainStatus.WAITING)
        reward -= 0.01 * waiting
        
        return max(0.0, min(1.0, reward + 0.5))  # Normalize to [0, 1]
    
    def _is_done(self) -> bool:
        """Check if episode is done."""
        if self._step_count >= self._max_steps:
            return True
        
        # Done if all trains have arrived
        all_arrived = all(
            t.status in [TrainStatus.ARRIVED, TrainStatus.DELAYED]
            for t in self._trains.values()
        )
        
        return all_arrived
    
    def get_final_state(self) -> dict:
        """Get the final state for grading purposes."""
        return {
            "trains": {tid: train.model_dump() for tid, train in self._trains.items()},
            "collisions": self._collisions,
            "step": self._step_count,
            "max_steps": self._max_steps,
            "task_name": self._task_name,
            "weather_active": self._weather_active,
        }
    
    def grade_task(self) -> TaskResult:
        """Grade the task performance."""
        trains_arrived = sum(
            1 for t in self._trains.values()
            if t.status in [TrainStatus.ARRIVED, TrainStatus.DELAYED]
        )
        trains_delayed = sum(
            1 for t in self._trains.values()
            if t.delay > 0
        )
        avg_delay = sum(t.delay for t in self._trains.values()) / max(len(self._trains), 1)
        
        # Calculate score
        total_trains = len(self._trains)
        arrival_score = trains_arrived / total_trains if total_trains > 0 else 0
        delay_penalty = min(avg_delay * 0.05, 0.3)
        collision_penalty = min(self._collisions * 0.2, 0.5)
        
        score = max(0.0, min(1.0, arrival_score - delay_penalty - collision_penalty))
        
        return TaskResult(
            task_name=self._task_name,
            score=score,
            trains_arrived=trains_arrived,
            trains_delayed=trains_delayed,
            collisions=self._collisions,
            avg_delay=avg_delay,
            message=f"Task completed. {trains_arrived}/{total_trains} trains arrived, "
                    f"{self._collisions} collisions, avg delay: {avg_delay:.1f} steps"
        )
    
    @property
    def state(self) -> State:
        """Get current environment state."""
        return self._state