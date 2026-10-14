import os
import hmac
from fastapi import Header, HTTPException

def verify_edge_node(x_api_key: str = Header(..., alias="X-API-Key")):
    expected_key = os.environ.get("EDGE_API_KEY", "default-dev-key")
    env = os.environ.get("ENVIRONMENT", "development").lower()
    if env in ("production", "prod") and (not expected_key or expected_key == "default-dev-key"):
        raise HTTPException(status_code=500, detail="EDGE_API_KEY must be configured in production environment")
    if not (x_api_key and hmac.compare_digest(x_api_key, expected_key)):
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return x_api_key
