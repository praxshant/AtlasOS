import os
import uuid
import logging
from datetime import datetime
from sqlalchemy import text

# App imports
from backend.config import get_settings
from backend.db.postgres import SessionLocal, init_db, Tenant, Document, Chunk, Entity, ProcessingJob, User
from backend.graph.neo4j_client import neo4j_client
from backend.vector.qdrant_client import qdrant_client
from backend.utils.auth import hash_password

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("atlasos-bootstrapper")
settings = get_settings()

DEMO_TENANT_ID = "default"

def clear_existing_data(db):
    logger.info(f"Clearing old demo data for tenant: {DEMO_TENANT_ID}...")

    # 1. Clear PostgreSQL
    docs = db.query(Document).filter(Document.tenant_id == DEMO_TENANT_ID).all()
    doc_ids = [d.id for d in docs]
    
    if doc_ids:
        # Delete related chunks, entities, and jobs
        db.query(Chunk).filter(Chunk.document_id.in_(doc_ids)).delete(synchronize_session=False)
        db.query(Entity).filter(Entity.source_doc_id.in_(doc_ids)).delete(synchronize_session=False)
        db.query(ProcessingJob).filter(ProcessingJob.document_id.in_(doc_ids)).delete(synchronize_session=False)
        db.query(Document).filter(Document.id.in_(doc_ids)).delete(synchronize_session=False)
    
    # Delete users for default tenant
    db.query(User).filter(User.tenant_id == DEMO_TENANT_ID).delete(synchronize_session=False)
    
    db.commit()
    logger.info("✓ PostgreSQL cleared.")

    # 2. Clear Qdrant
    try:
        qdrant_client.delete_by_tenant(settings.QDRANT_COLLECTION_NAME, DEMO_TENANT_ID)
        logger.info("✓ Qdrant vectors cleared.")
    except Exception as e:
        logger.warning(f"Failed to clear Qdrant: {e}")

    # 3. Clear Neo4j
    try:
        driver = neo4j_client.get_driver()
        if driver:
            with driver.session() as session:
                session.run("MATCH (n) WHERE n.tenant_id = $tid DETACH DELETE n", {"tid": DEMO_TENANT_ID})
            logger.info("✓ Neo4j nodes/edges cleared.")
    except Exception as e:
        logger.warning(f"Failed to clear Neo4j: {e}")


