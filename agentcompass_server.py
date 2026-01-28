"""
    AgentCompass(https://github.com/open-compass/AgentCompass) OSWorld Simple Server

    Start:
    ```
    python agentcompass_server.py --path_to_vm {your_vm_path(only support docker)} --workers {num_workers} --port {your_port}
    ```
"""

import argparse
from datetime import datetime
import os
import json
import logging
import time
import shutil
import tempfile
import asyncio
import sys
from contextlib import asynccontextmanager
from typing import Dict, Any, List, Optional

import uvicorn
from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool

from desktop_env.osworld.desktop_env import DesktopEnv as OSWorldDesktopEnv

from mm_agents.qwen3vl_agent import Qwen3VLAgent

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [PID:%(process)d] - %(levelname)s - %(message)s'
)
logger = logging.getLogger("osworld_service")


# --- Default Configuration ---
class ServiceConfig:
    # Environment configuration (fixed at process startup)
    PATH_TO_VM = os.getenv("PATH_TO_VM", "/nvme/yangbowen/osworld/docker_vm_data/Ubuntu.qcow2")
    PROVIDER_NAME = os.getenv("PROVIDER_NAME", "docker")
    HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
    ACTION_SPACE = os.getenv("ACTION_SPACE", "pyautogui")
    SCREEN_WIDTH = int(os.getenv("SCREEN_WIDTH", 1920))
    SCREEN_HEIGHT = int(os.getenv("SCREEN_HEIGHT", 1080))
    OBSERVATION_TYPE = os.getenv("OBSERVATION_TYPE", "screenshot")

    DEFAULT_MAX_TOKENS = int(os.getenv("MAX_TOKENS", 32768))
    DEFAULT_TOP_P = float(os.getenv("TOP_P", 0.9))
    DEFAULT_TEMPERATURE = float(os.getenv("TEMPERATURE", 0.0))

    TMP_ROOT_DIR = "agentcompass_results"
    # Execution configuration
    SLEEP_AFTER_EXECUTION = int(os.getenv("SLEEP_AFTER_EXECUTION", 2))
    MAX_STEPS = int(os.getenv("MAX_STEPS", 50))


# --- Process-level global variables ---
# Only the Env is global, Agent is local
worker_env = None
process_lock = None


def initialize_worker_resources():
    """
    Initialize only the environment (Env).
    Agent will be dynamically created per request based on parameters.
    """
    global worker_env, process_lock
    process_lock = asyncio.Lock()

    pid = os.getpid()
    logger.info(f"Initializing Environment for Worker PID: {pid}")

    try:
        # Initialize environment
        worker_env = OSWorldDesktopEnv(
            path_to_vm=ServiceConfig.PATH_TO_VM,
            action_space=ServiceConfig.ACTION_SPACE,
            provider_name=ServiceConfig.PROVIDER_NAME,
            region="us-east-1",
            snapshot_name=None,
            screen_size=(ServiceConfig.SCREEN_WIDTH, ServiceConfig.SCREEN_HEIGHT),
            headless=ServiceConfig.HEADLESS,
            os_type="Ubuntu",
            require_a11y_tree=ServiceConfig.OBSERVATION_TYPE in ["a11y_tree", "screenshot_a11y_tree", "som"],
            enable_proxy=True,
            proxy=os.environ["HTTP_PROXY"] if os.environ["HTTP_PROXY"] else ""
        )

        logger.info(f"Starting Environment for PID {pid}...")
        worker_env.start()
        logger.info(f"Environment Started for PID {pid}.")

    except Exception as e:
        logger.error(f"Failed to initialize env for worker {pid}: {e}", exc_info=True)
        raise e


