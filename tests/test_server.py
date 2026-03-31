"""Tests for the MCP server tool functions."""

from __future__ import annotations

import json
import os

import pytest

from opendss_mcp.server import (
    CompileFileInput,
    CompileScriptInput,
    RunCommandInput,
    VoltageInput,
    FaultInput,
    PlotInput,
    ResponseFormat,
    opendss_compile_file,
    opendss_compile_script,
    opendss_run_command,
    opendss_get_voltages,
    opendss_voltage_summary,
    opendss_get_loads,
    opendss_get_line_flows,
    opendss_fault_3ph,
    opendss_plot,
)

EXAMPLES_DIR = os.path.join(os.path.dirname(__file__), "..", "examples", "ieee13")
IEEE13_DSS = os.path.abspath(os.path.join(EXAMPLES_DIR, "IEEE13Nodesv2.dss"))
IEEE13_BUSCOORDS = os.path.abspath(os.path.join(EXAMPLES_DIR, "BusCoords.csv"))


@pytest.mark.asyncio
async def test_compile_file_tool():
    params = CompileFileInput(
        dss_path=IEEE13_DSS,
        buscoords_path=IEEE13_BUSCOORDS,
        response_format=ResponseFormat.JSON,
    )
    result = await opendss_compile_file(params)
    data = json.loads(result)
    assert data["converged"] is True
    assert data["n_buses"] > 0


@pytest.mark.asyncio
async def test_compile_script_tool():
    script = """
    Clear
    New Circuit.test bus1=src basekv=12.47 pu=1.0
    New Load.ld1 bus1=src phases=3 kv=12.47 kw=100 kvar=50
    Solve
    """
    params = CompileScriptInput(dss_script=script, response_format=ResponseFormat.JSON)
    result = await opendss_compile_script(params)
    data = json.loads(result)
    assert data["converged"] is True


@pytest.mark.asyncio
async def test_get_voltages_tool():
    # Compile first
    await opendss_compile_file(
        CompileFileInput(dss_path=IEEE13_DSS, buscoords_path=IEEE13_BUSCOORDS)
    )
    params = VoltageInput(kv_min=1, kv_max=100, response_format=ResponseFormat.JSON)
    result = await opendss_get_voltages(params)
    data = json.loads(result)
    assert len(data) > 0
    assert "bus" in data[0]


@pytest.mark.asyncio
async def test_voltage_summary_tool():
    await opendss_compile_file(
        CompileFileInput(dss_path=IEEE13_DSS, buscoords_path=IEEE13_BUSCOORDS)
    )
    params = VoltageInput(kv_min=1, kv_max=100, response_format=ResponseFormat.JSON)
    result = await opendss_voltage_summary(params)
    data = json.loads(result)
    assert "n_buses" in data
    assert "v_min_pu" in data


@pytest.mark.asyncio
async def test_get_loads_tool():
    await opendss_compile_file(
        CompileFileInput(dss_path=IEEE13_DSS, buscoords_path=IEEE13_BUSCOORDS)
    )
    params = VoltageInput(response_format=ResponseFormat.JSON)
    result = await opendss_get_loads(params)
    data = json.loads(result)
    assert len(data) > 0
    assert "load" in data[0]


@pytest.mark.asyncio
async def test_get_line_flows_tool():
    await opendss_compile_file(
        CompileFileInput(dss_path=IEEE13_DSS, buscoords_path=IEEE13_BUSCOORDS)
    )
    params = VoltageInput(response_format=ResponseFormat.JSON)
    result = await opendss_get_line_flows(params)
    data = json.loads(result)
    assert len(data) > 0
    assert "line" in data[0]


@pytest.mark.asyncio
async def test_fault_3ph_tool():
    await opendss_compile_file(
        CompileFileInput(dss_path=IEEE13_DSS, buscoords_path=IEEE13_BUSCOORDS)
    )
    params = FaultInput(bus="680", response_format=ResponseFormat.JSON)
    result = await opendss_fault_3ph(params)
    data = json.loads(result)
    assert data["fault_bus"] == "680"
    assert data["i_fault_a"] > 0


@pytest.mark.asyncio
async def test_run_command_tool():
    await opendss_compile_file(
        CompileFileInput(dss_path=IEEE13_DSS, buscoords_path=IEEE13_BUSCOORDS)
    )
    params = RunCommandInput(command="Solve")
    result = await opendss_run_command(params)
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_plot_tool():
    await opendss_compile_file(
        CompileFileInput(dss_path=IEEE13_DSS, buscoords_path=IEEE13_BUSCOORDS)
    )
    params = PlotInput(plot_type="voltage_profile", kv_min=1, kv_max=100)
    result = await opendss_plot(params)
    assert "Plot saved to" in result or "Error" not in result


@pytest.mark.asyncio
async def test_markdown_format():
    params = CompileFileInput(
        dss_path=IEEE13_DSS,
        buscoords_path=IEEE13_BUSCOORDS,
        response_format=ResponseFormat.MARKDOWN,
    )
    result = await opendss_compile_file(params)
    assert "**converged**" in result
    assert "**n_buses**" in result
