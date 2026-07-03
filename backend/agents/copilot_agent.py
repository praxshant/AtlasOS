import json
import logging
import re
from typing import TypedDict, List, Dict, Any, Generator

from langgraph.graph import StateGraph, END

from backend.vector.qdrant_client import qdrant_client
from backend.graph.neo4j_client import neo4j_client
from backend.utils.llm_client import stream_complete

logger = logging.getLogger(__name__)

# 1. State Definition
class CopilotState(TypedDict):
    query: str
    tenant_id: str
    history: List[Dict[str, Any]]
    planning_info: str
    sub_queries: List[str]
    query_type: str
    equipment_ids: List[str]
    retrieved_chunks: List[Dict[str, Any]]
    retrieved_graph: Dict[str, Any]
    answer: str
    citations: List[Dict[str, Any]]

def classify_query(query: str) -> str:
    """Simple keyword classifier — no LLM call needed."""
    q = query.lower()
    if any(w in q for w in ["pump", "reactor", "compressor", "valve", "asset", "equipment"]):
        return "asset"
    if any(w in q for w in ["failure", "incident", "accident", "fault", "broke", "failed"]):
        return "incident"
    if any(w in q for w in ["sop", "procedure", "how to", "steps", "protocol"]):
        return "procedure"
    if any(w in q for w in ["regulation", "compliance", "iso", "osha", "requirement"]):
        return "compliance"
    if any(w in q for w in ["engineer", "who knows", "expert", "person", "staff"]):
        return "engineer"
    if any(w in q for w in ["gap", "missing", "risk", "coverage", "unknown"]):
        return "risk"
    return "general"

# 2. Node Functions
def planning_node(state: CopilotState) -> Dict[str, Any]:
    query = state["query"]
    query_type = classify_query(query)
    equipment_ids = re.findall(r'\b([A-Z]{1,3}-\d{2,4}[A-Z]?)\b', query)
    logger.info(f"[Copilot Agent] Planning node for query: '{query}'. Type: {query_type}")
    return {
        "planning_info": f"Plan: Parallel semantic search and KG entity retrieval for query '{query}'",
        "query_type": query_type,
        "equipment_ids": equipment_ids
    }

def query_decomposition_node(state: CopilotState) -> Dict[str, Any]:
    from backend.config import get_settings
    settings = get_settings()

    if not settings.ENABLE_QUERY_DECOMPOSITION:
        return {"sub_queries": [state["query"]]}

    query = state["query"]

    complexity_indicators = ["and", "who", "what", "when", "where", "which", "related to", "connected to"]
    word_count = len(query.split())
    has_complexity = any(indicator in query.lower() for indicator in complexity_indicators) and word_count > 8

    if not has_complexity:
        return {"sub_queries": [query]}

    try:
        from backend.utils.llm_client import structured_complete
        decompose_prompt = f"""
        Decompose this complex question into 2-3 simpler sub-questions that can be searched independently.
        
        Question: "{query}"
        
        Return JSON: {{"sub_queries": ["sub-question 1", "sub-question 2"]}}
        Keep each sub-question focused on a single entity or relationship.
        """
        result = structured_complete(decompose_prompt)
        sub_queries = result.get("sub_queries", [query])
        if not sub_queries:
            sub_queries = [query]
        logger.info(f"[Copilot Agent] Decomposed into {len(sub_queries)} sub-queries: {sub_queries}")
        return {"sub_queries": sub_queries}
    except Exception as e:
        logger.warning(f"Query decomposition failed, using original query: {e}")
        return {"sub_queries": [query]}

