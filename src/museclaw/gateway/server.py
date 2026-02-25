"""Gateway FastAPI Server - Localhost only."""

import logging
from datetime import datetime
from typing import Any, Dict

from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import JSONResponse
import uvicorn

from .message import InternalMessage
from .session import SessionManager
from .security import SecurityGate
from .cron import CronEngine

logger = logging.getLogger(__name__)

# Global instances (singleton pattern for gateway)
session_manager = SessionManager()
security_gate = SecurityGate()
cron_engine = CronEngine()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="MuseClaw Gateway",
        description="24/7 Life Central - Message routing and session management",
        version="0.1.0",
    )

    @app.get("/health")
    async def health_check() -> Dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy", "timestamp": datetime.now().isoformat()}

    @app.post("/webhook")
    async def webhook_handler(
        request: Request, x_signature: str = Header(None)
    ) -> JSONResponse:
        """
        Webhook endpoint for external integrations.

        Validates HMAC signature and rate limiting before processing.
        """
        # Read raw body
        body = await request.body()

        # Validate HMAC if signature provided
        if x_signature:
            if not security_gate.validate_hmac(body, x_signature):
                logger.warning("Invalid HMAC signature")
                raise HTTPException(status_code=403, detail="Invalid signature")

        # Parse JSON
        try:
            data = await request.json()
        except Exception as e:
            logger.error(f"Invalid JSON: {e}")
            raise HTTPException(status_code=400, detail="Invalid JSON")

        # Extract user_id for rate limiting
        user_id = data.get("user_id", "unknown")

        # Check rate limit
        if not security_gate.check_rate_limit(user_id):
            logger.warning(f"Rate limit exceeded for user {user_id}")
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

        # Sanitize input
        try:
            content = security_gate.sanitize_input(data.get("content", ""))
        except ValueError as e:
            logger.warning(f"Suspicious input detected: {e}")
            raise HTTPException(status_code=400, detail=str(e))

        # Create internal message
        try:
            message = InternalMessage(
                source="webhook",
                session_id=data.get("session_id", f"webhook_{user_id}"),
                user_id=user_id,
                content=content,
                timestamp=datetime.now(),
                trust_level=data.get("trust_level", "external"),
                metadata=data.get("metadata", {}),
            )
        except ValueError as e:
            logger.error(f"Invalid message format: {e}")
            raise HTTPException(status_code=400, detail=str(e))

        # Acquire session lock
        session_id = message.session_id
        if not await session_manager.acquire(session_id):
            # Session is busy, queue the message (simplified: return 202 Accepted)
            return JSONResponse(
                status_code=202, content={"status": "queued", "session_id": session_id}
            )

        try:
            # TODO: Route to Agent Runtime
            # For now, just acknowledge receipt
            logger.info(f"Received message from {message.source}: {message.session_id}")
            return JSONResponse(
                content={"status": "received", "session_id": session_id}
            )
        finally:
            await session_manager.release(session_id)

    @app.on_event("startup")
    async def startup_event():
        """Initialize services on startup."""
        logger.info("Starting MuseClaw Gateway")
        cron_engine.start()

    @app.on_event("shutdown")
    async def shutdown_event():
        """Cleanup on shutdown."""
        logger.info("Shutting down MuseClaw Gateway")
        cron_engine.shutdown()

    return app


def main() -> None:
    """Run the Gateway server (localhost only)."""
    app = create_app()

    # CRITICAL: Only bind to localhost (127.0.0.1)
    # This prevents remote access to the Gateway
    uvicorn.run(
        app,
        host="127.0.0.1",  # localhost only
        port=8765,
        log_level="info",
    )


if __name__ == "__main__":
    main()
