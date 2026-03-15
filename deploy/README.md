# Deploy on Linux server (Docker + systemd)

## 1) Clone project on server

```bash
sudo mkdir -p /opt/bots
sudo chown -R $USER:$USER /opt/bots
cd /opt/bots
git clone https://github.com/android156/DomainSorter.git
cd DomainSorter/deploy
```

## 2) Configure environment

```bash
cp .env.example .env
nano .env
```

Set a real Telegram token:

```env
TELEGRAM_BOT_TOKEN=...
```

## 3) Start bot with Docker Compose

```bash
mkdir -p data
docker compose up -d --build
docker compose logs -f
```

Database is stored in `deploy/data/bot_data.db`.

## 4) Run under systemd

```bash
sudo cp domainsorter-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now domainsorter-bot
sudo systemctl status domainsorter-bot --no-pager
```

## 5) Update bot

```bash
cd /opt/bots/DomainSorter
git pull
cd deploy
docker compose up -d --build
```