def retrieve_vector_node(state: CopilotState) -> Dict[str, Any]:
    queries = state.get("sub_queries", [state["query"]])
    tenant_id = state.get("tenant_id")
    query_type = state.get("query_type", "general")
    logger.info(f"[Copilot Agent] Retrieving semantic chunks from Qdrant for {len(queries)} queries...")

    all_chunks = []
    seen_ids = set()

    try:
        # Retrieve extra chunks to allow post-filtering without missing top-k
        for q in queries:
            chunks = qdrant_client.similarity_search("document_chunks", q, top_k=15, tenant_id=tenant_id)
            for chunk in chunks:
                section_type = chunk.get("metadata", {}).get("section_type", "general")
                
                # Apply Section Type Filtering
                if query_type == "incident" and section_type != "work_order":
                    continue
                elif query_type == "procedure" and section_type not in ["procedure", "warning"]:
                    continue
                elif query_type == "compliance" and section_type != "compliance":
                    continue

                chunk_id = chunk.get("id")
                if chunk_id not in seen_ids:
                    seen_ids.add(chunk_id)
                    all_chunks.append(chunk)

        # Sort and take top 8 after filtering
        all_chunks = sorted(all_chunks, key=lambda x: x.get("score", 0), reverse=True)[:8]

        logger.info(f"[Copilot Agent] Found {len(all_chunks)} unique text chunks across {len(queries)} queries.")
        return {"retrieved_chunks": all_chunks}
    except Exception as e:
        logger.error(f"Vector search failed: {e}")
        return {"retrieved_chunks": []}

def _extract_keywords(query: str) -> List[str]:
    """
    Extracts meaningful keywords from a query for fallback graph search.
    Strips stopwords and returns individual tokens of length > 3.
    """
    stopwords = {
        "show", "list", "find", "what", "which", "where", "when", "how", "does", "the",
        "all", "are", "is", "for", "and", "or", "with", "about", "have", "that", "this",
        "from", "any", "has", "was", "were", "been", "its", "their", "your", "our"
    }
    tokens = re.findall(r'[A-Za-z0-9][A-Za-z0-9\-]*', query)
    keywords = [t for t in tokens if len(t) > 3 and t.lower() not in stopwords]
    # Also preserve things like "P-101", "R-201" as single tokens
    return list(dict.fromkeys(keywords))  # deduplicate preserving order

def retrieve_graph_node(state: CopilotState) -> Dict[str, Any]:
    query = state["query"]
    tenant_id = state.get("tenant_id")
    logger.info(f"COPILOT QUERY: {query}")

    try:
        # Primary: fulltext search on full query
        search_results = neo4j_client.fulltext_search(query, tenant_id=tenant_id)
        logger.info(f"GRAPH RESULT (full query): {len(search_results)} hits")

        # Also search sub-queries
        sub_queries = state.get("sub_queries", [])
        for sq in sub_queries:
            if sq != query:
                sq_results = neo4j_client.fulltext_search(sq, tenant_id=tenant_id)
                search_results.extend(sq_results)

        # Fallback: keyword-level search if full query returned nothing
        if not search_results:
            keywords = _extract_keywords(query)
            logger.info(f"Full-query search returned nothing. Trying keyword fallback: {keywords}")
            for kw in keywords[:5]:
                kw_results = neo4j_client.fulltext_search(kw, tenant_id=tenant_id)
                search_results.extend(kw_results)
                if len(search_results) >= 5:
                    break

        # Extract unique seed names, also adding equipment_ids from query
        start_names = []
        for eq in state.get("equipment_ids", []):
            if eq not in start_names:
                start_names.append(eq)
                
        for node in search_results[:5]:
            name = node.get("name")
            if name and name not in start_names:
                start_names.append(name)

        if not start_names:
            logger.info("[Copilot Agent] No graph seed nodes found.")
            return {"retrieved_graph": {"nodes": [], "edges": []}}

        from backend.config import get_settings
        settings = get_settings()

        retrieved_graph = neo4j_client.get_multihop_subgraph(
            start_names=start_names,
            max_depth=settings.NEO4J_MAX_DEPTH,
            limit=settings.NEO4J_MAX_PATH_LIMIT,
            tenant_id=tenant_id
        )
        logger.info(f"[Copilot Agent] Retrieved multihop subgraph: {len(retrieved_graph['nodes'])} nodes, {len(retrieved_graph['edges'])} edges")
        return {"retrieved_graph": retrieved_graph}

    except Exception as e:
        logger.error(f"Graph traversal failed: {e}")
        return {"retrieved_graph": {"nodes": [], "edges": []}}

