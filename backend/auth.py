import logging
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from backend.config import settings

logger = logging.getLogger(__name__)

_serializer = URLSafeTimedSerializer(settings.AUTH_SECRET_KEY)


def create_token(username: str) -> str:
    return _serializer.dumps(username, salt="auth")


def verify_token(token: str) -> str | None:
    try:
        return _serializer.loads(token, salt="auth", max_age=settings.AUTH_TOKEN_MAX_AGE)
    except (SignatureExpired, BadSignature):
        return None


# --- Router ---

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(req: LoginRequest):
    if req.username == settings.AUTH_USERNAME and req.password == settings.AUTH_PASSWORD:
        token = create_token(req.username)
        return {"token": token, "username": req.username}
    return JSONResponse(status_code=401, content={"detail": "Invalid username or password"})


@router.post("/check")
async def check_token(request: Request):
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        username = verify_token(token)
        if username:
            return {"valid": True, "username": username}
    return JSONResponse(status_code=401, content={"valid": False})


# --- Middleware ---

PUBLIC_PATHS = {"/login", "/api/v1/auth/login", "/api/v1/health"}
PUBLIC_PREFIXES = ("/css/", "/js/", "/api/v1/auth/")


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Allow public routes
        if path in PUBLIC_PATHS or any(path.startswith(p) for p in PUBLIC_PREFIXES):
            return await call_next(request)

        # Check token from header or query param (for file downloads)
        token = None
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
        if not token:
            token = request.query_params.get("token")

        if token and verify_token(token):
            return await call_next(request)

        # Not authenticated
        is_api = path.startswith("/api/")
        if is_api:
            return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
        return RedirectResponse(url="/login?expired=1", status_code=302)
