from fastapi import APIRouter

from app.api.v1.zentao.bug import router as bug_router
from app.api.v1.zentao.execution import router as execution_router
from app.api.v1.zentao.project import router as project_router
from app.api.v1.zentao.testcase import router as testcase_router
from app.api.v1.zentao.testtask import router as testtask_router

router = APIRouter()
router.include_router(project_router)
router.include_router(execution_router)
router.include_router(bug_router)
router.include_router(testtask_router)
router.include_router(testcase_router)
