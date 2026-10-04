"""
scripts/create_demo_repo.py
===========================
Generates a complete standalone example repository highlighting ALL reqtool features:
- IoT Environmental Sensor Platform
- Full Hierarchy: Themes, Initiatives, Epics, Features, User Stories, Tasks, Bugs
- ATAM Architecture Decision Records (ADRs with sensitivity, trade-offs, risks)
- Architecture Principles
- Reusable System Modules & Product Variants
- ISO 26262 Safety & Acceptance Criteria

Usage:
  python scripts/create_demo_repo.py [--out-dir ./demo-iot-repo]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure src/ is in sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from reqtool.store import Store
from reqtool.fileio import save_yaml
from reqtool.commands.scaffold import _write_base_repo, _write_enums, _write_product
from reqtool.commands.scaffold_demo import populate_demo_data


def build_demo_repository(out_dir: Path) -> Path:
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[*] Generating reqtool IoT Sensor Demo Repository at: {out_dir}")

    # 1. Base repo structure
    _write_base_repo(out_dir, repo_id="iot-sensor-platform", title="IoT Environmental Sensor Platform", theme="dark")
    _write_enums(out_dir, domains=["sensing", "comms", "ux", "power", "industrial", "mechanical", "security", "safety", "compliance", "cost", "system"])
    _write_product(out_dir, product_id="sensor_pro", title="IoT Sensor Pro")

    store = Store(out_dir)
    store.load()

    # 2. Populate IoT sensor data (Requirements, Principles, Agile items)
    populate_demo_data(out_dir, store)

    # 3. Add ATAM Decision Records
    print("[*] Creating ATAM Decision Records...")
    store.create_decision({
        "type": "decision",
        "id": "DEC-001",
        "title": "Smart Home Wireless Protocol Selection (Matter/Thread vs Wi-Fi)",
        "status": "accepted",
        "owner": "Principal Architect",
        "content": {
            "context": "The IoT sensor requires a reliable wireless protocol for battery-powered operation and ecosystem integration.",
            "description": "Evaluation of Matter over Thread vs Wi-Fi 6 (802.11ax) for environmental telemetry.",
            "options": [
                {
                    "name": "Option A: Matter over Thread",
                    "pros": ["Mesh networking", "Ultra-low sleep power", "Native Apple/Google/Amazon integration"],
                    "cons": ["Requires Thread Border Router"],
                    "risk_level": "low",
                },
                {
                    "name": "Option B: Wi-Fi 6 Low-Power",
                    "pros": ["Direct home router connection without border router"],
                    "cons": ["High peak TX current (120mA+)", "Reduced battery life"],
                    "risk_level": "high",
                },
            ],
            "chosen_option": "Option A: Matter over Thread",
            "rationale": "Thread mesh protocol enables 2-year battery life on coin cell while maintaining native smart home ecosystem compatibility.",
            "atam": {
                "enabled": True,
                "quality_attributes": ["battery_life", "interoperability", "latency", "security"],
                "sensitivity_points": [
                    {"attribute": "battery_life", "description": "Radio sleep current is the primary sensitivity point for overall 24-month operational lifetime."},
                    {"attribute": "interoperability", "description": "Compliance with Matter specification determines zero-hub ecosystem onboarding."},
                ],
                "tradeoff_points": [
                    {"attributes": ["battery_life", "latency"], "description": "Thread polling interval of 3000ms balances low power consumption against sensor event reporting latency."},
                ],
                "risks": [
                    "Consumers lacking a Thread Border Router will require fallback provisioning via Bluetooth LE.",
                ],
                "non_risks": [
                    "AES-128-CCM Thread link-layer encryption is hardware-accelerated on Nordic nRF5340 with zero CPU overhead.",
                ],
            },
        },
    })

    store.create_decision({
        "type": "decision",
        "id": "DEC-002",
        "title": "Cloud Telemetry Protocol & Serialization (MQTT/TLS vs HTTP/REST)",
        "status": "accepted",
        "owner": "Cloud Lead",
        "content": {
            "context": "Fleet sensor data ingestion at 100,000 active devices requires efficient protocol design.",
            "options": [
                {
                    "name": "Option A: MQTT over TLS with Protobuf payloads",
                    "pros": ["Persistent connection", "Minimal packet overhead (2 bytes header)", "Pub/Sub architecture"],
                    "cons": ["Requires TLS session resumption cache"],
                    "risk_level": "low",
                },
                {
                    "name": "Option B: HTTPS REST POST with JSON",
                    "pros": ["Simple cloud gateway implementation"],
                    "cons": ["High TCP/TLS handshake overhead on every sensor report"],
                    "risk_level": "medium",
                },
            ],
            "chosen_option": "Option A: MQTT over TLS with Protobuf payloads",
            "rationale": "Reduces network data transfer by 85% compared to JSON/HTTPS.",
            "atam": {
                "enabled": True,
                "quality_attributes": ["bandwidth", "cloud_cost", "security"],
                "sensitivity_points": [
                    {"attribute": "bandwidth", "description": "Protobuf binary encoding size minimizes Cellular/Wi-Fi data usage."},
                ],
                "tradeoff_points": [
                    {"attributes": ["cloud_cost", "security"], "description": "TLS 1.3 session resumption reduces cloud authentication compute costs while maintaining zero-trust security."},
                ],
                "risks": [
                    "Network firewalls blocking TCP port 8883 require WebSockets fallback.",
                ],
                "non_risks": [
                    "X.509 mutual authentication overhead is mitigated via hardware Secure Element.",
                ],
            },
        },
    })

    # 4. Create Multiple Reusable Modules
    print("[*] Creating Reusable Subsystem Modules...")
    
    mod_core_dir = out_dir / "modules" / "sensor-core"
    mod_core_dir.mkdir(parents=True, exist_ok=True)
    save_yaml(mod_core_dir / "_module.yaml", {
        "schema_version": "1.0.0",
        "type": "module",
        "id": "MOD-SENSOR-CORE",
        "name": "Environmental Sensor Core Subsystem",
        "version": "1.2.0",
        "description": "Standardized environmental sensing subsystem for temperature, humidity, and pressure.",
    })

    mod_sec_dir = out_dir / "modules" / "comms-security"
    mod_sec_dir.mkdir(parents=True, exist_ok=True)
    save_yaml(mod_sec_dir / "_module.yaml", {
        "schema_version": "1.0.0",
        "type": "module",
        "id": "MOD-COMMS-SECURITY",
        "name": "Communications Cybersecurity Baseline",
        "version": "1.0.0",
        "description": "Reusable communications security requirements enforcing UK PSTI Act 2022 and EU RED compliance.",
    })

    mod_pwr_dir = out_dir / "modules" / "power-mgmt"
    mod_pwr_dir.mkdir(parents=True, exist_ok=True)
    save_yaml(mod_pwr_dir / "_module.yaml", {
        "schema_version": "1.0.0",
        "type": "module",
        "id": "MOD-POWER-MGMT",
        "name": "Ultra-Low-Power Management Module",
        "version": "1.1.0",
        "description": "Power management firmware and hardware subsystem for extended battery operation.",
    })

    # 5. Create Multiple Product Manifests
    print("[*] Creating Product Line Manifests...")
    
    prod_pro_dir = out_dir / "products" / "sensor_pro"
    prod_pro_dir.mkdir(parents=True, exist_ok=True)
    save_yaml(prod_pro_dir / "_product.yaml", {
        "schema_version": "1.0.0",
        "type": "product",
        "id": "sensor_pro",
        "name": "IoT Sensor Pro Edition",
        "description": "High-accuracy commercial grade environmental sensor with Matter, Thread, BLE, and Security Core.",
        "modules": [
            {"id": "MOD-SENSOR-CORE", "version": "1.2.0"},
            {"id": "MOD-COMMS-SECURITY", "version": "1.0.0"},
            {"id": "MOD-POWER-MGMT", "version": "1.1.0"},
        ],
    })

    prod_lite_dir = out_dir / "products" / "sensor_lite"
    prod_lite_dir.mkdir(parents=True, exist_ok=True)
    save_yaml(prod_lite_dir / "_product.yaml", {
        "schema_version": "1.0.0",
        "type": "product",
        "id": "sensor_lite",
        "name": "IoT Sensor Lite Consumer Edition",
        "description": "Entry-level residential coin-cell environmental sensor node.",
        "modules": [
            {"id": "MOD-SENSOR-CORE", "version": "1.2.0"},
            {"id": "MOD-POWER-MGMT", "version": "1.1.0"},
        ],
    })

    prod_ind_dir = out_dir / "products" / "sensor_industrial"
    prod_ind_dir.mkdir(parents=True, exist_ok=True)
    save_yaml(prod_ind_dir / "_product.yaml", {
        "schema_version": "1.0.0",
        "type": "product",
        "id": "sensor_industrial",
        "name": "IoT Sensor Industrial Heavy-Duty Node",
        "description": "Harsh-environment IP67 sensor node with NB-IoT cellular, RS-485 Modbus, and ATEX safety classification.",
        "modules": [
            {"id": "MOD-SENSOR-CORE", "version": "1.2.0"},
            {"id": "MOD-COMMS-SECURITY", "version": "1.0.0"},
        ],
    })

    # Reload store & summarize
    store.load()
    print("\n[+] Production Demo Repository Successfully Created!")
    print(f"  - Requirements: {len(store.requirements)}")
    print(f"  - Architecture Principles: {len(store.principles)}")
    print(f"  - ATAM Decision Records: {len(store.decisions)}")
    print(f"  - Reusable Modules: {len(store.modules)}")
    print(f"  - Product Line Manifests: {len(store.products)}")
    return out_dir


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create reqtool IoT Sensor Demo Repository")
    parser.add_argument("--out-dir", default="./demo-iot-repo", help="Target output directory")
    args = parser.parse_args()
    build_demo_repository(Path(args.out_dir))
