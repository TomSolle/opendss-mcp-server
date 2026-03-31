"""
Core OpenDSS engine wrapper.

Provides a managed DSS instance with helper methods for circuit compilation,
voltage extraction, fault studies, and QSTS simulation.
"""

from __future__ import annotations

import os
import tempfile
from typing import Any

import numpy as np
from py_dss_interface import DSS


class DSSEngine:
    """Wrapper around py-dss-interface providing high-level analysis methods."""

    def __init__(self) -> None:
        self.dss = DSS()
        self._workdir: str | None = None

    # ── Circuit management ──────────────────────────────────────────

    def compile(self, dss_path: str, buscoords_path: str | None = None) -> dict[str, Any]:
        """Compile a DSS file and optionally load bus coordinates.

        Returns:
            dict with keys: converged, n_buses, n_lines, n_loads, n_elements
        """
        self.dss.text(f"Compile [{dss_path}]")
        self._workdir = os.path.dirname(dss_path)

        if buscoords_path and os.path.exists(buscoords_path):
            self.dss.text(f"Buscoords [{buscoords_path}]")

        self.dss.text("Solve")
        return self._circuit_summary()

    def compile_text(self, dss_script: str, workdir: str | None = None) -> dict[str, Any]:
        """Compile DSS commands from a string.

        Writes to a temp file, compiles, and returns summary.
        """
        wd = workdir or tempfile.mkdtemp(prefix="opendss_mcp_")
        self._workdir = wd
        path = os.path.join(wd, "Master.dss")
        with open(path, "w") as f:
            f.write(dss_script)
        return self.compile(path)

    def run_command(self, cmd: str) -> str:
        """Execute a raw DSS text command and return the result string."""
        return self.dss.text(cmd)

    def _circuit_summary(self) -> dict[str, Any]:
        converged = bool(self.dss.solution.converged)
        bus_names = self.dss.circuit.buses_names
        return {
            "converged": converged,
            "n_buses": len(bus_names),
            "n_lines": len(self.dss.lines.names) if self.dss.lines.names else 0,
            "n_loads": len(self.dss.loads.names) if self.dss.loads.names else 0,
            "losses_kw": self.dss.circuit.losses[0] / 1000,
            "losses_kvar": self.dss.circuit.losses[1] / 1000,
        }

    # ── Voltage extraction ──────────────────────────────────────────

    def get_bus_voltages(self) -> list[dict[str, Any]]:
        """Extract voltage magnitude (pu) for every bus.

        Returns:
            List of dicts with keys: bus, kv_base, n_phases, v_avg_pu, v_min_pu,
            v_max_pu, distance_km, x, y
        """
        results = []
        for bname in self.dss.circuit.buses_names:
            self.dss.circuit.set_active_bus(bname)
            v_pu_ang = self.dss.bus.vmag_angle_pu
            kv_base = self.dss.bus.kv_base
            n_phases = self.dss.bus.num_nodes
            x = self.dss.bus.x
            y = self.dss.bus.y
            dist = self.dss.bus.distance

            v_phases = [v_pu_ang[i] for i in range(0, len(v_pu_ang), 2)]
            if not v_phases:
                continue
            results.append(
                {
                    "bus": bname,
                    "kv_base": round(kv_base, 4),
                    "n_phases": n_phases,
                    "v_avg_pu": round(float(np.mean(v_phases)), 6),
                    "v_min_pu": round(float(np.min(v_phases)), 6),
                    "v_max_pu": round(float(np.max(v_phases)), 6),
                    "distance_km": round(dist, 4),
                    "x": x,
                    "y": y,
                }
            )
        return results

    def get_voltage_summary(self, kv_min: float = 0.0, kv_max: float = 1e6) -> dict[str, Any]:
        """Get voltage statistics filtered by kv_base range."""
        buses = self.get_bus_voltages()
        filtered = [b for b in buses if kv_min <= b["kv_base"] <= kv_max]
        if not filtered:
            return {"error": "No buses in the specified kv_base range"}

        v_all = [b["v_avg_pu"] for b in filtered]
        n_below = sum(1 for v in v_all if v < 0.95)
        n_above = sum(1 for v in v_all if v > 1.05)

        worst = min(filtered, key=lambda b: b["v_min_pu"])
        best = max(filtered, key=lambda b: b["v_max_pu"])

        return {
            "n_buses": len(filtered),
            "v_min_pu": round(min(v_all), 6),
            "v_max_pu": round(max(v_all), 6),
            "v_avg_pu": round(float(np.mean(v_all)), 6),
            "v_std_pu": round(float(np.std(v_all)), 6),
            "buses_below_095": n_below,
            "buses_above_105": n_above,
            "worst_bus": worst["bus"],
            "worst_v_pu": worst["v_min_pu"],
            "best_bus": best["bus"],
            "best_v_pu": best["v_max_pu"],
        }

    # ── Load extraction ─────────────────────────────────────────────

    def get_load_powers(self) -> list[dict[str, Any]]:
        """Extract active/reactive power for every load."""
        results = []
        self.dss.loads.first()
        while True:
            name = self.dss.loads.name
            kw = self.dss.loads.kw
            kvar = self.dss.loads.kvar
            self.dss.circuit.set_active_element(f"Load.{name}")
            bus_el = self.dss.cktelement.bus_names
            powers = self.dss.cktelement.powers

            n = len(powers) // 2
            p_total = sum(powers[i] for i in range(0, n, 2))
            q_total = sum(powers[i] for i in range(1, n, 2))

            results.append(
                {
                    "load": name,
                    "bus": bus_el[0].split(".")[0] if bus_el else "",
                    "kw_nominal": round(kw, 4),
                    "kvar_nominal": round(kvar, 4),
                    "kw_actual": round(p_total, 4),
                    "kvar_actual": round(q_total, 4),
                }
            )
            if not self.dss.loads.next():
                break
        return results

    # ── Line flows ──────────────────────────────────────────────────

    def get_line_flows(self) -> list[dict[str, Any]]:
        """Extract power flow and current for every line."""
        results = []
        self.dss.lines.first()
        while True:
            name = self.dss.lines.name
            length = self.dss.lines.length
            self.dss.circuit.set_active_element(f"Line.{name}")
            powers = self.dss.cktelement.powers
            currents = self.dss.cktelement.currents_mag_ang
            bus_el = self.dss.cktelement.bus_names

            n = len(powers) // 2
            p_send = sum(powers[i] for i in range(0, n, 2))
            q_send = sum(powers[i] for i in range(1, n, 2))
            i_max = max((currents[i] for i in range(0, min(6, len(currents)), 2)), default=0)

            results.append(
                {
                    "line": name,
                    "bus1": bus_el[0].split(".")[0] if bus_el else "",
                    "bus2": bus_el[1].split(".")[0] if len(bus_el) > 1 else "",
                    "length_km": round(length, 6),
                    "p_kw": round(p_send, 2),
                    "q_kvar": round(q_send, 2),
                    "i_max_a": round(i_max, 2),
                }
            )
            if not self.dss.lines.next():
                break
        return results

    # ── Fault study ─────────────────────────────────────────────────

    def run_fault_3ph(self, bus: str, r_fault: float = 0.0001) -> dict[str, Any]:
        """Run a three-phase fault at the specified bus.

        Returns:
            dict with fault currents per phase, Scc, and voltage impact summary.
        """
        # Pre-fault voltage
        self.dss.circuit.set_active_bus(bus)
        kv_base = self.dss.bus.kv_base
        dist = self.dss.bus.distance
        v_pre = self.dss.bus.vmag_angle_pu

        # Apply fault
        self.dss.text(f"New Fault.F3PH bus1={bus}.1.2.3 phases=3 r={r_fault}")
        self.dss.text("Solve")

        # Read fault current
        self.dss.circuit.set_active_element("Fault.F3PH")
        i_f = self.dss.cktelement.currents_mag_ang

        ia = i_f[0] if len(i_f) >= 2 else 0
        ib = i_f[2] if len(i_f) >= 4 else 0
        ic = i_f[4] if len(i_f) >= 6 else 0
        i_avg = (ia + ib + ic) / 3
        scc_mva = np.sqrt(3) * kv_base * np.sqrt(3) * i_avg / 1000

        # Post-fault voltages
        post_v = []
        for bname in self.dss.circuit.buses_names:
            self.dss.circuit.set_active_bus(bname)
            vpa = self.dss.bus.vmag_angle_pu
            kb = self.dss.bus.kv_base
            if len(vpa) >= 2 and 1 < kb < 100:
                post_v.append(vpa[0])

        n_below_80 = sum(1 for v in post_v if v < 0.80)
        n_below_50 = sum(1 for v in post_v if v < 0.50)

        # Clean up fault element
        self.dss.text("Fault.F3PH.enabled=no")
        self.dss.text("Solve")

        return {
            "fault_bus": bus,
            "fault_type": "3-phase",
            "distance_km": round(dist, 3),
            "kv_base": round(kv_base, 4),
            "v_pre_pu": round(v_pre[0], 5) if len(v_pre) >= 2 else None,
            "i_fault_a": round(ia, 1),
            "i_fault_b": round(ib, 1),
            "i_fault_c": round(ic, 1),
            "i_avg_a": round(i_avg, 1),
            "scc_mva": round(scc_mva, 1),
            "buses_below_80pct": n_below_80,
            "buses_below_50pct": n_below_50,
            "v_min_during_fault": round(min(post_v), 5) if post_v else None,
        }

    def run_fault_sweep(self, buses: list[str], r_fault: float = 0.0001) -> list[dict[str, Any]]:
        """Run 3-phase faults at multiple buses.

        Re-compiles the circuit for each fault to get clean results.
        Requires that the circuit was compiled from a file (not text).
        """
        if not self._workdir:
            return [{"error": "No circuit compiled from file. Use compile() first."}]

        # Find the master DSS file
        master = None
        for fname in os.listdir(self._workdir):
            if fname.lower().endswith(".dss"):
                master = os.path.join(self._workdir, fname)
                break

        if not master:
            return [{"error": "Cannot find DSS file in working directory"}]

        results = []
        for bus in buses:
            self.dss.text(f"Compile [{master}]")
            self.dss.text("Solve")
            result = self.run_fault_3ph(bus, r_fault)
            results.append(result)

        return results

    # ── QSTS (Quasi-Static Time Series) ─────────────────────────────

    def run_qsts(
        self, mode: str = "daily", stepsize: str = "1h", number: int = 24, monitor_bus: str | None = None
    ) -> dict[str, Any]:
        """Run a QSTS simulation.

        Args:
            mode: OpenDSS solution mode (daily, yearly, dutycycle)
            stepsize: Time step (e.g., '1h', '15m', '1s')
            number: Number of time steps
            monitor_bus: Optional bus to monitor voltage over time

        Returns:
            dict with convergence info and optional voltage time series.
        """
        if monitor_bus:
            # Find a line connected to this bus to attach monitor
            self.dss.lines.first()
            monitor_element = None
            while True:
                self.dss.circuit.set_active_element(f"Line.{self.dss.lines.name}")
                bnames = self.dss.cktelement.bus_names
                for i, bn in enumerate(bnames):
                    if bn.split(".")[0] == monitor_bus:
                        monitor_element = f"Line.{self.dss.lines.name}"
                        monitor_terminal = i + 1
                        break
                if monitor_element:
                    break
                if not self.dss.lines.next():
                    break

            if monitor_element:
                self.dss.text(f"New Monitor.qsts_mon element={monitor_element} terminal={monitor_terminal} mode=0")

        self.dss.text(f"set mode={mode} stepsize={stepsize} number={number}")
        self.dss.text("Solve")

        converged = bool(self.dss.solution.converged)
        result: dict[str, Any] = {
            "converged": converged,
            "mode": mode,
            "stepsize": stepsize,
            "number": number,
        }

        # Get final state voltages
        summary = self.get_voltage_summary(kv_min=1, kv_max=100)
        result["voltage_summary_final"] = summary

        return result

    # ── Hosting Capacity ────────────────────────────────────────────

    def run_hosting_capacity(
        self,
        load_buses: list[str],
        pv_kw_steps: list[float],
        trafo_kva: float,
        mode: str = "uniform",
    ) -> list[dict[str, Any]]:
        """Run a hosting capacity study by incrementally adding PV.

        Args:
            load_buses: List of bus names where PV can be placed.
            pv_kw_steps: List of total PV kW to test (e.g., [5, 10, 20, 50]).
            trafo_kva: Transformer capacity in kVA (for penetration %).
            mode: 'uniform' distributes equally, 'worst_case' concentrates at far end.

        Returns:
            List of dicts with penetration %, Vmax, Vmin, violations per step.
        """
        if not self._workdir:
            return [{"error": "No circuit compiled from file."}]

        master = None
        for fname in os.listdir(self._workdir):
            if fname.lower().endswith(".dss"):
                master = os.path.join(self._workdir, fname)
                break

        if not master:
            return [{"error": "Cannot find DSS file"}]

        # Get bus kV for PV
        self.dss.text(f"Compile [{master}]")
        self.dss.text("Solve")
        if load_buses:
            self.dss.circuit.set_active_bus(load_buses[0])
            kv = self.dss.bus.kv_base * np.sqrt(3)
        else:
            kv = 11.4

        results = []
        for pv_total in pv_kw_steps:
            self.dss.text(f"Compile [{master}]")
            self.dss.text("Solve")

            pen_pct = pv_total / trafo_kva * 100

            if mode == "uniform":
                kw_per = pv_total / len(load_buses)
                for bus in load_buses:
                    self.dss.text(
                        f"New PVSystem.PV_{bus} phases=3 bus1={bus} kV={kv:.3f} "
                        f"kVA={kw_per * 1.1:.2f} irradiance=1 Pmpp={kw_per:.2f} pf=1 "
                        f"%cutin=0.1 %cutout=0.1"
                    )
            else:  # worst_case — all at first bus (farthest)
                bus = load_buses[0]
                self.dss.text(
                    f"New PVSystem.PV_{bus} phases=3 bus1={bus} kV={kv:.3f} "
                    f"kVA={pv_total * 1.1:.2f} irradiance=1 Pmpp={pv_total:.2f} pf=1 "
                    f"%cutin=0.1 %cutout=0.1"
                )

            self.dss.text("Solve")
            vsummary = self.get_voltage_summary(kv_min=1, kv_max=100)

            results.append(
                {
                    "pv_total_kw": pv_total,
                    "penetration_pct": round(pen_pct, 1),
                    "mode": mode,
                    **vsummary,
                }
            )

        return results

    # ── Plotting helpers ────────────────────────────────────────────

    def plot_voltage_profile(self, output_path: str, kv_min: float = 1, kv_max: float = 100) -> str:
        """Generate voltage profile plot (V vs distance) and save to file.

        Returns:
            Path to the saved image.
        """
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        buses = self.get_bus_voltages()
        filtered = [b for b in buses if kv_min <= b["kv_base"] <= kv_max]
        if not filtered:
            return "Error: No buses in range"

        distances = [b["distance_km"] for b in filtered]
        voltages = [b["v_avg_pu"] for b in filtered]

        fig, ax = plt.subplots(figsize=(12, 5))
        sc = ax.scatter(
            distances,
            voltages,
            c=voltages,
            cmap="RdYlGn",
            vmin=0.90,
            vmax=1.05,
            s=18,
            alpha=0.8,
            edgecolors="k",
            linewidths=0.3,
        )
        ax.axhline(y=1.05, color="red", linestyle="--", linewidth=1.5, label="Upper limit (1.05 pu)")
        ax.axhline(y=0.95, color="red", linestyle="--", linewidth=1.5, label="Lower limit (0.95 pu)")
        ax.axhspan(0.95, 1.05, alpha=0.05, color="green")
        plt.colorbar(sc, ax=ax, label="Voltage (pu)")
        ax.set_xlabel("Distance from substation (km)")
        ax.set_ylabel("Voltage (pu)")
        ax.set_title("Voltage Profile")
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close()
        return output_path

    def plot_topology(self, output_path: str, kv_min: float = 1, kv_max: float = 100) -> str:
        """Generate a georeferenced topology map colored by voltage.

        Returns:
            Path to the saved image.
        """
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.colors import Normalize
        from matplotlib.cm import ScalarMappable

        buses = self.get_bus_voltages()
        filtered = {b["bus"]: b for b in buses if kv_min <= b["kv_base"] <= kv_max}

        if not filtered:
            return "Error: No buses in range"

        fig, ax = plt.subplots(figsize=(14, 12))
        norm = Normalize(vmin=0.90, vmax=1.05)
        cmap = plt.cm.RdYlGn

        # Draw lines
        self.dss.lines.first()
        while True:
            self.dss.circuit.set_active_element(f"Line.{self.dss.lines.name}")
            bnames = self.dss.cktelement.bus_names
            b1 = bnames[0].split(".")[0] if bnames else ""
            b2 = bnames[1].split(".")[0] if len(bnames) > 1 else ""

            if b1 in filtered and b2 in filtered:
                x1, y1 = filtered[b1]["x"], filtered[b1]["y"]
                x2, y2 = filtered[b2]["x"], filtered[b2]["y"]
                v_avg = (filtered[b1]["v_avg_pu"] + filtered[b2]["v_avg_pu"]) / 2
                ax.plot([x1, x2], [y1, y2], color=cmap(norm(v_avg)), linewidth=1.5, alpha=0.85)

            if not self.dss.lines.next():
                break

        # Draw nodes
        for b in filtered.values():
            ax.scatter(b["x"], b["y"], c=[cmap(norm(b["v_avg_pu"]))], s=15, edgecolors="k", linewidths=0.2, zorder=4)

        sm = ScalarMappable(cmap=cmap, norm=norm)
        sm.set_array([])
        plt.colorbar(sm, ax=ax, label="Voltage (pu)", shrink=0.7)
        ax.set_title("Circuit Topology — Voltage Map")
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
        ax.grid(True, alpha=0.15)
        ax.set_aspect("equal")
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close()
        return output_path