def synthesis_node(state: CopilotState) -> Dict[str, Any]:
    return {}

# --- Hybrid Ranking ---

def keyword_overlap_score(query: str, chunk_text: str) -> float:
    """
    Simple keyword overlap without external libraries.
    """
    query_words = set(re.findall(r'\b\w{3,}\b', query.lower()))
    chunk_words = set(re.findall(r'\b\w{3,}\b', chunk_text.lower()))

    if not query_words:
        return 0.0
    intersection = query_words & chunk_words
    return len(intersection) / len(query_words)

def hybrid_rank(chunks: List[Dict[str, Any]], graph_nodes: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    ranked = []

    for chunk in chunks:
        chunk_text = chunk.get("text", "")
        k_score = keyword_overlap_score(query, chunk_text)
        vector_score = chunk.get("score", 0.5)
        
        final_score = 0.45 * vector_score + 0.30 * k_score
        
        ranked.append({
            "type": "vector",
            "text": chunk_text,
            "score": final_score,
            "source": chunk.get("metadata", {}).get("source_file", "Unknown"),
            "page": chunk.get("page", 1),
            "doc_id": chunk.get("doc_id"),
            "raw_score": vector_score
        })

    for node in graph_nodes:
        node_text = f"{node.get('name', '')} ({node.get('label', 'Entity')})"
        props = {k: v for k, v in node.items() if k not in ["name", "label", "score"]}
        if props:
            node_text += f" — {', '.join(f'{k}: {v}' for k, v in props.items())}"

        graph_proximity = node.get("score", 0.5)
        final_score = 0.25 * graph_proximity
        
        ranked.append({
            "type": "graph",
            "text": node_text,
            "score": final_score,
            "source": "Knowledge Graph",
            "page": 0,
            "doc_id": None,
            "raw_score": graph_proximity
        })

    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked[:8]


# 3. LangGraph Workflow compilation
workflow = StateGraph(CopilotState)

workflow.add_node("planning", planning_node)
workflow.add_node("decompose_query", query_decomposition_node)
workflow.add_node("retrieve_vector", retrieve_vector_node)
workflow.add_node("retrieve_graph", retrieve_graph_node)
workflow.add_node("synthesis", synthesis_node)

workflow.set_entry_point("planning")
workflow.add_edge("planning", "decompose_query")
workflow.add_edge("decompose_query", "retrieve_vector")
workflow.add_edge("decompose_query", "retrieve_graph")
workflow.add_edge("retrieve_vector", "synthesis")
workflow.add_edge("retrieve_graph", "synthesis")
workflow.add_edge("synthesis", END)

compiled_copilot_graph = workflow.compile()


class CopilotAgent:
    def run_stream(self, query: str, history: List[Dict[str, Any]] = None, tenant_id: str = "default") -> Generator[Any, None, None]:
        """
        Runs the retrieval nodes to assemble context, and streams the LLM synthesis.
        Yields tokens, citations, and graph evidence. Scoped to tenant.
        """
        from backend.config import get_settings
        settings = get_settings()

        initial_state = {
            "query": query,
            "tenant_id": tenant_id,
            "history": history or [],
            "planning_info": "",
            "sub_queries": [],
            "retrieved_chunks": [],
            "retrieved_graph": {"nodes": [], "edges": []},
            "answer": "",
            "citations": []
        }

        # Execute nodes and stream stage events
        yield {"type": "stage", "stage": "vector_search", "status": "running"}
        initial_state.update(planning_node(initial_state))
        initial_state.update(query_decomposition_node(initial_state))
        initial_state.update(retrieve_vector_node(initial_state))

        chunks = initial_state.get("retrieved_chunks", [])
        yield {"type": "stage", "stage": "vector_search", "status": "done", "count": len(chunks)}

        yield {"type": "stage", "stage": "graph_search", "status": "running"}
        initial_state.update(retrieve_graph_node(initial_state))
        graph = initial_state.get("retrieved_graph", {"nodes": [], "edges": []})
        yield {"type": "stage", "stage": "graph_search", "status": "done", "count": len(graph.get("nodes", []))}

        # -----------------------------------------------------------------
        # EMPTY CONTEXT GUARD: If both Qdrant and Neo4j return nothing,
        # stream a helpful message rather than passing an empty prompt to the LLM.
        # -----------------------------------------------------------------
        has_vector_context = len(chunks) > 0
        has_graph_context = len(graph.get("nodes", [])) > 0

        if not has_vector_context and not has_graph_context:
            logger.warning("[Copilot Agent] No context found in Qdrant or Neo4j. Streaming empty-state message.")
            yield {"citations": []}
            yield {"graph": {"nodes": [], "edges": []}}
            yield {"type": "stage", "stage": "generating", "status": "running"}
            empty_message = "No industrial knowledge has been indexed yet. Upload documents first."
            for word in empty_message.split(" "):
                yield {"type": "token", "content": word + " "}
            return

        # Apply hybrid ranking
        ranked_results = hybrid_rank(
            chunks,
            graph.get("nodes", []),
            query
        )

        # Format citations
        citations = []
        for idx, item in enumerate(ranked_results):
            if item["type"] == "vector":
                citation_item = {
                    "id": idx + 1,
                    "filename": item.get("source", "Document"),
                    "page": item.get("page", 1),
                    "snippet": item.get("text", "")[:180] + "..."
                }
                citations.append(citation_item)

        logger.info("GRAPH CONTEXT SENT TO LLM")
        logger.info(json.dumps(graph, indent=2))

        # Yield SSE metadata
        metadata_event = {
            "type": "retrieval_metadata",
            "query_type": initial_state.get("query_type", "general"),
            "qdrant_results_count": len(chunks),
            "graph_nodes_found": len(graph.get("nodes", [])),
            "equipment_ids_detected": initial_state.get("equipment_ids", []),
            "top_evidence_count": len(ranked_results)
        }
        yield metadata_event

        yield {"citations": citations}
        yield {"graph": graph}

        # 2. Build the System Prompt & Context block
        context_text = ""

        if has_vector_context:
            context_text += "Retrieved Text Context:\n"
            for idx, item in enumerate(ranked_results):
                if item["type"] == "vector":
                    filename = item.get("source", "Unknown")
                    page = item.get("page", 1)
                    context_text += f"[{idx + 1}] File: {filename} (Page {page}): {item.get('text')}\n\n"

        if has_graph_context:
            context_text += "Retrieved Knowledge Graph Evidence:\n"
            context_text += "Nodes:\n"
            for item in ranked_results:
                if item["type"] == "graph":
                    context_text += f"- {item['text']}\n"

            if graph.get("edges"):
                context_text += "Relationships:\n"
                for edge in graph.get("edges", []):
                    context_text += f"- ({edge['source']}) -[{edge['type']}]-> ({edge['target']})\n"
            context_text += "\n"

        # Knowledge Gap + Engineer Expertise Enrichment
        seed_names = [n.get("name") for n in graph.get("nodes", []) if n.get("name")]

        gap_lines = []
        expert_lines = []
        for seed in seed_names[:5]:
            node_label = next(
                (n.get("label", "") for n in graph.get("nodes", []) if n.get("name") == seed),
                ""
            )
            if node_label in ("Asset", "Equipment") or any(
                kw in seed.upper() for kw in ("PUMP", "REACTOR", "VALVE", "VESSEL", "TANK", "COMPRESSOR", "BOILER")
            ):
                try:
                    gap = neo4j_client.compute_knowledge_gaps(seed, tenant_id=tenant_id)
                    gap_lines.append(
                        f"- {seed}: {gap['coverage_pct']}% coverage  "
                        f"| Missing: {', '.join(gap['missing']) if gap['missing'] else 'None'}"
                    )
                except Exception as _ge:
                    logger.debug(f"Gap analysis skipped for {seed}: {_ge}")
            elif node_label == "Person":
                try:
                    exp = neo4j_client.get_engineer_expertise(seed, tenant_id=tenant_id)
                    expert_lines.append(
                        f"- {seed}: expertise_score={exp['expertise_score']}/100  "
                        f"| equipment={exp['equipment_touched']}"
                    )
                except Exception as _ee:
                    logger.debug(f"Expertise analysis skipped for {seed}: {_ee}")

        if gap_lines:
            context_text += "Knowledge Coverage Analysis:\n" + "\n".join(gap_lines) + "\n\n"
        if expert_lines:
            context_text += "Engineer Expertise Analysis:\n" + "\n".join(expert_lines) + "\n\n"

        # ---- ALWAYS STRUCTURED OUTPUT ----
        # Return a structured JSON with judge-friendly sections for every query.
        STRUCTURED_SCHEMA = """{
  "mode": "structured",
  "summary": "One-sentence plain-language answer to the question",
  "likely_cause": "Root cause if applicable (null if not a failure/RCA question)",
  "evidence": [
    {"source": "filename.pdf", "page": 1, "excerpt": "Relevant quote from document"}
  ],
  "graph_evidence": [
    {"entity": "C-17", "type": "Equipment", "relationship": "AFFECTED_BY", "connected_to": "Bearing Failure 2025"}
  ],
  "recommendations": [
    "Actionable recommendation 1",
    "Actionable recommendation 2"
  ],
  "confidence": 85,
  "sources": ["filename1.pdf", "filename2.txt"]
}"""

        query_type_instructions = {
            "asset": "Structure your response as an asset intelligence card with: asset name, protection devices, evidence, confidence score, related assets, and maintenance recommendation.",
            "incident": "Structure your response with: incident summary, root cause chain, evidence sources, similar incidents if known, and corrective actions.",
            "procedure": "List the procedure steps clearly. Cite the specific SOP document and section for each step.",
            "compliance": "Identify the specific regulation clause, the compliance status, any gaps found, and recommended actions.",
            "engineer": "Summarize the engineer's knowledge areas, assets they own, and succession risk level.",
            "risk": "List knowledge gaps by priority. For each gap, explain the risk it creates and what document is needed.",
            "general": ""
        }
        query_type = initial_state.get("query_type", "general")
        type_instruction = query_type_instructions.get(query_type, "")

        system_prompt = f"""You are ATLASOS Expert Copilot, a senior operations and safety adviser for industrial plants.
You have access to retrieved documents and knowledge graph data.

MANDATORY RESPONSE FORMAT:
Return ONLY a JSON object following this exact schema. No markdown wrappers. No extra text.
{STRUCTURED_SCHEMA}

RULES:
- summary: direct one-sentence answer to the user's question
- likely_cause: fill if the question is about a failure, incident, or problem; otherwise null
- evidence: up to 5 items, each grounded in the retrieved text context
- graph_evidence: up to 5 items from the knowledge graph nodes/relationships
- recommendations: 2-4 specific, actionable next steps
- confidence: integer 0-100 based on how well the context answers the question
- sources: list of unique filenames cited
- If information is not in context, lower confidence and say so in summary. NEVER fabricate.
- Every claim MUST be grounded in the retrieved context below.

{type_instruction}"""

        # 3. Stream the LLM answer
        prompt = f"Operational History:\n{json.dumps(history or [])}\n\nUser Question: {query}\n\nContext:\n{context_text}"

        logger.info("=" * 80)
        logger.info("FINAL PROMPT")
        logger.info(prompt)
        logger.info("=" * 80)

        yield {"type": "stage", "stage": "generating", "status": "running"}
        token_stream = stream_complete(prompt, system_prompt=system_prompt)
        for token in token_stream:
            yield token

copilot_agent = CopilotAgent()

