import os
import hmac
from jose import jwt
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from auth import SECRET_KEY, ALGORITHM

class JWTMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        # Public or internal paths that don't need dashboard JWT
        if (
            request.method == "OPTIONS"
            or path.startswith("/api/internal")
            or path.startswith("/api/auth")
            or path.startswith("/ws/")
            or path == "/health"
            or not path.startswith("/api/")
        ):
            return await call_next(request)

        def _get_401_response(detail: str) -> JSONResponse:
            resp = JSONResponse(status_code=401, content={"detail": detail})
            origin = request.headers.get("origin")
            if origin:
                resp.headers["Access-Control-Allow-Origin"] = origin
                resp.headers["Access-Control-Allow-Credentials"] = "true"
            return resp

        # Edge node requests authenticated via X-API-Key (header or query param)
        api_key = request.headers.get("x-api-key") or request.query_params.get("api_key")
        expected_key = os.environ.get("EDGE_API_KEY", "default-dev-key")
        env = os.environ.get("ENVIRONMENT", "development").lower()
        if (
            api_key
            and not (env in ("production", "prod") and (not expected_key or expected_key == "default-dev-key"))
            and hmac.compare_digest(api_key, expected_key)
        ):
            return await call_next(request)

        # Query token authentication for media/stream endpoints (e.g. <img> tags)
        query_token = request.query_params.get("token")
        if query_token:
            try:
                payload = jwt.decode(query_token, SECRET_KEY, algorithms=[ALGORITHM])
                request.state.user = payload.get("sub")
                return await call_next(request)
            except Exception:
                return _get_401_response("Invalid or expired stream token")
            
        auth_header = request.headers.get("Authorization")
            
        if not auth_header or not auth_header.startswith("Bearer "):
            return _get_401_response("Missing or invalid authorization header")
            
        token = auth_header.split(" ")[1]
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            request.state.user = payload.get("sub")
        except Exception:
            return _get_401_response("Could not validate credentials")
            
        return await call_next(request)
