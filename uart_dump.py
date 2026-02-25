import serial
import serial.tools.list_ports
import os
import sys
import threading
import datetime

# Use the same port selector as in send_data.py
def select_serial_port():
	ports = list(serial.tools.list_ports.comports())
	if not ports:
		print("No serial devices found.")
		sys.exit(1)
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

def main():
	port = select_serial_port()
	baud = 115200
	ser = serial.Serial(port, baud, timeout=0.1)

	# Prepare dump file
	os.makedirs("dump", exist_ok=True)
	timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
	dump_path = os.path.join("dump", f"uart_dump_{timestamp}.txt")
	print(f"Dumping serial data to {dump_path}\nPress Ctrl+C to exit.")

	stop_event = threading.Event()

	def read_serial():
		with open(dump_path, "a", encoding="utf-8", errors="replace") as f:
			while not stop_event.is_set():
				try:
					data = ser.read(1024)
					if data:
						try:
							text = data.decode("utf-8", errors="replace")
						except Exception:
							text = data.hex()
						print(text, end="", flush=True)
						f.write(text)
						f.flush()
				except Exception as e:
					import time
					print(f"\n[Serial read error: {e}]. Retrying in 1s...")
					time.sleep(1)
					try:
						ser.close()
					except Exception:
						pass
					try:
						ser.open()
					except Exception:
						pass

	reader_thread = threading.Thread(target=read_serial, daemon=True)
	reader_thread.start()

	try:
		while True:
			user_input = input()
			if user_input:
				try:
					ser.write((user_input + "\n").encode("utf-8"))
				except Exception as e:
					print(f"[Serial write error: {e}]")
	except KeyboardInterrupt:
		print("\nExiting...")
	finally:
		stop_event.set()
		reader_thread.join()
		ser.close()

if __name__ == "__main__":
	main()
