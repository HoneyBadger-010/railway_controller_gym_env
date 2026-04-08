"""
Task Graders for Railway Traffic Controller Environment.

Each grader evaluates agent performance on a specific task,
returning a score between 0.0 and 1.0.

Grading considers:
- Train arrivals (on-time vs delayed)
- Collision prevention
- Priority train handling (express/high-speed trains should have lower delays)
- Overall efficiency
"""

from typing import Dict, Any
from .models import TaskResult, TrainStatus


class BaseGrader:
    """Base class for task graders."""
    
    def grade(self, final_state: Dict[str, Any]) -> TaskResult:
        """Grade the task based on final state."""
        raise NotImplementedError


class BasicControlGrader(BaseGrader):
    """
    Grader for Task 1: Basic Control (Easy)
    
    Criteria:
    - Both trains arrive safely (no collisions)
    - Minimal delays
    - Episode completes within time limit
    
    Scoring:
    - 70% weight on arrivals
    - Up to 30% bonus for efficiency (no collisions, low delay)
    """
    
    def grade(self, final_state: Dict[str, Any]) -> TaskResult:
        trains = final_state.get("trains", {})
        collisions = final_state.get("collisions", 0)
        
        # Count arrived trains
        arrived = sum(
            1 for t in trains.values()
            if t.get("status") in [TrainStatus.ARRIVED.value, TrainStatus.DELAYED.value]
        )
        
        # Calculate delays
        total_delay = sum(t.get("delay", 0) for t in trains.values())
        avg_delay = total_delay / max(len(trains), 1)
        
        # Score calculation:
        # Arrival component (0.0 - 0.7)
        arrival_score = arrived / max(len(trains), 1) * 0.7
        
        # Safety bonus (0.0 - 0.2): no collisions = full bonus
        safety_bonus = 0.2 if collisions == 0 else max(0.0, 0.2 - collisions * 0.15)
        
        # Efficiency bonus (0.0 - 0.1): low delays
        delay_penalty = min(avg_delay * 0.03, 0.1)
        efficiency_bonus = 0.1 - delay_penalty
        
        score = max(0.0, min(1.0, arrival_score + safety_bonus + efficiency_bonus))
        
        return TaskResult(
            task_name="basic_control",
            score=score,
            trains_arrived=arrived,
            trains_delayed=sum(1 for t in trains.values() if t.get("delay", 0) > 0),
            collisions=collisions,
            avg_delay=avg_delay,
            message=f"Basic control: {arrived}/{len(trains)} trains arrived, {collisions} collisions, avg delay: {avg_delay:.1f}"
        )


class JunctionManagementGrader(BaseGrader):
    """
    Grader for Task 2: Junction Management (Medium)
    
    Criteria:
    - All trains arrive safely
    - Express trains prioritized (lower delay than regular)
    - Efficient junction usage
    
    Scoring:
    - 50% weight on arrivals
    - 20% on collision avoidance
    - 15% on priority handling
    - 15% on delay minimization
    """
    
    def grade(self, final_state: Dict[str, Any]) -> TaskResult:
        trains = final_state.get("trains", {})
        collisions = final_state.get("collisions", 0)
        
        arrived = sum(
            1 for t in trains.values()
            if t.get("status") in [TrainStatus.ARRIVED.value, TrainStatus.DELAYED.value]
        )
        
        # Separate express and regular trains
        express_delays = [t.get("delay", 0) for t in trains.values() if t.get("priority", 1) >= 2]
        regular_delays = [t.get("delay", 0) for t in trains.values() if t.get("priority", 1) < 2]
        
        avg_express_delay = sum(express_delays) / max(len(express_delays), 1)
        avg_regular_delay = sum(regular_delays) / max(len(regular_delays), 1)
        
        # Arrival component (0.0 - 0.5)
        arrival_score = arrived / max(len(trains), 1) * 0.5
        
        # Safety component (0.0 - 0.2)
        collision_penalty = min(collisions * 0.1, 0.2)
        safety_score = 0.2 - collision_penalty
        
        # Priority handling (0.0 - 0.15): bonus if express delay <= regular delay
        priority_bonus = 0.15 if avg_express_delay <= avg_regular_delay else 0.05
        
        # Efficiency (0.0 - 0.15)
        total_delay = (avg_express_delay + avg_regular_delay)
        delay_penalty = min(total_delay * 0.02, 0.15)
        efficiency_score = 0.15 - delay_penalty
        
        score = max(0.0, min(1.0, arrival_score + safety_score + priority_bonus + efficiency_score))
        
        return TaskResult(
            task_name="junction_management",
            score=score,
            trains_arrived=arrived,
            trains_delayed=sum(1 for t in trains.values() if t.get("delay", 0) > 0),
            collisions=collisions,
            avg_delay=(avg_express_delay + avg_regular_delay) / 2,
            message=f"Junction management: {arrived}/{len(trains)} arrived, express avg delay: {avg_express_delay:.1f}, collisions: {collisions}"
        )


