from backend.app import get_graph_data
from backend.db.postgres import SessionLocal
db = SessionLocal()
try:
    data = get_graph_data(depth=2, db=db, current_user=None, tenant_id='default')
    print("Nodes:", len(data['nodes']))
    print("Edges:", len(data['edges']))
except Exception as e:
    print("Error:", e)
