from fastapi import APIRouter, Request, Response

router = APIRouter()


@router.post("/webhook")
async def telegram_webhook(request: Request) -> Response:
    # TODO: parse the incoming Telegram Update JSON and dispatch to handlers
    body = await request.json()
    return Response(status_code=200)


@router.get("/set-webhook")
async def set_webhook() -> dict:
    # TODO: call Telegram setWebhook API with WEBHOOK_URL + /bot/webhook
    return {"status": "not implemented"}
