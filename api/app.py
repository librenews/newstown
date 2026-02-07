"""FastAPI application for News Town API."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from db.connection import db
from publishing.scheduler import scheduler
from api.publishing import router as publishing_router
from api.governance import router as governance_router
from api.dashboard import router as dashboard_router
from config.logging import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting News Town API")
    
    # Connect to database
    await db.connect()
    logger.info("Database connected")
    
    # Start publishing scheduler
    await scheduler.start()
    logger.info("Publishing scheduler started")
    
    yield
    
    # Shutdown
    logger.info("Shutting down News Town API")
    
    # Stop scheduler
    await scheduler.stop()
    
    # Disconnect database
    await db.disconnect()
    logger.info("Database disconnected")


# Create FastAPI app
app = FastAPI(
    title="News Town API",
    description="Multi-agent news reporting system",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])
app.include_router(publishing_router)
app.include_router(governance_router)


@app.get("/")
async def root():
    """API root endpoint."""
    return {
        "name": "News Town API",
        "version": "1.0.0",
        "status": "operational",
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
