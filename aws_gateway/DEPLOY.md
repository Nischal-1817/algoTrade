# AWS gateway deploy (fixed IP for Groww / Shoonya whitelist)

Your **laptop** calls this Flask app on **EC2**. The **broker** only sees the **EC2 public IP**.

```
Laptop  --HTTPS-->  EC2 Flask gateway  --API-->  Groww
                         ^
              Whitelist this IP on Groww
```

## 1. AWS EC2 (free tier ~12 months)

1. Create **Ubuntu 22.04** instance (t2.micro / t3.micro).
2. **Elastic IP** → allocate → associate with instance (stable IP).
3. Security group inbound:
   - SSH (22) from **your IP only**
   - HTTP (8080) from **your IP only** (or use nginx + 443 later)
4. SSH in: `ssh -i key.pem ubuntu@<ELASTIC_IP>`

## 2. Install on EC2

```bash
sudo apt update && sudo apt install -y python3-pip python3-venv git

git clone <your-private-repo-url> algoTrade
cd algoTrade
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r aws_gateway/requirements.txt

cp aws_gateway/.env.example .env
nano .env   # GATEWAY_SECRET, GROWW_API_KEY, GROWW_API_SECRET, ALGO_*
# OR: cp credentials.example.py credentials.py and fill Groww keys
```

## 3. Whitelist IP on Groww

On the server:

```bash
source .venv/bin/activate
python aws_gateway/scripts/call_gateway.py --url http://127.0.0.1:8080 --secret YOUR_SECRET public-ip
```

Or before gateway is up:

```bash
curl -s https://api.ipify.org
```

Add that IP in [Groww Trade API](https://groww.in/trade-api) whitelist.

## 4. Run gateway (production)

```bash
cd algoTrade
source .venv/bin/activate
export $(grep -v '^#' .env | xargs)   # Linux; or set vars in systemd

gunicorn -w 1 -b 0.0.0.0:8080 --timeout 120 aws_gateway.app:app
```

### systemd (optional)

```bash
sudo cp aws_gateway/algo-gateway.service.example /etc/systemd/system/algo-gateway.service
sudo nano /etc/systemd/system/algo-gateway.service   # fix paths
sudo systemctl enable --now algo-gateway
```

## 5. Call from your Windows laptop

```powershell
cd algoTrade
$env:GATEWAY_URL="http://<ELASTIC_IP>:8080"
$env:GATEWAY_SECRET="your_secret"

.\.venv\Scripts\python.exe aws_gateway\scripts\call_gateway.py health
.\.venv\Scripts\python.exe aws_gateway\scripts\call_gateway.py status
.\.venv\Scripts\python.exe aws_gateway\scripts\call_gateway.py run-cycle
```

## API endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/health` | No | Liveness |
| GET | `/api/public-ip` | No | IP to whitelist |
| GET | `/api/status` | Yes | Balance, state, LTP |
| POST | `/api/run-cycle` | Yes | Run one trading cycle |
| GET | `/api/state` | Yes | Raw `algo_state.json` |

Auth header: `Authorization: Bearer <GATEWAY_SECRET>` or `X-API-Key: <GATEWAY_SECRET>`

## Security

- **Never** commit `.env` or `credentials.py`.
- Restrict security group to **your home IP** (use `show_public_ip.py` on laptop).
- Use a long random `GATEWAY_SECRET`.
- Prefer **HTTPS** (nginx + Let's Encrypt) if exposed beyond your IP.
- Groww keys only on EC2, not on laptop.

## Cost note

AWS free tier ~12 months; then ~$5–10/month for t3.micro + Elastic IP if instance stopped.

Oracle Cloud Always Free is an alternative with no 12-month limit.
