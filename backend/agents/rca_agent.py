import json
import logging
from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, END

from backend.vector.qdrant_client import qdrant_client
from backend.graph.neo4j_client import neo4j_client
from backend.utils.llm_client import structured_complete

logger = logging.getLogger(__name__)

# 1. State Definition
class RCAState(TypedDict):
    incident_description: str
    tenant_id: str
    parsed_incident: Dict[str, Any]
    similar_incidents: List[Dict[str, Any]]
    maintenance_history: List[Dict[str, Any]]
    relevant_procedures: List[Dict[str, Any]]
    report: Dict[str, Any]

# 2. Node Functions

def parsing_node(state: RCAState) -> Dict[str, Any]:
    """
    Parses the incident text into key structural fields using LLM.
    """
    desc = state["incident_description"]
    logger.info(f"[RCA Agent] Parsing incident description: {desc[:60]}...")
    
    prompt = f"""
    Analyze the following industrial incident description and parse it into structured JSON.
    
    Incident Description:
    "{desc}"
    
    Identify:
    - asset: The specific equipment or asset identifier (e.g., "Pump P-104", "Valve V-12").
    - failure_mode: The physical mechanism of failure (e.g., "seal leak", "bearing wear", "overpressure").
    - date: The date of the incident if mentioned.
    - severity: Estimated severity level (e.g., "Low", "Medium", "High", "Critical").
    
    Return response strictly as JSON with keys: "asset", "failure_mode", "date", "severity". No markdown formatting.
    """
    try:
        parsed = structured_complete(prompt)
        logger.info(f"[RCA Agent] Parsed incident details: {parsed}")
        return {"parsed_incident": parsed}
    except Exception as e:
        logger.error(f"Failed parsing incident: {e}")
        # Default parse
        return {"parsed_incident": {"asset": "Unknown", "failure_mode": "Unknown", "date": "Unknown", "severity": "Medium"}}

def retrieve_incidents_node(state: RCAState) -> Dict[str, Any]:
    """
    Retrieves historically similar incidents from Qdrant, scoped to tenant.
    """
    desc = state["incident_description"]
    tenant_id = state.get("tenant_id")
    logger.info("[RCA Agent] Retrieving similar incidents from Qdrant...")
    try:
        similar = qdrant_client.similarity_search("document_chunks", desc, top_k=3, tenant_id=tenant_id)
        return {"similar_incidents": similar}
    except Exception as e:
        logger.error(f"Failed retrieving similar incidents: {e}")
        return {"similar_incidents": []}

def retrieve_history_node(state: RCAState) -> Dict[str, Any]:
    """
    Traverses Neo4j to find maintenance logs, failure modes, and related items for the asset, scoped to tenant.
    """
    parsed = state["parsed_incident"]
    tenant_id = state.get("tenant_id")
    asset_name = parsed.get("asset", "Unknown")
    logger.info(f"[RCA Agent] Querying maintenance logs for {asset_name} in Neo4j...")
    
    history = []
    if asset_name and asset_name != "Unknown":
        try:
            tenant_filter = "AND a.tenant_id = $tenant_id" if tenant_id else ""
            query = f"""
            MATCH (a {{name: $asset_name}})-[r]-(m)
            WHERE true {tenant_filter}
            RETURN m.name as entity, labels(m)[0] as type, type(r) as relationship
            LIMIT 15
            """
            params = {"asset_name": asset_name}
            if tenant_id:
                params["tenant_id"] = tenant_id
            history = neo4j_client.run_query(query, params)
            logger.info(f"[RCA Agent] Found {len(history)} related records in Neo4j.")
        except Exception as e:
            logger.error(f"Failed Neo4j history lookup: {e}")
    return {"maintenance_history": history}

def retrieve_procedures_node(state: RCAState) -> Dict[str, Any]:
    """
    Searches for related safety procedures or regulations, scoped to tenant.
    """
    parsed = state["parsed_incident"]
    tenant_id = state.get("tenant_id")
    failure_mode = parsed.get("failure_mode", "")
    logger.info(f"[RCA Agent] Searching Neo4j for procedures related to failure mode: {failure_mode}...")
    
    procedures = []
    tenant_filter = "AND p.tenant_id = $tenant_id" if tenant_id else ""
    
    try:
        # Match Regulations/Procedures connected to failure mode or asset
        query = f"""
        MATCH (fm:FailureMode {{name: $failure_mode}})-[r]-(p:Procedure)
        WHERE true {tenant_filter}
        RETURN p.name as name, p.description as description
        LIMIT 5
        """
        params = {"failure_mode": failure_mode}
        if tenant_id:
            params["tenant_id"] = tenant_id
        procedures = neo4j_client.run_query(query, params)
        
        # If empty, do a broader search
        if not procedures:
            query_broad = f"""
            MATCH (p:Procedure)
            WHERE ((p.name IS NOT NULL AND p.name CONTAINS $fm)
               OR (p.description IS NOT NULL AND p.description CONTAINS $fm))
               {tenant_filter}
            RETURN p.name as name, p.description as description
            LIMIT 5
            """
            params_broad = {"fm": failure_mode}
            if tenant_id:
                params_broad["tenant_id"] = tenant_id
            procedures = neo4j_client.run_query(query_broad, params_broad)
    except Exception as e:
        logger.error(f"Failed procedure search: {e}")
        
    # Fallback to general safety regulations if Neo4j contains no regulation nodes yet
    if not procedures:
        procedures = [
            {"name": "OISD-105 Work Permit System", "requirement": "Ensure hot work permit is signed off by safety officer and gas test is conducted prior to ignition.", "code": "OISD-105"},
            {"name": "Factory Act Section 36", "requirement": "Requires safety guards, regular inspection of pressure vessels, and hydrostatic testing every 2 years.", "code": "FA-36"},
            {"name": "PESO Gas Cylinder Rules", "requirement": "Cylinders containing compressed gas must be stored in well-ventilated sheds, chained, and kept away from electrical switchboards.", "code": "PESO-GCR"}
        ]
        
    logger.info(f"[RCA Agent] Identified {len(procedures)} applicable regulations.")
    return {"relevant_procedures": procedures}

