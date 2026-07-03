import asyncio
import os
import sys

# Ensure backend path is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from backend.db.postgres import SessionLocal, Tenant, User, Document, ensure_default_tenant
from backend.vector.qdrant_client import qdrant_client
from backend.graph.neo4j_client import neo4j_client
from backend.config import get_settings
from backend.utils.auth import hash_password

settings = get_settings()

DOCUMENT_SET = [
    {
        "filename": "Pump_P101_Maintenance_Manual.pdf",
        "type": "vendor_manual",
        "content_text": "Asset: Pump P-101. Type: centrifugal pump for hydrocracker feed line. Procedure: Seal replacement every 24 months. Procedure: Bearing inspection every 6 months. Specification: Max operating pressure 450 PSI. Engineer owner: Rahul Mehta.",
    },
    {
        "filename": "Incident_Report_IR-033_Pump_P101.pdf",
        "type": "incident_report",
        "content_text": "Incident Report IR-033. Asset: Pump P-101. Incident: Seal rupture at 03:42 on 2023-08-14. Cause: Seal not replaced since 2020 (overdue by 18 months). Contributing factor: Wrong lubricant grade (supplier changed, not documented). Corrective action: Emergency seal replacement completed 2023-08-15. Engineer owner: Rahul Mehta signed off.",
    },
    {
        "filename": "SOP-12_Standard_Pump_Maintenance.pdf",
        "type": "sop",
        "content_text": "SOP-12: Standard Pump Maintenance Procedure. Applies to: all centrifugal pumps including P-101. Seal replacement interval: 24 months. Bearing inspection interval: 6 months. Required PPE: Level B. Approved by: Rahul Mehta.",
    },
    {
        "filename": "Inspection_Report_INS-052_P101.pdf",
        "type": "inspection_report",
        "content_text": "Inspection Report INS-052. Asset: Pump P-101. Date: 2024-01-15. Inspector: Suresh Kumar. Finding: Vibration within normal range. Finding: Seal replaced 2023-08-15 (post-incident). Recommendation: Next inspection due 2025-01.",
    },
    {
        "filename": "Compliance_Audit_CA-007_OSHA_PSM.pdf",
        "type": "compliance",
        "content_text": "Compliance Audit CA-007: OSHA PSM Compliance 2024-Q2. Standard: OSHA 29 CFR 1910.119 (PSM). Asset covered: Reactor R-201, Pump P-101. Status: P-101 compliant, R-201 missing emergency SOP -> GAP FLAGGED. Auditor: External (ABC Consulting).",
    },
    {
        "filename": "Reactor_R201_Operations_Manual.pdf",
        "type": "vendor_manual",
        "content_text": "Reactor R-201 Operations Manual. Asset: Reactor R-201. Unit: hydrocracker unit. Protection device: PSV-301 (pressure safety valve). Max operating temperature: 450°C. Emergency shutdown: Manual isolation required.",
    },
    {
        "filename": "Lessons_Learned_LL-008_Seal_Failure.pdf",
        "type": "lessons_learned",
        "content_text": "Lessons Learned LL-008: Pump Seal Failure Pattern Analysis. Pattern: 3 seal failures across plant in 2022-2023. Root pattern: All missed the 24-month replacement interval. Recommendation: Add automated maintenance alerts. Status: Alert system not yet implemented -> knowledge gap.",
    }
]

ENGINEER_PROFILES = [
    {
        "name": "Rahul Mehta",
        "role": "Senior Reliability Engineer",
        "expertise": "Pump P-101, centrifugal pumps, PSM compliance",
        "retirement_risk": "HIGH",
        "retirement_date": "2027-06-01"
    },
    {
        "name": "Suresh Kumar",
        "role": "Inspector",
        "expertise": "inspection procedures, Reactor R-201",
        "retirement_risk": "MEDIUM",
        "retirement_date": "2032-12-01"
    },
    {
        "name": "Priya Sharma",
        "role": "Compliance Officer",
        "expertise": "compliance, OSHA standards",
        "retirement_risk": "LOW",
        "retirement_date": "2045-05-01"
    }
]

INTENTIONAL_GAPS = [
    {"asset": "Pump P-101", "gap": "Missing emergency shutdown SOP"},
    {"asset": "Reactor R-201", "gap": "Missing emergency SOP"},
    {"asset": "Plant-wide", "gap": "No automated maintenance alert system"}
]

# Simple entity extraction for demo
def extract_entities(text: str, doc_type: str):
    entities = []
    
    if "Pump P-101" in text:
        entities.append({"name": "Pump P-101", "label": "Equipment"})
        
    if "Reactor R-201" in text:
        entities.append({"name": "Reactor R-201", "label": "Equipment"})
        
    if "Rahul Mehta" in text:
        entities.append({"name": "Rahul Mehta", "label": "Person"})
        
    if "Suresh Kumar" in text:
        entities.append({"name": "Suresh Kumar", "label": "Person"})
        
    if "IR-033" in text:
        entities.append({"name": "IR-033", "label": "Incident"})
        entities.append({"name": "Pump P-101", "label": "Equipment"})
        
    if "SOP-12" in text:
        entities.append({"name": "SOP-12", "label": "Procedure"})

    return entities

