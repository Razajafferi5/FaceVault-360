"""Recognition API routes — single-frame and real-time WebSocket recognition."""

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.api.deps import get_recognition_service, get_pipeline
from app.utils.image import decode_base64_frame

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Recognition"])


class SingleFrameRequest(BaseModel):
    """Request body for single-frame recognition."""
    frame: str  # Base64 encoded JPEG


@router.post("/api/recognition")
async def recognize_single_frame(
    req: SingleFrameRequest,
    recognition_service=Depends(get_recognition_service),
    pipeline=Depends(get_pipeline),
):
    """Perform recognition on a single base64-encoded frame.

    Returns recognition results including detected faces, confidence, and authorization.
    """
    """Perform recognition on a single base64-encoded frame and record attendance events."""
    frame = decode_base64_frame(req.frame)
    if frame is None:
        raise HTTPException(status_code=400, detail="Invalid image data")

    try:
        result = await asyncio.to_thread(recognition_service.recognize_frame, frame)
        faces = result.get("faces", [])
        for face in faces:
            asyncio.create_task(pipeline._log_access_event(face))
        return result
    except Exception as e:
        logger.error(f"Single-frame recognition error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Recognition failed")


@router.websocket("/ws/recognition")
async def recognition_stream(websocket: WebSocket):
    """Real-time recognition WebSocket stream.

    Sends:
        - Binary messages: JPEG-encoded camera frames
        - Text messages: JSON recognition results

    Uses a single-slot pattern — if processing takes longer than the frame
    interval, frames are dropped to prevent lag buildup.
    """
    await websocket.accept()
    logger.info("WebSocket recognition stream connected")

    # Access pipeline from app state
    pipeline = websocket.app.state.pipeline

    try:
        await pipeline.start(mode='entry')
        last_sent_frame = -1

        while True:
            event = pipeline.get_latest_event()

            if event and hasattr(event, 'frame_jpeg') and event.frame_jpeg:
                if pipeline.state.frame_count != last_sent_frame:
                    last_sent_frame = pipeline.state.frame_count

                    # Send frame as binary
                    await websocket.send_bytes(event.frame_jpeg)

                    # Send recognition data as JSON
                    result_data = {
                        "type": "recognition_result",
                        "faces": event.faces if isinstance(event.faces, list) else [],
                        "camera_guidance": event.guidance if isinstance(event.guidance, dict) else (
                            {
                                "face_detected": event.guidance.face_detected,
                                "position_ok": event.guidance.position_ok,
                                "message": event.guidance.message,
                                "severity": event.guidance.severity,
                                "yaw": event.guidance.yaw,
                                "pitch": event.guidance.pitch,
                                "roll": event.guidance.roll,
                            } if event.guidance else None
                        ),
                        "camera_health": event.health,
                    }
                    await websocket.send_json(result_data)

            # Check every 80ms (~12 FPS)
            await asyncio.sleep(0.08)

    except WebSocketDisconnect:
        logger.info("WebSocket recognition stream disconnected")
    except Exception as e:
        logger.error(f"WebSocket recognition error: {e}", exc_info=True)
    finally:
        await pipeline.stop()


@router.websocket("/ws/enrollment")
async def enrollment_stream(websocket: WebSocket):
    """Real-time enrollment WebSocket stream.

    Client sends session_id as the first text message after connecting.
    Server streams camera frames and enrollment progress.
    """
    await websocket.accept()
    logger.info("WebSocket enrollment stream connected")

    pipeline = websocket.app.state.pipeline

    try:
        # Receive session_id from client
        session_id = await websocket.receive_text()
        logger.info(f"Enrollment stream started for session: {session_id}")

        while True:
            result = await pipeline.process_enrollment_frame(session_id)

            if isinstance(result, dict) and "error" in result:
                await websocket.send_json(result)
                await asyncio.sleep(0.5)
                continue

            # Send frame as binary if present
            if "frame_jpeg" in result and result["frame_jpeg"]:
                frame_jpeg = result.pop("frame_jpeg")
                await websocket.send_bytes(frame_jpeg)

            # Send enrollment progress as JSON
            await websocket.send_json(result)

            # Check if enrollment is complete
            if result.get("status") == "completed":
                logger.info(f"Enrollment complete for session: {session_id}")
                break

            await asyncio.sleep(1 / 30)

    except WebSocketDisconnect:
        logger.info("WebSocket enrollment stream disconnected")
    except Exception as e:
        logger.error(f"WebSocket enrollment error: {e}", exc_info=True)
