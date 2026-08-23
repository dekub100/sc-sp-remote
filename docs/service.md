# Service Management

## Windows

Run the server as a background Windows Service. The script automatically asks for Administrator privileges if needed.

### Install & Start

```powershell
python manage.py service install
python manage.py service start
```

### Stop & Remove

```powershell
python manage.py service stop
python manage.py service remove
```

## Linux

Use `systemd` to run the server in the background.

1. Create a service file:

```bash
sudo nano /etc/systemd/system/sc-sp-remote.service
```

2. Paste the following (replace `YOUR_USER` and `YOUR_PATH`):

```ini
[Unit]
Description=sc-sp-remote Server
After=network.target

[Service]
ExecStart=/usr/bin/python3 /path/to/sc-sp-remote/server/server.py
WorkingDirectory=/path/to/sc-sp-remote
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
sudo systemctl enable sc-sp-remote
sudo systemctl start sc-sp-remote
```
