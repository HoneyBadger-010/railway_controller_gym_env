"""
FastAPI application for the Railway Traffic Controller Environment.

This module creates an HTTP server that exposes the RailwayControllerEnvironment
over HTTP and WebSocket endpoints.
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openenv.core.env_server.http_server import create_app
from openenv.core.env_server.mcp_types import CallToolAction, CallToolObservation

from server.railway_environment import RailwayControllerEnvironment


# Create the app with web interface
app = create_app(
    RailwayControllerEnvironment,
    CallToolAction,
    CallToolObservation,
    env_name="railway_controller"
)


def main():
    """Entry point for direct execution."""
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()