# Deploying ORTU Fitness on AWS Lightsail (alongside your existing app)

This runs ORTU on the **same** Lightsail instance as your other site, fully
isolated, reachable at `http://<LIGHTSAIL_IP>:8090`. A domain + HTTPS can be
added later (see the last section).

## Why this is safe next to your other app

- ORTU runs as its **own** Docker Compose project (`ortu-web-1`, `ortu-db-1`,
  network `ortu_default`) — your existing `voiceagent` container is untouched.
- It ships its **own** Postgres container with its own volume. It never
  connects to your other database.
- It listens on **port 8090**, not 8000, so there is no clash with your other app.

The only shared things on one box are the host ports (handled by using 8090) and
RAM/CPU (an extra ~300–400 MB — comfortable on a 2 GB+ plan, tight on 512 MB–1 GB).

---

## 0. Prerequisites (SSH into the instance)

Check Docker + Compose v2 are present (your other app already uses Docker):

```bash
docker --version
docker compose version
```

If the compose plugin is missing:

```bash
sudo apt-get update && sudo apt-get install -y docker-compose-plugin
```

Optional — see what's already using ports, so you understand your current setup:

```bash
sudo ss -tlnp | grep -E ':(80|443|8000|8090)\b'
```

(Port 8000 = your existing app. 80/443 may be empty if the site is reached
directly by IP:port, or in use if a web server/HTTPS is configured.)

---

## 1. Get the code

```bash
cd ~
git clone https://github.com/Gopaldixithath/Ortu.git ortu
cd ortu
```

## 2. Configure

```bash
cp .env.example .env
nano .env
```

Set at least:

```
PORT=8090                         # keeps ORTU off your other app's 8000
POSTGRES_PASSWORD=<long-random-string>

# Optional now — required for live payments and the studio admin panel:
ORTU_FITNESS_ADMIN_KEY=<long-random-string>
GOCARDLESS_ENVIRONMENT=sandbox
GOCARDLESS_ACCESS_TOKEN=
GOCARDLESS_WEBHOOK_ENDPOINT_SECRET=
# Leave ORTU_FITNESS_PUBLIC_URL blank while using IP access.
```

## 3. Start it

```bash
docker compose up -d --build
docker compose ps                        # web + db should be "healthy"
docker compose exec web python seed.py   # optional: 8 starter classes
curl -s http://localhost:8090/healthz    # -> {"status":"ok"}
```

## 4. Open the port in Lightsail

Lightsail console → your instance → **Networking** → **IPv4 Firewall** →
**Add rule**:

- Application: **Custom**, Protocol: **TCP**, Port: **8090**

If the OS firewall (ufw) is active, also:

```bash
sudo ufw allow 8090/tcp
```

## 5. Open the site

```
http://<LIGHTSAIL_IP>:8090
```

---

## Managing it

```bash
docker compose logs -f web            # live logs
git pull && docker compose up -d --build   # deploy updates
docker compose down                   # stop (add -v to also wipe ORTU's database)
```

Your other app (`voiceagent` on :8000) is unaffected by any of the above.

---

## Later: a real domain + HTTPS

When you're ready to hand the client a proper `https://` address:

1. Point a DNS **A record** (a subdomain of yours, or the client's domain) at the
   Lightsail public IP.
2. Put a reverse proxy in front — **Caddy** is easiest (automatic Let's Encrypt) —
   routing that hostname to `127.0.0.1:8090`.
3. Set `ORTU_FITNESS_PUBLIC_URL` to the `https://…` address and restart.
4. Remove the public 8090 firewall rule so traffic only arrives via 443.

> **Security note:** `http://IP:8090` is fine for a review, but set up HTTPS
> before taking real Direct Debit payments — GoCardless live mode needs a secure
> public URL, and the studio admin panel should not be served over plain HTTP.
