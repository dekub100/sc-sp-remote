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

> **Untested.** This project is developed on Windows and the maintainer has no Linux environment to verify this against; treat it as a starting point, not a guaranteed-working recipe. PRs that fix it up are welcome.

Use `systemd` to run the server in the background. The unit runs `server/server.py` directly rather than `python manage.py run`, so systemd tracks the server process itself instead of a wrapper subprocess.

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
StandardOutput=journal
StandardError=journal
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
