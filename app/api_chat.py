from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from app import repository
from app.config import get_settings
from app.db import get_pool
from app.deps import get_current_user_id
from app.models import ChatAnswerResponse, ChatAsk, ChatMessageOut

router = APIRouter(prefix="/api/books", tags=["chat"])


@router.post("/{book_id}/chat", response_model=ChatAnswerResponse)
async def chat(
    book_id: UUID,
    body: ChatAsk,
    user_id: UUID = Depends(get_current_user_id),
):
    settings = get_settings()
    pool = get_pool()

    # Verify book exists and is published
    book = await repository.get_book_chat_context(pool, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    # Rate limit check
    used_today = await repository.count_user_messages_today(
        pool, user_id, book_id
    )
    if used_today >= settings.daily_chat_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily chat limit of {settings.daily_chat_limit} "
                   f"messages per book reached. Try again tomorrow.",
        )

    # Get or create session
    session_id = await repository.get_or_create_session(
        pool, book_id, user_id
    )

    # Get recent history
    history_rows = await repository.get_session_messages(
        pool, session_id, limit=settings.max_history_messages
    )
    history = [
        {"role": r["role"], "content": r["content"]}
        for r in reversed(history_rows)
    ]

    # Save user message
    await repository.save_message(
        pool, session_id, "user", body.question
    )

    # Call agents service
    payload = {
        "book_id": str(book_id),
        "question": body.question,
        "history": history
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                settings.agents_chat_url, json=payload
            )
            resp.raise_for_status()
            answer = resp.json()["answer"]
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"AI service unavailable: {exc}",
        )

    # Save assistant message
    await repository.save_message(
        pool, session_id, "assistant", answer
    )

    remaining = max(0, settings.daily_chat_limit - used_today - 1)

    return ChatAnswerResponse(
        answer=answer,
        session_id=session_id,
        messages_used_today=used_today + 1,
        messages_remaining=remaining,
    )


@router.get(
    "/{book_id}/chat/history",
    response_model=list[ChatMessageOut],
)
async def chat_history(
    book_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    pool = get_pool()
    session_id = await repository.get_or_create_session(
        pool, book_id, user_id
    )
    rows = await repository.get_session_messages(pool, session_id, limit=50)
    return [ChatMessageOut(**dict(r)) for r in reversed(rows)]
