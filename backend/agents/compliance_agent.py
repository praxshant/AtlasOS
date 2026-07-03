import json
import logging
from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, END

from backend.db.postgres import SessionLocal, Document, Chunk, Entity
from backend.graph.neo4j_client import neo4j_client
from backend.utils.llm_client import structured_complete
import re

logger = logging.getLogger(__name__)

REGULATION_REQUIREMENTS = {
    "OSHA 1910": [
        {"id": "osha-1", "text": "Must have pressure relief valves installed on all vessels."},
        {"id": "osha-2", "text": "Requires annual hydrostatic testing."}
    ],
    "ISO 13849": [
        {"id": "iso-1", "text": "Emergency stop buttons must be hardwired."},
        {"id": "iso-2", "text": "Control systems must fail to a safe state."}
    ]
}

def extract_clauses(text: str) -> List[str]:
    """Extract numbered clauses (e.g. '1.1', 'Section 2') or paragraphs."""
    clauses = re.split(r'\n(?=\d+\.\d+|\bSection\b)', text)
    return [c.strip() for c in clauses if len(c.strip()) > 20]

# 1. State Definition
class ComplianceState(TypedDict):
    document_id: int
    tenant_id: str
    regulation_scope: Optional[str]
    document_text: str
    document_entities: List[Dict[str, Any]]
    applicable_regulations: List[Dict[str, Any]]
    report: Dict[str, Any]

# 2. Node Functions

def load_document_context_node(state: ComplianceState) -> Dict[str, Any]:
    """
    Loads raw text and extracted entities of the target document from PostgreSQL, scoped to tenant.
    """
    doc_id = state["document_id"]
    tenant_id = state.get("tenant_id")
    logger.info(f"[Compliance Agent] Loading context for document ID {doc_id} from Postgres...")
    
    db = SessionLocal()
    try:
        # Load chunks to construct full text — filtered by tenant
        query = db.query(Chunk).filter(Chunk.document_id == doc_id)
        if tenant_id:
            query = query.filter(Chunk.tenant_id == tenant_id)
        chunks = query.order_by(Chunk.chunk_index).all()
        full_text = "\n".join([c.text_content for c in chunks])
        
        # Load entities — filtered by tenant
        entity_query = db.query(Entity).filter(Entity.source_doc_id == doc_id)
        if tenant_id:
            entity_query = entity_query.filter(Entity.tenant_id == tenant_id)
        entities = entity_query.all()
        entity_list = [{"name": e.canonical_name, "type": e.entity_type} for e in entities]
        
        return {
            "document_text": full_text[:4000], # Cap text size for context window
            "document_entities": entity_list
        }
    except Exception as e:
        logger.error(f"Failed to load document context: {e}")
        return {"document_text": "", "document_entities": []}
    finally:
        db.close()

def identify_regulations_node(state: ComplianceState) -> Dict[str, Any]:
    """
    Queries Neo4j for Regulation nodes linked to the document's entities or matching the scope, scoped to tenant.
    """
    entities = state["document_entities"]
    scope = state["regulation_scope"]
    tenant_id = state.get("tenant_id")
    logger.info("[Compliance Agent] Querying Neo4j for applicable regulations...")
    
    regulations = []
    entity_names = [e["name"] for e in entities]
    tenant_filter = "AND r.tenant_id = $tenant_id" if tenant_id else ""
    
    try:
        # 1. Query for regulations connected to document entities
        if entity_names:
            query = f"""
            MATCH (r:Regulation)-[rel]-(e)
            WHERE e.name IN $entity_names {tenant_filter}
            RETURN r.name as name, r.requirement as requirement, r.code as code
            LIMIT 10
            """
            params = {"entity_names": entity_names}
            if tenant_id:
                params["tenant_id"] = tenant_id
            regulations = neo4j_client.run_query(query, params)
            
        # 2. If no connected regulations, fetch all general regulations
        if not regulations:
            tenant_filter_node = "WHERE r.tenant_id = $tenant_id" if tenant_id else ""
            query_general = f"""
            MATCH (r:Regulation)
            {tenant_filter_node}
            RETURN r.name as name, r.requirement as requirement, r.code as code
            LIMIT 5
            """
            params_general = {}
            if tenant_id:
                params_general["tenant_id"] = tenant_id
            regulations = neo4j_client.run_query(query_general, params_general)
            
        # 3. Filter by scope if provided
        if scope and regulations:
            regulations = [r for r in regulations if scope.lower() in r.get("name", "").lower() or scope.lower() in r.get("code", "").lower()]
            
    except Exception as e:
        logger.error(f"Failed Neo4j regulation lookup: {e}")

    # Fallback to general safety regulations if Neo4j contains no regulation nodes yet
    if not regulations:
        regulations = [
            {"name": "OISD-105 Work Permit System", "requirement": "Ensure hot work permit is signed off by safety officer and gas test is conducted prior to ignition.", "code": "OISD-105"},
            {"name": "Factory Act Section 36", "requirement": "Requires safety guards, regular inspection of pressure vessels, and hydrostatic testing every 2 years.", "code": "FA-36"},
            {"name": "PESO Gas Cylinder Rules", "requirement": "Cylinders containing compressed gas must be stored in well-ventilated sheds, chained, and kept away from electrical switchboards.", "code": "PESO-GCR"}
        ]
        
    logger.info(f"[Compliance Agent] Identified {len(regulations)} applicable regulations.")
    return {"applicable_regulations": regulations}

