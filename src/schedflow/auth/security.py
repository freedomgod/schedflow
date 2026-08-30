from abc import ABC, abstractmethod
from dataclasses import dataclass

from fastapi import Request

from schedflow.auth.services import verify_api_key, verify_jwt_token


@dataclass
class AuthResult:
    success: bool
    user_id: str | None = None
    method: str | None = None  # "jwt" or "apikey"


class AuthBackend(ABC):
    @abstractmethod
    async def authenticate(self, request: Request) -> AuthResult:
        ...


class JWTBackend(AuthBackend):
    async def authenticate(self, request: Request) -> AuthResult:
        header = request.headers.get("Authorization", "")
        token = header[7:] if header.startswith("Bearer ") else None
        if not token:
            # EventSource cannot set Authorization headers, so SSE clients
            # pass the JWT as a query parameter instead.
            token = request.query_params.get("token")
        if not token:
            return AuthResult(success=False)
        payload = verify_jwt_token(token)
        if payload is None:
            return AuthResult(success=False)
        return AuthResult(success=True, user_id=payload["sub"], method="jwt")


class APIKeyBackend(AuthBackend):
    async def authenticate(self, request: Request) -> AuthResult:
        key = request.headers.get("X-API-Key", "") or request.query_params.get(
            "api_key", ""
        )
        if not key:
            return AuthResult(success=False)
        record = verify_api_key(key)
        if record is None:
            return AuthResult(success=False)
        return AuthResult(
            success=True,
            user_id=f"apikey:{record['id']}",
            method="apikey",
        )
