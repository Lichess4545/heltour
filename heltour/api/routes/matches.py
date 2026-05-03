import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from heltour.api.pubsub import subscribe

logger = logging.getLogger("heltour.api.matches")
router = APIRouter()


@router.websocket("/ws/rounds/{round_id}/matches")
async def round_matches_ws(ws: WebSocket, round_id: int) -> None:
    await ws.accept()
    channel = f"matches:round:{round_id}"
    client = ws.client
    logger.info("ws connect round=%s client=%s", round_id, client)
    sent = 0
    try:
        async for message in subscribe(channel):
            sent += 1
            logger.info(
                "ws forward round=%s client=%s seq=%s type=%s",
                round_id, client, sent, message.get("type"),
            )
            await ws.send_json(message)
    except WebSocketDisconnect:
        logger.info(
            "ws disconnect round=%s client=%s sent=%s",
            round_id, client, sent,
        )
    except Exception:
        logger.exception(
            "ws error round=%s client=%s sent=%s",
            round_id, client, sent,
        )
        raise
