import serial
import serial.tools.list_ports

ports = list(serial.tools.list_ports.comports())
ourport = [port for port in ports if "usbserial" in port.device]
if len(ourport) == 0:
    print("No serial device found")
    exit(1)
ourport = ourport[0].device

ser = serial.Serial(
    port=ourport,\
    baudrate=9600,\
    parity=serial.PARITY_NONE,\
    stopbits=serial.STOPBITS_ONE,\
    bytesize=serial.EIGHTBITS,\
        timeout=0)

print("connected to: " + ser.portstr)
# count=1

def handle_state_change(ser):
    state = bool.from_bytes(ser.read(1))
    if state:
        print("Card Reader Connected")
    else:
        print("Card Reader Disconnected")

def card_read(ser):
    num_bytes, = ser.read(1)
    data = ser.read(num_bytes)
    print(data)

commands = {
    0x01: handle_state_change,
    0x02: card_read
}

while True:
    if ser.in_waiting == 0:
        continue
    command, = ser.read(1)
    if command not in commands:
        print(f"Unknown command: {command}")
        # Flush the buffer
        while ser.in_waiting > 0:
            ser.read(1)

    commands[command](ser)

# ser.close()