async def seed_demo_data():
    print("Starting AtlasOS Demo Seed Script...")
    
    # 1. Ensure default tenant exists
    ensure_default_tenant()
    tenant_id = settings.DEFAULT_TENANT_ID
    
    db = SessionLocal()
    
    # 2. Create demo user if not exists
    demo_user = db.query(User).filter(User.email == "demo@atlasos.io").first()
    if not demo_user:
        demo_user = User(
            username="demo",
            email="demo@atlasos.io",
            hashed_password=hash_password("AtlasDemo2026!"),
            tenant_id=tenant_id,
            role="admin"
        )
        db.add(demo_user)
        db.commit()
        db.refresh(demo_user)
        print("Created demo user.")
    
    # Empty existing Qdrant and Neo4j for the tenant to start fresh
    print("Clearing existing Qdrant tenant data...")
    qdrant_client.delete_by_tenant(settings.QDRANT_COLLECTION_NAME, tenant_id)
    
    print("Clearing existing Neo4j tenant data...")
    neo4j_client.run_query("MATCH (n) WHERE n.tenant_id = $tenant_id DETACH DELETE n", {"tenant_id": tenant_id})
    
    # 3. Insert Documents
    for i, doc in enumerate(DOCUMENT_SET):
        # Insert metadata to PostgreSQL
        db_doc = db.query(Document).filter(Document.filename == doc["filename"], Document.tenant_id == tenant_id).first()
        if not db_doc:
            db_doc = Document(
                tenant_id=tenant_id,
                filename=doc["filename"],
                file_path=f"/demo/{doc['filename']}",
                file_type=doc["type"],
                status="completed",
                source="api"
            )
            db.add(db_doc)
            db.commit()
            db.refresh(db_doc)
        
        doc_id = db_doc.id
        
        text = doc["content_text"]
        
        chunk = {
            "text": text,
            "doc_id": doc_id,
            "page": 1,
            "chunk_index": 0,
            "metadata": {"source_file": doc["filename"], "type": doc["type"]}
        }
        
        # Store in Qdrant
        qdrant_client.upsert_chunks(settings.QDRANT_COLLECTION_NAME, [chunk], tenant_id)
        
        # Extract entities
        entities = extract_entities(text, doc["type"])
        
        # Store in Neo4j (Simple representation)
        for ent in entities:
            # Create node
            neo4j_client.run_query(
                f"MERGE (n:{ent['label']} {{name: $name, tenant_id: $tenant_id}}) ON CREATE SET n.confidence = 1.0, n.source_doc_id = $doc_id",
                {"name": ent["name"], "tenant_id": tenant_id, "doc_id": doc_id}
            )
            
        # Create relationships based on co-occurrence in document
        for j in range(len(entities)):
            for k in range(j + 1, len(entities)):
                e1 = entities[j]
                e2 = entities[k]
                if e1["name"] != e2["name"]:
                    rel_type = "RELATED_TO"
                    if e1["label"] == "Person" and e2["label"] == "Equipment":
                        rel_type = "MAINTAINED_BY"
                    elif e2["label"] == "Person" and e1["label"] == "Equipment":
                        rel_type = "MAINTAINED_BY"
                        
                    neo4j_client.run_query(
                        f"""
                        MATCH (a:{e1['label']} {{name: $name1, tenant_id: $tenant_id}})
                        MATCH (b:{e2['label']} {{name: $name2, tenant_id: $tenant_id}})
                        MERGE (a)-[r:{rel_type}]->(b)
                        ON CREATE SET r.confidence = 1.0, r.source_doc_id = $doc_id, r.tenant_id = $tenant_id
                        """,
                        {"name1": e1["name"], "name2": e2["name"], "tenant_id": tenant_id, "doc_id": doc_id}
                    )
        print(f"Processed document {i+1}: {doc['filename']}")
        
    # 4. Insert engineer profiles directly into Neo4j
    for engineer in ENGINEER_PROFILES:
        neo4j_client.run_query(
            """
            MERGE (p:Person {name: $name, tenant_id: $tenant_id})
            SET p.role = $role, p.expertise = $expertise, p.retirement_risk = $risk, p.retirement_date = $date
            """,
            {
                "name": engineer["name"], 
                "tenant_id": tenant_id, 
                "role": engineer["role"],
                "expertise": engineer["expertise"],
                "risk": engineer["retirement_risk"],
                "date": engineer["retirement_date"]
            }
        )
        print(f"Processed engineer: {engineer['name']}")
    
    # 5. Create explicit gap nodes in Neo4j
    for gap in INTENTIONAL_GAPS:
        neo4j_client.run_query(
            """
            MERGE (g:MissingCategory {name: $gap, tenant_id: $tenant_id})
            WITH g
            MATCH (a:Equipment {name: $asset, tenant_id: $tenant_id})
            MERGE (a)-[r:HAS_KNOWLEDGE_GAP]->(g)
            ON CREATE SET r.tenant_id = $tenant_id, r.created_at = timestamp()
            """,
            {"gap": gap["gap"], "asset": gap["asset"], "tenant_id": tenant_id}
        )
    print("Added intentional gaps.")
    
    print("Seed complete. Demo data ready.")

if __name__ == "__main__":
    asyncio.run(seed_demo_data())
