#!/usr/bin/env python3
"""Remove a platform agent scaffold and its registry entry.

Usage:
    python scripts/agent/unregister_agent.py [agent_name]

Examples:
    python scripts/agent/unregister_agent.py               # interactive selection
    python scripts/agent/unregister_agent.py ichiba_app_marketplace
"""

import json
import re
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]
AGENTS_DIR = PROJECT_ROOT / "src" / "pr_assistant" / "agents"
REGISTRY = AGENTS_DIR / "registry.json"

CORE = {"core", "utils"}  # directories that are not agents


def list_registered_agents() -> list[str]:
    registry = json.loads(REGISTRY.read_text())
    names = []
    for entry in registry["agents"]:
        cls = entry.get("reviewer_class", "")
        # pr_assistant.agents.<name>.reviewer_agent.ClassName
        parts = cls.split(".")
        if len(parts) >= 3:
            names.append(parts[2])
    return names


def main():
    if len(sys.argv) > 2:
        print("Usage: python scripts/agent/unregister_agent.py [agent_name]")
        sys.exit(1)

    if len(sys.argv) == 2:
        agent_name = sys.argv[1].strip()
    else:
        agents = list_registered_agents()
        if not agents:
            sys.exit("No registered agents found in registry.json")
        print("Registered agents:")
        for i, name in enumerate(agents, 1):
            print(f"  {i}. {name}")
        choice = input("Select agent to unregister (number or name): ").strip()
        if choice.isdigit():
            idx = int(choice) - 1
            if idx < 0 or idx >= len(agents):
                sys.exit("Error: invalid selection")
            agent_name = agents[idx]
        else:
            agent_name = choice

    if not re.match(r'^[a-z][a-z0-9_]+$', agent_name):
        sys.exit("Error: agent_name must be lowercase snake_case")

    agent_dir = AGENTS_DIR / agent_name
    if not agent_dir.exists():
        sys.exit(f"Error: {agent_dir} does not exist")

    # Remove from registry.json
    registry = json.loads(REGISTRY.read_text())
    module_base = f"pr_assistant.agents.{agent_name}"
    before = len(registry["agents"])
    registry["agents"] = [
        e for e in registry["agents"]
        if not e.get("reviewer_class", "").startswith(module_base)
    ]
    if len(registry["agents"]) == before:
        print(f"Warning: no registry entry found for {agent_name}")
    else:
        REGISTRY.write_text(json.dumps(registry, indent=2) + "\n")
        print(f"Removed registry entry for {agent_name}")

    # Remove directory
    shutil.rmtree(agent_dir)
    print(f"Removed directory: src/pr_assistant/agents/{agent_name}/")


if __name__ == "__main__":
    main()
