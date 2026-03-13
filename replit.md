# Workspace

## Overview

pnpm workspace monorepo using TypeScript + a Python Telegram bot for domain/IP list management.

## Stack

- **Monorepo tool**: pnpm workspaces
- **Node.js version**: 24
- **Package manager**: pnpm
- **TypeScript version**: 5.9
- **API framework**: Express 5
- **Database**: PostgreSQL + Drizzle ORM
- **Validation**: Zod (`zod/v4`), `drizzle-zod`
- **API codegen**: Orval (from OpenAPI spec)
- **Build**: esbuild (CJS bundle)
- **Python version**: 3.11 (Telegram bot)

## Structure

```text
artifacts-monorepo/
├── artifacts/              # Deployable applications
│   └── api-server/         # Express API server
├── lib/                    # Shared libraries
│   ├── api-spec/           # OpenAPI spec + Orval codegen config
│   ├── api-client-react/   # Generated React Query hooks
│   ├── api-zod/            # Generated Zod schemas from OpenAPI
│   └── db/                 # Drizzle ORM schema + DB connection
├── telegram-bot/           # Python Telegram bot (aiogram v3)
│   ├── bot.py              # Entry point + all handlers
│   ├── processor.py        # Pure parsing & sorting logic
│   ├── database.py         # aiosqlite DB interactions
│   ├── utils.py            # File chunking helpers
│   ├── requirements.txt    # Python dependencies
│   ├── bot_data.db         # SQLite database (auto-created)
│   └── README.md           # Bot documentation
├── scripts/                # Utility scripts
├── pnpm-workspace.yaml
├── tsconfig.base.json
├── tsconfig.json
└── package.json
```

## Telegram Bot

### Purpose
Multi-user bot that accumulates, deduplicates, and sorts:
- **Domain lists** from `.txt` files (one domain per line)
- **IP route lists** from `.bat` files (`route ADD ip MASK mask 0.0.0.0`)

### Commands
| Command | Description |
|---|---|
| `/start` | Welcome |
| `/help` | All commands |
| `/status` | List sizes + settings |
| `/set_sort abc` | Alphabetical sort (default) |
| `/set_sort domain` | Sort by TLD first (right-to-left) |
| `/set_list_len N` | Max domains per file (default 300) |
| `/set_ip_list_len N` | Max IP routes per file (default 1000) |
| `/get_list [name]` | Export & clear all data |

### Workflow
- Name: **Telegram Bot**
- Command: `cd telegram-bot && python3 bot.py`
- Requires secret: `TELEGRAM_BOT_TOKEN`

### Data model (SQLite)
- `settings` — per-user: sort_mode, list_len, ip_list_len, first filenames
- `domain_items` — (user_id, domain) unique pairs
- `ip_items` — (user_id, ip, mask) unique pairs with sort_key BLOB

## TypeScript & Composite Projects

Every package extends `tsconfig.base.json` which sets `composite: true`. The root `tsconfig.json` lists all packages as project references.

- **Always typecheck from the root** — run `pnpm run typecheck`
- **`emitDeclarationOnly`** — only `.d.ts` files during typecheck
- **Project references** — when package A depends on package B, A's `tsconfig.json` must list B in its `references` array

## Root Scripts

- `pnpm run build` — runs `typecheck` first, then recursively runs `build`
- `pnpm run typecheck` — runs `tsc --build --emitDeclarationOnly`

## Packages

### `artifacts/api-server` (`@workspace/api-server`)

Express 5 API server. Routes in `src/routes/`, uses `@workspace/api-zod` for validation.

### `lib/db` (`@workspace/db`)

Database layer using Drizzle ORM with PostgreSQL.

### `lib/api-spec` (`@workspace/api-spec`)

OpenAPI 3.1 spec + Orval config. Run codegen: `pnpm --filter @workspace/api-spec run codegen`

### `lib/api-zod` (`@workspace/api-zod`)

Generated Zod schemas from the OpenAPI spec.

### `lib/api-client-react` (`@workspace/api-client-react`)

Generated React Query hooks and fetch client.
