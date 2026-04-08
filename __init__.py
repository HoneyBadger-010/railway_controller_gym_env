"""
Railway Traffic Controller Environment for OpenEnv.

A real-world simulation of railway traffic control where an AI agent
manages train movements, signals, and routing to ensure safe and
efficient operations.

Tasks (easy -> hard):
1. basic_control: 2 trains, simple track, prevent collision
2. junction_management: 4 trains, multiple junctions, optimize flow  
3. rush_hour: 6+ trains, delays, weather, prioritize express trains

Example:
    >>> from railway_controller import RailwayControllerEnv
    >>> 
    >>> with RailwayControllerEnv(base_url="http://localhost:8000") as env:
    ...     env.reset()
    ...     tools = env.list_tools()
    ...     result = env.call_tool("set_signal", segment_id="J1-CROSS", state="red")
"""

from .client import RailwayControllerEnv
from .graders import (
    BaseGrader,
    BasicControlGrader,
    ExpressPriorityGrader,
    JunctionManagementGrader,
    RushHourGrader,
    get_grader,
    TASK_GRADERS,
)
from .models import (
    RailwayControllerAction,
    RailwayObservation,
    RailwayState,
    SignalState,
    TaskResult,
    TrackSegment,
    TrainState,
    TrainStatus,
)

# Import MCP types with graceful fallback
try:
    from openenv.core.env_server.mcp_types import CallToolAction, ListToolsAction
except ImportError:
    CallToolAction = None
    ListToolsAction = None

__all__ = [
    # Client
    "RailwayControllerEnv",
    # Models
    "RailwayControllerAction",
    "RailwayObservation",
    "RailwayState",
    "TrainState",
    "TrainStatus",
    "TrackSegment",
    "SignalState",
    "TaskResult",
    # Graders
    "BaseGrader",
    "BasicControlGrader",
    "ExpressPriorityGrader",
    "JunctionManagementGrader",
    "RushHourGrader",
    "get_grader",
    "TASK_GRADERS",
    # MCP Types
    "CallToolAction",
    "ListToolsAction",
]