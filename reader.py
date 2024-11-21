import serial.tools.list_ports
import mysql.connector

import serial
import json
import time
import os

def card_handle_id(data, database):
    cursor = database.cursor()
    cursor.execute("SELECT `id` FROM `cards` WHERE `card_data` = %s", (data,))
    result = cursor.fetchone()
    if result is None:
        cursor.execute("INSERT INTO `cards` (`card_data`) VALUES (%s)", (data,))
        database.commit()
        return cursor.lastrowid
    return result[0]

def card_add_log(card_id, database):
    cursor = database.cursor()
    cursor.execute("INSERT INTO `logs` (`card_id`) VALUES (%s)", (card_id,))
    database.commit()

#### COMMANDS ####

def handle_state_change(ser, _):
    state = bool.from_bytes(ser.read(1), byteorder="big")
    if state:
        print("Card Reader Connected")
    else:
        print("Card Reader Disconnected")

def card_read(ser, database):
    num_bytes, = ser.read(1)
    data = ser.read(num_bytes)

    card_id = card_handle_id(data, database)
    card_add_log(card_id, database)
    print(f"Card ID: {card_id}, Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")

COMMANDS = {
    0x01: handle_state_change,
    0x02: card_read
}

#### END COMMANDS ####

def get_config():
    config = {
        "database": {
            "host": "localhost",
            "port": 3306,
            "username": None,
            "password": None,
            "database": None
        },
        "arduino": {
            "port": None
        }
    }
    if not os.path.exists("config.json"):
        json.dump(config, open("config.json", "w"), indent=2)
        return config
    return json.load(open("config.json"))

def find_port(config):
    if config["arduino"]["port"] is not None:
        return config["arduino"]["port"]
    
    arduino_port_search_list = ["Arduino", "CH340", "usbserial"]

    ports = list(serial.tools.list_ports.comports())
    ourport = [port for port in ports if any(arduino_port in port.description for arduino_port in arduino_port_search_list)]
    if len(ourport) == 0:
        return None
    ourport = ourport[0].device
    return ourport

def reader_loop(ser, database):
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

            COMMANDS[command](ser, database)
    except KeyboardInterrupt:
        pass
    finally:
        ser.close()

def create_tables(database):
    cursor = database.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS `cards` (
        `id` INT AUTO_INCREMENT PRIMARY KEY,
        `card_data` BLOB NOT NULL
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS `logs` (
        `id` INT AUTO_INCREMENT PRIMARY KEY,
        `card_id` INT NOT NULL,
        `timestamp` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (`card_id`) REFERENCES `cards`(`id`)
    )
    """)
    database.commit()

def main():
    config = get_config()
    arduino_port = find_port(config)

    # Check if we found the arduino port
    if arduino_port is None:
        print("Could not find arduino port")
        return
    
    # Check if we have database information
    if any(config["database"][key] is None for key in config["database"]):
        print("Please input database information in config.json")
        return

    ser = serial.Serial(
        port=arduino_port,
        baudrate=9600
    )
    database = mysql.connector.connect(
        host=config["database"]["host"],
        port=config["database"]["port"],
        user=config["database"]["username"],
        password=config["database"]["password"],
        database=config["database"]["database"]
    )
    create_tables(database)

    print("Connected To: " + ser.portstr)
    reader_loop(ser, database)


if __name__ == "__main__":
    main()