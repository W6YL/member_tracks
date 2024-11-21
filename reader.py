from datetime import datetime, timezone
import serial.tools.list_ports
import mysql.connector

import requests
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

def card_get_user(card_id, database):
    cursor = database.cursor()
    cursor.execute("SELECT id, first_name, last_name, callsign, position_in_club, discord_user_id FROM `members` WHERE `card_id` = %s", (card_id,))
    result = cursor.fetchone()
    if result is None:
        return None
    return {
        "id": result[0],
        "first_name": result[1],
        "last_name": result[2],
        "callsign": result[3],
        "position_in_club": result[4],
        "discord_user_id": result[5]
    }

#### COMMANDS ####

def handle_state_change(ser, *args):
    state = bool.from_bytes(ser.read(1), byteorder="big")
    if state:
        print("Card Reader Connected")
    else:
        print("Card Reader Disconnected")

def card_read(ser, config, database):
    num_bytes, = ser.read(1)
    data = ser.read(num_bytes)

    card_id = card_handle_id(data, database)
    card_add_log(card_id, database)
    print(f"Card ID: {card_id}, Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    user = card_get_user(card_id, database)
    if user is not None:
        full_webhook_push(user["first_name"] + " " + user["last_name"], user["callsign"], user["position_in_club"], data, user["discord_user_id"], config)
    else:
        pass

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
        },
        "discord": {
            "webhook_url": None,
            "api_version": 10,
            "discord_token": None
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

def get_discord_user_info(discord_id, config):
    with requests.get(f'https://discord.com/api/v{config["discord"]["api_version"]}/users/{discord_id}', headers={
        'Authorization': f'Bot {config["discord"]["discord_token"]}'
    }) as response:
        user = response.json()
        return user['global_name'] if "global_name" in user else user["username"], f"https://cdn.discordapp.com/avatars/{discord_id}/{user['avatar']}.webp"
    
def current_timestamp():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S.000Z")

def full_webhook_push(name, callsign, position, card_id, discord_id, config):
    member = f'<@{discord_id}>' if discord_id is not None else 'A member'
    username, avatar_url = get_discord_user_info(discord_id, config)

    requests.post(config["discord"]["webhook_url"], json={
        'content': '', 
        'tts': False, 
        'embeds': [
            {
                'id': 652627557, 
                'title': 'Member Login', 
                'description': f'{member} has logged in to the hamshack', 
                'color': 2326507, 
                'fields': [
                    {'id': 2340604, 
                     'name': 'Name', 
                     'value': name, 
                     'inline': True}, 
                    {'id': 445672415, 
                      'name': 'Callsign', 
                      'value': callsign if callsign is not None else 'N/A', 
                      'inline': True}, 
                    {'id': 449601989, 
                     'name': 'Position', 
                     'value': position if position is not None else 'N/A', 
                     'inline': True}, 
                    {'id': 974455510, 
                     'name': 'CARD ID', 
                     'value': card_id.hex().upper()}
                ], 
                'author': {'name': username, 
                           'icon_url': avatar_url},
                'timestamp': current_timestamp(),
            }
        ], 
        'components': [], 
        'actions': {},
        'username': 'HamShackBot'})

def reader_loop(ser, config, database):
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

            COMMANDS[command](ser, config, database)
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
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS `members` (
        `id` int(11) NOT NULL AUTO_INCREMENT PRIMARY KEY,
        `first_name` text NOT NULL,
        `last_name` text NOT NULL,
        `callsign` text DEFAULT NULL,
        `address` text DEFAULT NULL,
        `card_id` int(11) DEFAULT NULL,
        `position_in_club` text NOT NULL DEFAULT 'member',
        `joined_when` timestamp NULL DEFAULT current_timestamp(),
        `email` text DEFAULT NULL,
        `notes` text NOT NULL,
        `discord_user_id` bigint(11) DEFAULT NULL,
        FOREIGN KEY (`card_id`) REFERENCES `cards`(`id`)
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS `member_logs` (
        `id` int(11) NOT NULL AUTO_INCREMENT PRIMARY KEY, 
        `member_id` int(11) NOT NULL,
        `position_after` text DEFAULT NULL,
        `position_before` text DEFAULT NULL,
        `what_changed` text DEFAULT NULL,
        `notes` text DEFAULT NULL,
        `timestamp` timestamp NOT NULL DEFAULT current_timestamp(),
        FOREIGN KEY (`member_id`) REFERENCES `members`(`id`)
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
    reader_loop(ser, config, database)


if __name__ == "__main__":
    main()