import os
from jose import jwt
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from auth import SECRET_KEY, ALGORITHM

class JWTMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        # Public or internal paths that don't need dashboard JWT
        if request.method == "OPTIONS" or path.startswith("/api/internal") or path.startswith("/api/auth") or path.startswith("/ws/") or not path.startswith("/api/"):
            return await call_next(request)
            
        auth_header = request.headers.get("Authorization")
        
        def _get_401_response(detail: str) -> JSONResponse:
            resp = JSONResponse(status_code=401, content={"detail": detail})
            origin = request.headers.get("origin")
            if origin:
                resp.headers["Access-Control-Allow-Origin"] = origin
                resp.headers["Access-Control-Allow-Credentials"] = "true"
            return resp
            
        if not auth_header or not auth_header.startswith("Bearer "):
            return _get_401_response("Missing or invalid authorization header")
            
        token = auth_header.split(" ")[1]
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            request.state.user = payload.get("sub")
        except Exception:
            return _get_401_response("Could not validate credentials")
            
        return await call_next(request)
