from typing import Set

# The strict ontology of allowed relationship types for V2.
VALID_RELATIONSHIPS: Set[str] = {
    "AFFECTED_BY",
    "APPLIES_TO",
    "ASSIGNED_TO",
    "AUTHORED_BY",
    "BELONGS_TO",
    "CAUSED_BY",
    "CAUSES",
    "COMMANDS",
    "COMPLIES_WITH",
    "CONNECTED_TO",
    "DEPENDS_ON",
    "DESIGNED",
    "DETECTS",
    "DOCUMENTED_BY",
    "DOCUMENTED_IN",
    "EMPLOYS",
    "FAILED_AT",
    "FEEDS",
    "FOLLOWS",
    "FUNDED_BY",
    "GOVERNED_BY",
    "GOVERNS",
    "HAS_KNOWLEDGE_GAP",
    "HAS_PROCEDURE",
    "INSPECTED_BY",
    "INSPECTS",
    "INTERCEPTS",
    "INVESTIGATED",
    "INVESTIGATED_BY",
    "INVOLVED_IN",
    "KNOWLEDGE_OWNER",
    "LEARNED_FROM",
    "LOCATED_AT",
    "MAINTAINED_BY",
    "MAINTAINS",
    "MANAGES",
    "OCCURRED_ON",
    "OPERATED_BY",
    "OPERATES",
    "OWNS",
    "PART_OF",
    "PERFORMED_ON",
    "PREVENTS",
    "REFERENCES",
    "RELATED_TO",
    "REPORTED_BY",
    "REPORTS",
    "RESPONSE_TO",
    "RESPONSIBLE_FOR",
    "RESULTED_IN",
    "SUPPLIES",
    "TESTED_IN",
    "TRACKS",
    "VIOLATES"
}

# Alias table: maps common LLM synonyms / near-misses to the canonical ontology type.
# Add entries here whenever the extractor emits a type that isn't in VALID_RELATIONSHIPS.
RELATIONSHIP_ALIASES: dict[str, str] = {
    "RELATED": "RELATED_TO",
    "ASSOCIATED_WITH": "RELATED_TO",
    "ASSOCIATED": "RELATED_TO",
    "LINKED_TO": "RELATED_TO",
    "HAS_PART": "PART_OF",
    "IS_PART_OF": "PART_OF",
    "CONTAINS": "PART_OF",
    "WORKS_WITH": "RESPONSIBLE_FOR",
    "COLLABORATED_WITH": "RESPONSIBLE_FOR",
    "AUTHORED": "AUTHORED_BY",
    "WRITTEN_BY": "AUTHORED_BY",
    "CREATED_BY": "AUTHORED_BY",
    "CAUSED": "CAUSES",
    "LED_TO": "RESULTED_IN",
    "RESULTS_IN": "RESULTED_IN",
    "DEPENDS": "DEPENDS_ON",
    "REQUIRED_BY": "DEPENDS_ON",
    "MAINTAINED": "MAINTAINS",
    "MANAGED_BY": "MAINTAINS",
    "OWNED_BY": "OWNS",
    "BELONGS": "BELONGS_TO",
    "LOCATED": "LOCATED_AT",
    "SITUATED_AT": "LOCATED_AT",
    "WORKS_FOR": "EMPLOYS",
    "EMPLOYED_BY": "EMPLOYS",
    "INSPECTED": "INSPECTED_BY",
    "REPORTED": "REPORTED_BY",
    "MANAGED": "MANAGES",
    "OPERATED": "OPERATES",
    "CONNECTED": "CONNECTED_TO",
    "LINKED": "CONNECTED_TO",
    "AFFECTS": "AFFECTED_BY",
    "VIOLATED": "VIOLATES",
    "COMPLIANT_WITH": "COMPLIES_WITH",
    "GOVERNED": "GOVERNED_BY",
    "FOLLOWED": "FOLLOWS",
}

def normalize_relationship(rel_type: str) -> str:
    """
    Normalizes a relationship string to match the ontology.
    1. Exact match against VALID_RELATIONSHIPS.
    2. Alias lookup for common LLM synonyms.
    3. Falls back to RELATED_TO (not UNKNOWN_RELATIONSHIP) so real edges are never junk.
    UNKNOWN_RELATIONSHIP is reserved for the extractor prompt's explicit "I don't know" signal.
    """
    if not rel_type:
        return "RELATED_TO"

    normalized = rel_type.upper().replace(" ", "_").strip()

    if normalized in VALID_RELATIONSHIPS:
        return normalized

    # Alias lookup
    alias = RELATIONSHIP_ALIASES.get(normalized)
    if alias:
        return alias

    # Safe default — never expose UNKNOWN_RELATIONSHIP as a real edge label
    return "RELATED_TO"
