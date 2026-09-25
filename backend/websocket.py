"""WebSocket manager for real-time updates."""
from typing import Set, Dict, Any, Optional
import json
import logging
import asyncio
from datetime import datetime
from config import IST, settings
import redis.asyncio as redis

logger = logging.getLogger(__name__)


class WebSocketConnectionManager:
    """Manages WebSocket connections for real-time updates.
    If REDIS_URL is configured, acts as a distributed pub-sub relay.
    Otherwise, falls back to local in-memory broadcasting.
    """
    
    def __init__(self):
        # Track active connections by channel
        self.active_connections: Dict[str, Set[Any]] = {
            "alerts": set(),
            "cameras": set(),
            "kpis": set(),
            "forensic": set(),
        }
        self.redis: Optional[redis.Redis] = None
        self.pubsub: Optional[redis.client.PubSub] = None
        self.listener_task: Optional[asyncio.Task] = None

    async def startup(self):
        """Initialize Redis connection and start the listener task if enabled."""
        if settings.redis_url:
            logger.info("Connecting to Redis for Pub/Sub scaling...")
            try:
                self.redis = redis.from_url(settings.redis_url)
                self.pubsub = self.redis.pubsub()
                await self.pubsub.subscribe(*self.active_connections.keys())
                self.listener_task = asyncio.create_task(self._listen_to_redis())
                logger.info("Successfully connected to Redis Pub/Sub.")
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                self.redis = None

    async def shutdown(self):
        """Cleanup Redis connections."""
        if self.listener_task:
            self.listener_task.cancel()
        if self.pubsub:
            await self.pubsub.close()
        if self.redis:
            await self.redis.aclose()
            
    async def _listen_to_redis(self):
        """Background task that listens for Redis messages and relays them to local WebSockets."""
        if not self.pubsub:
            return
        try:
            async for message in self.pubsub.listen():
                if message["type"] == "message":
                    channel = message["channel"].decode("utf-8")
                    data = message["data"].decode("utf-8")
                    # Broadcast the raw JSON string payload received from Redis
                    await self._local_broadcast_raw(channel, data)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Redis listener task crashed: {e}")

    async def connect(self, channel: str, websocket):
        """Subscribe to a channel."""
        if channel not in self.active_connections:
            self.active_connections[channel] = set()
            if self.pubsub:
                await self.pubsub.subscribe(channel)
        self.active_connections[channel].add(websocket)
        await websocket.accept()
        logger.info(f"Client connected to {channel}: {len(self.active_connections[channel])} subscribers")
    
    async def disconnect(self, channel: str, websocket):
        """Unsubscribe from a channel."""
        self.active_connections[channel].discard(websocket)
        logger.info(f"Client disconnected from {channel}: {len(self.active_connections[channel])} subscribers")
    
    async def broadcast(self, channel: str, message: Dict[str, Any]):
        """Send message to all subscribers of a channel."""
        payload = json.dumps({
            "type": channel,
            "timestamp": datetime.now(IST).isoformat(),
            "data": message,
        })

        if self.redis:
            # Publish to Redis so all workers receive it
            await self.redis.publish(channel, payload)
        else:
            # Fall back to local broadcast
            await self._local_broadcast_raw(channel, payload)

    async def _local_broadcast_raw(self, channel: str, raw_payload: str):
        """Internal helper to push a raw string payload to local WebSocket connections."""
        if channel not in self.active_connections:
            return
            
        disconnected = []
        for connection in self.active_connections[channel]:
            try:
                await connection.send_text(raw_payload)
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
