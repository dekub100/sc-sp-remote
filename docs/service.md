# Service Management

## Windows

Run the server as a background Windows Service. The script automatically asks for Administrator privileges if needed.

### Install & Start

```powershell
python tools/service.py install
python tools/service.py start
```

### Stop & Remove

```powershell
python tools/service.py stop
python tools/service.py remove
```

## Linux

Use `systemd` to run the server in the background.

1. Create a service file:

```bash
sudo nano /etc/systemd/system/spicetify-remote.service
```

2. Paste the following (replace `YOUR_USER` and `YOUR_PATH`):

```ini
[Unit]
Description=Spicetify Remote Server
After=network.target

[Service]
ExecStart=/usr/bin/python3 /path/to/spicetify-remote/server/server.py
WorkingDirectory=/path/to/spicetify-remote
StandardOutput=inherit
StandardError=inherit
Restart=always
User=YOUR_USER

[Install]
WantedBy=multi-user.target
```

3. Start and enable:

```bash
sudo systemctl daemon-reload
sudo systemctl enable spicetify-remote
sudo systemctl start spicetify-remote
```
