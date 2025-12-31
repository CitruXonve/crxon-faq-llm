import logging
from fastapi import FastAPI

from src.config.settings import settings
from src.service.knowledge_base import KnowledgeBaseServiceMarkdown
from src.service.llm_service import ClaudeLLMService
from src.service.session_service import SessionService
from src.api.chat import router as chat_router, stream_router

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.APP_TITLE,
    description=settings.APP_DESCRIPTION,
    version=settings.APP_VERSION,
)

app.include_router(chat_router)
app.include_router(stream_router)


@app.on_event("startup")
async def startup_event():
    """Initialize resources when the application starts."""
    logger.info("Starting up...")
    kb_service = KnowledgeBaseServiceMarkdown()
    app.state.llm_service = ClaudeLLMService(kb_service)
    app.state.session_service = SessionService()
    logger.info("Resources initialized successfully")
    print("Resources initialized successfully")


@app.get("/")
async def root():
    """
    Root endpoint to verify the API is running.
    """
    return {"message": settings.APP_TITLE + " API is running"}
