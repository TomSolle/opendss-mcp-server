# OpenDSS MCP Server

MCP (Model Context Protocol) server for **power distribution system simulation** using [OpenDSS](https://www.epri.com/pages/sa/opendss) via [py-dss-interface](https://github.com/PauloRadatz/py_dss_interface).

Enables LLMs (Claude, GPT, etc.) to compile circuits, run power flow, fault studies, hosting capacity analysis, QSTS simulations, and generate voltage plots — all through standardized MCP tools.

## Tools

| Tool | Description |
|------|-------------|
| `opendss_compile_file` | Compile a `.dss` file and run snapshot power flow |
| `opendss_compile_script` | Compile DSS commands from inline text |
| `opendss_run_command` | Execute a raw OpenDSS text command |
| `opendss_get_voltages` | Get voltage (pu) for all buses |
| `opendss_voltage_summary` | Voltage statistics: min, max, violations |
| `opendss_get_loads` | Get active/reactive power per load |
| `opendss_get_line_flows` | Get P, Q, and current per line |
| `opendss_fault_3ph` | Three-phase fault at a specific bus |
| `opendss_fault_sweep` | Fault sweep across multiple buses |
| `opendss_run_qsts` | Quasi-static time series simulation |
| `opendss_hosting_capacity` | PV hosting capacity study |
| `opendss_plot` | Generate voltage profile or topology plot |

## Installation

```bash
# Clone the repository
git clone https://github.com/TomSolle/opendss-mcp-server.git
cd opendss-mcp-server

# Install with pip
pip install -e .
```

### Requirements

- Python >= 3.10
- OpenDSS engine (included with py-dss-interface on Linux/Windows)
- Dependencies: py-dss-interface, pandas, numpy, matplotlib, pydantic, mcp

## Usage

### With Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "opendss": {
      "command": "python",
      "args": ["-m", "opendss_mcp.server"],
      "env": {
        "OPENDSS_MCP_OUTPUT_DIR": "/path/to/output/plots"
      }
    }
  }
}
```

### With Claude Code (Cowork)

Add to your `.claude/settings.json` or MCP configuration:

```json
{
  "mcpServers": {
    "opendss": {
      "command": "opendss-mcp",
      "env": {
        "OPENDSS_MCP_OUTPUT_DIR": "./results"
      }
    }
  }
}
```

### Standalone (stdio)

```bash
opendss-mcp
```

## Example Workflow

```
User: "Compile the IEEE 13-node test feeder and show me the voltage summary"

Claude uses: opendss_compile_file(dss_path="examples/ieee13/IEEE13Nodesv2.dss",
                                   buscoords_path="examples/ieee13/BusCoords.csv")
Then:       opendss_voltage_summary(kv_min=1, kv_max=10)

Result:
- n_buses: 13
- v_min_pu: 0.9808
- v_max_pu: 1.0499
- buses_below_095: 0
- buses_above_105: 0
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENDSS_MCP_OUTPUT_DIR` | System temp dir | Directory for plot output files |

## Project Structure

```
opendss-mcp-server/
  src/opendss_mcp/
    __init__.py
    server.py          # MCP server with all tools
    dss_engine.py      # OpenDSS engine wrapper
  examples/
    ieee13/            # IEEE 13-node test feeder
  tests/
  pyproject.toml
  README.md
  LICENSE
```

## License

MIT License. See [LICENSE](LICENSE).

## Author

Juan Pablo Salamanca — [PROING S.A](https://proing.com.co)