def bootstrap():
    init_db()
    db = SessionLocal()
    
    # Ensure tenant exists
    tenant = db.query(Tenant).filter(Tenant.id == DEMO_TENANT_ID).first()
    if not tenant:
        tenant = Tenant(
            id=DEMO_TENANT_ID,
            name="AeroChem Industrial",
            slug="aerochem",
            plan="enterprise",
            is_active=True
        )
        db.add(tenant)
        db.commit()

    clear_existing_data(db)

    # Seed default user for manual testing
    logger.info("Seeding default manual testing user: admin@atlasos.com / password123")
    default_user = User(
        username="admin",
        email="admin@atlasos.com",
        hashed_password=hash_password("password123"),
        role="admin",
        tenant_id=DEMO_TENANT_ID
    )
    db.add(default_user)
    db.commit()

    # 1. Create mock files in UPLOAD_DIR
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    
    doc_specs = [
        {
            "filename": "SOP-P104-StartUp.pdf",
            "file_type": "PDF",
            "content": (
                "Section 1: Standard Operating Procedure for Centrifugal Pump P-104 Start-up sequence. "
                "Step 1: Check lube oil levels and verify they are within the green zone on dial G-10. "
                "Step 2: Prime pump casing and ensure all air is vented. "
                "Step 3: Keep the discharge valve closed during initial motor start to prevent electrical overload. "
                "Step 4: Gradually open discharge valve to ramp up flow rate. "
                "Safety Notice: Compliance with OSHA 1910.119 Process Safety Management is mandatory. "
                "Any overspeed or abnormal vibration above 4.5 mm/s requires immediate emergency stop button activation. "
                "Testing schedule: Hydrostatic inspection and seal pressure testing must be performed every 3 years."
            )
        },
        {
            "filename": "MAINT-LOG-V202.pdf",
            "file_type": "PDF",
            "content": (
                "Maintenance event log for pressure safety valve Valve V-202. "
                "Performed by Lead Maintenance Engineer John Doe. "
                "Scope: Scheduled re-calibration and O-ring seal replacement. "
                "Detailed log: Removed safety valve V-202 from high-pressure line. "
                "Found fluorocarbon O-ring degraded due to sulfurous gas exposure. "
                "Replaced with premium grade chemical-resistant gasket. "
                "Re-calibrated relief pressure threshold to 150 PSI. "
                "Hydrostatic integrity testing completed. Reinstalled and verified zero leakage."
            )
        },
        {
            "filename": "INCIDENT-REPORT-P104.pdf",
            "file_type": "PDF",
            "content": (
                "Incident Investigation Report: Pump P-104 Seal Failure and downstream Valve V-202 lockup. "
                "Occurred on 2025-03-12 at Sector 4 refinery. "
                "Description: During startup sequence of centrifugal pump P-104, high vibration occurred. "
                "The mechanical seal failed, leading to pressurized fluid leakage. "
                "Pressurized chemical spill sprayed onto downstream safety valve Valve V-202, causing seal degradation. "
                "5-Whys Causal Timeline: "
                "Why 1: Seal failed and fluid leaked. "
                "Why 2: High vibration occurred during startup. "
                "Why 3: Discharge valve was opened too rapidly, causing dry run and cavitation. "
                "Why 4: Operator did not follow the startup sequence in SOP-P104. "
                "Why 5: Lack of training on PSM OSHA 1910.119 guidelines. "
                "Recommendations: "
                "1. Retrain all shift engineers on Centrifugal Pump P-104 Start-up SOP. "
                "2. Install safety shields around Pump P-104 seal lines. "
                "3. Perform weekly vibration scans on P-104 and Valve V-202."
            )
        },
        {
            "filename": "REG-OSHA-1910.pdf",
            "file_type": "PDF",
            "content": (
                "OSHA Standard 1910.119: Process Safety Management of Highly Hazardous Chemicals. "
                "Section A: Operating Procedures. Requires clear written operating procedures (SOPs) "
                "for all highly critical pumps and compressors. "
                "Section B: Mechanical Integrity. Requires regular testing and inspection of safety valves "
                "and pressure containment vessels. Hydrostatic testing of safety valves must be performed "
                "every 2 years to prevent seal fatigue and escape of volatile chemicals."
            )
        }
    ]

    inserted_docs = []
    
    for spec in doc_specs:
        file_path = os.path.join(settings.UPLOAD_DIR, f"demo_{spec['filename']}")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(spec["content"])
            
        doc = Document(
            tenant_id=DEMO_TENANT_ID,
            filename=spec["filename"],
            file_path=file_path,
            file_type=spec["file_type"],
            status="completed",
            source="upload",
            upload_time=datetime.utcnow()
        )
        db.add(doc)
        db.flush() # populated doc.id
        inserted_docs.append((doc, spec["content"]))
        logger.info(f"Created Document record: {spec['filename']} (ID: {doc.id})")

    # 2. Insert Chunks into PostgreSQL & Qdrant
    qdrant_chunks = []
    for doc, content in inserted_docs:
        # Split content into a few sentences for chunks
        sentences = content.split(". ")
        chunks = []
        # Group sentences in pairs
        for i in range(0, len(sentences), 2):
            text_chunk = ". ".join(sentences[i:i+2]) + "."
            chunks.append(text_chunk)
            
        for chunk_idx, text_chunk in enumerate(chunks):
            q_id = str(uuid.uuid4())
            db_chunk = Chunk(
                tenant_id=DEMO_TENANT_ID,
                document_id=doc.id,
                page_number=1,
                chunk_index=chunk_idx,
                text_content=text_chunk,
                qdrant_id=q_id
            )
            db.add(db_chunk)
            
            qdrant_chunks.append({
                "text": text_chunk,
                "doc_id": doc.id,
                "page": 1,
                "chunk_index": chunk_idx,
                "qdrant_id": q_id,
                "metadata": {"source_file": doc.filename}
            })
            
    db.commit()
    logger.info("✓ Saved Chunks to PostgreSQL.")

    # Upsert vectors to Qdrant
    try:
        qdrant_client.upsert_chunks(
            settings.QDRANT_COLLECTION_NAME,
            qdrant_chunks,
            tenant_id=DEMO_TENANT_ID
        )
        logger.info("✓ Upserted chunks to Qdrant.")
    except Exception as e:
        logger.error(f"Failed to upsert to Qdrant: {e}")

    # 3. Create Entities in PostgreSQL
    # Find doc IDs
    sop_doc = next(d for d, _ in inserted_docs if d.filename == "SOP-P104-StartUp.pdf")
    maint_doc = next(d for d, _ in inserted_docs if d.filename == "MAINT-LOG-V202.pdf")
    inc_doc = next(d for d, _ in inserted_docs if d.filename == "INCIDENT-REPORT-P104.pdf")
    reg_doc = next(d for d, _ in inserted_docs if d.filename == "REG-OSHA-1910.pdf")

    entities = [
        # Equipment/Assets
        ("Pump P-104", "Equipment", sop_doc.id),
        ("Valve V-202", "Equipment", maint_doc.id),
        ("Boiler B-501", "Equipment", reg_doc.id),
        # Personnel
        ("John Doe", "Person", maint_doc.id),
        ("Alice Smith", "Person", reg_doc.id),
        # Incidents
        ("Pump P-104 Seal Leakage", "Incident", inc_doc.id),
        # Procedures
        ("P-104 Start-up SOP", "Procedure", sop_doc.id),
        # Regulations
        ("OSHA 1910.119", "Regulation", reg_doc.id)
    ]

    for name, etype, doc_id in entities:
        db_ent = Entity(
            tenant_id=DEMO_TENANT_ID,
            canonical_name=name,
            entity_type=etype,
            confidence=1.0,
            source_doc_id=doc_id
        )
        db.add(db_ent)
    
    db.commit()
    logger.info("✓ Saved Entities to PostgreSQL.")

    # 4. Create Nodes & Relationships in Neo4j
    driver = neo4j_client.get_driver()
    if driver:
        # Load indexes/constraints
        neo4j_client.init_indexes()
        
        with driver.session() as session:
            # Create nodes
            session.run("""
                CREATE (p1:Equipment:Entity {name: 'Pump P-104', description: 'Main high-pressure centrifugal feed pump in Sector 4 refinery', tenant_id: $tid, source_doc_id: $sop_id, type: 'Equipment'})
                CREATE (v2:Equipment:Entity {name: 'Valve V-202', description: 'Downstream pressure safety relief valve calibrated to 150 PSI', tenant_id: $tid, source_doc_id: $maint_id, type: 'Equipment'})
                CREATE (b5:Equipment:Entity {name: 'Boiler B-501', description: 'Steam generation boiler unit 501', tenant_id: $tid, source_doc_id: $reg_id, type: 'Equipment'})
                CREATE (jd:Person:Entity {name: 'John Doe', description: 'Lead Mechanical Maintenance Engineer', tenant_id: $tid, source_doc_id: $maint_id, type: 'Person'})
                CREATE (as_:Person:Entity {name: 'Alice Smith', description: 'EHS Process Safety Coordinator', tenant_id: $tid, source_doc_id: $reg_id, type: 'Person'})
                CREATE (inc:Incident:Entity {name: 'Pump P-104 Seal Leakage', description: 'Mechanical seal failure during startup sequence', tenant_id: $tid, source_doc_id: $inc_id, type: 'Incident', event_time: '2025-03-12T10:30:00Z'})
                CREATE (sop:Procedure:Entity {name: 'P-104 Start-up SOP', description: 'Standard Operating Procedure for P-104 centrifugal pump', tenant_id: $tid, source_doc_id: $sop_id, type: 'Procedure'})
                CREATE (reg:Regulation:Entity {name: 'OSHA 1910.119', description: 'Process Safety Management regulation', tenant_id: $tid, source_doc_id: $reg_id, type: 'Regulation'})
            """, {
                "tid": DEMO_TENANT_ID,
                "sop_id": sop_doc.id,
                "maint_id": maint_doc.id,
                "inc_id": inc_doc.id,
                "reg_id": reg_doc.id
            })
            
            # Create relationships
            session.run("""
                MATCH (p1 {name: 'Pump P-104', tenant_id: $tid})
                MATCH (v2 {name: 'Valve V-202', tenant_id: $tid})
                MATCH (b5 {name: 'Boiler B-501', tenant_id: $tid})
                MATCH (jd {name: 'John Doe', tenant_id: $tid})
                MATCH (as_ {name: 'Alice Smith', tenant_id: $tid})
                MATCH (inc {name: 'Pump P-104 Seal Leakage', tenant_id: $tid})
                MATCH (sop {name: 'P-104 Start-up SOP', tenant_id: $tid})
                MATCH (reg {name: 'OSHA 1910.119', tenant_id: $tid})
                
                CREATE (jd)-[:KNOWLEDGE_OWNER_FOR {tenant_id: $tid, confidence: 1.0}]->(p1)
                CREATE (jd)-[:MAINTAINED_BY {tenant_id: $tid, confidence: 0.9, last_maintenance: '2025-05-10'}]->(v2)
                CREATE (as_)-[:INSPECTED_BY {tenant_id: $tid, confidence: 1.0, last_inspection: '2025-06-01'}]->(v2)
                
                CREATE (inc)-[:OCCURRED_ON {tenant_id: $tid, confidence: 1.0, event_time: '2025-03-12T10:30:00Z'}]->(p1)
                CREATE (inc)-[:AFFECTED_BY {tenant_id: $tid, confidence: 0.85}]->(v2)
                
                CREATE (sop)-[:APPLIES_TO {tenant_id: $tid, confidence: 1.0}]->(p1)
                CREATE (sop)-[:COMPLIES_WITH {tenant_id: $tid, confidence: 0.95}]->(reg)
            """, {"tid": DEMO_TENANT_ID})
            
            # Compute initial gaps to create gap relationships (so the graph has HAS_KNOWLEDGE_GAP edges)
            logger.info("Computing and persisting knowledge gaps in Neo4j...")
            neo4j_client.compute_knowledge_gaps("Pump P-104", DEMO_TENANT_ID)
            neo4j_client.compute_knowledge_gaps("Valve V-202", DEMO_TENANT_ID)
            neo4j_client.compute_knowledge_gaps("Boiler B-501", DEMO_TENANT_ID)
            
            logger.info("✓ Neo4j nodes, edges, and gaps initialized.")

    db.close()
    logger.info("========================================")
    logger.info("BOOTSTRAP SUCCESSFUL!")
    logger.info("========================================")

if __name__ == "__main__":
    bootstrap()
