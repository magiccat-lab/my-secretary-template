[Unit]
Description=my-secretary-template watchdog
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=secretary
WorkingDirectory=/opt/my-secretary-template
EnvironmentFile=-/opt/my-secretary-template/.env
ExecStart=/usr/bin/python3 /opt/my-secretary-template/scripts/system/watchdog.py --pgrep discord_bot --interval 60
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
