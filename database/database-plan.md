# D.S.F.S.T Database Plan

## Purpose
This defines the database structure for the Distributed Systems Failure Simulation Tool (D.S.F.S.T).

The system uses:
- MongoDB for document-based application data
- InfluxDB for time-series metrics data


## MongoDB Collections

### 1. experiments
Stores experiment configuration, target, parameters, state, and timestamps.

Suggested fields:
- experiment_id
- name
- failure_type
- target_container
- parameters
- status
- created_at
- started_at
- ended_at

### 2. logs
Stores experiment event logs and timestamps.

Suggested fields:
- log_id
- experiment_id
- event_type
- message
- timestamp

### 3. users
Stores user information for future access control and ownership tracking.

Suggested fields:
- user_id
- name
- email
- role
- created_at


## InfluxDB Measurements

### 1. cpu
Stores CPU usage metrics over time.

Suggested fields/tags:
- container_id
- cpu_usage_percent
- timestamp

### 2. memory
Stores memory usage metrics over time.

Suggested fields/tags:
- container_id
- memory_used_mb
- memory_percent
- timestamp

### 3. network
Stores network behavior metrics over time.

Suggested fields/tags:
- container_id
- latency_ms
- packet_loss_percent
- throughput_kbps
- timestamp


## Notes
- MongoDB will be used for experiment metadata and logs.
- InfluxDB will be used for real-time charting and historical metrics.
- This structure supports future dashboard, reporting, and export features.