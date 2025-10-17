"""HTTP Basic Authentication"""

import os
import secrets
from typing import Optional

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials


security = HTTPBasic()


def verify_credentials(credentials: HTTPBasicCredentials) -> bool:
    """Verify username and password against environment variables"""
    correct_username = os.environ.get("ADMIN_USERNAME", "admin")
    correct_password = os.environ.get("ADMIN_PASSWORD", "changeme")

    # Use constant-time comparison to prevent timing attacks
    username_correct = secrets.compare_digest(
        credentials.username.encode("utf8"), correct_username.encode("utf8")
    )
    password_correct = secrets.compare_digest(
        credentials.password.encode("utf8"), correct_password.encode("utf8")
    )

    return username_correct and password_correct


def requires_admin(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    """Dependency that requires admin authentication"""
    if not verify_credentials(credentials):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def get_current_user(request: Request) -> Optional[str]:
    """Get current authenticated user from request if available"""
    # Try to extract from Authorization header
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Basic "):
        try:
            import base64

            encoded = auth_header.replace("Basic ", "")
            decoded = base64.b64decode(encoded).decode("utf-8")
            username, _ = decoded.split(":", 1)
            return username
        except Exception:
            pass
    return None
