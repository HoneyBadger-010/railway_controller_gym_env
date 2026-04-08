"""
Inference Script for Railway Traffic Controller Environment.

MANDATORY
- Before submitting, ensure the following variables are defined in your environment configuration:
    API_BASE_URL   The API endpoint for the LLM.
    MODEL_NAME     The model identifier to use for inference.
    HF_TOKEN       Your Hugging Face / API key.
    LOCAL_IMAGE_NAME The name of the local image to use for the environment.

STDOUT FORMAT
- The script must emit exactly three line types to stdout, in this order:
    [START] task=<task_name> env=<benchmark> model=<model_name>
    [STEP]  step=<n> action=<action_str> reward=<0.00> done=<true|false> error=<msg|null>
    [END]   success=<true|false> steps=<n> score=<score> rewards=<r1,r2,...,rn>
"""

import asyncio
import os
import textwrap
import json
from typing import List, Optional

from openai import OpenAI

from railway_controller import RailwayControllerEnv
from railway_controller.graders import get_grader

# Environment variables
IMAGE_NAME = os.getenv("LOCAL_IMAGE_NAME", "railway-controller:latest")
API_KEY = os.getenv("HF_TOKEN") or os.getenv("API_KEY")
API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct")
BENCHMARK = "railway_controller"
TEMPERATURE = 0.7
MAX_TOKENS = 500
SUCCESS_SCORE_THRESHOLD = 0.7
MAX_HISTORY = 10  # Keep last N message pairs to avoid context overflow

SYSTEM_PROMPT = textwrap.dedent(
    """
    You are a railway traffic controller managing a train network.
    
    Your job is to:
    1. Prevent train collisions by controlling signals and holding trains
    2. Manage train routing at junctions  
    3. Minimize delays while ensuring safety
    4. Prioritize high-speed (priority 3) and express (priority 2) trains over regular (priority 1)
    
    Strategy:
    - First call get_status() or get_collision_warnings() to understand the situation
    - Use get_control_suggestions() for AI-assisted recommendations
    - Hold lower-priority trains to let higher-priority trains pass through junctions
    - Set signals to RED on junction segments to block entry, then GREEN to allow
    - Release held trains once the path is clear
    - Monitor delays with get_delay_status()
    
    Available tools:
    - set_signal(segment_id, state): Set signal to 'red', 'yellow', or 'green'
    - hold_train(train_id, reason): Hold a train at its current position
    - release_train(train_id): Release a held train
    - route_train(train_id, via_segment): Route train through specific segment
    - get_status(): Get current network status
    - get_collision_warnings(): Get warnings about potential collisions
    - get_segment_occupancy(): Get occupancy status of all segments
    - get_control_suggestions(): Get intelligent control suggestions
    - get_delay_status(): Get delay status of all trains
    
    Respond with ONLY a JSON object containing:
    - "tool": the tool name to call
    - "args": object with the tool arguments
    
    Example responses:
    {"tool": "get_control_suggestions", "args": {}}
    {"tool": "set_signal", "args": {"segment_id": "J1-CORE", "state": "red"}}
    {"tool": "hold_train", "args": {"train_id": "R1", "reason": "Let HS1 pass"}}
    {"tool": "release_train", "args": {"train_id": "R1"}}
    """
).strip()


def log_start(task: str, env: str, model: str) -> None:
    print(f"[START] task={task} env={env} model={model}", flush=True)


def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str]) -> None:
    error_val = error if error else "null"
    done_val = str(done).lower()
    print(
        f"[STEP] step={step} action={action} reward={reward:.2f} done={done_val} error={error_val}",
        flush=True,
    )


def log_end(success: bool, steps: int, score: float, rewards: List[float]) -> None:
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(f"[END] success={str(success).lower()} steps={steps} score={score:.3f} rewards={rewards_str}", flush=True)


def build_user_prompt(status: dict, step: int, last_result: Optional[dict] = None) -> str:
    trains_info = []
    for tid, train in status.get("trains", {}).items():
        trains_info.append(
            f"  {tid}: segment={train['current_segment']}, status={train['status']}, "
            f"dest={train['destination']}, delay={train['delay']}, priority={train['priority']}"
        )
    
    result_info = ""
    if last_result:
        result_info = f"\nLast action result: {json.dumps(last_result, default=str)[:500]}\n"
    
    return textwrap.dedent(
        f"""
        Step: {step}/{status.get('max_steps', 50)}
        Collisions so far: {status.get('collisions', 0)}
        Held trains: {status.get('held_trains', [])}
        Weather active: {status.get('weather_active', False)}
        {result_info}
        Trains:
        {chr(10).join(trains_info)}
        
        What action should you take? Respond with a JSON object.
        """
    ).strip()