class RushHourGrader(BaseGrader):
    """
    Grader for Task 3: Rush Hour (Hard)
    
    Criteria:
    - High on-time arrival rate despite congestion
    - High-speed trains (priority 3) must have lowest delays
    - Express trains (priority 2) should have lower delays than regular
    - Minimal collisions under pressure
    
    Scoring:
    - 40% weight on arrivals
    - 20% on collision avoidance
    - 25% on priority handling (HS + express)
    - 15% on overall delay minimization
    """
    
    def grade(self, final_state: Dict[str, Any]) -> TaskResult:
        trains = final_state.get("trains", {})
        collisions = final_state.get("collisions", 0)
        
        arrived = sum(
            1 for t in trains.values()
            if t.get("status") in [TrainStatus.ARRIVED.value, TrainStatus.DELAYED.value]
        )
        
        # Categorize by priority
        high_speed = [t for t in trains.values() if t.get("priority", 1) == 3]
        express = [t for t in trains.values() if t.get("priority", 1) == 2]
        regular = [t for t in trains.values() if t.get("priority", 1) == 1]
        
        # Calculate delays by priority
        hs_delay = sum(t.get("delay", 0) for t in high_speed) / max(len(high_speed), 1)
        exp_delay = sum(t.get("delay", 0) for t in express) / max(len(express), 1)
        reg_delay = sum(t.get("delay", 0) for t in regular) / max(len(regular), 1)
        
        # Arrival component (0.0 - 0.4)
        arrival_score = arrived / max(len(trains), 1) * 0.4
        
        # Safety component (0.0 - 0.2)
        collision_penalty = min(collisions * 0.1, 0.2)
        safety_score = 0.2 - collision_penalty
        
        # Priority handling (0.0 - 0.25)
        priority_bonus = 0.0
        if hs_delay <= reg_delay:
            priority_bonus += 0.15
        if exp_delay <= reg_delay:
            priority_bonus += 0.10
        
        # High-speed delay penalty (reduce priority bonus if HS trains are late)
        hs_penalty = min(hs_delay * 0.02, 0.10)
        priority_bonus = max(0.0, priority_bonus - hs_penalty)
        
        # Efficiency (0.0 - 0.15)
        total_delay = (hs_delay + exp_delay + reg_delay) / 3
        delay_penalty = min(total_delay * 0.02, 0.15)
        efficiency_score = 0.15 - delay_penalty
        
        score = max(0.0, min(1.0, arrival_score + safety_score + priority_bonus + efficiency_score))
        
        # Build detailed message
        hs_status = "on-time" if hs_delay == 0 else f"{hs_delay:.0f} steps late"
        exp_status = "on-time" if exp_delay == 0 else f"{exp_delay:.0f} steps late"
        
        return TaskResult(
            task_name="rush_hour",
            score=score,
            trains_arrived=arrived,
            trains_delayed=sum(1 for t in trains.values() if t.get("delay", 0) > 0),
            collisions=collisions,
            avg_delay=total_delay,
            message=f"Rush hour: {arrived}/{len(trains)} arrived | HS: {hs_status} | Express: {exp_status} | Collisions: {collisions}"
        )


class ExpressPriorityGrader(BaseGrader):
    """
    Grader for Task 4: Express Priority (Medium-Hard)
    
    Criteria:
    - All trains arrive safely under tight schedules
    - High-speed trains (priority 3) must have ZERO delay
    - Cascading junction conflicts resolved correctly
    - No collisions despite shared starting segments
    
    Scoring:
    - 40% weight on arrivals
    - 25% on collision avoidance (tight network = high collision risk)
    - 25% on priority handling (HS trains must be on-time)
    - 10% on overall delay minimization
    """
    
    def grade(self, final_state: Dict[str, Any]) -> TaskResult:
        trains = final_state.get("trains", {})
        collisions = final_state.get("collisions", 0)
        
        arrived = sum(
            1 for t in trains.values()
            if t.get("status") in [TrainStatus.ARRIVED.value, TrainStatus.DELAYED.value]
        )
        
        # Categorize by priority
        high_speed = [t for t in trains.values() if t.get("priority", 1) == 3]
        express = [t for t in trains.values() if t.get("priority", 1) == 2]
        regular = [t for t in trains.values() if t.get("priority", 1) == 1]
        
        hs_delay = sum(t.get("delay", 0) for t in high_speed) / max(len(high_speed), 1)
        exp_delay = sum(t.get("delay", 0) for t in express) / max(len(express), 1)
        reg_delay = sum(t.get("delay", 0) for t in regular) / max(len(regular), 1)
        
        # Arrival component (0.0 - 0.4)
        arrival_score = arrived / max(len(trains), 1) * 0.4
        
        # Safety component (0.0 - 0.25) — tight network means collisions are likely
        collision_penalty = min(collisions * 0.15, 0.25)
        safety_score = 0.25 - collision_penalty
        
        # Priority handling (0.0 - 0.25) — HS trains must be on-time
        priority_bonus = 0.0
        if hs_delay == 0:
            priority_bonus += 0.15  # Big bonus: both HS trains on time
        if exp_delay <= reg_delay:
            priority_bonus += 0.10
        
        # Efficiency (0.0 - 0.10)
        total_delay = (hs_delay + exp_delay + reg_delay) / 3
        delay_penalty = min(total_delay * 0.03, 0.10)
        efficiency_score = 0.10 - delay_penalty
        
        score = max(0.0, min(1.0, arrival_score + safety_score + priority_bonus + efficiency_score))
        
        hs_status = "on-time" if hs_delay == 0 else f"{hs_delay:.0f} steps late"
        
        return TaskResult(
            task_name="express_priority",
            score=score,
            trains_arrived=arrived,
            trains_delayed=sum(1 for t in trains.values() if t.get("delay", 0) > 0),
            collisions=collisions,
            avg_delay=total_delay,
            message=f"Express priority: {arrived}/{len(trains)} arrived | HS: {hs_status} | Collisions: {collisions}"
        )


# Task registry
TASK_GRADERS = {
    "basic_control": BasicControlGrader(),
    "junction_management": JunctionManagementGrader(),
    "rush_hour": RushHourGrader(),
    "express_priority": ExpressPriorityGrader(),
}


def get_grader(task_name: str) -> BaseGrader:
    """Get the grader for a task."""
    return TASK_GRADERS.get(task_name, BasicControlGrader())