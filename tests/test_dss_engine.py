"""Tests for the DSSEngine wrapper."""

from __future__ import annotations

import os
import tempfile

import pytest

from opendss_mcp.dss_engine import DSSEngine
from conftest import IEEE13_DSS, IEEE13_BUSCOORDS


class TestEngineInit:
    def test_engine_creates(self):
        engine = DSSEngine()
        assert engine.dss is not None

    def test_engine_workdir_none(self):
        engine = DSSEngine()
        assert engine._workdir is None


class TestCompile:
    def test_compile_ieee13(self, engine: DSSEngine):
        result = engine.compile(IEEE13_DSS, IEEE13_BUSCOORDS)
        assert result["converged"] is True
        assert result["n_buses"] > 0
        assert result["n_lines"] > 0
        assert result["n_loads"] > 0
        assert "losses_kw" in result
        assert "losses_kvar" in result

    def test_compile_sets_workdir(self, engine: DSSEngine):
        engine.compile(IEEE13_DSS)
        assert engine._workdir is not None
        assert os.path.isdir(engine._workdir)

    def test_compile_text(self, engine: DSSEngine):
        script = """
        Clear
        New Circuit.test bus1=src basekv=12.47 pu=1.0
        New Line.line1 bus1=src bus2=load1 length=1 units=km
        New Linecode.default nphases=3 r1=0.1 x1=0.1
        New Load.ld1 bus1=load1 phases=3 kv=12.47 kw=100 kvar=50
        Set voltagebases=[12.47]
        Calcvoltagebases
        Solve
        """
        result = engine.compile_text(script)
        assert result["converged"] is True
        assert result["n_buses"] >= 2


class TestVoltages:
    def test_get_bus_voltages(self, compiled_engine: DSSEngine):
        voltages = compiled_engine.get_bus_voltages()
        assert len(voltages) > 0
        bus = voltages[0]
        assert "bus" in bus
        assert "kv_base" in bus
        assert "v_avg_pu" in bus
        assert "v_min_pu" in bus
        assert "v_max_pu" in bus
        assert "distance_km" in bus
        assert "n_phases" in bus

    def test_voltages_in_range(self, compiled_engine: DSSEngine):
        voltages = compiled_engine.get_bus_voltages()
        for bus in voltages:
            assert 0.5 < bus["v_avg_pu"] < 1.5, f"Unexpected voltage at {bus['bus']}"

    def test_voltage_summary(self, compiled_engine: DSSEngine):
        summary = compiled_engine.get_voltage_summary(kv_min=1, kv_max=100)
        assert "n_buses" in summary
        assert "v_min_pu" in summary
        assert "v_max_pu" in summary
        assert "v_avg_pu" in summary
        assert "v_std_pu" in summary
        assert "buses_below_095" in summary
        assert "buses_above_105" in summary
        assert "worst_bus" in summary
        assert "best_bus" in summary
        assert summary["n_buses"] > 0

    def test_voltage_summary_empty_range(self, compiled_engine: DSSEngine):
        summary = compiled_engine.get_voltage_summary(kv_min=999, kv_max=1000)
        assert "error" in summary


class TestLoads:
    def test_get_load_powers(self, compiled_engine: DSSEngine):
        loads = compiled_engine.get_load_powers()
        assert len(loads) > 0
        load = loads[0]
        assert "load" in load
        assert "bus" in load
        assert "kw_nominal" in load
        assert "kvar_nominal" in load
        assert "kw_actual" in load
        assert "kvar_actual" in load


class TestLineFlows:
    def test_get_line_flows(self, compiled_engine: DSSEngine):
        lines = compiled_engine.get_line_flows()
        assert len(lines) > 0
        line = lines[0]
        assert "line" in line
        assert "bus1" in line
        assert "bus2" in line
        assert "p_kw" in line
        assert "q_kvar" in line
        assert "i_max_a" in line
        assert "length_km" in line


class TestFault:
    def test_fault_3ph(self, compiled_engine: DSSEngine):
        buses = compiled_engine.get_bus_voltages()
        # Pick a bus that has kv_base > 1 (MV bus)
        mv_buses = [b for b in buses if b["kv_base"] > 1]
        assert len(mv_buses) > 0
        bus_name = mv_buses[0]["bus"]

        result = compiled_engine.run_fault_3ph(bus_name)
        assert result["fault_bus"] == bus_name
        assert result["fault_type"] == "3-phase"
        assert result["i_fault_a"] > 0
        assert result["scc_mva"] > 0
        assert "buses_below_80pct" in result
        assert "buses_below_50pct" in result

    def test_fault_sweep(self, compiled_engine: DSSEngine):
        buses = compiled_engine.get_bus_voltages()
        mv_buses = [b["bus"] for b in buses if b["kv_base"] > 1][:3]
        assert len(mv_buses) > 0

        results = compiled_engine.run_fault_sweep(mv_buses)
        assert len(results) == len(mv_buses)
        for r in results:
            assert r["i_fault_a"] > 0


class TestRunCommand:
    def test_run_command(self, compiled_engine: DSSEngine):
        result = compiled_engine.run_command("Solve")
        assert isinstance(result, str)


class TestPlot:
    def test_voltage_profile_plot(self, compiled_engine: DSSEngine):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "voltage_profile.png")
            result = compiled_engine.plot_voltage_profile(path, kv_min=1, kv_max=100)
            assert os.path.exists(result)
            assert result.endswith(".png")

    def test_topology_plot(self, compiled_engine: DSSEngine):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "topology.png")
            result = compiled_engine.plot_topology(path, kv_min=1, kv_max=100)
            assert os.path.exists(result)
            assert result.endswith(".png")


class TestHostingCapacity:
    def test_hosting_capacity_uniform(self, compiled_engine: DSSEngine):
        loads = compiled_engine.get_load_powers()
        load_buses = [l["bus"] for l in loads[:3]]
        assert len(load_buses) > 0

        results = compiled_engine.run_hosting_capacity(
            load_buses=load_buses,
            pv_kw_steps=[10, 50, 100],
            trafo_kva=500,
            mode="uniform",
        )
        assert len(results) == 3
        for r in results:
            assert "pv_total_kw" in r
            assert "penetration_pct" in r
            assert "v_min_pu" in r
            assert "v_max_pu" in r
