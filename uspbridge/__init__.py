"""
USP Bridge Package

Provides abstract interfaces and concrete implementations for bridging
USP (User Services Platform) protocol to various transport/service protocols.

Current Implementations:
- WRP Bridge: Translates USP ↔ WRP (Web Routing Protocol) for RDK/Xfinity ecosystem
"""

from uspbridge.base import UspBridge
from uspbridge.wrp_bridge import WrpBridge

__all__ = [
    'UspBridge',
    'WrpBridge'
]
