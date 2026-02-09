"""
Copyright (c) 2026

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

# File Name: uds_async.py
#
# Description: Async Unix Domain Socket transport for USP
#
"""

import os
import asyncio
import logging
import struct
from collections import deque
from typing import Deque, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Maximum message size (64KB) for legacy length-prefixed framing
MAX_MESSAGE_SIZE = 65536

# ServiceSdk UDS framing: "_USP" + u32be payload length + TLVs
SERVICESDK_SYNC = b"_USP"
SERVICESDK_TLV_HANDSHAKE = 1
SERVICESDK_TLV_ERROR = 2
SERVICESDK_TLV_RECORD = 3
MAX_SERVICESDK_FRAME_SIZE = 16 * 1024 * 1024


class UdsTransport:
    """Async Unix Domain Socket transport.

    Supports two wire formats:
    - framing='length-prefix' (default): 4-byte big-endian length + USP Record bytes
    - framing='servicesdk': "_USP" sync + u32be payload length + TLVs (handshake/record/error)
    """

    def __init__(self, socket_path, mode='listen', *, endpoint_id: Optional[str] = None, framing: str = 'length-prefix'):
        """
        Initialize UDS transport
        
        Args:
            socket_path (str): Path to Unix socket
            mode (str): 'listen' or 'connect'
            endpoint_id (str|None): Local endpoint id (required for 'servicesdk' handshake)
            framing (str): 'length-prefix' or 'servicesdk'
        """
        self.socket_path = socket_path
        self.mode = mode
        self.endpoint_id = endpoint_id
        self.framing = (framing or 'length-prefix').lower().strip()
        if self.framing not in ('length-prefix', 'servicesdk'):
            raise ValueError(f"Unknown UDS framing: {self.framing}")

        self.server = None
        self.reader = None
        self.writer = None

        # For servicesdk framing, populated after handshake.
        self.peer_endpoint_id: Optional[str] = None

        self._servicesdk_pending_records: Deque[bytes] = deque()

    @staticmethod
    def _servicesdk_encode_frame(tlvs: Iterable[Tuple[int, bytes]]) -> bytes:
        tlv_list = list(tlvs)
        if not tlv_list:
            raise ValueError("Frame contains no TLVs")

        payload = bytearray()
        for tlv_type, tlv_value in tlv_list:
            if not (0 <= int(tlv_type) <= 255):
                raise ValueError("Invalid TLV type")
            if not isinstance(tlv_value, (bytes, bytearray, memoryview)):
                raise ValueError("TLV value must be bytes")
            payload.append(int(tlv_type))
            payload.extend(struct.pack('!I', len(tlv_value)))
            payload.extend(bytes(tlv_value))

        return SERVICESDK_SYNC + struct.pack('!I', len(payload)) + bytes(payload)

    @staticmethod
    def _servicesdk_decode_frame(frame: bytes) -> List[Tuple[int, bytes]]:
        if len(frame) < 8:
            raise ValueError("Truncated frame header")
        if frame[:4] != SERVICESDK_SYNC:
            raise ValueError("Bad sync bytes")

        payload_len = struct.unpack('!I', frame[4:8])[0]
        if len(frame) != 8 + payload_len:
            raise ValueError("Frame length mismatch")

        payload = frame[8:]
        idx = 0
        tlvs: List[Tuple[int, bytes]] = []
        while idx < len(payload):
            if idx + 5 > len(payload):
                raise ValueError("Truncated TLV header")
            tlv_type = payload[idx]
            tlv_len = struct.unpack('!I', payload[idx + 1:idx + 5])[0]
            idx += 5
            if idx + tlv_len > len(payload):
                raise ValueError("Truncated TLV value")
            tlvs.append((tlv_type, payload[idx:idx + tlv_len]))
            idx += tlv_len

        if not tlvs:
            raise ValueError("Frame contains no TLVs")
        return tlvs

    async def _servicesdk_read_frame(self, reader: asyncio.StreamReader, *, max_frame_size: int = MAX_SERVICESDK_FRAME_SIZE) -> Optional[bytes]:
        try:
            header = await reader.readexactly(8)
        except asyncio.IncompleteReadError:
            return None

        if header[:4] != SERVICESDK_SYNC:
            raise ValueError("Bad sync bytes")

        payload_len = struct.unpack('!I', header[4:8])[0]
        if payload_len > max_frame_size:
            raise ValueError("Frame too large")

        try:
            payload = await reader.readexactly(payload_len)
        except asyncio.IncompleteReadError:
            return None

        return header + payload

    async def _servicesdk_send_handshake(self, writer: asyncio.StreamWriter) -> None:
        if not self.endpoint_id:
            raise RuntimeError("endpoint_id is required for servicesdk UDS handshake")
        frame = self._servicesdk_encode_frame([(SERVICESDK_TLV_HANDSHAKE, self.endpoint_id.encode('utf-8'))])
        writer.write(frame)
        await writer.drain()

    async def _servicesdk_wait_for_handshake(self, reader: asyncio.StreamReader, *, timeout_seconds: float = 30.0) -> str:
        async def _wait() -> str:
            while True:
                frame = await self._servicesdk_read_frame(reader)
                if frame is None:
                    raise RuntimeError("Connection closed before handshake")
                tlvs = self._servicesdk_decode_frame(frame)
                for tlv_type, tlv_value in tlvs:
                    if tlv_type == SERVICESDK_TLV_ERROR:
                        msg = tlv_value.decode('utf-8', errors='replace')
                        raise RuntimeError(f"UDS error during handshake: {msg}")
                    if tlv_type == SERVICESDK_TLV_RECORD:
                        # Don't lose records that arrive early.
                        self._servicesdk_pending_records.append(bytes(tlv_value))
                    if tlv_type == SERVICESDK_TLV_HANDSHAKE:
                        return tlv_value.decode('utf-8', errors='replace')

        return await asyncio.wait_for(_wait(), timeout=timeout_seconds)
        
    async def start_server(self, message_callback):
        """
        Start listening for connections (server mode)
        
        Args:
            message_callback: Async callback function(data) for received messages
        """
        if self.mode != 'listen':
            raise ValueError("start_server() only valid in listen mode")
        
        # Remove old socket if exists
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)

        async def handle_client(reader, writer):
            """Handle individual client connection"""
            addr = writer.get_extra_info('peername')
            logger.info(f"UDS connection accepted from {addr}")

            try:
                if self.framing == 'servicesdk':
                    if not self.endpoint_id:
                        raise RuntimeError("endpoint_id is required for servicesdk framing")

                    # Wait for client handshake, then respond with our handshake.
                    peer_endpoint_id = None
                    while peer_endpoint_id is None:
                        frame = await self._servicesdk_read_frame(reader)
                        if frame is None:
                            return
                        tlvs = self._servicesdk_decode_frame(frame)
                        for tlv_type, tlv_value in tlvs:
                            if tlv_type == SERVICESDK_TLV_ERROR:
                                return
                            if tlv_type == SERVICESDK_TLV_HANDSHAKE:
                                peer_endpoint_id = tlv_value.decode('utf-8', errors='replace')
                                break
                            # Ignore record TLVs until handshake is complete.

                    logger.info(f"UDS servicesdk handshake from peer: {peer_endpoint_id}")
                    await self._servicesdk_send_handshake(writer)

                    while True:
                        frame = await self._servicesdk_read_frame(reader)
                        if frame is None:
                            return
                        tlvs = self._servicesdk_decode_frame(frame)
                        for tlv_type, tlv_value in tlvs:
                            if tlv_type == SERVICESDK_TLV_ERROR:
                                msg = tlv_value.decode('utf-8', errors='replace')
                                logger.error(f"UDS servicesdk error from peer: {msg}")
                                return
                            if tlv_type == SERVICESDK_TLV_RECORD:
                                await message_callback(bytes(tlv_value), writer)
                    
                # Legacy length-prefixed framing
                while True:
                    # Read 4-byte length prefix
                    length_data = await reader.readexactly(4)
                    msg_length = struct.unpack('!I', length_data)[0]

                    if msg_length > MAX_MESSAGE_SIZE:
                        logger.error(f"Message too large: {msg_length} bytes")
                        break

                    # Read message payload
                    data = await reader.readexactly(msg_length)
                    logger.debug(f"Received {len(data)} bytes")

                    # Process message
                    await message_callback(data, writer)

            except asyncio.IncompleteReadError:
                logger.debug("Connection closed by peer")
            except Exception as e:
                logger.error(f"Error handling client: {e}", exc_info=True)
            finally:
                writer.close()
                await writer.wait_closed()
        
        # Start Unix socket server
        self.server = await asyncio.start_unix_server(
            handle_client,
            path=self.socket_path
        )
        
        logger.info(f"UDS server listening on: {self.socket_path}")
        
    async def connect(self):
        """Connect to UDS server (client mode)"""
        if self.mode != 'connect':
            raise ValueError("connect() only valid in connect mode")
        
        self.reader, self.writer = await asyncio.open_unix_connection(
            path=self.socket_path
        )
        logger.info(f"Connected to UDS server: {self.socket_path}")

        if self.framing == 'servicesdk':
            # ServiceSdk framing requires a handshake exchange before records are sent/processed.
            await self._servicesdk_send_handshake(self.writer)
            peer_id = await self._servicesdk_wait_for_handshake(self.reader)
            self.peer_endpoint_id = peer_id
            logger.info(f"UDS servicesdk handshake complete (peer={peer_id})")
        
    async def send_message(self, data, writer=None):
        """
        Send message with length prefix
        
        Args:
            data (bytes): Message to send
            writer: StreamWriter (if None, uses self.writer)
        """
        target_writer = writer or self.writer
        
        if not target_writer:
            raise RuntimeError("No connection available")
        
        if self.framing == 'servicesdk':
            frame = self._servicesdk_encode_frame([(SERVICESDK_TLV_RECORD, data)])
            target_writer.write(frame)
            await target_writer.drain()
            logger.debug(f"Sent servicesdk record {len(data)} bytes")
            return

        # Legacy length-prefixed framing
        msg_length = len(data)
        length_prefix = struct.pack('!I', msg_length)

        # Send length + data
        target_writer.write(length_prefix + data)
        await target_writer.drain()

        logger.debug(f"Sent {msg_length} bytes")
    
    async def receive_message(self, reader=None):
        """
        Receive message with length prefix
        
        Args:
            reader: StreamReader (if None, uses self.reader)
            
        Returns:
            bytes: Received message data
        """
        target_reader = reader or self.reader
        
        if not target_reader:
            raise RuntimeError("No connection available")
        
        if self.framing == 'servicesdk':
            if self._servicesdk_pending_records:
                return self._servicesdk_pending_records.popleft()

            while True:
                frame = await self._servicesdk_read_frame(target_reader)
                if frame is None:
                    logger.debug("Connection closed by peer")
                    return None

                tlvs = self._servicesdk_decode_frame(frame)
                for tlv_type, tlv_value in tlvs:
                    if tlv_type == SERVICESDK_TLV_ERROR:
                        msg = tlv_value.decode('utf-8', errors='replace')
                        raise ValueError(f"UDS servicesdk error: {msg}")
                    if tlv_type == SERVICESDK_TLV_RECORD:
                        self._servicesdk_pending_records.append(bytes(tlv_value))
                    # Ignore handshake TLVs at this stage.

                if self._servicesdk_pending_records:
                    return self._servicesdk_pending_records.popleft()

        try:
            # Read 4-byte length prefix
            length_data = await target_reader.readexactly(4)
            msg_length = struct.unpack('!I', length_data)[0]

            if msg_length > MAX_MESSAGE_SIZE:
                raise ValueError(f"Message too large: {msg_length} bytes")

            # Read message data
            data = await target_reader.readexactly(msg_length)
            logger.debug(f"Received {msg_length} bytes")

            return data

        except asyncio.IncompleteReadError:
            logger.debug("Connection closed by peer")
            return None
        
    async def close(self):
        """Close connection and clean up"""
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
            
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            
        if os.path.exists(self.socket_path) and self.mode == 'listen':
            os.unlink(self.socket_path)
            logger.info(f"Removed socket file: {self.socket_path}")
        
        logger.info("UDS transport closed")
