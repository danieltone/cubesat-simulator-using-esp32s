# CubeSat Telemetry Pipeline Flowchart

```mermaid
flowchart LR
    A[Spacecraft Sensors\nEPS / ADCS / Thermal / Orbit] --> B[Onboard Computer\nSample + Build Telemetry]
    B --> C[Packetization / Framing\nAX.25 / CSP / Mission Frame]
    C --> D[Space Radio + Antenna\nDownlink During Pass]
    D --> E[Ground RF Chain\nAntenna+Rotator → LNA/SDR/TNC]
    E --> F[Frame Decode + Integrity\nCRC/FEC/Metadata]
    F --> G[Ground Ingest Service\nParse + Scale + Normalize]
    G --> H[(Telemetry Storage\nSQLite/CSV/DB)]
    H --> I[Analytics + Rules\nThresholds / Trends / Alerts]
    I --> J[Dashboards + Reports]
    J --> K[Ops Decisions\nCommand/Uplink Planning]

    subgraph This Repo (Prototype)
      P1[cubesat_simulator.ino]
      P2[ground_station_logger.py]
      P3[telemetry_report.py]
      P4[telemetry_dashboard.py\nlive_dashboard_server.py]
      P1 --> P2 --> P3 --> P4
    end
```
