import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Ensure project root is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.graph.neo4j_client import Neo4jClient

class TestGraphRAG(unittest.TestCase):
    @patch('backend.graph.neo4j_client.GraphDatabase')
    def test_multihop_subgraph_parsing(self, mock_graph_database):
        # We want to mock neo4j session and run query results
        client = Neo4jClient()
        
        # Mock the driver and session
        mock_driver = MagicMock()
        mock_session = MagicMock()
        client._driver = mock_driver
        mock_driver.session.return_value.__enter__.return_value = mock_session
        
        # Mock records returned by session.run
        mock_node1 = MagicMock()
        mock_node1.get.return_value = "P-101"
        mock_node1.labels = ["Asset"]
        
        mock_node2 = MagicMock()
        mock_node2.get.return_value = "Reactor R-201"
        mock_node2.labels = ["Asset"]
        
        mock_relationship = MagicMock()
        mock_relationship.type = "CONNECTED_TO"
        mock_relationship.get.return_value = 0.95
        mock_relationship.nodes = [mock_node1, mock_node2]
        
        mock_path = MagicMock()
        mock_path.nodes = [mock_node1, mock_node2]
        mock_path.relationships = [mock_relationship]
        
        mock_record = {
            "path": mock_path
        }
        
        mock_session.run.return_value = [mock_record]
        
        # Execute
        result = client.get_multihop_subgraph(["P-101"], max_depth=3, limit=10)
        
        # Verify
        self.assertIn("nodes", result)
        self.assertIn("edges", result)
        
        # Check node parsing
        self.assertEqual(len(result["nodes"]), 2)
        node_names = [n["name"] for n in result["nodes"]]
        self.assertIn("P-101", node_names)
        self.assertIn("Reactor R-201", node_names)
        
        # Check node proximity scoring
        for node in result["nodes"]:
            if node["name"] == "P-101":
                self.assertEqual(node["score"], 1.0)
            elif node["name"] == "Reactor R-201":
                self.assertEqual(node["score"], 0.5)
                
        # Check relationship edge parsing and deduplication
        self.assertEqual(len(result["edges"]), 1)
        edge = result["edges"][0]
        self.assertEqual(edge["source"], "P-101")
        self.assertEqual(edge["target"], "Reactor R-201")
        self.assertEqual(edge["type"], "CONNECTED_TO")
        self.assertEqual(edge["confidence"], 0.95)

if __name__ == '__main__':
    unittest.main()
