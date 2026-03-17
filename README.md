# ⚡ IEC 62056 TCP Electricity Meter Simulator

This is a Python-based, **IEC 62056-21** (formerly IEC 1107) inspired, **TCP-enabled** electricity meter simulator.  
It does not perform real measurements; instead, at fixed intervals (default **15 minutes**) it generates random but **positive and consistent** energy consumption, and updates:

- **Total import energy (OBIS 1.8.0)**
- **Instantaneous power (1.7.0)**
- **Voltage (32.7.0)**
- **Load profile (P.01 records)**  

These values are exposed both via **TCP readout** and via **local data files**.

> This repository is designed both as a test meter for **embedded developers** and as a **data‑provider backend** for a future UI.

---

## 🛠 Features

- **Layered architecture**:
  - **Transport layer**: TCP server (`tcp_server.py`)
  - **Protocol / message parsing**: IEC 62056‑like state machine (`iec62056_protocol.py`)
  - **Meter core & load profile**: Simulation and data file management (`meter_model.py`)
- **Short / default readout** support:
  - `/?!` handshake → meter identification
  - `ACK050` → full OBIS readout
- **Load profile (P.01)** query:
  - `P.01(YYMMDDhhmm)(YYMMDDhhmm)` → returns all records in the given range
- **Load profile data file**:
  - Default file: `meter_data.txt` — one line per interval in 6-field format (date, time, total energy, voltage, current, power factor).
  - Snapshot file: `meter_data_total_endex.txt` — contains last timestamp and total import; **content is derived from the total energy field** of the last record (or written on shutdown).
  - On startup the application loads state from the **last line** of `meter_data.txt` (or from the snapshot file), so OBIS 1.8.0 stays consistent with the load profile.
- **Faster test cycles**:
  - Real‑life interval is 15 minutes, but for testing you can use e.g. 10 seconds.

- **🖥 TCP Client application** (`Meter_Client_Test.py`):
  - Connects over TCP and performs protocol requests
  - Host and port are configurable via CLI
  - Safe connection with timeout and basic error handling
  - OBIS readout:
    - `/?!` → get meter ID
    - `ACK050` → receive short/full readout
  - Load profile (P.01) query:
    - Fetch data for a given start/end time range
    - Supports larger responses (buffer ≥ 4 KB)
  - **Arguments**
    ```text
    --host, --port   → target server
    --interval       → query interval in seconds
    --start, --end   → load profile time window
    ```
  - **Continuous monitoring**
    - Automatically re‑queries at the given interval
    - Can be stopped safely with Ctrl+C
---

## ⚙ Installation

### 📦 Requirements

- Python **3.9+** (3.10 or newer recommended)
- Windows, Linux or macOS (examples below use Windows/PowerShell)

### 🚀 Running

After cloning the project, go into the folder:

```bash
cd ElectricityMeter
```

To start the simulator with default settings:

```bash
python run_simulator.py
```

Default configuration:

- Host: `0.0.0.0`
- Port: `5000`
- Load profile file: `meter_data.txt`
- Interval: `900` seconds (**15 minutes**)

For testing you may speed up the interval (e.g. create a new record every 10 seconds):

```bash
python run_simulator.py --interval-seconds 10
```

Custom host/port and data file example:

```bash
python run_simulator.py --host 127.0.0.1 --port 5000 --data-file data\my_meter.txt
```

To connect with the TCP client and fetch data:

```bash
python Meter_Client_Test.py --host 127.0.0.1 --port 5000 --interval 10
```

---

## 🧩 How It Works (Step by Step)

### 1️⃣ Meter core (`MeterSimulator`)

The `MeterSimulator` class in `meter_model.py`:

- Starts a background **thread**.
- On each interval (e.g. 15 minutes / 10 seconds in tests):
  - Generates **random positive consumption** in the range 0.1–0.6 kWh.
  - From this interval energy, computes an average power and sets **instant power (1.7.0)** around that value.
  - Generates **voltage (32.7.0)** around 230 V with a small random variation.
  - For each interval:
    - Computes **voltage** (≈210–240 V), **power factor** (≈0.85–1.0), and **current** from power (I = P/(V×PF)).
    - Appends a **load profile record** with cumulative total energy, voltage, current, and power factor.
    - Adds the interval consumption to **total import 1.8.0**.
  - Writes each record in **6-field format**:

```text
(YYYY-MM-DD)(HH:MM)(000000.000*kWh)(229*V)(000.0*A)(1.00)
```

  | Field | Meaning |
  |-------|--------|
  | 1 | Date (YYYY-MM-DD) |
  | 2 | Time (HH:MM) |
  | 3 | Total energy consumption (kWh, cumulative) |
  | 4 | Single-phase voltage (V) |
  | 5 | Single-phase current (A) |
  | 6 | Power factor |

- On startup:
  - Reads the **last line** of `meter_data.txt` (or `meter_data_total_endex.txt` if the data file is missing) to set **OBIS 1.8.0 total import** and last timestamp.

