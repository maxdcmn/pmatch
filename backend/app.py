from __future__ import annotations

"""
FastAPI application template.

This file sets up a minimal FastAPI app with:
- CORS configured for local development
- A health check endpoint
- A versioned API router (`/api/v1`) with placeholder CRUD routes

Replace placeholder implementations with real logic as needed.
"""

from fastapi import FastAPI, APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from starlette.middleware.cors import CORSMiddleware


# ----------------------------------------------------------------------------
# App setup
# ----------------------------------------------------------------------------

app = FastAPI(title="PMatch API", version="0.1.0")

# Configure CORS for local Next.js dev and same-origin by default
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost",
        "http://127.0.0.1",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------------------------------------------------------
# Models (placeholders)
# ----------------------------------------------------------------------------

class ItemCreate(BaseModel):
    """Request model for creating an item (placeholder)."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=1000)


class ItemRead(BaseModel):
    """Response model for an item (placeholder)."""

    id: int
    name: str
    description: str | None = None


# ----------------------------------------------------------------------------
# Routers
# ----------------------------------------------------------------------------

api = APIRouter(prefix="/api/v1", tags=["api"])


@app.get("/healthz", tags=["health"], summary="Health check")
def health() -> dict[str, str]:
    return {"status": "ok", "version": app.version}


@app.get("/", tags=["meta"], summary="Service info")
def root() -> dict[str, str]:
    return {"service": app.title, "version": app.version}


@api.get("/items", response_model=list[ItemRead], summary="List items")
def list_items() -> list[ItemRead]:
    # TODO: implement listing from storage/database
    return []


@api.post(
    "/items",
    response_model=ItemRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create item",
)
def create_item(payload: ItemCreate) -> ItemRead:
    # TODO: implement creation logic
    # Using 501 here signals the endpoint is not implemented yet
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="create_item not implemented",
    )


@api.get("/items/{item_id}", response_model=ItemRead, summary="Get item by id")
def get_item(item_id: int) -> ItemRead:
    # TODO: implement retrieval logic
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"get_item not implemented for id={item_id}",
    )


@api.put("/items/{item_id}", response_model=ItemRead, summary="Update item")
def update_item(item_id: int, payload: ItemCreate) -> ItemRead:
    # TODO: implement update logic
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"update_item not implemented for id={item_id}",
    )


@api.delete(
    "/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete item",
)
def delete_item(item_id: int) -> None:
    # TODO: implement delete logic
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"delete_item not implemented for id={item_id}",
    )


# Register router(s)
app.include_router(api)


# ----------------------------------------------------------------------------
# Local dev entrypoint (optional)
# ----------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    # Run with: python backend/app.py
    # Or: uvicorn backend.app:app --reload
    uvicorn.run(
        "backend.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
