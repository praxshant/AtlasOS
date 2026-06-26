import json
import logging
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
    retrieved_chunks: List[Dict[str, Any]]
    retrieved_graph: Dict[str, Any]
    answer: str
    citations: List[Dict[str, Any]]

# 2. Node Functions
def planning_node(state: CopilotState) -> Dict[str, Any]:
    """
    Analyzes the query and determines retrieval keywords and filters.
    """
    query = state["query"]
    logger.info(f"[Copilot Agent] Planning node for query: '{query}'")
    
    return {
        "planning_info": f"Plan: Parallel semantic search and KG entity retrieval for query '{query}'"
    }

def query_decomposition_node(state: CopilotState) -> Dict[str, Any]:
    """
    Decomposes complex queries into sub-queries for better retrieval coverage.
    Simple queries pass through unchanged.
    """
    from backend.config import get_settings
    settings = get_settings()
    
    if not settings.ENABLE_QUERY_DECOMPOSITION:
        return {"sub_queries": [state["query"]]}
    
    query = state["query"]
    
    # Simple heuristic: if query has conjunctions or multiple question words, decompose
    complexity_indicators = ["and", "who", "what", "when", "where", "which", "related to", "connected to"]
    word_count = len(query.split())
    has_complexity = any(indicator in query.lower() for indicator in complexity_indicators) and word_count > 8
    
    if not has_complexity:
        return {"sub_queries": [query]}
    
    # For complex queries, use LLM decomposition
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
    """
    Retrieves semantic text chunks from Qdrant vector database, scoped to tenant.
    Supports multiple sub-queries for broader coverage.
    """
    queries = state.get("sub_queries", [state["query"]])
    tenant_id = state.get("tenant_id")
    logger.info(f"[Copilot Agent] Retrieving semantic chunks from Qdrant for {len(queries)} queries...")
    
    all_chunks = []
    seen_ids = set()
    
    try:
        for q in queries:
            chunks = qdrant_client.similarity_search("document_chunks", q, top_k=5, tenant_id=tenant_id)
            for chunk in chunks:
                chunk_id = chunk.get("id")
                if chunk_id not in seen_ids:
                    seen_ids.add(chunk_id)
                    all_chunks.append(chunk)
        
        logger.info(f"[Copilot Agent] Found {len(all_chunks)} unique text chunks across {len(queries)} queries.")
        return {"retrieved_chunks": all_chunks}
    except Exception as e:
        logger.error(f"Vector search failed: {e}")
        return {"retrieved_chunks": []}

def retrieve_graph_node(state: CopilotState) -> Dict[str, Any]:
    """
    Retrieves entity and relationship paths from Neo4j knowledge graph using multi-hop traversal, scoped to tenant.
    """
    query = state["query"]
    tenant_id = state.get("tenant_id")
    logger.info(f"COPILOT QUERY: {query}")
    
    try:
        # Search for nodes mentioned in the query
        search_results = neo4j_client.fulltext_search(query, tenant_id=tenant_id)
        logger.info(f"GRAPH RESULT: {search_results}")
        
        # Also search sub-queries for better coverage
        sub_queries = state.get("sub_queries", [])
        for sq in sub_queries:
            if sq != query:
                sq_results = neo4j_client.fulltext_search(sq, tenant_id=tenant_id)
                search_results.extend(sq_results)
        
        # Extract unique names of matched entities as seeds
        start_names = []
        for node in search_results[:5]:
            name = node.get("name")
            if name and name not in start_names:
                start_names.append(name)
                
        if not start_names:
            return {"retrieved_graph": {"nodes": [], "edges": []}}
            
        from backend.config import get_settings
        settings = get_settings()
        
        # Retrieve multi-hop subgraph
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
    """
    Compiles final LLM prompt. In a batch run, saves the answer.
    """
    return {}

# --- Hybrid Ranking ---

