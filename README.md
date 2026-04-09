---
title: Railway Traffic Controller
emoji: 🚂
colorFrom: blue
colorTo: green
sdk: docker
app_port: 8000
pinned: false
tags:
  - openenv
  - rl-environment
  - railway
  - traffic-control
license: mit
---

# Railway Traffic Controller Environment

A real-world simulation of railway traffic control for OpenEnv, where an AI agent manages train movements, signals, and routing to ensure safe and efficient operations.

## Overview

This environment simulates the job of a railway traffic controller — an actual profession where dispatchers manage railway networks to keep trains safe and on time. The agent must:
- Control signals to prevent train collisions (block signaling)
- Manage train routing at junctions
- Minimize delays while ensuring safety
- Prioritize express and high-speed trains over regular services

## Real-World Application

Train dispatching is valued for:
- **Training RL agents** for transportation logistics
- **Evaluating decision-making** under time pressure with competing priorities
- **Testing multi-objective optimization** (safety vs. efficiency vs. fairness)

## Tasks

### Task 1: Basic Control (Easy)
- **Trains:** 2 regular trains on a simple track
- **Network:** 5 segments with one shared crossing (J1-CROSS)
- **Goal:** Prevent collision at the shared junction
- **Max Steps:** 30
- **Key Challenge:** Coordinate signal timing so both trains pass through J1-CROSS safely

### Task 2: Junction Management (Medium)
- **Trains:** 4 trains (3 regular, 1 express)
- **Network:** 13 segments with two junctions (J1-CORE, J2-CORE)
- **Goal:** Optimize flow, prevent collisions, prioritize express train T2
- **Max Steps:** 50
- **Key Challenge:** Three trains (T1, T2, T3) all need J1-CORE — must sequence them by priority

### Task 3: Express Priority (Medium-Hard)
- **Trains:** 5 trains (2 high-speed, 1 express, 2 regular)
- **Network:** 11 segments with three junctions in a chain (J1→J2→J3)
- **Goal:** Get all high-speed trains through on time despite cascading conflicts
- **Max Steps:** 40
- **Key Challenge:** HS1 & EX1 both start at Station A (immediate conflict at J1); HS2 & R2 both start at Station C (conflict at J2); EX1 crosses both J1 and J2

### Task 4: Rush Hour (Hard)
- **Trains:** 6 trains (2 high-speed, 2 express, 2 regular)
- **Network:** 19 segments with four junctions (J1–J4), weather effects active
- **Goal:** Prioritize high-speed/express trains, manage congestion, handle random delays
- **Max Steps:** 80
- **Key Challenge:** Multiple crossing conflicts at J2-CORE and J4-CORE with weather randomly delaying trains

## Action Space (MCP Tools)

| Tool | Description | Parameters |
|------|-------------|------------|
| `set_signal` | Set signal state for a track segment | `segment_id`: str, `state`: "red"/"yellow"/"green" |
| `hold_train` | Hold a train at current position | `train_id`: str, `reason`: str (optional) |
| `release_train` | Release a held train | `train_id`: str |
| `route_train` | Route train through specific segment | `train_id`: str, `via_segment`: str |
| `get_status` | Get current network status | None |
| `get_collision_warnings` | Get warnings about potential collisions | None |
| `get_segment_occupancy` | Get occupancy status of all segments | None |
| `get_control_suggestions` | Get intelligent control suggestions | None |
| `get_delay_status` | Get delay status of all trains | None |

## Track Safety (Block Signaling)

The environment implements **block signaling** for safe train operations:

- **One Train Per Block**: Each track segment can only hold ONE train at a time
- **Signal Control**: Signals control **entry** to the next block:
  - RED = Stop (train cannot enter next segment)
  - YELLOW = Caution (train waits one step, then signal auto-clears to GREEN)
  - GREEN = Proceed (if next segment is unoccupied)
- **Collision Detection**: If two trains enter the same block, it's a critical failure

## Train Priority System

| Priority | Type | Description |
|----------|------|-------------|
| 3 | High-Speed | Premium trains, get right-of-way at junctions |
| 2 | Express | Fast trains, priority over regular trains |
| 1 | Regular | Standard trains, lowest priority |

**Priority rules:**
- Higher priority trains move first when multiple trains want the same junction
- Late trains get a priority boost: `effective_priority = base_priority + min(delay * 0.1, 0.5)`

## Reward Function

| Event | Reward |
|-------|--------|
| Train arrives on time | +0.2 × priority (one-time) |
| Train arrives late | -0.05 × min(delay, 5) (one-time) |
| New collision | -0.5 per collision event |
| Train waiting | -0.01 per waiting train per step |

Rewards are normalized to [0.0, 1.0] per step. Only **new** events are rewarded/penalized to prevent cumulative drift.

## Grading

Each task has a dedicated grader that evaluates the final state:

| Component | Basic | Junction | Express Priority | Rush Hour |
|-----------|-------|----------|------------------|-----------|
| Arrivals | 70% | 50% | 40% | 40% |
| Safety | 20% | 20% | 25% | 20% |
| Priority handling | — | 15% | 25% | 25% |
| Efficiency | 10% | 15% | 10% | 15% |

## Weather System (Rush Hour)

During the rush hour task, weather effects are active:
- Each train has a 25% chance per step of being weather-delayed
- Weather-delayed trains skip their movement for that step
- This adds unpredictability that the agent must handle

## Baseline Scores

| Task | Baseline Score | Notes |
|------|---------------|-------|
| basic_control | ~0.85 | Simple collision avoidance |
| junction_management | ~0.65 | Requires junction coordination |
| express_priority | ~0.55 | Tight schedules, cascading conflicts |
| rush_hour | ~0.45 | Complex multi-train + weather management |

## Setup & Usage

```bash
# Build Docker image
docker build -t railway-controller:latest -f server/Dockerfile .

# Run container
docker run -p 8000:8000 railway-controller:latest

# Test endpoints
curl http://localhost:8000/health
curl -X POST http://localhost:8000/reset -H "Content-Type: application/json" -d '{}'

# Run inference
python inference.py
```

```python
from railway_controller import RailwayControllerEnv

with RailwayControllerEnv(base_url="http://localhost:8000") as env:
    env.reset()
    
    # Get current status
    status = env.call_tool("get_status")
    
    # Set signal to prevent collision
    env.call_tool("set_signal", segment_id="J1-CROSS", state="red")
    
    # Hold a train
    env.call_tool("hold_train", train_id="T2", reason="Let T1 pass")
    
    # Get AI-powered control suggestions
    suggestions = env.call_tool("get_control_suggestions")
```

## License

MIT License