from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws/v1/analysis/{task_id}/progress")
async def analysis_progress(websocket: WebSocket, task_id: str):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_json({"task_id": task_id, "status": "running", "message": data})
    except WebSocketDisconnect:
        pass