from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from . import models  # noqa: F401  (register tables)
from .config import settings
from .db import Base, engine
from .demo.seed import ensure_seeded
from .routers import applications, audit, auth, dashboard, documents, findings, meta, rules, verification
from .services.prescrutiny import fail_stale_runs

API = "/api/v1"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(engine)
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    ensure_seeded()
    fail_stale_runs()
    yield


app = FastAPI(title="AICTE VerifyAI", version="0.1.0", lifespan=lifespan,
              description="Evidence-first AI pre-scrutiny for AICTE applications. Decision support only.")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

for r in (auth, meta, dashboard, applications, documents, findings, verification, rules, audit):
    app.include_router(r.router, prefix=API)


# ── Built frontend (single-process launch). In development Vite serves the UI instead. ──
@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    if path.startswith("api/"):
        raise HTTPException(404, "Not found")
    dist = settings.frontend_dist.resolve()
    target = (dist / path).resolve()
    if path and target.is_file() and dist in target.parents:
        return FileResponse(target)
    index = dist / "index.html"
    if index.exists():
        return FileResponse(index)
    raise HTTPException(404, "Frontend not built. Run `npm run build` in frontend/ or use the Vite dev server.")
