import os
import sys
import json
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from backend.agents.copilot_agent import copilot_agent

logging.basicConfig(level=logging.INFO)

def trace_query():
    query = "Why did C17 fail?"
    print(f"Tracing query: {query}")
    stream = copilot_agent.run_stream(query=query)
    
    for item in stream:
        if isinstance(item, dict):
            if item.get("type") == "stage":
                print(f"Stage: {item['stage']} -> {item['status']}")
            elif "citations" in item:
                print(f"Citations: {len(item['citations'])}")
            elif "graph" in item:
                print(f"Graph Nodes: {len(item['graph'].get('nodes', []))}")
        elif isinstance(item, str):
            sys.stdout.write(item)
    print("\nDone.")

if __name__ == "__main__":
    trace_query()
