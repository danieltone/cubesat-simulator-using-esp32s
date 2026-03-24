# CubeSat Telemetry Pipeline (Spacecraft → Ground Station → Data Products)

This document explains the **exact operational pipeline** for telemetry delivery in a typical LEO CubeSat mission, and how this project maps to that pipeline.

## 1) Onboard telemetry generation (spacecraft side)

The flight software (OBC) periodically collects subsystem data from:

- EPS: battery SOC/voltage/current, solar power, load power
- ADCS: attitude, gyro, magnetometer, sun sensor vectors
- Thermal: bus/battery/payload temperatures
- Orbit/state: time, position estimate, eclipse flag
- COMMS status: TX state, RSSI/SNR estimates, counters

The spacecraft creates one telemetry record per heartbeat interval (e.g., every 15 seconds).

## 2) Packetization and framing

Raw telemetry is serialized and put into downlink frames.

Typical real missions:

- Frame/protocol layer: AX.25, CSP, or mission-specific framing
- Error handling: CRC/FEC/retransmit strategy depending on link budget and mission design
- Message classes: beacon/housekeeping, engineering, payload telemetry, event logs

In this simulator:

- Full record is emitted as line-delimited JSON (`Serial`)
- Optional compact heartbeat is transmitted over ESP-NOW (local infra-free demo link)

## 3) RF transmission from orbit

The spacecraft COMMS subsystem drives a radio and antenna system to transmit to Earth during visibility windows.

Typical real RF chain:

1. OBC telemetry frame →
2. Radio modem/baseband (framing/modulation) →
3. PA (power amplifier) →
4. Spacecraft antenna (UHF/VHF/S-band/etc.)

Important: most CubeSats in LEO do not have continuous contact; downlink occurs only during ground-station passes.

## 4) Ground station RF reception

During a pass, the ground station tracks the satellite and receives RF telemetry.

Typical ground RF chain:

1. Tracking antenna + rotator follows predicted pass
2. LNA/filter improves received signal quality
3. SDR or hardware transceiver digitizes/receives signal
4. Demodulator/TNC decodes frames
5. Frame parser verifies integrity (CRC/FEC/status)

## 5) Ground software ingest and decoding

Once decoded, ground software:

1. Parses protocol frames into engineering fields
2. Converts/scales values into engineering units
3. Adds metadata (station ID, timestamp, pass ID, confidence)
4. Stores raw + decoded data for traceability

## 6) Storage, monitoring, and alerting

Ground segment data services then:

- Write timeseries/log data to DB
- Build housekeeping dashboards
- Run rules (low battery SOC, high temperature, poor link quality)
- Trigger alerts/escalations for operators

## 7) Mission operations use of data

Operators use telemetry products to:

- Assess spacecraft health and safety
- Decide command uplinks for next pass
- Trend long-term subsystem performance/degradation
- Produce mission reports and anomaly investigations

---

## Practical pipeline in this repository

This project implements a local/prototype version of the same flow:

1. `cubesat_simulator.ino`
   - Generates realistic LEO telemetry every 15s
   - Outputs full JSON stream on Serial
   - Optional compact ESP-NOW heartbeat

2. (Optional) `ground_station_receiver.ino`
   - Receives ESP-NOW heartbeat packets

3. `ground_station_logger.py`
   - Ingests serial JSON stream
   - Stores to `data/telemetry.csv` and `data/telemetry.db`
   - Optional live plots

4. `telemetry_report.py`
   - Produces min/max/avg and anomaly summaries

5. `telemetry_dashboard.py`
   - Builds offline HTML dashboard from SQLite

6. `live_dashboard_server.py`
   - Auto-refreshes dashboard and serves local web view

7. Demo artifacts
   - `generate_demo_dashboards.py` creates sample DBs and dashboard HTML demos

---

## What is “flight-like” vs “demo-only” here

Flight-like concepts represented:

- Heartbeat cadence
- Subsystem-oriented telemetry model
- Ground ingest → storage → analytics → dashboard pipeline
- Anomaly thresholding and health visualization

Demo-only substitutions:

- ESP32 Wi-Fi/ESP-NOW instead of space-qualified UHF/S-band radios
- JSON over serial instead of strict spacecraft packet protocol chain
- No pass prediction/orbital tracking control loop
- No regulatory/licensing constraints modeled

---

## One-line pipeline summary

**Spacecraft sensors → onboard telemetry packetization → RF downlink during pass → ground RF decode → software parsing/storage → health analytics/dashboards → operator decisions and uplink planning.**

## Presentation flowchart (Mermaid)

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
