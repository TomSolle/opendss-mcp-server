#!/usr/bin/env python3
"""
OpenDSS MCP Server.

Provides tools for power distribution system simulation and analysis using OpenDSS.
Supports power flow, fault studies, hosting capacity, QSTS, and visualization.
"""

from __future__ import annotations

import json
import os
import tempfile
from enum import Enum
from typing import Optional

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .dss_engine import DSSEngine

# ── Server initialization ───────────────────────────────────────────
mcp = FastMCP("opendss_mcp")

# Shared engine instance
_engine: DSSEngine | None = None


def _get_engine() -> DSSEngine:
    global _engine
    if _engine is None:
        _engine = DSSEngine()
    return _engine


def _output_dir() -> str:
    d = os.environ.get("OPENDSS_MCP_OUTPUT_DIR", tempfile.mkdtemp(prefix="opendss_mcp_"))
    os.makedirs(d, exist_ok=True)
    return d


# ── Enums ───────────────────────────────────────────────────────────


class ResponseFormat(str, Enum):
    MARKDOWN = "markdown"
    JSON = "json"


class HCMode(str, Enum):
    UNIFORM = "uniform"
    WORST_CASE = "worst_case"


# ── Input models ────────────────────────────────────────────────────


class CompileFileInput(BaseModel):
    """Input for compiling a DSS file from disk."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    dss_path: str = Field(..., description="Absolute path to the Master DSS file to compile")
    buscoords_path: Optional[str] = Field(default=None, description="Optional path to a BusCoords.csv file")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class CompileScriptInput(BaseModel):
    """Input for compiling DSS commands from a string."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    dss_script: str = Field(
        ...,
        description="Complete OpenDSS script text (multi-line) to compile and solve",
        min_length=10,
    )
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class RunCommandInput(BaseModel):
    """Input for running a single DSS text command."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    command: str = Field(..., description="OpenDSS text command to execute", min_length=1)


class VoltageInput(BaseModel):
    """Input for voltage queries."""

    model_config = ConfigDict(extra="forbid")

    kv_min: float = Field(default=1.0, description="Minimum kV base to include (filters LV buses)", ge=0)
    kv_max: float = Field(default=100.0, description="Maximum kV base to include", ge=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class FaultInput(BaseModel):
    """Input for a three-phase fault study."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    bus: str = Field(..., description="Name of the bus where the fault is applied (e.g., 'bus_410')", min_length=1)
    r_fault: float = Field(default=0.0001, description="Fault resistance in ohms (0.0001 = bolted fault)", ge=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class FaultSweepInput(BaseModel):
    """Input for fault sweep across multiple buses."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    buses: list[str] = Field(..., description="List of bus names to fault sequentially", min_length=1)
    r_fault: float = Field(default=0.0001, ge=0)
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class QSTSInput(BaseModel):
    """Input for quasi-static time series simulation."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    mode: str = Field(default="daily", description="Solution mode: daily, yearly, dutycycle")
    stepsize: str = Field(default="1h", description="Time step (e.g., '1h', '15m', '1s')")
    number: int = Field(default=24, description="Number of time steps to simulate", ge=1, le=87600)
    monitor_bus: Optional[str] = Field(default=None, description="Bus to monitor voltage over time")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        allowed = {"daily", "yearly", "dutycycle", "snapshot"}
        if v.lower() not in allowed:
            raise ValueError(f"Mode must be one of {allowed}")
        return v.lower()


class HostingCapacityInput(BaseModel):
    """Input for hosting capacity study."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    load_buses: list[str] = Field(..., description="List of bus names where PV can be connected", min_length=1)
    pv_kw_steps: list[float] = Field(
        ...,
        description="List of total PV capacities (kW) to test, e.g. [5, 10, 25, 50, 100]",
        min_length=1,
    )
    trafo_kva: float = Field(..., description="Transformer rated capacity in kVA", gt=0)
    mode: HCMode = Field(default=HCMode.UNIFORM, description="PV allocation mode")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


class PlotInput(BaseModel):
    """Input for generating plots."""

    model_config = ConfigDict(extra="forbid")

    plot_type: str = Field(..., description="Type of plot: 'voltage_profile' or 'topology'")
    kv_min: float = Field(default=1.0, ge=0)
    kv_max: float = Field(default=100.0, ge=0)

    @field_validator("plot_type")
    @classmethod
    def validate_plot_type(cls, v: str) -> str:
        allowed = {"voltage_profile", "topology"}
        if v.lower() not in allowed:
            raise ValueError(f"plot_type must be one of {allowed}")
        return v.lower()


# ── Formatting helpers ──────────────────────────────────────────────


def _format_dict(data: dict, fmt: ResponseFormat) -> str:
    if fmt == ResponseFormat.JSON:
        return json.dumps(data, indent=2, ensure_ascii=False)
    lines = []
    for k, v in data.items():
        if isinstance(v, float):
            lines.append(f"- **{k}**: {v:.4f}" if abs(v) < 1000 else f"- **{k}**: {v:,.1f}")
        else:
            lines.append(f"- **{k}**: {v}")
    return "\n".join(lines)


def _format_list(data: list[dict], fmt: ResponseFormat, title: str = "") -> str:
    if fmt == ResponseFormat.JSON:
        return json.dumps(data, indent=2, ensure_ascii=False)
    if not data:
        return "No results."
    lines = []
    if title:
        lines.append(f"# {title}\n")
    for i, item in enumerate(data):
        lines.append(f"## Entry {i + 1}")
        for k, v in item.items():
            if isinstance(v, float):
                lines.append(f"- **{k}**: {v:.4f}" if abs(v) < 1000 else f"- **{k}**: {v:,.1f}")
            else:
                lines.append(f"- **{k}**: {v}")
        lines.append("")
    return "\n".join(lines)


def _format_table_md(data: list[dict], title: str = "") -> str:
    if not data:
        return "No data."
    lines = []
    if title:
        lines.append(f"# {title}\n")
    keys = list(data[0].keys())
    lines.append("| " + " | ".join(keys) + " |")
    lines.append("| " + " | ".join(["---"] * len(keys)) + " |")
    for row in data:
        vals = []
        for k in keys:
            v = row.get(k, "")
            if isinstance(v, float):
                vals.append(f"{v:.4f}" if abs(v) < 1000 else f"{v:,.1f}")
            else:
                vals.append(str(v))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


# ── Tool: Compile DSS file ──────────────────────────────────────────


@mcp.tool(
    name="opendss_compile_file",
    annotations={
        "title": "Compile OpenDSS File",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def opendss_compile_file(params: CompileFileInput) -> str:
    """Compile an OpenDSS model from a .dss file on disk and run power flow.

    Loads the circuit, solves it in snapshot mode, and returns a summary
    with convergence status, bus/line/load counts, and total losses.

    Args:
        params: CompileFileInput with dss_path and optional buscoords_path.

    Returns:
        Circuit summary with convergence, counts, and losses.
    """
    try:
        engine = _get_engine()
        result = engine.compile(params.dss_path, params.buscoords_path)
        return _format_dict(result, params.response_format)
    except Exception as e:
        return f"Error compiling DSS file: {e}"


# ── Tool: Compile DSS script ────────────────────────────────────────


@mcp.tool(
    name="opendss_compile_script",
    annotations={
        "title": "Compile OpenDSS Script",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def opendss_compile_script(params: CompileScriptInput) -> str:
    """Compile an OpenDSS circuit from inline DSS commands and run power flow.

    Pass the complete DSS script as a multi-line string. The server writes it
    to a temporary file, compiles it, and solves in snapshot mode.

    Args:
        params: CompileScriptInput with the DSS script text.

    Returns:
        Circuit summary with convergence, counts, and losses.
    """
    try:
        engine = _get_engine()
        result = engine.compile_text(params.dss_script)
        return _format_dict(result, params.response_format)
    except Exception as e:
        return f"Error compiling DSS script: {e}"


# ── Tool: Run DSS command ───────────────────────────────────────────


@mcp.tool(
    name="opendss_run_command",
    annotations={
        "title": "Run OpenDSS Command",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def opendss_run_command(params: RunCommandInput) -> str:
    """Execute a single OpenDSS text command on the currently loaded circuit.

    Useful for modifying the circuit after compilation (adding elements,
    changing parameters, setting modes, etc.).

    Args:
        params: RunCommandInput with the DSS command string.

    Returns:
        The DSS result string, or confirmation of execution.
    """
    try:
        engine = _get_engine()
        result = engine.run_command(params.command)
        return result if result and result.strip() else f"Command executed: {params.command}"
    except Exception as e:
        return f"Error running command: {e}"


# ── Tool: Get bus voltages ──────────────────────────────────────────


@mcp.tool(
    name="opendss_get_voltages",
    annotations={
        "title": "Get Bus Voltages",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def opendss_get_voltages(params: VoltageInput) -> str:
    """Get voltage magnitude (pu) for all buses in the compiled circuit.

    Returns per-bus voltage data including average, min, max pu values,
    kV base, number of phases, distance from source, and coordinates.
    Filter by kv_base range to focus on MV or LV buses.

    Args:
        params: VoltageInput with kv_min/kv_max filters.

    Returns:
        Table of bus voltages sorted by voltage (ascending).
    """
    try:
        engine = _get_engine()
        buses = engine.get_bus_voltages()
        filtered = [b for b in buses if params.kv_min <= b["kv_base"] <= params.kv_max]
        filtered.sort(key=lambda b: b["v_avg_pu"])

        if params.response_format == ResponseFormat.JSON:
            return json.dumps(filtered, indent=2)
        return _format_table_md(filtered, "Bus Voltages")
    except Exception as e:
        return f"Error getting voltages: {e}"


# ── Tool: Voltage summary ──────────────────────────────────────────


@mcp.tool(
    name="opendss_voltage_summary",
    annotations={
        "title": "Voltage Summary Statistics",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def opendss_voltage_summary(params: VoltageInput) -> str:
    """Get voltage statistics: min, max, mean, std, violation counts.

    Provides a quick overview of the voltage regulation status including
    the number of buses below 0.95 pu and above 1.05 pu.

    Args:
        params: VoltageInput with kv_min/kv_max filters.

    Returns:
        Voltage statistics summary.
    """
    try:
        engine = _get_engine()
        summary = engine.get_voltage_summary(params.kv_min, params.kv_max)
        return _format_dict(summary, params.response_format)
    except Exception as e:
        return f"Error getting voltage summary: {e}"


# ── Tool: Get load powers ──────────────────────────────────────────


@mcp.tool(
    name="opendss_get_loads",
    annotations={
        "title": "Get Load Powers",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def opendss_get_loads(params: VoltageInput) -> str:
    """Get active and reactive power for every load in the circuit.

    Returns nominal and actual (solved) kW/kvar for each load element.

    Args:
        params: VoltageInput (only response_format is used).

    Returns:
        Table of load powers.
    """
    try:
        engine = _get_engine()
        loads = engine.get_load_powers()
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(loads, indent=2)
        return _format_table_md(loads, "Load Powers")
    except Exception as e:
        return f"Error getting loads: {e}"


# ── Tool: Get line flows ───────────────────────────────────────────


@mcp.tool(
    name="opendss_get_line_flows",
    annotations={
        "title": "Get Line Power Flows",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def opendss_get_line_flows(params: VoltageInput) -> str:
    """Get power flow (P, Q) and max current for every line.

    Useful for identifying overloaded lines and understanding power
    distribution across the network.

    Args:
        params: VoltageInput (only response_format is used).

    Returns:
        Table of line flows sorted by current (descending).
    """
    try:
        engine = _get_engine()
        lines = engine.get_line_flows()
        lines.sort(key=lambda line: line["i_max_a"], reverse=True)
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(lines, indent=2)
        return _format_table_md(lines, "Line Power Flows")
    except Exception as e:
        return f"Error getting line flows: {e}"


# ── Tool: Three-phase fault ────────────────────────────────────────


@mcp.tool(
    name="opendss_fault_3ph",
    annotations={
        "title": "Run Three-Phase Fault Study",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def opendss_fault_3ph(params: FaultInput) -> str:
    """Run a three-phase fault at a specific bus.

    Applies a 3-phase fault with specified resistance and returns fault
    currents (per phase), short-circuit power (Scc), and voltage sag impact
    (number of buses below 0.80 and 0.50 pu during the fault).

    The circuit must be compiled first with opendss_compile_file or _script.

    Args:
        params: FaultInput with bus name and fault resistance.

    Returns:
        Fault currents, Scc, and voltage impact summary.
    """
    try:
        engine = _get_engine()
        result = engine.run_fault_3ph(params.bus, params.r_fault)
        return _format_dict(result, params.response_format)
    except Exception as e:
        return f"Error running fault study: {e}"


# ── Tool: Fault sweep ──────────────────────────────────────────────


@mcp.tool(
    name="opendss_fault_sweep",
    annotations={
        "title": "Run Fault Sweep Across Buses",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def opendss_fault_sweep(params: FaultSweepInput) -> str:
    """Run three-phase faults at multiple buses to build a fault current curve.

    Re-compiles the circuit for each bus to get clean, independent results.
    Useful for plotting Icc vs distance or sizing protection equipment.

    Args:
        params: FaultSweepInput with list of buses.

    Returns:
        Table of fault currents and Scc per bus.
    """
    try:
        engine = _get_engine()
        results = engine.run_fault_sweep(params.buses, params.r_fault)
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(results, indent=2)
        return _format_table_md(results, "Fault Sweep Results (3-Phase)")
    except Exception as e:
        return f"Error running fault sweep: {e}"


# ── Tool: QSTS ─────────────────────────────────────────────────────


@mcp.tool(
    name="opendss_run_qsts",
    annotations={
        "title": "Run Quasi-Static Time Series Simulation",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def opendss_run_qsts(params: QSTSInput) -> str:
    """Run a quasi-static time series (QSTS) simulation.

    Requires LoadShapes to be defined in the circuit model. Supports
    daily (24h), yearly (8760h), and dutycycle modes.

    The circuit must be compiled first. LoadShapes must already be
    defined in the DSS model for time-varying behavior.

    Args:
        params: QSTSInput with mode, stepsize, number of steps.

    Returns:
        Convergence status and final-state voltage summary.
    """
    try:
        engine = _get_engine()
        result = engine.run_qsts(
            mode=params.mode,
            stepsize=params.stepsize,
            number=params.number,
            monitor_bus=params.monitor_bus,
        )
        return _format_dict(result, params.response_format)
    except Exception as e:
        return f"Error running QSTS: {e}"


# ── Tool: Hosting Capacity ─────────────────────────────────────────


@mcp.tool(
    name="opendss_hosting_capacity",
    annotations={
        "title": "Run Hosting Capacity Study",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def opendss_hosting_capacity(params: HostingCapacityInput) -> str:
    """Run a hosting capacity study by incrementally adding PV generation.

    Tests multiple PV penetration levels and reports voltage impact.
    Supports uniform distribution (equal PV per bus) and worst-case
    (all PV at the farthest bus).

    The circuit must be compiled from a file first (not from script).

    Args:
        params: HostingCapacityInput with bus list, PV steps, and transformer kVA.

    Returns:
        Table with penetration %, Vmax, Vmin, and violation counts per PV level.
    """
    try:
        engine = _get_engine()
        results = engine.run_hosting_capacity(
            load_buses=params.load_buses,
            pv_kw_steps=params.pv_kw_steps,
            trafo_kva=params.trafo_kva,
            mode=params.mode.value,
        )
        if params.response_format == ResponseFormat.JSON:
            return json.dumps(results, indent=2)
        return _format_table_md(results, "Hosting Capacity Results")
    except Exception as e:
        return f"Error running hosting capacity: {e}"


# ── Tool: Generate plot ─────────────────────────────────────────────


@mcp.tool(
    name="opendss_plot",
    annotations={
        "title": "Generate Voltage Plot",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def opendss_plot(params: PlotInput) -> str:
    """Generate a voltage visualization plot and save it as PNG.

    Supported plot types:
    - voltage_profile: Scatter plot of voltage vs distance from substation.
    - topology: Georeferenced network map colored by voltage level.

    The circuit must be compiled and solved first.

    Args:
        params: PlotInput with plot_type and kv_base filters.

    Returns:
        Path to the generated PNG image file.
    """
    try:
        engine = _get_engine()
        outdir = _output_dir()
        output_path = os.path.join(outdir, f"{params.plot_type}.png")

        if params.plot_type == "voltage_profile":
            result = engine.plot_voltage_profile(output_path, params.kv_min, params.kv_max)
        elif params.plot_type == "topology":
            result = engine.plot_topology(output_path, params.kv_min, params.kv_max)
        else:
            return f"Unknown plot type: {params.plot_type}"

        return f"Plot saved to: {result}"
    except Exception as e:
        return f"Error generating plot: {e}"


# ── Entry point ─────────────────────────────────────────────────────


def main():
    mcp.run()


if __name__ == "__main__":
    main()