def get_model_action(client: OpenAI, messages: list) -> tuple:
    """Get action from the model using conversation history."""
    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            stream=False,
        )
        
        response_text = (completion.choices[0].message.content or "").strip()
        
        # Parse JSON response
        try:
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                json_str = response_text.split("```")[1].split("```")[0].strip()
            else:
                json_str = response_text
            
            action_data = json.loads(json_str)
            tool_name = action_data.get("tool", "get_status")
            tool_args = action_data.get("args", {})
            
            return tool_name, tool_args, None, response_text
        except json.JSONDecodeError:
            return "get_status", {}, f"Failed to parse response: {response_text[:100]}", response_text
            
    except Exception as exc:
        return "get_status", {}, str(exc), ""


async def run_task(env: RailwayControllerEnv, client: OpenAI, task_name: str) -> tuple:
    """Run a single task and return results."""
    rewards: List[float] = []
    steps_taken = 0
    score = 0.0
    success = False
    
    # Get task-specific max steps
    task_max_steps = {"basic_control": 30, "junction_management": 50, "express_priority": 40, "rush_hour": 80}.get(task_name, 50)
    
    log_start(task=task_name, env=BENCHMARK, model=MODEL_NAME)
    
    # Maintain conversation history for multi-turn reasoning
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    try:
        # Reset environment WITH task name
        result = await env.reset(task_name=task_name)
        
        last_tool_result = None
        
        for step in range(1, task_max_steps + 1):
            if result.done:
                break
            
            # Get current status
            status = await env.call_tool_async("get_status")
            
            # Build user prompt with context
            user_prompt = build_user_prompt(status, step, last_tool_result)
            messages.append({"role": "user", "content": user_prompt})
            
            # Trim history to avoid context overflow (keep system + last N pairs)
            if len(messages) > 1 + MAX_HISTORY * 2:
                messages = [messages[0]] + messages[-(MAX_HISTORY * 2):]
            
            # Get action from model
            tool_name, tool_args, error, response_text = get_model_action(client, messages)
            
            # Add assistant response to history
            if response_text:
                messages.append({"role": "assistant", "content": response_text})
            
            # Execute action
            if error:
                action_str = f"error: {error}"
                reward = 0.0
                done = False
                last_tool_result = {"error": error}
            else:
                action_str = f"{tool_name}({tool_args})"
                try:
                    result = await env.step_tool(tool_name, **tool_args)
                    reward = result.reward or 0.0
                    done = result.done
                    error = None
                    last_tool_result = result.metadata if hasattr(result, 'metadata') else {}
                except Exception as e:
                    reward = 0.0
                    done = False
                    error = str(e)
                    last_tool_result = {"error": str(e)}
            
            rewards.append(reward)
            steps_taken = step
            
            log_step(step=step, action=action_str, reward=reward, done=done, error=error)
            
            if done:
                break
        
        # Use the proper grader for final scoring (not naive reward average)
        grader = get_grader(task_name)
        final_status = await env.call_tool_async("get_status")
        task_result = grader.grade(final_status)
        score = task_result.score
        success = score >= SUCCESS_SCORE_THRESHOLD
        
        print(f"[GRADER] {task_result.message}", flush=True)
        
    finally:
        try:
            await env.close()
        except Exception as e:
            print(f"[DEBUG] env.close() error: {e}", flush=True)
        
        log_end(success=success, steps=steps_taken, score=score, rewards=rewards)
    
    return success, steps_taken, score


async def main() -> None:
    """Main entry point."""
    client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)
    
    # Run all three tasks
    tasks = ["basic_control", "junction_management", "express_priority", "rush_hour"]
    total_score = 0.0
    total_success = 0
    
    for task_name in tasks:
        print(f"\n{'='*50}", flush=True)
        print(f"Running task: {task_name}", flush=True)
        print(f"{'='*50}", flush=True)
        
        # Create environment for this task
        # Use SERVER_URL if provided (for local testing when docker needs sudo)
        # Otherwise use from_docker_image (for hackathon evaluators)
        server_url = os.getenv("SERVER_URL")
        if server_url:
            env = RailwayControllerEnv(base_url=server_url)
            await env.reset(task_name=task_name)
        else:
            env = await RailwayControllerEnv.from_docker_image(IMAGE_NAME)
        
        success, steps, score = await run_task(env, client, task_name)
        total_score += score
        if success:
            total_success += 1
    
    print(f"\n{'='*50}", flush=True)
    print(f"FINAL RESULTS", flush=True)
    print(f"{'='*50}", flush=True)
    print(f"Tasks completed: {total_success}/{len(tasks)}", flush=True)
    print(f"Average score: {total_score/len(tasks):.3f}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())