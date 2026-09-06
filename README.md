# APIX AI Platform

> **Multimodal AI generation product** · FastAPI · aiogram · PostgreSQL · Redis · React/TypeScript Mini App · payments · Docker
>
> Repository codename: `lena_bot`.

APIX is a production AI platform for generating images, video and music. The product combines a Telegram bot, a React Mini App, a standalone web surface, backend APIs, multiple AI providers, billing, referrals and a prompt marketplace.

## What this project demonstrates

- FastAPI backend and aiogram 3 Telegram integration.
- Async SQLAlchemy + PostgreSQL with Alembic migrations.
- Redis-backed FSM and throttling.
- React + TypeScript + Vite Mini App.
- Server-side Telegram WebApp `initData` verification.
- Multi-provider AI integration and provider fallback paths.
- Image, video and music generation workflows.
- Payment integrations including Telegram Stars, card payments and crypto paths.
- Referral accounting, balances, generation history and prompt marketplace.
- Docker Compose deployment and automated tests.

## Architecture

```text
Telegram Bot -----------+
                        |
Telegram Mini App ------+--> FastAPI backend
                        |       |-- generation services --> AI providers
Standalone Web ---------+       |-- payments ------------> payment providers
                                |-- PostgreSQL
                                |-- Redis
                                +-- public media / webhooks

React + TypeScript Mini App --> /api/webapp/*
Telegram updates -------------> /webhook/telegram
Provider callbacks -----------> generation webhook handlers
Payment callbacks ------------> payment webhook handlers
```

## Main product capabilities

### AI generation

The platform supports text-to-image, image editing, text/image-to-video and music generation. Provider integrations are encapsulated behind service clients instead of being implemented directly in Telegram handlers.

Model families represented in the project include Seedream, Nano Banana, GPT Image, Kling, WAN, Seedance, Grok, Veo and Midjourney-compatible flows.

### Mini App

The React Mini App includes:

- home/create flows;
- public feed;
- prompt library/marketplace;
- generation history;
- profile and balance;
- referrals;
- authenticated API communication through Telegram `initData`.

### Billing and economy

The backend owns balances and transaction state. Payment callbacks are verified and processed idempotently so duplicate webhooks do not credit a user twice.

## Stack

| Area | Technology |
| --- | --- |
| Backend | Python 3.12, FastAPI, aiogram 3 |
| Database | PostgreSQL, SQLAlchemy 2, Alembic |
| Runtime state | Redis |
| Frontend | React, TypeScript, Vite |
| AI providers | KIE.AI, CometAPI and provider-specific adapters |
| Payments | Telegram Stars, card/crypto provider integrations |
| Deployment | Docker Compose, Nginx |
| Tests | pytest, pytest-asyncio |

## Repository layout

```text
artflow/
├── bot/              # Telegram handlers, FSM, keyboards, middlewares
├── api/              # AI/provider clients, webhooks and web APIs
├── db/               # ORM models, repositories and migrations
├── payments/         # payment provider adapters
├── webapp/           # React + TypeScript Mini App
├── landing/          # standalone public web surface
├── tests/            # backend/provider/auth contracts
├── Dockerfile
└── docker-compose.yml
```

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

For the Mini App:

```bash
cd webapp
npm install
npm run dev
```

Backend checks:

```bash
pytest
```

## Engineering focus

APIX is useful as a portfolio project because it shows a complete product boundary: Telegram UX, web frontend, backend API design, database migrations, payments, provider integrations and deployment are all part of the same system rather than isolated demo scripts.