def hybrid_rank(chunks: List[Dict[str, Any]], graph_nodes: List[Dict[str, Any]], 
                vector_weight: float = 0.6, graph_weight: float = 0.4) -> List[Dict[str, Any]]:
    """
    Merges and ranks results from vector search and graph retrieval into a unified scored list.
    """
    ranked = []
    
    # Score vector results
    for chunk in chunks:
        ranked.append({
            "type": "vector",
            "text": chunk.get("text", ""),
            "score": vector_weight * (chunk.get("score", 0.5)),
            "source": chunk.get("metadata", {}).get("source_file", "Unknown"),
            "page": chunk.get("page", 1),
            "doc_id": chunk.get("doc_id"),
            "raw_score": chunk.get("score", 0.5)
        })
    
    # Score graph nodes
    for node in graph_nodes:
        node_text = f"{node.get('name', '')} ({node.get('label', 'Entity')})"
        props = {k: v for k, v in node.items() if k not in ["name", "label", "score"]}
        if props:
            node_text += f" — {', '.join(f'{k}: {v}' for k, v in props.items())}"
        
        ranked.append({
            "type": "graph",
            "text": node_text,
            "score": graph_weight * node.get("score", 0.5),
            "source": "Knowledge Graph",
            "page": 0,
            "doc_id": None,
            "raw_score": node.get("score", 0.5)
        })
    
    # Sort by hybrid score descending
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked


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
        
        # 1. Execute the LangGraph to collect context
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
        
        # Run graph steps up to synthesis node
        state = compiled_copilot_graph.invoke(initial_state)
        
        chunks = state.get("retrieved_chunks", [])
        graph = state.get("retrieved_graph", {"nodes": [], "edges": []})
        
        # Apply hybrid ranking
        ranked_results = hybrid_rank(
            chunks, 
            graph.get("nodes", []),
            vector_weight=settings.VECTOR_WEIGHT,
            graph_weight=settings.GRAPH_WEIGHT
        )
        
        # Format citations
        citations = []
        for idx, chunk in enumerate(chunks):
            citation_item = {
                "id": idx + 1,
                "filename": chunk.get("metadata", {}).get("source_file", "Document"),
                "page": chunk.get("page", 1),
                "snippet": chunk.get("text", "")[:180] + "..."
            }
            citations.append(citation_item)
            
        # Send citations and graph evidence first
        logger.info("GRAPH CONTEXT SENT TO LLM")
        logger.info(json.dumps(graph, indent=2))
        
        yield {"citations": citations}
        yield {"graph": graph}
        
        # 2. Build the System Prompt & Context block
        context_text = "Retrieved Text Context:\n"
        for idx, chunk in enumerate(chunks):
            filename = chunk.get("metadata", {}).get("source_file", "Unknown")
            page = chunk.get("page", 1)
            context_text += f"[{idx + 1}] File: {filename} (Page {page}): {chunk.get('text')}\n\n"
            
        if graph.get("nodes"):
            context_text += "Retrieved Knowledge Graph Evidence:\n"
            context_text += "Nodes:\n"
            for node in graph.get("nodes", []):
                props_str = ", ".join([f"{k}: {v}" for k, v in node.items() if k not in ["name", "label"]])
                context_text += f"- {node['name']} ({node['label']}){f' [{props_str}]' if props_str else ''}\n"
            
            if graph.get("edges"):
                context_text += "Relationships:\n"
                for edge in graph.get("edges", []):
                    context_text += f"- ({edge['source']}) -[{edge['type']}]-> ({edge['target']})\n"
            context_text += "\n"

        # ── Knowledge Gap + Engineer Expertise Enrichment ─────────────────────
        # For each graph seed node we found, compute knowledge coverage and
        # engineer expertise so the LLM can surface these in its answer.
        seed_names = [n.get("name") for n in graph.get("nodes", []) if n.get("name")]

        # Knowledge Gap analysis for equipment/asset nodes
        gap_lines = []
        expert_lines = []
        for seed in seed_names[:5]:  # limit to avoid latency spikes
            node_label = next(
                (n.get("label", "") for n in graph.get("nodes", []) if n.get("name") == seed),
                ""
            )
            if node_label in ("Asset", "Equipment") or any(
                kw in seed.upper() for kw in ("PUMP", "REACTOR", "VALVE", "VESSEL", "TANK", "COMPRESSOR")
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
        # ──────────────────────────────────────────────────────────────────────

        system_prompt = (
            "You are ATLASOS Expert Copilot, a senior operations and safety adviser in industrial plants. "
            "Your task is to provide clear, accurate, and grounded answers using the provided context. "
            "You must cite your sources. Format citations in your text as [1], [2], etc., corresponding "
            "to the retrieved text context indices. If you use information from the knowledge graph, "
            "mention it explicitly (e.g., 'The knowledge graph shows that...'). "
            "If the retrieved context is insufficient to answer the query, state that you don't know "
            "rather than fabricating details."
        )
        
        # 3. Stream the LLM answer
        prompt = f"Operational History:\n{json.dumps(history or [])}\n\nUser Question: {query}\n\nContext:\n{context_text}"
        
        logger.info("=" * 80)
        logger.info("FINAL PROMPT")
        logger.info(prompt)
        logger.info("=" * 80)
        
        token_stream = stream_complete(prompt, system_prompt=system_prompt)
        for token in token_stream:
            yield token

copilot_agent = CopilotAgent()
