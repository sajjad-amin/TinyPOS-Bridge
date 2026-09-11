"""
TinyPOS Client WebSocket API Route
Provides real-time bidirectional WebSocket connection for store client software.
Authenticates client requests via configured API key and delegates messages to relay_manager.
"""

import datetime
import logging
from typing import Optional
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

import server.db as db
from server.services.relay_manager import relay_manager

logger = logging.getLogger("tinypos.ws")

websocket_api_router = APIRouter()


@websocket_api_router.websocket("/ws/client")
async def websocket_client_endpoint(
    websocket: WebSocket,
    api_key: Optional[str] = Query(None),
    client_name: Optional[str] = Query("Store POS Client"),
):
    """
    WebSocket endpoint for store client machines.
    Expected connection URL: wss://<domain>/ws/client?api_key=<API_KEY>&client_name=<NAME>
    """
    # 1. Fallback to headers if query param is not supplied
    if not api_key:
        api_key = websocket.headers.get("x-api-key") or websocket.headers.get("authorization", "").replace("Bearer ", "").strip()

    # 2. Authenticate strictly against dedicated client_api_keys table
    client_entry = db.get_client_api_key(api_key)
    if not client_entry:
        logger.warning(f"WebSocket connection rejected: unauthorized client API key '{api_key}'")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized: Invalid Client API key")
        return

    # 3. Resolve client display name and assigned group
    key_name = client_entry["name"]
    client_group = client_entry.get("group_name")
    resolved_name = client_name.strip() if (client_name and client_name.strip() and client_name != "Store POS Client") else key_name

    # 4. Resolve client IP (support reverse proxy headers)
    client_ip = websocket.client.host if websocket.client else "unknown"
    x_forwarded_for = websocket.headers.get("x-forwarded-for")
    if x_forwarded_for:
        client_ip = x_forwarded_for.split(",")[0].strip()

    # 5. Accept connection & register client terminal
    await websocket.accept()
    client_id = await relay_manager.register(
        websocket=websocket,
        client_name=resolved_name,
        key_name=key_name,
        client_ip=client_ip,
        api_key=api_key,
        group=client_group,
    )

    # 6. Send welcome acknowledgement with client_id and group
    try:
        await websocket.send_json({
            "type": "welcome",
            "client_id": client_id,
            "client_name": resolved_name,
            "key_name": key_name,
            "group": client_group,
            "message": f"Successfully authenticated with TinyPOS Cloud Relay as '{resolved_name}'" + (f" (Group: {client_group})" if client_group else ""),
            "server_version": "1.3.0",
            "server_time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        })
    except Exception as e:
        logger.error(f"Failed to send welcome message to client: {e}")
        await relay_manager.unregister(websocket)
        return

    # 7. Listen for messages until disconnect
    try:
        while True:
            data = await websocket.receive_json()
            if isinstance(data, dict):
                await relay_manager.handle_client_message(websocket, data)
    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected cleanly: {client_ip}")
    except Exception as e:
        logger.warning(f"WebSocket error for client {client_ip}: {e}")
    finally:
        await relay_manager.unregister(websocket)
