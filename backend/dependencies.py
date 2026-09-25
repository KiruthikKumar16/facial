import os
from fastapi import Header, HTTPException

def verify_edge_node(x_api_key: str = Header(..., alias="X-API-Key")):
    expected_key = os.environ.get("EDGE_API_KEY", "default-dev-key")
    if x_api_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return x_api_key
