"""
Railway Traffic Controller Environment Client.

This module provides the client for connecting to a Railway Controller
Environment server. RailwayControllerEnv extends MCPToolClient to provide
tool-calling style interactions.

Example:
    >>> with RailwayControllerEnv(base_url="http://localhost:8000") as env:
    ...     env.reset()
    ...
    ...     # Discover tools
    ...     tools = env.list_tools()
    ...     print([t.name for t in tools])
    ...
    ...     # Set a signal
    ...     result = env.call_tool("set_signal", segment_id="B-C", state="red")
    ...
    ...     # Hold a train
    ...     result = env.call_tool("hold_train", train_id="T1", reason="Waiting for T2")
    ...
    ...     # Get status
    ...     status = env.call_tool("get_status")
"""

from openenv.core.mcp_client import MCPToolClient


class RailwayControllerEnv(MCPToolClient):
    """
    Client for the Railway Traffic Controller Environment.
    
    This client provides a simple interface for interacting with the Railway
    Controller Environment via MCP tools. It inherits all functionality from
    MCPToolClient:
    - `list_tools()`: Discover available tools
    - `call_tool(name, **kwargs)`: Call a tool by name
    - `reset(**kwargs)`: Reset the environment
    - `step(action)`: Execute an action
    
    Available Tools:
    - `set_signal(segment_id, state)`: Set signal state (red/yellow/green)
    - `hold_train(train_id, reason)`: Hold a train at current position
    - `release_train(train_id)`: Release a held train
    - `route_train(train_id, via_segment)`: Route train through specific segment
    - `get_status()`: Get current network status
    
    Example:
        >>> # Connect to a running server
        >>> with RailwayControllerEnv(base_url="http://localhost:8000") as env:
        ...     env.reset()
        ...
        ...     # Get current status
        ...     status = env.call_tool("get_status")
        ...     print(f"Step: {status['step']}")
        ...
        ...     # Set signal to red to prevent collision
        ...     env.call_tool("set_signal", segment_id="B-C", state="red")
        ...
        ...     # Hold a train
        ...     env.call_tool("hold_train", train_id="T1", reason="Safety")
    
    Example with Docker:
        >>> # Automatically start container and connect
        >>> env = RailwayControllerEnv.from_docker_image("railway-controller:latest")
        >>> try:
        ...     env.reset()
        ...     status = env.call_tool("get_status")
        ... finally:
        ...     env.close()
    
    Example with HuggingFace Space:
        >>> # Run from HuggingFace Space
        >>> env = RailwayControllerEnv.from_env("your-username/railway-controller")
        >>> try:
        ...     env.reset()
        ...     result = env.call_tool("set_signal", segment_id="B-C", state="green")
        ... finally:
        ...     env.close()
    """
    
    pass  # MCPToolClient provides all needed functionality