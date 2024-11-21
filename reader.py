import serial
import serial.tools.list_ports

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

COMMANDS = {
    0x01: handle_state_change,
    0x02: card_read
}

def find_port():
    arduino_port_search_list = ["Arduino", "CH340", "usbserial"]

    ports = list(serial.tools.list_ports.comports())
    ourport = [port for port in ports if any(arduino_port in port.device for arduino_port in arduino_port_search_list)]
    if len(ourport) == 0:
        return None
    ourport = ourport[0].device
    return ourport

def reader_loop(ser):
    try:
        while True:
            if ser.in_waiting == 0:
                continue
            command, = ser.read(1)
            if command not in COMMANDS:
                print(f"Unknown command: {command}")
                # Flush the buffer
                while ser.in_waiting > 0:
                    ser.read(1)

            COMMANDS[command](ser)
    except KeyboardInterrupt:
        pass
    finally:
        ser.close()

def main():
    arduino_port = find_port()

    ser = serial.Serial(
        port=arduino_port,
        baudrate=9600
    )

    print("Connected To: " + ser.portstr)
    reader_loop(ser)


if __name__ == "__main__":
    main()