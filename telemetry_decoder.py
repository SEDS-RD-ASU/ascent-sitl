import serial
import serial.tools.list_ports
import struct
import threading
import requests
import time

# ---------- Discord webhook ----------
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1481537255641317418/FEl1fF-hrQ414kObQ02TKo-PMOJdpo0r6cVL4khxewVbha42pch0M-kqKVjSTachjwzq"
DISCORD_RATE_LIMIT = 1  # seconds between messages
_last_discord_send = 0
_discord_lock = threading.Lock()

def send_to_discord(message):
    """Send a message to the Discord webhook (rate limited to 1 per 15 seconds)."""
    global _last_discord_send
    with _discord_lock:
        now = time.time()
        if now - _last_discord_send < DISCORD_RATE_LIMIT:
            return  # Skip if rate limited
        _last_discord_send = now
    try:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": message}, timeout=5)
    except Exception:
        pass  # Silently ignore webhook errors

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
    msg = f"  Header: dev_id={dev_id}, dev_mode={dev_mode}, seq_id={seq_id}, msg_cls={msg_cls}, payload_length={payload_length}"
    print(msg)
    return dev_id, dev_mode, seq_id, msg_cls, payload_length, msg


def decode_ascent_telemetry(data):
    """Decode ascent_telemetry_t from payload bytes."""
    timestamp, lat, lon, alt_agl, vert_vel, y_acc, gyr_y, pyro_state, sats, flight_state, bat_voltage = struct.unpack_from(ASCENT_TELEMETRY_FORMAT, data)
    msgs = [
        f"  Telemetry:",
        f"    timestamp={timestamp}, lat={lat}, lon={lon}",
        f"    altitude_agl={alt_agl:.2f}m, vertical_velocity={vert_vel:.2f}m/s",
        f"    y_acc={y_acc:.3f}m/s², gyr_y={gyr_y:.3f}deg/s",
        f"    pyro_state={pyro_state}, sats={sats}, flight_state={flight_state}",
        f"    battery_voltage={bat_voltage / 2500}V"
    ]
    for msg in msgs:
        print(msg)

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
    
    return "\n".join(msgs)


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
            line_buffer = ""
            while True:
                data = ser.read(ser.in_waiting or 1)
                if data:
                    try:
                        text = data.decode("utf-8", errors="replace")
                    except Exception:
                        text = data.hex()
                    # Buffer and filter lines starting with +EVT:RXP2P:
                    line_buffer += text
                    while '\n' in line_buffer:
                        line, line_buffer = line_buffer.split('\n', 1)
                        if not line.startswith('+EVT:RXP2P:'):
                            print(line)
                    # Print partial line if it doesn't start with the ignored prefix
                    if line_buffer and not line_buffer.startswith('+EVT:RXP2P:'):
                        print(line_buffer, end="", flush=True)
                        line_buffer = ""
        else:
            print("Normal mode — parsing +EVT:RXP2P packets\n")
            line_buffer = ""
            while True:
                data = ser.read(ser.in_waiting or 1)
                if data:
                    try:
                        text = data.decode("utf-8", errors="replace")
                    except Exception:
                        continue
                    line_buffer += text
                    while '\n' in line_buffer:
                        line, line_buffer = line_buffer.split('\n', 1)
                        if line.startswith('+EVT:RXP2P:'):
                            # Format: +EVT:RXP2P:<rssi>:<snr>:<hex_payload>
                            parts = line.split(':')
                            if len(parts) >= 5:
                                rssi = parts[2]
                                hex_payload = parts[4]
                                rssi_msg = f"RSSI: {rssi} dBm"
                                print(rssi_msg)
                                discord_parts = [rssi_msg]
                                try:
                                    packet_data = bytes.fromhex(hex_payload)
                                    if len(packet_data) >= GOOBER_HEADER_SIZE:
                                        _, _, _, msg_cls, _, header_msg = decode_goober_header(packet_data)
                                        discord_parts.append(header_msg)
                                        payload = packet_data[GOOBER_HEADER_SIZE:]
                                        if msg_cls == MSG_CLS_ASCENT_TELEMETRY:
                                            telemetry_msg = decode_ascent_telemetry(payload)
                                            discord_parts.append(telemetry_msg)
                                except ValueError as e:
                                    print(f"  Error parsing hex: {e}")
                                # Send full message to Discord
                                # send_to_discord("\n".join(discord_parts))

    rx = threading.Thread(target=receive_thread, daemon=True)
    rx.start()

    try:
        rx.join()
    except KeyboardInterrupt:
        print("\nExiting...")