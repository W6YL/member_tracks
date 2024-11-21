import sys
import os 

dir_path = os.path.dirname(os.path.realpath(__file__))
exec_path = sys.executable

service = f"""
/etc/systemd/system/w6yl-card-tracks.service
######################################
[Unit]
Description=W6YL Card Tracks Service
After=multi-user.target

[Service]
Type=simple
WorkingDirectory={dir_path}
ExecStart={exec_path} {dir_path}/reader.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
######################################

/etc/systemd/system/w6yl-card-bot.service
######################################
[Unit]
Description=W6YL Card Bot Service
After=multi-user.target

[Service]
Type=simple
WorkingDirectory={dir_path}/controller_bot/
ExecStart={exec_path} {dir_path}/controller_bot/bot.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
######################################"""

print(service)