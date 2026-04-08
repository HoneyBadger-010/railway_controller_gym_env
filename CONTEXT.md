# Railway Traffic Controller - Project Context

## Hackathon Requirements (OpenEnv Round 1)

### Key Requirements
1. **Real-world task simulation** - Must simulate a task humans actually do (not games/toys)
2. **OpenEnv spec compliance** - typed models, step()/reset()/state(), openenv.yaml
3. **Minimum 3 tasks with agent graders** - easy → medium → hard, scores 0.0–1.0
4. **Meaningful reward function** - partial progress signals, not just binary
5. **Baseline inference script** - uses OpenAI API client, reproducible scores
6. **Deploy to Hugging Face Spaces** - containerized HF Space tagged with openenv
7. **Working Dockerfile** - docker build + docker run works
8. **README documentation** - environment description, action/observation spaces, setup instructions

### Evaluation Criteria
- Real-world utility (30%)
- Task & grader quality (25%)
- Environment design (20%)
- Code quality & spec compliance (15%)
- Creativity & novelty (10%)

### Pre-Submission Checklist
- [x] HF Space deploys (responds to /reset with 200)
- [x] OpenEnv spec compliance (openenv validate passes)
- [x] Dockerfile builds
- [x] Baseline reproduces scores
- [x] 3+ tasks with graders (scores 0.0-1.0)

---

## Project Overview

### Concept
Railway Traffic Controller - Agent acts as central traffic controller managing a railway network with multiple trains. Must prevent collisions, manage routing at junctions, minimize delays, and prioritize express trains.

### Real-World Application
Train dispatching is an actual profession. Controllers manage railway networks to ensure trains run safely and on time. This environment models that task for:
- Training RL agents for transportation logistics
- Evaluating agent decision-making under time pressure
- Testing multi-objective optimization (safety vs. efficiency)

---

## Technical Implementation

### Project Structure
```
railway_controller/
├── __init__.py           # Package exports
├── models.py             # Pydantic models (TrainState, TrackSegment, etc.)
├── client.py             # RailwayControllerEnv client (MCPToolClient)
├── graders.py            # Task graders for 3 difficulty levels
├── inference.py          # Baseline inference script
├── openenv.yaml          # Environment manifest
├── pyproject.toml        # Package configuration
├── uv.lock               # Dependency lock file
├── README.md             # Documentation with HF metadata
├── .dockerignore         # Docker exclusions
└── server/
    ├── __init__.py
    ├── app.py            # FastAPI application
    ├── Dockerfile        # Container definition
    ├── requirements.txt  # Server dependencies
    └── railway_environment.py  # Core environment logic (MCPEnvironment)
```

### Models (models.py)

#### TrainState
- train_id: str
- current_segment: str
- destination: str
- status: TrainStatus (MOVING, WAITING, ARRIVED, DELAYED)
- speed: float (0-1)
- scheduled_arrival: int
- delay: int
- priority: int (1=regular, 2=express, 3=high-speed)
- train_type: str

#### TrackSegment
- segment_id: str
- length: float
- signal_state: SignalState (RED, YELLOW, GREEN)
- occupied_by: Optional[str] (train ID)
- next_segments: List[str]
- is_junction: bool
- station_name: Optional[str]

#### SignalState (Enum)
- RED = "red" (stop)
- YELLOW = "yellow" (caution)
- GREEN = "green" (go)

---

## Tasks

### Task 1: Basic Control (Easy)
- **Trains:** 2 regular trains
- **Network:** Simple track with one shared junction segment
- **Goal:** Prevent collision at intersection
- **Max Steps:** 30
- **Routes:** 
  - T1: A-J1 → J1-CROSS → J1-B
  - T2: D-J1 → J1-CROSS → J1-C

### Task 2: Junction Management (Medium)
- **Trains:** 4 trains (3 regular, 1 express)
- **Network:** Multiple junctions with crossing routes
- **Goal:** Optimize flow, prevent collisions, prioritize express
- **Max Steps:** 50
- **Routes:**
  - T1: N1-J1 → J1-CORE → J1-E1 → E1-E2
  - T2 (express): W1-J1 → J1-CORE → J1-S1 → J2-CORE → S1-J2
  - T3: E1-J1 → J1-CORE → J1-W1 → W1-W2
  - T4: S1-J2 → J2-CORE → J2-E2 → E1-E2

### Task 3: Rush Hour (Hard)
- **Trains:** 6 trains (2 high-speed, 2 express, 2 regular)
- **Network:** Complex network with multiple junctions and stations
- **Goal:** Prioritize high-speed/express, manage congestion, handle delays
- **Max Steps:** 80
- **Routes:**
  - HS1 (priority 3): A-J1 → J1-CORE → J1-B
  - HS2 (priority 3): F-J4 → J4-CORE → J2-CORE → J2-C
  - EX1 (priority 2): A-J2 → J2-CORE → C-J3 → J3-CORE → J3-E
  - EX2 (priority 2): B-J1 → J1-CORE → J1-J2 → J2-CORE → J4-CORE → J4-F
  - R1 (priority 1): D-J4 → J4-CORE → J2-CORE → J2-D
  - R2 (priority 1): E-J4 → J4-CORE → J4-F

