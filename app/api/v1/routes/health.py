from fastapi import APIRouter, Depends

from app.core.security import CurrentUser, get_current_user

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """Public liveness check (no auth)."""
    return {"status": "ok"}


@router.get("/me")
def me(user: CurrentUser = Depends(get_current_user)) -> dict[str, str | None]:
    """Authenticated check — confirms the JWT pipeline works end to end."""
    return {"user_id": str(user.id), "email": user.email}