def synthesis_node(state: RCAState) -> Dict[str, Any]:
    """
    Assembles evidence from Qdrant and Neo4j and calls LLM to generate the cause tree.
    """
    desc = state["incident_description"]
    parsed = state["parsed_incident"]
    similar = state["similar_incidents"]
    history = state["maintenance_history"]
    procedures = state["relevant_procedures"]
    
    logger.info("[RCA Agent] Synthesizing evidence to generate RCA report...")
    
    # Format evidence block
    evidence_str = f"Incident details: {json.dumps(parsed)}\n\n"
    
    evidence_str += "Similar historical incidents:\n"
    for idx, item in enumerate(similar):
        evidence_str += f"- [{idx + 1}] {item.get('text')} (Doc: {item.get('metadata', {}).get('source_file')})\n"
        
    evidence_str += "\nAsset Operations History (from Graph):\n"
    for item in history:
        evidence_str += f"- Connected node: {item['entity']} ({item['type']}) via relationship {item['relationship']}\n"
        
    evidence_str += "\nSafety Procedures & Regulations:\n"
    for p in procedures:
        evidence_str += f"- {p.get('name')}: {p.get('description', p.get('requirement', ''))}\n"
        
    prompt = f"""
    You are a principal Reliability & Process Safety Engineer. Perform a Root Cause Analysis (RCA) on the following incident.
    
    Incident:
    "{desc}"
    
    Evidence collected:
    {evidence_str}
    
    Your task is to analyze this data and generate a JSON Root Cause Analysis report matching this schema:
    {{
      "summary": "High-level summary of the incident, direct cause, and recommendations.",
      "probable_causes": [
        {{
          "cause": "Specific failure or physical mechanism",
          "confidence": 0.85,
          "evidence_refs": ["Ref to similar incident or history log"]
        }}
      ],
      "cause_tree": {{
        "name": "Incident Name",
        "children": [
          {{
            "name": "Direct Cause",
            "children": [
              {{ "name": "Contributing Factor" }},
              {{ "name": "Root Cause" }}
            ]
          }}
        ]
      }},
      "confidence_score": 0.75
    }}
    
    Return the response strictly as a JSON block. Avoid any conversational text or markdown wrappers.
    """
    try:
        report_data = structured_complete(prompt)
        
        # Add citations source documents
        cited_docs = list(set([item.get('metadata', {}).get('source_file') for item in similar if item.get('metadata', {}).get('source_file')]))
        report_data["cited_docs"] = cited_docs
        
        return {"report": report_data}
    except Exception as e:
        logger.error(f"Failed to synthesize RCA report: {e}")
        # Return fallback report structure
        fallback = {
            "summary": f"Failed to run automated RCA due to error: {e}. Standard inspection of asset {parsed.get('asset')} recommended.",
            "probable_causes": [{"cause": "Unresolved engine error", "confidence": 0.5, "evidence_refs": []}],
            "cause_tree": {"name": "Incident", "children": [{"name": f"Asset: {parsed.get('asset')}"}, {"name": f"Failure: {parsed.get('failure_mode')}"}]},
            "confidence_score": 0.2,
            "cited_docs": []
        }
        return {"report": fallback}

# 3. LangGraph Workflow Compilation
workflow = StateGraph(RCAState)

workflow.add_node("parsing", parsing_node)
workflow.add_node("retrieve_incidents", retrieve_incidents_node)
workflow.add_node("retrieve_history", retrieve_history_node)
workflow.add_node("retrieve_procedures", retrieve_procedures_node)
workflow.add_node("synthesis", synthesis_node)

workflow.set_entry_point("parsing")
workflow.add_edge("parsing", "retrieve_incidents")
workflow.add_edge("parsing", "retrieve_history")
workflow.add_edge("parsing", "retrieve_procedures")
workflow.add_edge("retrieve_incidents", "synthesis")
workflow.add_edge("retrieve_history", "synthesis")
workflow.add_edge("retrieve_procedures", "synthesis")
workflow.add_edge("synthesis", END)

compiled_rca_graph = workflow.compile()

class RCARagent:
    def run(self, incident_description: str, tenant_id: str = "default") -> Dict[str, Any]:
        initial_state = {
            "incident_description": incident_description,
            "tenant_id": tenant_id,
            "parsed_incident": {},
            "similar_incidents": [],
            "maintenance_history": [],
            "relevant_procedures": [],
            "report": {}
        }
        final_state = compiled_rca_graph.invoke(initial_state)
        return final_state.get("report", {})

rca_agent = RCARagent()
