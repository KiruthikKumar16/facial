import json
import re

for path in ['backend/test_idempotent_ingestion.py', 'backend/test_sync_sequences.py']:
    with open(path, 'r', encoding='utf-8') as f:
        data = f.read()
    
    # We want to replace `"timestamp": now.isoformat(),` with `"timestamp": now.isoformat(), "event_id": "test-evt-123",`
    new_data = data.replace('"timestamp": now.isoformat(),', '"timestamp": now.isoformat(),\n        "event_id": "test-evt-123",')
    
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_data)
    
    print(f"Updated {path}")
