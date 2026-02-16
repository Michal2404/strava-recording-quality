# EC2 Deployment Runbook (SRQ-08)

This runbook deploys the backend on one EC2 host with:
- Docker Compose runtime
- Nginx reverse proxy
- Let's Encrypt TLS
- systemd auto-start on reboot

## 0) Prerequisites

- Ubuntu EC2 instance (22.04 or newer)
- Domain A record pointed to the EC2 public IP (example: `api.example.com`)
- Security group open for:
  - TCP `22` (SSH)
  - TCP `80` (HTTP)
  - TCP `443` (HTTPS)

## 1) Clone repository on EC2

```bash
sudo mkdir -p /opt
sudo chown -R "$USER":"$USER" /opt
cd /opt
git clone <your-repo-url> strava-recording-quality
cd strava-recording-quality
```

## 2) Bootstrap host dependencies

```bash
sudo bash infra/ec2/bootstrap_host.sh
```

What this installs/enables:
- Docker + Docker Compose plugin
- Nginx
- Certbot (`python3-certbot-nginx`)

If your user was just added to docker group, log out/in once.

## 3) Configure environment

```bash
cp infra/ec2/.env.ec2.example infra/ec2/.env.ec2
```

Edit `infra/ec2/.env.ec2`:
- `STRAVA_CLIENT_ID`
- `STRAVA_CLIENT_SECRET`
- `STRAVA_REDIRECT_URI` (must be HTTPS domain callback, e.g. `https://api.example.com/auth/strava/callback`)

Also update Strava developer app settings:
- Authorization Callback Domain: your API domain (for example `api.example.com`)
- Redirect URI: `https://api.example.com/auth/strava/callback`

## 4) Deploy API + DB

```bash
bash infra/ec2/deploy.sh /opt/strava-recording-quality
```

This command:
- builds and starts `api`, `db`, `redis`
- runs `alembic upgrade head`
- verifies local health endpoint

## 5) Configure Nginx + TLS

```bash
sudo bash infra/ec2/setup_nginx_tls.sh api.example.com you@example.com
```

This command:
- installs Nginx site config for your domain
- gets a Let's Encrypt certificate
- configures HTTPS redirect

## 6) Enable reboot-safe startup

```bash
sudo bash infra/ec2/install_systemd_service.sh /opt/strava-recording-quality
```

Check service:
```bash
systemctl status srq-stack.service
```

## 7) Validate deployment

```bash
curl -fsS https://api.example.com/health
```

Expected response:
```json
{"status":"ok"}
```

Open docs in browser:
- `https://api.example.com/docs`

## 8) Reboot validation (acceptance)

```bash
sudo reboot
```

After reconnecting:
```bash
systemctl status srq-stack.service
curl -fsS https://api.example.com/health
```

If both checks pass, startup is reboot-safe with zero manual restart.
