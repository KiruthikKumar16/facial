"""WebSocket manager for real-time updates."""
from typing import Set, List, Dict, Any
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class WebSocketConnectionManager:
    """Manages WebSocket connections for real-time updates."""
    
    def __init__(self):
        # Track active connections by channel
        self.active_connections: Dict[str, Set[Any]] = {
            "alerts": set(),
            "cameras": set(),
            "kpis": set(),
            "forensic": set(),
        }
    
    async def connect(self, channel: str, websocket):
        """Subscribe to a channel."""
        if channel not in self.active_connections:
            self.active_connections[channel] = set()
        self.active_connections[channel].add(websocket)
        await websocket.accept()
        logger.info(f"Client connected to {channel}: {len(self.active_connections[channel])} subscribers")
    
    async def disconnect(self, channel: str, websocket):
        """Unsubscribe from a channel."""
        self.active_connections[channel].discard(websocket)
        logger.info(f"Client disconnected from {channel}: {len(self.active_connections[channel])} subscribers")
    
    async def broadcast(self, channel: str, message: Dict[str, Any]):
        """Send message to all subscribers of a channel."""
        if channel not in self.active_connections:
            return
        
        payload = json.dumps({
            "type": channel,
            "timestamp": datetime.utcnow().isoformat(),
            "data": message,
        })
        
        # Remove dead connections
        disconnected = []
        for connection in self.active_connections[channel]:
            try:
                await connection.send_text(payload)
            except Exception as e:
                logger.warning(f"Failed to send to {channel}: {e}")
                disconnected.append(connection)
        
        # Clean up
        for conn in disconnected:
            await self.disconnect(channel, conn)
    
    async def send_personal(self, websocket, message: Dict[str, Any]):
        """Send message to a specific connection."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Failed to send personal message: {e}")


# Global manager instance
manager = WebSocketConnectionManager()
