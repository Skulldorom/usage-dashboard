from fastapi import APIRouter, Depends

from app.core.auth import require_admin_auth
from app.schemas import UpdateCheckRead
from app.updates import check_for_update

router = APIRouter()


@router.get("", response_model=UpdateCheckRead, dependencies=[Depends(require_admin_auth)])
async def get_update_status() -> UpdateCheckRead:
    return UpdateCheckRead.model_validate((await check_for_update()).__dict__)
