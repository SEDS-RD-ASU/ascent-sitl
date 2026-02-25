import serial
import serial.tools.list_ports
import struct
import threading

# ---------- Protocol constants ----------
RX_PACKET_SIZE = 120
DELIMITER = b'\n\n\n\n'

GOOBER_HEADER_FORMAT = '<BBBBB'
GOOBER_HEADER_SIZE = struct.calcsize(GOOBER_HEADER_FORMAT)

ASCENT_TELEMETRY_FORMAT = '<IiiffffBBBxH'
ASCENT_TELEMETRY_SIZE = struct.calcsize(ASCENT_TELEMETRY_FORMAT)

MSG_CLS_ASCENT_TELEMETRY = 21


def decode_goober_header(data):
    dev_id, dev_mode, seq_id, msg_cls, payload_length = struct.unpack_from(GOOBER_HEADER_FORMAT, data)
    print(f"  Header: dev_id={dev_id}, dev_mode={dev_mode}, seq_id={seq_id}, msg_cls={msg_cls}, payload_length={payload_length}")
    return dev_id, dev_mode, seq_id, msg_cls, payload_length


def decode_ascent_telemetry(data):
    """Decode ascent_telemetry_t from payload bytes."""
    timestamp, lat, lon, alt_agl, vert_vel, y_acc, gyr_y, pyro_state, sats, flight_state, bat_voltage = struct.unpack_from(ASCENT_TELEMETRY_FORMAT, data)
    print(f"  Telemetry:")
    print(f"    timestamp={timestamp}, lat={lat}, lon={lon}")
    print(f"    altitude_agl={alt_agl:.2f}m, vertical_velocity={vert_vel:.2f}m/s")
    print(f"    y_acc={y_acc:.3f}m/s², gyr_y={gyr_y:.3f}deg/s")
    print(f"    pyro_state={pyro_state}, sats={sats}, flight_state={flight_state}")
    print(f"    battery_voltage={bat_voltage / 2500}V")

    # CSV logging
    import os
    import csv
    telemetry_dir = os.path.join(os.path.dirname(__file__), 'telemetry')
    os.makedirs(telemetry_dir, exist_ok=True)
    csv_path = os.path.join(telemetry_dir, 'ascent_telemetry.csv')

    # Write header if file does not exist
    write_header = not os.path.exists(csv_path)
    with open(csv_path, 'a', newline='') as csvfile:
        writer = csv.writer(csvfile)
        if write_header:
            writer.writerow([
                'timestamp', 'lat', 'lon', 'altitude_agl', 'vertical_velocity',
                'y_acc', 'gyr_y', 'pyro_state', 'sats', 'flight_state', 'battery_voltage'
            ])
        writer.writerow([
            timestamp, lat, lon, alt_agl, vert_vel, y_acc, gyr_y,
            pyro_state, sats, flight_state, bat_voltage / 2500
        ])


def sync_to_delimiter(ser):
    """Scan byte-by-byte until we find the delimiter to sync packet boundaries."""
    buffer = b''
    while True:
        byte = ser.read(1)
        if not byte:
            continue
        buffer += byte
        if len(buffer) > len(DELIMITER):
            buffer = buffer[-len(DELIMITER):]
        if buffer == DELIMITER:
            return


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


if __name__ == "__main__":
    port = select_serial_port()
    ser = serial.Serial(port, 115200)

    mode = input("Select mode — [n]ormal or [d]ebug: ").strip().lower()
    debug_mode = mode in ("d", "debug")

    def receive_thread():
        """Receive from serial. In debug mode, print raw data. In normal mode, decode packets."""
        if debug_mode:
            print("Debug mode — printing raw serial data\n")
            while True:
                data = ser.read(ser.in_waiting or 1)
                if data:
                    try:
                        text = data.decode("utf-8", errors="replace")
                    except Exception:
                        text = data.hex()
                    print(text, end="", flush=True)
        else:
            sync_to_delimiter(ser)

            while True:
                data = ser.read(RX_PACKET_SIZE)

                if len(data) == RX_PACKET_SIZE:
                    _, _, _, msg_cls, _ = decode_goober_header(data)

                    payload = data[GOOBER_HEADER_SIZE:]
                    if msg_cls == MSG_CLS_ASCENT_TELEMETRY:
                        decode_ascent_telemetry(payload)

                    delimiter = ser.read(len(DELIMITER))
                    if delimiter != DELIMITER:
                        sync_to_delimiter(ser)

    rx = threading.Thread(target=receive_thread, daemon=True)
    rx.start()

    try:
        rx.join()
    except KeyboardInterrupt:
        print("\nExiting...")