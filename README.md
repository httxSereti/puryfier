> [!IMPORTANT]
> 🚀 **Puryfier will soon be publicly released!** Want to test it out early? [Join our Discord](https://discord.gg/vD8zyyMXne) to get access to the beta.

<p align="center">
  <img src="front/public/puryfier_main.png" width="600px" alt="Puryfier" />
  <br><b>🌙 Puryfier</b>
</p>

**Puryfier** is a Chaster extension that link [Pury.fi](https://pury.fi/) with [Chaster.app](https://chaster.app/) to provide more fun to your chastity locks and self lock.

## ✨ Key Features

- ❄️ Lock & Enable Puryfi when your lock is frozen.
- 🔓 Unlock & Disable Puryfi when your lock is unfrozen.
- 📸 Add time when media is censored by Puryfi.

## 🚀 Goals

Censorship is fun, even more when involving other things such as Chastity, Denial and more.. Puryfier is something made to help you to have fun with these.

## 📖 Requirements

- Puryfi 0.8.6.0 or higher (https://pury.fi)
- Docker (https://docs.docker.com/get-started/get-docker/)
- Chaster API Access & a Chaster Extension (https://chaster.app/developers/applications)
- A domain managed by Cloudflare (required for the tunnel)

## 🌟 Run

**⚠ Fill the `.env` file before running using docker compose.**

```bash
git clone https://github.com/httxSereti/puryfier.git
cd puryfier
cp .env.example .env
# Fill .env, then create the Cloudflare Tunnel (see below)
docker compose up -d --build
```

By default Compose starts the app behind a Cloudflare Tunnel (`COMPOSE_PROFILES=tunnel`).
To self-host behind Traefik instead, see [Traefik](#traefik-self-hosting).

## 🧑‍💻 Development

Requirements: Node.js 22.12+, pnpm 11+ and Python 3.12+ with [uv](https://docs.astral.sh/uv/).

The repository is a [Turborepo](https://turborepo.com) monorepo with two workspaces:
`front` (React + Vite) and `server` (FastAPI, managed with `uv`).

```bash
pnpm install   # installs Turborepo and the frontend dependencies
cp front/.env.example front/.env
cp server/.env.example server/.env
pnpm dev       # runs the frontend and backend together
```

| Command | Description |
| --- | --- |
| `pnpm dev` | Run the frontend dev server and the backend with reload |
| `pnpm build` | Build the frontend for production |
| `pnpm lint` | Lint the frontend |
| `pnpm test` | Run the backend test suite |
| `pnpm generate:api` | Export the FastAPI OpenAPI schema and regenerate the frontend DTO types |
| `pnpm check:api` | Fail if `server/openapi.json` or `front/src/types/api.generated.ts` is out of date |

To target a single workspace, use `pnpm --filter server dev` (or `front`).

### API types

Backend request and response types are the source of truth for the frontend:

```text
server/src/domain/entities.py
        │ FastAPI
        ▼
server/openapi.json                       (committed contract)
        │ openapi-typescript
        ▼
front/src/types/api.generated.ts          (generated, do not edit)
        │ aliases
        ▼
front/src/types/api.ts
```

Run `pnpm generate:api` after changing a route, a request model or a response
model, then commit `server/openapi.json` and `front/src/types/api.generated.ts`.
`pnpm check:api` verifies both files are up to date, which makes it suitable for
CI. The WebSocket status frame (`PuryfiRealtimeStatus`) stays hand-written in
`front/src/types/api.ts` because it is not part of the HTTP OpenAPI document.

`pnpm dev` serves the front on `http://localhost:5173` and proxies `/api` and `/ws`
to the local backend on port 8000. The front therefore always uses same-origin URLs,
exactly like in production.

### Dev with the Cloudflare Tunnel (watch)

You do **not** need the whole Compose stack to expose the dev server. The tunnel runs
on its own and can route to the host:

1. Add a dev hostname to the same tunnel (same rule order: specific paths first):

| Public hostname | Path | Service |
| --- | --- | --- |
| `dev.example.com` | `/api` | `http://host.docker.internal:8000` |
| `dev.example.com` | `/ws` | `http://host.docker.internal:8000` |
| `dev.example.com` | — | `http://host.docker.internal:5173` |

2. Start only MongoDB and the tunnel, then run the dev servers:

```bash
docker compose up -d mongo cloudflared
VITE_HMR_CLIENT_PORT=443 pnpm dev
```

`dev.example.com` now serves Vite with hot reload, while `app.example.com` can keep
pointing to the built containers. If you only develop locally, `pnpm dev` alone is
enough; you can also run `docker compose up -d` alongside it (the application ports
are not published, so there is no conflict).

If the tunnel returns `502` with `dial tcp ...:5173: connect: connection refused`,
check that Vite listens on IPv4:

```bash
ss -4 -ltnp | grep 5173
```

It must show `0.0.0.0:5173`. On some Docker Desktop/WSL setups, `host: true` binds
Vite to IPv6 only, which `host.docker.internal` cannot reach; the config therefore
uses `host: "0.0.0.0"`.

If your `front/.env` still contains `VITE_BACKEND_URL`, remove it: the Vite proxy
and the edge router handle `/api` and `/ws`.

The backend needs a reachable MongoDB instance; set `DATABASE_URL` in `server/.env`
(or the repository `.env`). The quickest option is to start just the database from
Compose, which publishes it on `127.0.0.1:27017`:

```bash
docker compose up -d mongo
```

The backend tests use an in-memory MongoDB and do not need one.

## ❓ How to use

### Cloudflare Tunnel (recommended)

Puryfier uses a remotely-managed Cloudflare Tunnel: there is no port to open and no SSL certificate to manage.

1. In the [Cloudflare Zero Trust dashboard](https://one.dash.cloudflare.com/), go to **Networks → Tunnels** and create a tunnel (choose `cloudflared`).
2. Add these public hostnames (same domain, different paths):

| Public hostname | Path | Service |
| --- | --- | --- |
| `app.example.com` | `/api` | `http://server:8000` |
| `app.example.com` | `/ws` | `http://server:8000` |
| `app.example.com` | — | `http://front:80` |

Add the `/api` and `/ws` routes first, then the catch-all route without a path. `/api` and `/ws` go directly to the backend, so the Puryfi WebSocket is reachable at `wss://app.example.com/ws/<token>` without going through the React app. The frontend is served by `front` for every other path.

3. In `.env`, set the domain and the tunnel token:

```dotenv
COMPOSE_PROFILES=tunnel
PUBLIC_DOMAIN=app.example.com
CLOUDFLARE_TUNNEL_TOKEN=eyJ...
```

4. Start the stack:

```bash
docker compose up -d --build
```

`PUBLIC_DOMAIN` is not embedded in the frontend build: the SPA calls `/api` and `/ws` on its own origin, so changing the domain only requires restarting the stack.

### Traefik (self-hosting)

Traefik is kept for deployments that already have a public IP / their own reverse proxy.

1. In `.env`, use the Traefik profile instead of the tunnel one:

```dotenv
COMPOSE_PROFILES=traefik
```

2. Fill `PUBLIC_DOMAIN`, `ACME_EMAIL` and `CF_DNS_API_TOKEN`.
3. Point the `PUBLIC_DOMAIN` DNS record to the server and open ports 80 and 443.
4. Create a Cloudflare API token with these permissions (Let's Encrypt DNS challenge):

```md
Zone / DNS / Edit
Zone / Zone / Read
```

5. Start the stack:

```bash
docker compose up -d --build
```

Traefik routes `/api` and `/ws` directly to the backend; the frontend is only used for all other paths.

> Switching modes: run `docker compose down` first, change `COMPOSE_PROFILES` in `.env`, then `docker compose up -d --build`.

### Common

1. Create a Chaster extension with these URLs, where `<public-url>` is `https://` + `PUBLIC_DOMAIN`:

```md
Main page URL: <public-url>/extension/main
Configuration page URL: <public-url>/extension/configuration
Webhook URL: <public-url>/api/webhooks/extensions/chaster
```

2. Create a Lock or Self-Lock with this extension.
3. Go to the extension in the lock settings page.
4. Link Chaster and Puryfi. The WebSocket URL is generated automatically as `wss://<public-domain>/ws/<token>`.
5. Enjoy!

> Upgrading from the old two-domain setup: update the Chaster webhook URL and re-copy the Puryfi WebSocket URL. The old `api.` hostname is no longer needed.

### Firefox refuses to display the Chaster iframe

If Firefox shows a message like *"this site will not allow Firefox Developer Edition to display the page if it is embedded by another site"*, the response contains either:

- `X-Frame-Options: DENY` or `SAMEORIGIN`, or
- a `Content-Security-Policy: frame-ancestors` that does not allow `chaster.app`.

The front nginx (production) and the Vite dev server both send
`frame-ancestors 'self' https://chaster.app https://*.chaster.app`.
If the header is still blocked, check the response with:

```bash
curl -sI https://your-domain.example | grep -iE 'x-frame-options|content-security-policy'
```

If Cloudflare adds `X-Frame-Options`, disable it in **Rules → Transform Rules → Managed Transforms → Security Headers**, or remove it with a response-header Transform Rule. Also make sure the tunnel origin is up: a Cloudflare `502` error page itself sends `X-Frame-Options: SAMEORIGIN` and will be blocked in the iframe.

## 🤝 How to Contribute / Contact Us

I've made a discord server to centralize information, suggestions, bugs and more.
You can join it [Join our discord here](https://discord.gg/vD8zyyMXne)

* 🌍 [Website](https://paa.ge/sereti)
* ✉️ [Email](mailto:httxsereti@gmail.com)
* 💜 [Discord](https://discord.com/users/939288874281222225)