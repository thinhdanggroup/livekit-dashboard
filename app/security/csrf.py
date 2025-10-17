"""CSRF Protection"""

import os
import secrets
from typing import Optional

from fastapi import Request, HTTPException, status
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired


def get_secret_key() -> str:
    """Get secret key from environment"""
    return os.environ.get("APP_SECRET_KEY", "dev-secret-key-change-in-production")


def generate_csrf_token() -> str:
    """Generate a new CSRF token"""
    serializer = URLSafeTimedSerializer(get_secret_key())
    token = secrets.token_urlsafe(32)
    return serializer.dumps(token, salt="csrf-token")


def validate_csrf_token(token: str, max_age: int = 3600) -> bool:
    """Validate a CSRF token"""
    if not token:
        return False

    serializer = URLSafeTimedSerializer(get_secret_key())
    try:
        serializer.loads(token, salt="csrf-token", max_age=max_age)
        return True
    except (BadSignature, SignatureExpired):
        return False


def get_csrf_token(request: Request) -> str:
    """Get or generate CSRF token for a request"""
    # Check if token exists in session/cookie
    if hasattr(request.state, "csrf_token"):
        return request.state.csrf_token

    # Generate new token
    token = generate_csrf_token()
    request.state.csrf_token = token
    return token


async def verify_csrf_token(request: Request) -> None:
    """Verify CSRF token from form data"""
    if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
        form_data = await request.form()
        token = form_data.get("csrf_token", "")

        if not validate_csrf_token(token):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid or expired CSRF token",
            )
