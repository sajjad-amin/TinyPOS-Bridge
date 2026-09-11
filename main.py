import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from server.config import HOST, PORT
from server.routes.web import web_router
from server.routes.internal_api import internal_api_router
from server.routes.public_api import public_api_router
from server.routes.websocket_api import websocket_api_router
import server.db as db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB schema & run initial cleanup of stale temporary jobs
    db.init_db()
    db.cleanup_temporary_jobs(older_than_seconds=300)

    # Periodic background job cleaner (every 60s)
    async def periodic_cleaner():
        while True:
            try:
                await asyncio.sleep(60)
                db.cleanup_temporary_jobs(older_than_seconds=300)
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    cleaner_task = asyncio.create_task(periodic_cleaner())
    yield
    cleaner_task.cancel()


# Create FastAPI application
app = FastAPI(
    title="TinyPOS Thermal Printer Bridge",
    description="FastAPI bridge to stream invoices and receipts to Bainiu / Tiny Print BLE thermal printers.",
    version="1.3.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register modular routes
app.include_router(web_router)
app.include_router(internal_api_router)
app.include_router(public_api_router)
app.include_router(websocket_api_router)

if __name__ == "__main__":
    print(f"Starting TinyPOS on http://{HOST}:{PORT}")
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True, proxy_headers=True, forwarded_allow_ips="*")
