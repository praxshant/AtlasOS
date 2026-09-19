from typing import Dict, Set

# Defines which relationships are semantically valid for a given entity TYPE acting as the SOURCE node.
# e.g. "Equipment" node as a source can connect to a Person via "MAINTAINED_BY"
# but a "Person" node as a source cannot connect to an Equipment via "MAINTAINED_BY" (it would be MAINTAINS).

ENTITY_TO_RELATIONSHIPS: Dict[str, Set[str]] = {
    "Equipment": {
        "MAINTAINED_BY", "INSPECTED_BY", "OPERATED_BY", "BELONGS_TO",
        "LOCATED_AT", "CONNECTED_TO", "FEEDS", "SUPPLIES", "CAUSED_BY",
        "AFFECTED_BY", "HAS_PROCEDURE", "GOVERNED_BY", "DOCUMENTED_IN",
        "RELATED_TO", "FAILED_AT"
    },
    "Component": {
        "PART_OF", "BELONGS_TO", "MAINTAINED_BY", "INSPECTED_BY", "AFFECTED_BY",
        "CAUSED_BY", "FAILED_AT", "RELATED_TO"
    },
    "Person": {
        "MAINTAINS", "INSPECTS", "OPERATES", "AUTHORED_BY", "REPORTS",
        "INVESTIGATED", "INVOLVED_IN", "RESPONSIBLE_FOR", "KNOWLEDGE_OWNER",
        "DESIGNED", "RELATED_TO"
    },
    "Organization": {
        "OWNS", "MANAGES", "EMPLOYS", "FUNDED_BY", "RELATED_TO"
    },
    "Incident": {
        "OCCURRED_ON", "RESULTED_IN", "REPORTED_BY", "INVOLVED_IN",
        "INVESTIGATED_BY", "DOCUMENTED_IN", "RELATED_TO"
    },
    "Procedure": {
        "APPLIES_TO", "PREVENTS", "AUTHORED_BY", "COMPLIES_WITH",
        "GOVERNED_BY", "RELATED_TO"
    },
    "Regulation": {
        "APPLIES_TO", "GOVERNS", "RELATED_TO"
    },
    "WorkOrder": {
        "PERFORMED_ON", "RESPONSE_TO", "ASSIGNED_TO", "RELATED_TO"
    },
    "Document": {
        "REFERENCES", "DOCUMENTED_BY", "AUTHORED_BY", "RELATED_TO"
    }
}
