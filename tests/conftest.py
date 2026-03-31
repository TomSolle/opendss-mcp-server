"""Shared fixtures for opendss-mcp tests."""

from __future__ import annotations

import os
import pytest

from opendss_mcp.dss_engine import DSSEngine

EXAMPLES_DIR = os.path.join(os.path.dirname(__file__), "..", "examples", "ieee13")
IEEE13_DSS = os.path.abspath(os.path.join(EXAMPLES_DIR, "IEEE13Nodesv2.dss"))
IEEE13_BUSCOORDS = os.path.abspath(os.path.join(EXAMPLES_DIR, "BusCoords.csv"))

# Single shared engine to avoid COM threading conflicts on Windows.
# py-dss-interface uses COM (win32com) and multiple DSS() instances
# in the same process can cause RPC_E_CANTCALLOUT_ININPUTSYNCCALL (0x8001010d).
_shared_engine = DSSEngine()


@pytest.fixture
def engine() -> DSSEngine:
    """Return the shared DSSEngine instance."""
    return _shared_engine


@pytest.fixture
def compiled_engine() -> DSSEngine:
    """Return the shared engine with the IEEE 13-node feeder compiled and solved."""
    _shared_engine.compile(IEEE13_DSS, IEEE13_BUSCOORDS)
    return _shared_engine
