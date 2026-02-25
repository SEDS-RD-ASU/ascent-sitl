import serial
import serial.tools.list_ports
import struct
import time
import os

import pandas as pd


# ---------- flash_packet format ----------
# Layout:
#   uint64_t n; int64_t timestamp; float bat_voltage; uint8_t flight_state; uint8_t pyro_cont;
#   [2x pad]
#   double pressure, temperature, altitude_agl, ground_altitude, baro_vel, avg_baro_vel;
#   uint32_t UTCtstamp, lat, lon, altitude_ellipsoid, altitude_msl;
#   uint8_t fixType, num_sats; [2x pad]
#   float acc_x, acc_y, acc_z, hacc_x, hacc_y, hacc_z, gyr_x, gyr_y, gyr_z;
#   [4x pad]
FLASH_PACKET_FORMAT = "<QqfBB2xddddddIIIII BB2x fff fff fff 4x"
FLASH_PACKET_SIZE = struct.calcsize(FLASH_PACKET_FORMAT)

DELIMITER = b'\n\n\n\n'

SEND_HZ = 200
SEND_INTERVAL = 1.0 / SEND_HZ


def pack_row(idx, row):
    """Pack a single CSV row into a flash_packet bytestring."""
    return struct.pack(
        FLASH_PACKET_FORMAT,
        idx,                                        # n
        int(row["timestamp_s"] * 1e6),              # timestamp (µs)
        0.0,                                        # bat_voltage
        0,                                          # flight_state
        0,                                          # pyro_cont
        float(row["baro_press"]),                   # pressure
        float(row["baro_temp"]),                    # temperature
        float(row["baro_alt"]),                     # altitude_agl
        0.0,                                        # ground_altitude
        0.0,                                        # baro_vel
        0.0,                                        # avg_baro_vel
        0,                                          # UTCtstamp
        int(row["latitude"]) & 0xFFFFFFFF,          # lat
        int(row["longitude"]) & 0xFFFFFFFF,         # lon
        0,                                          # alt_ellipsoid
        int(row["gps_altitude"]) & 0xFFFFFFFF,      # alt_msl
        0,                                          # fixType
        0,                                          # num_sats
        float(row["accx"]),                         # acc_x
        float(row["accy"]),                         # acc_y
        float(row["accz"]),                         # acc_z
        float(row["haccx"]),                        # hacc_x
        float(row["haccy"]),                        # hacc_y
        float(row["haccz"]),                        # hacc_z
        float(row["gyrx"]),                         # gyr_x
        float(row["gyry"]),                         # gyr_y
        float(row["gyrz"]),                         # gyr_z
    )


def select_serial_port():
    """Scan for serial devices and let the user pick one."""
    ports = list(serial.tools.list_ports.comports())

    if not ports:
        print("No serial devices found.")
        exit(1)

    if len(ports) == 1:
        print(f"Found: {ports[0].device} - {ports[0].description}")
        return ports[0].device

    print("Available serial devices:")
    for i, port in enumerate(ports):
        print(f"  [{i}] {port.device} - {port.description}")

    while True:
        try:
            choice = int(input("Select a device: "))
            if 0 <= choice < len(ports):
                return ports[choice].device
        except (ValueError, EOFError):
            pass
        print(f"Enter a number between 0 and {len(ports) - 1}")


def select_flight_data():
    sim_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sim_flight_data")
    if not os.path.isdir(sim_folder):
        print(f"Error: Directory not found: {sim_folder}")
        exit(1)
    
    csv_files = sorted([f for f in os.listdir(sim_folder) if f.lower().endswith(".csv")])
    if not csv_files:
        print(f"No CSV files found in {sim_folder}")
        exit(1)

    print("Available flight datasets:")
    for i, file_name in enumerate(csv_files):
        csv_path = os.path.join(sim_folder, file_name)
        df = pd.read_csv(csv_path)
        
        max_alt = df["baro_alt"].max() if "baro_alt" in df.columns else 0.0
        max_haccy = df["haccy"].max() if "haccy" in df.columns else 0.0
        
        max_vel = 0.0
        if "baro_alt" in df.columns and "timestamp_s" in df.columns:
            dy = df["baro_alt"].diff()
            dt = df["timestamp_s"].diff()
            valid = dt > 0
            if valid.any():
                max_vel = (dy[valid] / dt[valid]).max()
                
        print(f"  [{i}] {file_name} (Max Alt: {max_alt:.2f}, Max Vert Vel: {max_vel:.2f}, Max haccy: {max_haccy:.2f})")

    while True:
        try:
            choice = input(f"Select a CSV [0-{len(csv_files)-1}]: ")
            choice = int(choice)
            if 0 <= choice < len(csv_files):
                return os.path.join(sim_folder, csv_files[choice])
        except (ValueError, EOFError):
            pass
        except KeyboardInterrupt:
            print("\nExiting...")
            exit(0)
        print(f"Please enter a valid number between 0 and {len(csv_files) - 1}")


if __name__ == "__main__":
    csv_path = select_flight_data()
    df = pd.read_csv(csv_path)
    print(f"\nLoaded {len(df)} samples from {os.path.basename(csv_path)}\n")

    port = select_serial_port()
    ser = serial.Serial(port, 115200)

    total = len(df)
    t_start = time.perf_counter()

    try:
        for idx in range(total):
            # Schedule next send relative to start to avoid drift
            target_time = t_start + idx * SEND_INTERVAL

            now = time.perf_counter()
            sleep_time = target_time - now
            if sleep_time > 0:
                time.sleep(sleep_time)

            packet = pack_row(idx, df.iloc[idx])
            print(f"Sending sample t={df.iloc[idx]['timestamp_s']:.4f}s", end="\r")
            ser.write(packet + DELIMITER)
            # print(f"accy: {df.iloc[idx]['accy']:.4f}")

            # Check for any received data and print it
            if ser.in_waiting:
                rx_data = ser.read(ser.in_waiting)
                try:
                    rx_text = rx_data.decode("utf-8", errors="replace")
                except Exception:
                    rx_text = rx_data.hex()
                print(f"\nReceived: {rx_text}")
        print(f"\nDone. Sent {total} packets at {SEND_HZ} Hz.")
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        ser.close()
