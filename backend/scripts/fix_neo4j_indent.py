import os
import re

file_path = r"c:\Users\ACER\OneDrive\Desktop\AtlasOS\backend\graph\neo4j_client.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# We want to move everything below `neo4j_client = Neo4jClient()` to just above it.
parts = content.split("neo4j_client = Neo4jClient()")
if len(parts) == 2 and "def get_dashboard_stats" in parts[1]:
    new_content = parts[0] + parts[1] + "\n\nneo4j_client = Neo4jClient()\n"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("Fixed neo4j_client.py")
else:
    print("Could not find the expected pattern.")