def evaluate_compliance_node(state: ComplianceState) -> Dict[str, Any]:
    """
    Uses the LLM to check if the document content meets the regulation requirements.
    """
    text = state["document_text"]
    scope = state["regulation_scope"]
    regs = state["applicable_regulations"]
    logger.info("[Compliance Agent] Evaluating compliance and identifying gaps...")
    
    if not text:
        return {
            "report": {
                "compliance_score": 0,
                "compliant_count": 0,
                "gap_count": 1,
                "gaps": [{"regulation": "All", "requirement": "N/A", "finding": "Document is empty or has no text content.", "risk_level": "High", "recommendation": "Check document upload."}],
                "overall_risk": "High",
                "cited_docs": []
            }
        }
        
    clauses = extract_clauses(text)
    
    requirements = []
    if scope and scope in REGULATION_REQUIREMENTS:
        requirements = REGULATION_REQUIREMENTS[scope]
    else:
        for reqs in REGULATION_REQUIREMENTS.values():
            requirements.extend(reqs)
            
    for r in regs:
        requirements.append({"id": r.get("code", "REQ"), "text": r.get("requirement", r.get("description", ""))})
        
    prompt = f"""
    You are an industrial process safety and compliance auditor. Evaluate the following document clauses against the listed requirements.
    
    Requirements:
    {json.dumps(requirements, indent=2)}
    
    Document Clauses:
    {json.dumps(clauses, indent=2)}
    
    Perform compliance gap detection. For each requirement:
    1. Check if the document clauses satisfy the requirement (using clause-level keyword/semantic match).
    2. Identify any missing process, safety measures, or compliance records (gaps).
    3. Assign a risk level (Low, Medium, High).
    4. Provide specific recommendations to close the gaps.
    
    Generate a JSON report matching this structure:
    {{
      "compliance_score": 85,
      "compliant_count": 4,
      "gap_count": 1,
      "overall_risk": "Medium",
      "gaps": [
        {{
          "regulation": "Name of regulation",
          "requirement": "Description of regulation requirement",
          "finding": "Specific gap or non-compliance found in the document.",
          "risk_level": "High",
          "recommendation": "Clear instruction to fix the gap."
        }}
      ]
    }}
    
    Return the response strictly as JSON. No markdown wrappers.
    """
    try:
        report_data = structured_complete(prompt)
        return {"report": report_data}
    except Exception as e:
        logger.error(f"Failed to generate compliance report: {e}")
        # Return fallback report
        fallback = {
            "compliance_score": 0,
            "compliant_count": 0,
            "gap_count": 1,
            "gaps": [{"regulation": "Compliance Checker", "requirement": "Automated evaluation", "finding": f"Failed checking compliance: {e}", "risk_level": "Medium", "recommendation": "Conduct manual compliance review."}],
            "overall_risk": "Medium"
        }
        return {"report": fallback}

# 3. LangGraph Workflow Compilation
workflow = StateGraph(ComplianceState)

workflow.add_node("load_context", load_document_context_node)
workflow.add_node("identify_regulations", identify_regulations_node)
workflow.add_node("evaluate_compliance", evaluate_compliance_node)

workflow.set_entry_point("load_context")
workflow.add_edge("load_context", "identify_regulations")
workflow.add_edge("identify_regulations", "evaluate_compliance")
workflow.add_edge("evaluate_compliance", END)

compiled_compliance_graph = workflow.compile()

class ComplianceAgent:
    def run(self, document_id: int, regulation_scope: Optional[str] = None, tenant_id: str = "default") -> Dict[str, Any]:
        initial_state = {
            "document_id": document_id,
            "tenant_id": tenant_id,
            "regulation_scope": regulation_scope,
            "document_text": "",
            "document_entities": [],
            "applicable_regulations": [],
            "report": {}
        }
        
        # Load document from db to get filename for citation
        db = SessionLocal()
        doc_query = db.query(Document).filter(Document.id == document_id)
        if tenant_id:
            doc_query = doc_query.filter(Document.tenant_id == tenant_id)
        doc = doc_query.first()
        filename = doc.filename if doc else "Document"
        db.close()
        
        final_state = compiled_compliance_graph.invoke(initial_state)
        report = final_state.get("report", {})
        report["cited_docs"] = [filename]
        return report

compliance_agent = ComplianceAgent()