### 2️⃣ Protocol flow (IEC 62056‑like)

The `ConnectionState` class in `iec62056_protocol.py` handles the basic IEC 62056‑21 style flow:

1. **Handshake**:
   - Client sends:
     - `/?!` + CRLF
   - Meter responds with:
     - `/ZD5ME666-1003` + CRLF

2. **Baudrate selection (ACK050)**:
   - Client sends:
     - `ACK050` + CRLF
   - Because this is TCP, the physical baudrate is not changed, but the command is **accepted for protocol compatibility**.
   - The meter immediately sends a **short/default readout**:

```text
0.0.0(12345678)
1.8.0(0012345.67*kWh)
2.8.0(0000123.45*kWh)
1.7.0(0001.42*kW)
32.7.0(230.4*V)
0.9.1(HH:MM:SS)
0.9.2(YY-MM-DD)
!
```

3. **Load profile query (P.01)**:
   - Client sends the start and end timestamps:

```text
P.01(YYMMDDhhmm)(YYMMDDhhmm)
Example: `P.01(2401010000)(2401012359)`
```

   - The meter returns all records in the given range (same 6-field format as the data file), or **No-Data** + `!` when the range is empty or invalid (e.g. start &gt; end):

```text
(2026-03-17)(14:10)(000030.960*kWh)(230*V)(008.5*A)(0.92)
(2026-03-17)(14:25)(000031.520*kWh)(228*V)(007.2*A)(0.89)
...
!
```

This design ensures that:

- **Total import (1.8.0)** ≈ **Sum of daily/weekly load profile** over time, giving a consistent simulation.

### 3️⃣ TCP server

The `MeterTCPServer` class in `tcp_server.py`:

- Acts like a meter device and **opens the TCP listening socket itself**:
  - `bind(host, port)` + `listen()`
- Spawns a dedicated thread for each new client.
- Converts incoming bytes to ASCII and sends them **line by line** into `ConnectionState`:
  - Uses **CRLF** (or LF) as line terminator.
- If `ConnectionState.handle_line()` returns a response string, it is sent back to the client.

---

## Example terminal session

Assume the simulator is running in the background:

```bash
python run_simulator.py --host 127.0.0.1 --port 5000 --interval-seconds 10
```

From another terminal you can connect using a simple TCP client (e.g. `telnet`):

```bash
telnet 127.0.0.1 5000
```

1. **Handshake**:

```text
Client:  /?!
Meter :  /ISK5ME382-1003
```

2. **ACK + Short readout**:

```text
Client:  ACK050
Meter :
 0.0.0(12345678)
 1.8.0(0000005.23*kWh)
 2.8.0(0000000.00*kWh)
 1.7.0(0001.42*kW)
 32.7.0(230.4*V)
 0.9.1(14:22:31)
 0.9.2(24-01-01)
 !
```

3. **Load profile query** (example date range):

```text
Client:  P.01(2401010000)(2401012359)
Meter :
 (2026-01-01)(00:00)(000012.340*kWh)(229*V)(005.2*A)(0.91)
 (2026-01-01)(00:15)(000012.720*kWh)(231*V)(004.8*A)(0.93)
 ...
 !
```

If the requested range has no data (e.g. future date) or start &gt; end, the meter responds with:

```text
No-Data
!
```

> Note: Actual output will depend on runtime and randomly generated consumption.

---
## 🔗 Client–Server interaction
<img width="325" height="550" alt="image" src="https://github.com/user-attachments/assets/1bffdaa9-d343-4b75-95c4-25080fb55ed4" />

<img width="315" height="478" alt="image" src="https://github.com/user-attachments/assets/4aa3a94b-c415-4fce-b25d-abe4391a66ac" />


## Simple text‑based daily consumption chart

The following is a text‑based chart for an example day with **~12.34 kWh** total energy (15‑minute intervals):

```text
Saat   Tüketim (kWh)   Grafik
-----  --------------  ----------------------------
00:00      0.42        ################
00:15      0.38        ###############
00:30      0.35        #############
00:45      0.40        ###############
01:00      0.50        ####################
...
23:45      0.41        ###############

Total ≈ 12.34 kWh  (OBIS 1.8.0 ≈ 12.34 kWh)
```

This idea can later be turned into real daily/weekly charts in a **GUI or web dashboard**.

---

## 💡 Ideas for extension

- **New OBIS codes** (e.g. current, power factor, per‑phase measurements)
- **Selectable profile sets**:
  - Residential consumer
  - Industrial tariff
  - PV / solar production scenario (using 2.8.0 for export)
- **Real TCP/serial bridge**:
  - TCP → Serial port → real physical meter (proxy)
- **UI integration**:
  - Tkinter / PyQt / web‑based dashboard:
    - Instant power, voltage, total energy
    - Load profile charts
    - Simple alarm/limit notifications

---

## Contributing and license

This repository is a simulator for testing and educational purposes.  
Pull requests, new OBIS support and improvement ideas are very welcome.

