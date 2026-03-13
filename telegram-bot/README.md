# Domain & IP Route Sorter — Telegram Bot

Multi-user Telegram bot that accumulates, deduplicates, and sorts lists of
domain names and Windows IP route commands. Data is persisted in a local
SQLite database, isolated per Telegram user ID.

---

## Architecture

| File | Responsibility |
|---|---|
| `bot.py` | Aiogram v3 entry point, all message/command handlers |
| `processor.py` | Pure parsing & sorting logic (no I/O) |
| `database.py` | All `aiosqlite` SQL interactions |
| `utils.py` | File chunking and byte-content helpers |

---

## Supported file types

### `.txt` — domain lists
One domain per line (blank lines and `#` comments are ignored).

```
anthropic.com
cdn.prod.website-files.com
claude.ai
```

### `.bat` — IP route lists
Standard Windows route format (both IPv4 and IPv6 are supported):

```
route ADD 104.21.32.39 MASK 255.255.255.255 0.0.0.0
route ADD 2606:4700:3031::6815:2027 MASK 255.255.255.255 0.0.0.0
```

---

## Commands

| Command | Description |
|---|---|
| `/start` | Welcome + help |
| `/help` | Show all commands |
| `/status` | Current list sizes and settings |
| `/set_sort abc` | Sort domains alphabetically (default) |
| `/set_sort domain` | Sort domains by TLD first (right-to-left) |
| `/set_list_len N` | Max domains per output file (default: 300) |
| `/set_ip_list_len N` | Max IP routes per output file (default: 1000) |
| `/get_list [name]` | Export and clear; name defaults to first uploaded filename |

---

## Sort modes for domains

- **abc** — plain `str.sort()` over the full domain string
- **domain** — sort key is the reversed label tuple, so TLD groups together:
  - `ai.com` → key `('com', 'ai')`
  - `z.ai.com` → key `('com', 'ai', 'z')`
  - `api.z.ai.com` → key `('com', 'ai', 'z', 'api')`
  - `banana.com` → key `('com', 'banana')`
  Result order: `ai.com`, `z.ai.com`, `api.z.ai.com`, `banana.com`

---

## Pagination / multi-file export

If the total count exceeds the configured limit, multiple files are produced:

```
my-list.txt
my-list-2.txt
my-list-3.txt
```

After all files are delivered the user's data is cleared from the DB.

---

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set the token (or add to .env)
export TELEGRAM_BOT_TOKEN=<your_token>

# 3. Run
python bot.py
```

The SQLite database (`bot_data.db`) is created automatically in the same
directory as `bot.py` on first run.