---

## MCP Tools (9 tools)

1. **set_signal(segment_id, state)** - Set signal state (red/yellow/green)
2. **hold_train(train_id, reason)** - Hold train at current position
3. **release_train(train_id)** - Release held train
4. **route_train(train_id, via_segment)** - Route train through specific segment
5. **get_status()** - Get current network status
6. **get_collision_warnings()** - Get warnings about potential collisions
7. **get_segment_occupancy()** - Get occupancy status of all segments
8. **get_control_suggestions()** - Get intelligent control suggestions
9. **get_delay_status()** - Get delay status of all trains

---

## Track Safety (Block Signaling)

### Rules
1. Each segment can only hold ONE train at a time
2. Trains automatically stop if next segment is occupied
3. Signal control:
   - RED: Train cannot enter segment
   - YELLOW: Train waits 1 step then proceeds
   - GREEN: Train proceeds if segment is clear
4. Collision = critical failure (two trains in same block)

### Implementation
- `_simulate_trains()` - Moves trains with block signaling
- `_check_collisions()` - Detects if two trains in same segment
- Priority-based movement: higher priority + late trains move first

---

## Priority System

### Train Types
| Priority | Type | Description |
|----------|------|-------------|
| 3 | High-Speed | Premium trains, right-of-way |
| 2 | Express | Fast trains, priority over regular |
| 1 | Regular | Standard trains |

### Priority Rules
- Higher priority trains move first at junctions
- Late trains get priority boost (delay * 0.1, max 0.5)
- effective_priority = base_priority + delay_bonus

---

## Reward Function

| Event | Reward |
|-------|--------|
| Train arrives on time | +0.2 × priority |
| Train delayed | -0.05 per step of delay |
| Collision | -0.5 |
| Train waiting | -0.01 per waiting train |

Rewards normalized to [0.0, 1.0] range.

---

## Graders (graders.py)

### BasicControlGrader
- arrival_score = arrived/total * 0.6
- collision_penalty = min(collisions * 0.3, 0.5)
- delay_penalty = min(avg_delay * 0.02, 0.2)
- score = arrival_score - collision_penalty - delay_penalty + 0.4

### JunctionManagementGrader
- arrival_score = arrived/total * 0.5
- collision_penalty = min(collisions * 0.25, 0.4)
- priority_bonus = 0.1 if express_delay <= regular_delay
- delay_penalty = min(total_delay * 0.01, 0.2)

### RushHourGrader
- arrival_score = arrived/total * 0.4
- collision_penalty = min(collisions * 0.2, 0.3)
- priority_bonus = 0.15 if high-speed delay <= regular delay
- high-speed penalty = min(hs_delay * 0.03, 0.15)

---

## Intelligent Control Suggestions

### Types
1. **collision_prevention** - Hold lower-priority train at junction
2. **priority_override** - Let late/high-priority train pass
3. **signal_optimization** - Clear signal for waiting train
4. **release_train** - Release held train when path clear

### Logic
- Detects multiple trains heading to same junction
- Identifies late trains needing priority
- Finds blocked trains that can be released

---

## Inference Script (inference.py)

### Configuration
- Uses OpenAI API client
- Reads from env: API_BASE_URL, MODEL_NAME, HF_TOKEN, LOCAL_IMAGE_NAME
- Default model: Qwen/Qwen2.5-72B-Instruct

### Output Format
```
[START] task=<task_name> env=<benchmark> model=<model_name>
[STEP] step=<n> action=<action_str> reward=<0.00> done=<true|false> error=<msg|null>
[END] success=<true|false> steps=<n> score=<score> rewards=<r1,r2,...,rn>
```

### System Prompt
Instructs model to act as railway controller with JSON responses containing tool name and args.

---

## Known Issues / Potential Improvements

1. **Import structure** - Uses sys.path manipulation for Docker compatibility
2. **Route calculation** - Simple BFS, could be optimized
3. **Weather effects** - Defined in config but not fully implemented
4. **Random delays** - Only in rush_hour task
5. **No visualization** - Could add web interface for debugging

---

## Testing Commands

```bash
# Validate
openenv validate railway_controller

# Build Docker
sudo docker build -t railway-controller:latest -f railway_controller/server/Dockerfile railway_controller

# Run container
sudo docker run -p 8000:8000 railway-controller:latest

# Test endpoints
curl http://localhost:8000/health
curl -X POST http://localhost:8000/reset -H "Content-Type: application/json" -d '{}'

# Run inference
python railway_controller/inference.py
```

---

## Deployment to Hugging Face

```bash
# Login
huggingface-cli login

# Push
cd railway_controller
openenv push
```

Or manually create Docker Space and upload files.