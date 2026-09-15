from __future__ import annotations

from app import app
from autonomy_api import router as autonomy_router
from enterprise_readiness import router as enterprise_router

# Production composition wrapper. It keeps the established ORBYTHRA application
# intact and mounts the persistent-operator and enterprise-proof surfaces that
# previously existed as standalone modules.
app.include_router(autonomy_router)
app.include_router(enterprise_router)
app.version = "1.4.0"
