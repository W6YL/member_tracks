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
        cursor.close()
        return cursor.lastrowid
    return result[0]

def card_add_log(card_id, database):
    cursor = database.cursor()
    cursor.execute("INSERT INTO `logs` (`card_id`, `login_out`) SELECT `id`, `inside_shack` FROM `cards` WHERE `id`=%s", (card_id,))
    database.commit()
    cursor.close()

def check_login_within_timeout(card_id, database, interval_min_injectable):
    cursor = database.cursor()
    cursor.execute(f"SELECT * FROM `logs` WHERE `timestamp` > (now() - INTERVAL {interval_min_injectable} MINUTE) AND `card_id` = %s ORDER BY `timestamp` DESC LIMIT 1", (card_id,))
    result = cursor.fetchone()
    cursor.close()
    if result is None:
        return None
    return result[0] != 0 # if the resulting number of rows is not 0, then the user has logged in within the timeout

def card_get_user(card_id, database):
    cursor = database.cursor()
    cursor.execute("SELECT id, first_name, last_name, callsign, position_in_club, discord_user_id FROM `members` WHERE `card_id` = %s", (card_id,))
    result = cursor.fetchone()
    cursor.close()
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

def toggle_inside_shack(card_id, database):
    cursor = database.cursor()
    cursor.execute("SELECT `inside_shack` FROM `cards` WHERE `id` = %s", (card_id,))
    result = cursor.fetchone()
    if result is None:
        return None
    inside_shack = 0 if result[0] else 1
    cursor.execute("UPDATE `cards` SET `inside_shack` = %s WHERE `id` = %s", (inside_shack, card_id))
    cursor.close()
    database.commit()
    return inside_shack == 1

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

    print(f"Card ID: {card_id}, Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    user = card_get_user(card_id, database)

    # If the user has logged in within the timeout, we don't want to do anything
    login_within_timeout = check_login_within_timeout(card_id, database, config["database"]["card_tap_timeout_min"])
    if login_within_timeout is not None:
        return
    
    # If the user is not in the database, we don't have any information on them
    status = toggle_inside_shack(card_id, database)
    
    # add the log
    card_add_log(card_id, database)
    
    if user is not None:
        full_webhook_push(user["first_name"] + " " + user["last_name"], user["callsign"], user["position_in_club"], data, user["discord_user_id"], status, config)
    else:
        unk_webhook_push(data, card_id, status, config)

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
            "database": None,
            "card_tap_timeout_min": 2
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
        if not response.ok:
            return None, None
        user = response.json()
        return user['global_name'] if "global_name" in user else user["username"], f"https://cdn.discordapp.com/avatars/{discord_id}/{user['avatar']}.webp"
    
def current_timestamp():
    time_now = datetime.now()
    dt_local = time_now.astimezone()
    dt_utc = dt_local.astimezone(timezone.utc)
    return dt_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")

def unk_webhook_push(card_id, card_index, in_out, config):
    in_out = "in" if in_out else "out"
    to_of = "to" if in_out == "in" else "from"

    requests.post(config["discord"]["webhook_url"], json={
        'content': '', 
        'tts': False, 
        'embeds': [
            {'id': 652627557, 
             'title': f'Member Log{in_out}', 
             'description': f'A member has logged {in_out} {to_of} the hamshack (Unregistered Card)', 
             'color': 15409955, 
             'fields': [
                 {'id': 974455510, 'name': 'CARD ID', 'value': card_id.hex().upper(), 'inline': True},
                 {"id": 770098205, "name": "CARD INDEX", "value": card_index, "inline": True}
             ], 
             'author': {'icon_url': 'https://cdn.discordapp.com/embed/avatars/0.png', 'name': 'Unknown User'}, 
             'timestamp': current_timestamp()}
        ], 
        'components': [], 
        'actions': {}, 
        'username': 'HamShackBot'
    })

def full_webhook_push(name, callsign, position, card_id, discord_id, in_out, config):
    member = f'<@{discord_id}>' if discord_id is not None else name
    username, avatar_url = get_discord_user_info(discord_id, config)
    in_out = "in" if in_out else "out"
    to_of = "to" if in_out == "in" else "from"

    if username is None:
        username = name
        member = name
        avatar_url = "https://cdn.discordapp.com/embed/avatars/0.png"

    requests.post(config["discord"]["webhook_url"], json={
        'content': '', 
        'tts': False, 
        'embeds': [
            {
                'id': 652627557, 
                'title': f'Member Log{in_out}', 
                'description': f'{member} has logged {in_out} {to_of} the hamshack', 
                'color': 2473520 if in_out == "in" else 2326507, 
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
        database.close()

def create_tables(database):
    cursor = database.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS `cards` (
        `id` INT AUTO_INCREMENT PRIMARY KEY,
        `inside_shack` int DEFAULT 0,
        `card_data` BLOB NOT NULL
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS `logs` (
        `id` INT AUTO_INCREMENT PRIMARY KEY,
        `card_id` INT NOT NULL,
        `timestamp` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        `login_out` BOOLEAN DEFAULT 0,
        INDEX `timestamp_FI_1` (`timestamp`),
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