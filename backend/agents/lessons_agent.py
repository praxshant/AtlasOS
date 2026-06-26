import json
import logging
from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, END

from backend.vector.qdrant_client import qdrant_client
from backend.graph.neo4j_client import neo4j_client
from backend.utils.llm_client import structured_complete

logger = logging.getLogger(__name__)

# 1. State Definition
class LessonsState(TypedDict):
    topic: str
    tenant_id: str
    historical_incidents: List[Dict[str, Any]]
    graph_evidence: List[Dict[str, Any]]
    report: Dict[str, Any]

# 2. Node Functions

def retrieve_history_node(state: LessonsState) -> Dict[str, Any]:
    """
    Searches Qdrant for historical documents, incidents, and near-misses related to the topic, scoped to tenant.
    """
    topic = state["topic"]
    tenant_id = state.get("tenant_id")
    logger.info(f"[Lessons Agent] Searching Qdrant for history related to '{topic}'...")
    try:
        incidents = qdrant_client.similarity_search(
            "document_chunks", f"incident accident failure near-miss {topic}", 
            top_k=5, tenant_id=tenant_id
        )
        return {"historical_incidents": incidents}
    except Exception as e:
        logger.error(f"Failed historical incident retrieval: {e}")
        return {"historical_incidents": []}

def retrieve_graph_node(state: LessonsState) -> Dict[str, Any]:
    """
    Traverses Neo4j to find FailureModes, Incidents, and LessonsLearned nodes related to the topic, scoped to tenant.
    """
    topic = state["topic"]
    tenant_id = state.get("tenant_id")
    logger.info(f"[Lessons Agent] Traversing Neo4j for lessons linked to '{topic}'...")
    
    evidence = []
    tenant_filter = "AND i.tenant_id = $tenant_id" if tenant_id else ""
    
    try:
        # Match Incident nodes connected to Assets or FailureModes containing the topic
        query = f"""
        MATCH (i:Incident)-[r]-(n)
        WHERE ((i.description IS NOT NULL AND i.description CONTAINS $topic)
           OR (n.name IS NOT NULL AND n.name CONTAINS $topic))
           {tenant_filter}
        RETURN i.name as incident_name, i.description as description, 
               labels(n)[0] as connected_type, n.name as connected_name, type(r) as relationship
        LIMIT 10
        """
        params = {"topic": topic}
        if tenant_id:
            params["tenant_id"] = tenant_id
        evidence = neo4j_client.run_query(query, params)
    except Exception as e:
        logger.error(f"Failed Neo4j lessons retrieval: {e}")
        
    return {"graph_evidence": evidence}

def pattern_mining_node(state: LessonsState) -> Dict[str, Any]:
    """
    Analyzes historical incidents and graph evidence using the LLM to find recurring patterns and preventative recommendations.
    """
    topic = state["topic"]
    incidents = state["historical_incidents"]
    graph = state["graph_evidence"]
    
    logger.info("[Lessons Agent] Mining patterns and generating prevention strategies...")
    
    # Format collected evidence
    evidence_str = ""
    for idx, item in enumerate(incidents):
        evidence_str += f"- Chunk [{idx + 1}]: {item.get('text')} (Source: {item.get('metadata', {}).get('source_file')})\n"
        
    evidence_str += "\nGraph-related Incidents:\n"
    for item in graph:
        evidence_str += f"- Incident: {item.get('incident_name')} is connected to {item.get('connected_name')} ({item.get('connected_type')}) via {item.get('relationship')}\n"
        
    prompt = f"""
    You are a Director of Reliability Engineering and Safety Culture. Analyze the following operational logs and incident histories related to '{topic}'.
    
    Operational Logs & Graph Evidence:
    {evidence_str}
    
    Extract recurring incident patterns and compile a ranked list of preventative recommendations.
    
    Format your response strictly as a JSON object matching this schema:
    {{
      "patterns": [
        {{
          "description": "Short description of the recurring failure pattern",
          "frequency": "High/Medium/Low",
          "example_incidents": ["Ref to incident description or log index"],
          "prevention": "Direct engineering or procedural safeguard to prevent recurrence"
        }}
      ],
      "recommendations": [
        {{
          "rank": 1,
          "recommendation": "Detailed description of action plan",
          "evidence_refs": ["Ref to historical evidence"]
        }}
      ]
    }}
    
    Return the response strictly as JSON. No markdown wrappers or extra conversational text.
    """
    try:
        report_data = structured_complete(prompt)
        return {"report": report_data}
    except Exception as e:
        logger.error(f"Failed to mine lessons patterns: {e}")
        # Return fallback report
        fallback = {
            "patterns": [{"description": f"Failed pattern analysis for '{topic}': {e}", "frequency": "Low", "example_incidents": [], "prevention": "Review logs manually."}],
            "recommendations": [{"rank": 1, "recommendation": "Review historical records manually.", "evidence_refs": []}]
        }
        return {"report": fallback}

# 3. LangGraph Workflow Compilation
workflow = StateGraph(LessonsState)

workflow.add_node("retrieve_history", retrieve_history_node)
workflow.add_node("retrieve_graph", retrieve_graph_node)
workflow.add_node("pattern_mining", pattern_mining_node)

workflow.set_entry_point("retrieve_history")
workflow.add_edge("retrieve_history", "retrieve_graph")
workflow.add_edge("retrieve_graph", "pattern_mining")
workflow.add_edge("pattern_mining", END)

compiled_lessons_graph = workflow.compile()

class LessonsAgent:
    def run(self, topic: str, tenant_id: str = "default") -> Dict[str, Any]:
        initial_state = {
            "topic": topic,
            "tenant_id": tenant_id,
            "historical_incidents": [],
            "graph_evidence": [],
            "report": {}
        }
        final_state = compiled_lessons_graph.invoke(initial_state)
        return final_state.get("report", {})

lessons_agent = LessonsAgent()