def cleanup_worker_resources():
    global worker_env
    pid = os.getpid()
    if worker_env:
        try:
            logger.info(f"Closing Environment for PID {pid}...")
            worker_env.close()
        except Exception as e:
            logger.error(f"Error closing env for PID {pid}: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize Env when worker starts
    initialize_worker_resources()
    yield
    # Clean up Env when worker shuts down
    cleanup_worker_resources()


app = FastAPI(lifespan=lifespan)


def _create_agent_from_request(agent_config: Dict[str, Any]):
    """
    Factory function: Create Agent instance based on request parameters
    """
    # Get parameters from request, use defaults if not provided

    model_name = agent_config.get("model_name", "")
    if not model_name:
        raise Exception("Model name not provided!")

    base_url = agent_config.get("url", None)  # e.g., vllm address
    api_key = agent_config.get("api_key", None)  # If dynamic API key is needed

    model_infer_params = agent_config.get("model_infer_params", {})
    max_tokens = model_infer_params.get("max_tokens", ServiceConfig.DEFAULT_MAX_TOKENS)
    top_p = model_infer_params.get("top_p", ServiceConfig.DEFAULT_TOP_P)
    temperature = model_infer_params.get("temperature", ServiceConfig.DEFAULT_TEMPERATURE)

    logger.info(f"Creating Agent: {model_name} (Temp: {temperature})")

    # Note: If your Agent supports dynamic api_key, ensure the Agent constructor accepts it
    # or set the global Key in environment variables
    if any(keyword in model_name.lower() for keyword in ["qwen3-vl", "qwen3vl"]):
        agent = Qwen3VLAgent(
            model=model_name,
            base_url=base_url,
            max_tokens=max_tokens,
            top_p=top_p,
            temperature=temperature,
            history_n=8,
            action_space=ServiceConfig.ACTION_SPACE,
            coordinate_type="relative",
            add_thought_prefix=False
        )
    else:
        raise Exception(f"Model name {model_name} not supported")

    return agent


def _run_task_sync(request_data: Dict[str, Any], temp_dir: str) -> Dict[str, Any]:
    """
    Synchronous task execution logic
    """
    global worker_env
    assert isinstance(worker_env, OSWorldDesktopEnv)

    params = request_data["params"]
    task_id = params.get("task_id", "unknown")
    instruction = params.get("question", "")
    metadata = params.get("metadata", {})

    # 1. Dynamically create Agent
    try:
        agent = _create_agent_from_request(agent_config=request_data["llm_config"])
    except Exception as e:
        logger.error(f"[{task_id}] Failed to create agent: {e}")
        raise e

    # 2. Prepare configuration
    example_config = metadata.get("config", {})

    logger.info(f"[{task_id}] Processing in PID {os.getpid()}. Instruction: {instruction}")

    # 3. Reset environment and Agent

    # Agent Reset
    agent.reset()

    # Env Reset (pass task configuration)
    worker_env.reset(task_config=example_config)

    time.sleep(5)  # Wait for VM interface to stabilize

    obs = worker_env._get_obs()
    done = False
    step_idx = 0
    trajectory = []

    max_steps = int(request_data["service_env_params"]["max_steps"]) if request_data.get("service_env_params", {}).get(
        "max_steps", None) else ServiceConfig.MAX_STEPS
    try:
        while not done and step_idx < max_steps:
            # Agent prediction
            response, actions = agent.predict(
                instruction,
                obs
            )

            for action in actions:
                # Save screenshot
                img_name = f"step_{step_idx + 1}.png"
                screenshot_path = os.path.join(temp_dir, img_name)
                with open(screenshot_path, "wb") as _f:
                    _f.write(obs['screenshot'])

                logger.info(f"[{task_id}] Step {step_idx + 1}: {action}")

                # Execute action
                obs, _, done, _ = worker_env.step(action, ServiceConfig.SLEEP_AFTER_EXECUTION)

                trajectory.append({
                    "step": step_idx + 1,
                    "action": action,
                    "response": response,
                    "done": done
                })

                # Write to log
                with open(os.path.join(temp_dir, "traj.jsonl"), "a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "instruction": instruction,
                        "step_num": step_idx + 1,
                        "action": action,
                        "response": response,
                        "done": done,
                        "screenshot_file": img_name
                    }, ensure_ascii=False) + "\n")

                if done:
                    break

            step_idx += 1

        # Evaluate
        score = float(worker_env.evaluate())
        logger.info(f"[{task_id}] Finished. Score: {score}")

        return {
            "score": score,
            "trajectory": trajectory
        }

    except Exception as e:
        logger.error(f"[{task_id}] Execution failed: {e}", exc_info=True)
        raise e


@app.get("/health")
async def health():
    return {"status": "success"}


@app.post("/api/tasks")
async def execute_single_task(request: Request):
    """
    Wait mode interface
    """
    global process_lock
    try:
        # Get only core parameters
        request_data = await request.json()
        logger.info(f"\n\nRequest Body: {request_data}\n\n")
        task_id = request_data["params"].get("task_id", f"req_{int(time.time())}")

        # Use temporary directory
        temp_dir = os.path.join(ServiceConfig.TMP_ROOT_DIR,
                                f"osworld_{task_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        os.makedirs(temp_dir, exist_ok=True)

        # If current process is busy, new requests will wait here until lock is released
        logger.info(f"[{task_id}] Waiting for process lock in PID {os.getpid()}...")

        async with process_lock:
            logger.info(f"[{task_id}] Acquired lock. Starting execution...")

            # Only when lock is acquired, submit task to thread pool
            result_data = await run_in_threadpool(_run_task_sync, request_data, temp_dir)

        return {
            "status": "completed",
            "task_id": task_id,
            "result": {
                "final_answer": result_data["score"],
                "trajectory": result_data["trajectory"],
                "ground_truth": "placeholder",
                "metrics": {"score": result_data["score"]}
            }
        }

    except Exception as e:
        logger.error(f"API Error: {e}")
        return {
            "status": "failed",
            "error": str(e),
            "result": {
                "final_answer": 0.0,
                "ground_truth": "placeholder",
                "metrics": {"score": 0.0}
            }
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--path_to_vm",
        type=str,
        default="/nvme/yangbowen/osworld/docker_vm_data/Ubuntu.qcow2"
    )
    parser.add_argument(
        "--proxy",
        type=str,
        default="http://10.1.8.5"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9000
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1  # 4/8
    )
    args = parser.parse_args()

    ServiceConfig.PATH_TO_VM = args.path_to_vm
    os.environ["HTTP_PROXY"] = args.proxy
    os.environ["HTTPS_PROXY"] = args.proxy

    uvicorn.run("agentcompass_flask:app", host="0.0.0.0", port=args.port, workers=args.workers)