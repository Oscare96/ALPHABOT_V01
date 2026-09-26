# Small EC2 paper dashboard deployment

This service runs the dashboard continuously, but paper orders still require
manual preview and execution. It never uses a live-money Alpaca endpoint.

Before creating an instance, check the AWS account's Free Tier eligibility,
credit balance, and current regional prices. A continuously running EC2
instance, disk, and public IPv4 address can cost money. Set an AWS budget.

Use Ubuntu 24.04 on an instance size eligible for **your** account's Free Tier.
Allow inbound SSH (port 22) only from your current IP. Do not open port 8000.
The app listens on localhost and is reached through an SSH tunnel.

After the reviewed branch is available to the instance, install the app:

```bash
sudo apt-get update
sudo apt-get install -y git python3-venv
sudo git clone https://github.com/Oscare96/ALPHABOT_V01.git /opt/alphabot
sudo chown -R ubuntu:ubuntu /opt/alphabot
cd /opt/alphabot
git switch harden-paper-access
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Create `/etc/alphabot.env` on the instance with permissions `0600` and four
private environment variables: `ALPHABOT_DASHBOARD_USER`,
`ALPHABOT_DASHBOARD_PASSWORD`, `ALPACA_API_KEY`, and `ALPACA_SECRET_KEY`.
Use **paper** keys only. Do not put secrets in Git, shell history, or chat.

```bash
sudo cp /opt/alphabot/deploy/alphabot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now alphabot
sudo systemctl status alphabot --no-pager
curl -fsS http://127.0.0.1:8000/health
```

From your computer, open a tunnel with your actual key path and instance
address, then visit `http://127.0.0.1:8000` in your browser:

```bash
ssh -i <KEY_PATH> -L 8000:127.0.0.1:8000 ubuntu@<INSTANCE_ADDRESS>
```

The browser prompts for the dashboard username and password. Before placing
paper orders, compare a fresh scan and proposed order plan with the account's
actual holdings. Review logs with `sudo journalctl -u alphabot -n 100 --no-pager`.
