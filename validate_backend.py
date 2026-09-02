#!/usr/bin/env python
"""Quick validation of backend integration."""

import sys

try:
    from backend.models import Detection
    from backend.schemas import DetectionCreateRequest
    print("✓ Models and schemas imported successfully")
    
    # Check Detection model
    d = Detection()
    has_event_id = hasattr(d, "event_id")
    print(f"✓ Detection model has event_id field: {has_event_id}")
    
    # Check DetectionCreateRequest schema
    has_event_id_field = "event_id" in DetectionCreateRequest.model_fields
    print(f"✓ DetectionCreateRequest has event_id: {has_event_id_field}")
    
    # Validate
    if has_event_id and has_event_id_field:
        print("\n✓✓✓ Backend integration PASSED ✓✓✓")
        sys.exit(0)
    else:
        print("\n✗ Backend integration FAILED")
        sys.exit(1)
        
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
