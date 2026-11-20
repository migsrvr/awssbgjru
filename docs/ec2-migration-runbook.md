# AWS EC2 Docker Migration & Cutover Runbook (`awssbgjru.me`)

This runbook walks you through launching the EC2 server, configuring your production `.env`, connecting GitHub Actions CI/CD, and switching `awssbgjru.me` from Vercel to EC2 with zero downtime — while keeping costs within **AWS Free Tier + $300 USD credits for 12+ months**.

---

## 1. Set AWS Budget Alerts First (Cost Protection)

Before launching any resources:
1. Open **AWS Console → Billing and Cost Management → Budgets → Create budget**.
2. Choose **Customized (Zero-spend budget)** and another **Monthly cost budget** set to **$15.00 USD** (with alerts at 33% / $5, 100% / $15, and forecasted $25).
3. Add your officer email so your org is alerted immediately if anything unexpected incurs charges.

---

## 2. Launch the EC2 Instance (`ap-southeast-1` Singapore)

1. **Region:** Select **Asia Pacific (Singapore) `ap-southeast-1`** (lowest latency to JRU Philippines).
2. **Name:** `awssbgjru-prod-web`
3. **AMI:** **Ubuntu Server 24.04 LTS (HVM), SSD Volume Type** (`64-bit (x86)`).
4. **Instance Type:** **`t3.micro`** (Free Tier eligible — 2 vCPU, 1 GB RAM).
5. **Key Pair:** Create or select an ED25519 key pair (e.g., `awssbgjru-prod-key.pem`). Save the private key securely — you will also paste it into GitHub Secrets (`EC2_SSH_KEY`).
6. **Network / Security Group (`awssbgjru-sg`):**
   - **SSH (`TCP 22`):** Your IP (or `0.0.0.0/0` if using GitHub-hosted runners over SSH — keys-only auth is enforced on Ubuntu).
   - **HTTP (`TCP 80`):** `0.0.0.0/0` and `::/0` (required for HTTP → HTTPS redirect & Let's Encrypt ACME HTTP-01 challenge).
   - **HTTPS (`TCP 443`):** `0.0.0.0/0` and `::/0` (TCP) + `0.0.0.0/0` (UDP port 443 for HTTP/3 QUIC).
   - *Note:* Do **not** expose port `8001` in the Security Group — Caddy reaches FastAPI internally over the Docker bridge network.
7. **Storage (EBS):** **25 GiB `gp3`** (Free Tier includes up to 30 GiB `gp3`/`gp2` free for 12 months).
8. **Elastic IP (Static Public IPv4):**
   - Go to **EC2 → Elastic IPs → Allocate Elastic IP address**.
   - Immediately **Associate Elastic IP address** with your running `awssbgjru-prod-web` instance.
   - *Cost warning:* An Elastic IP is covered by the 750 hrs/mo Free Tier **only while attached to a running EC2 instance**. Never leave an allocated Elastic IP unattached.

---

## 3. One-Time EC2 Bootstrap (2 GB Swap + Docker + `/opt/awssbgjru`)

SSH into your EC2 instance (`ssh -i awssbgjru-prod-key.pem ubuntu@<ELASTIC_IP>`) and run:

```bash
# 1. Create a 2 GB swap file (prevents OOM spikes on 1 GB RAM t3.micro)
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# 2. Install Docker Engine & Docker Compose plugin
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Allow ubuntu user to run docker without sudo
sudo usermod -aG docker ubuntu

# 3. Create application directory
sudo mkdir -p /opt/awssbgjru
sudo chown -R ubuntu:ubuntu /opt/awssbgjru
```

Log out and SSH back in once so your `docker` group membership takes effect.

---

## 4. Create the Production `.env` on EC2

On the EC2 instance, create `/opt/awssbgjru/.env`:

```bash
nano /opt/awssbgjru/.env
chmod 600 /opt/awssbgjru/.env
```

Paste your production secrets (copy values from your existing `.env` / Vercel project settings):

```dotenv
# Domain & Base URL (CRITICAL: do NOT use localhost in production so dev-token auth bypass is disabled)
DOMAIN=awssbgjru.me
WWW_DOMAIN=www.awssbgjru.me
APP_BASE_URL=https://awssbgjru.me
ALLOWED_ORIGINS=https://awssbgjru.me,https://www.awssbgjru.me

# Groq AI (Captain Hima + AI ATS Resume Evaluation)
GROQ_API_KEY=gsk_your_real_groq_key
GROQ_MODEL=openai/gpt-oss-20b
GROQ_EVAL_MODEL=openai/gpt-oss-120b
RATE_LIMIT_REQUESTS=20
RATE_LIMIT_WINDOW=60
CACHE_TTL=300

# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key

# Gmail SMTP (Port 587 STARTTLS works natively on EC2)
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USER=your-email@gmail.com
EMAIL_PASS=your_gmail_app_password
NOTIFY_EMAIL=notifications@example.com
```

---

## 5. Configure GitHub Actions Secrets (`dev` → `main` Workflow)

In your GitHub repository, open **Settings → Secrets and variables → Actions → New repository secret** and add:

| Secret Name | Value |
| :--- | :--- |
| `EC2_HOST` | Your EC2 Elastic IP address (e.g., `13.212.xx.xx`) |
| `EC2_USER` | `ubuntu` |
| `EC2_SSH_KEY` | Full contents of your private key (`-----BEGIN OPENSSH PRIVATE KEY----- ...`) |
| `GHCR_TOKEN` | *(Optional)* Only needed if you make the repo **private** after transferring it to your GitHub Organization. Create a GitHub Personal Access Token (Classic) with `read:packages` scope. |

### How Your Branching & Org Transfer Works
- **Pushes/PRs to `dev`:** Triggers `.github/workflows/ci.yml` (runs Python unit tests, Node tests, and validates Docker image builds).
- **Merging `dev` → `main`:** Triggers `.github/workflows/deploy.yml` (runs tests, builds & pushes `backend` and `web` images to `ghcr.io`, copies `docker-compose*.yml` to `/opt/awssbgjru`, pulls images on EC2, restarts containers, and verifies health).
- **Moving to Your GitHub Organization:** `deploy.yml` computes `ghcr.io/${{ github.repository }}` dynamically in lowercase. When you transfer `migsrvr/awssbgjru` to your GitHub Org, repository secrets transfer automatically and image names update with zero workflow changes.

---

## 6. Zero-Downtime Namecheap DNS Cutover (`awssbgjru.me`)

1. **Trigger First Deploy to EC2:**
   - Merge `dev` into `main` (or trigger **CD — Build & Deploy to AWS EC2** manually in the GitHub Actions tab).
   - Verify on EC2 that both containers are running:
     ```bash
     docker ps
     curl -i http://127.0.0.1:80/api/health -H "Host: awssbgjru.me"
     ```
2. **Update Namecheap DNS:**
   - Log into **Namecheap → Domain List → `awssbgjru.me` → Manage → Advanced DNS**.
   - Update (or replace the Vercel records with):
     - **Type:** `A Record` | **Host:** `@` | **Value:** `<YOUR_EC2_ELASTIC_IP>` | **TTL:** `1 min` (or `Automatic`)
     - **Type:** `CNAME Record` | **Host:** `www` | **Value:** `awssbgjru.me.` | **TTL:** `1 min` (or `Automatic`)
   - *(Tip)* If you have a CAA record restricting certificate authorities to Vercel, either remove it or allow `letsencrypt.org`.
3. **Automatic HTTPS Provisioning:**
   - Within 1–3 minutes of DNS propagation, Caddy automatically obtains Let's Encrypt TLS certificates for `awssbgjru.me` and `www.awssbgjru.me`.
   - Watch the logs live if desired:
     ```bash
     docker logs -f awssbgjru-web
     ```
4. **Post-Cutover Verification Checklist:**
   - [ ] `https://awssbgjru.me` loads with a valid Let's Encrypt HTTPS padlock.
   - [ ] `https://www.awssbgjru.me` 301-redirects to `https://awssbgjru.me`.
   - [ ] `https://awssbgjru.me/api/health` returns `{"status":"ok", ...}`.
   - [ ] Captain Hima chatbot streams tokens in real time on `/`.
   - [ ] Clean URLs (`/events`, `/register`, `/office`, `/skillbuilder`, `/admin`, `/revision`) load properly.
   - [ ] `/admin` login works with a real officer account, and `curl -i https://awssbgjru.me/api/v1/admin/me -H "Authorization: Bearer dev-admin-token"` returns **`401 Unauthorized`**.
   - [ ] Keep the Vercel project untouched for 24–48 hours as an instant DNS rollback option, then remove `awssbgjru.me` from Vercel.
