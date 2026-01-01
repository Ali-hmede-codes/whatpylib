"""
Protobuf package init.
"""

try:
    from . import wa_pb2
except ImportError:
    # Fallback if not compiled
    wa_pb2 = None

__all__ = ["wa_pb2"]
