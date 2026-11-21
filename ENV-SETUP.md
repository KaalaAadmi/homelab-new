# What goes in each .env file

Every stack in `docker/<stack>/` reads its settings from a `.env` file next to its `compose.yaml`.
The repo only has `.env.example` files; the real `.env` files hold passwords and are never
committed (`.gitignore` blocks them).

## The quick way

```bash
cd ~/homelab
python3 scripts/make-env.py          # asks for your domain and email
```

The script:
- creates every `.env` from its `.env.example`
- fills in every password and secret key with a fresh random value (63 of them)
- puts the **same** database password in `docker/postgres/.env` and in each app's `.env`
- fills every web address from your domain, e.g. `https://vault.home.arnavbhattacharya.com`
- makes every `.env` readable only by you
- lists what you still have to fill in by hand (about 25 values)

It never overwrites anything already filled in, so you can run it again at any time. After you
paste in a few keys, run it again to see what's left.

## How to read the tables

| Mark | Meaning |
|---|---|
| **auto** | The script generates it. You don't need to do anything. |
| **domain** | The script fills it from your domain or email. |
| **you** | You get it from another website or account before you start. |
| **after start** | It only exists once that app has started; start the app, copy it, then `docker compose up -d` again. |
| **leave** | Keep the value from the example. |

## Rules for every .env

- **No comments after a value.** Compose reads `KEY=   # note` as the value `# note`. Comments go on their own line.
- **No quotes needed**, and no spaces around `=`.
- **A `$` inside a value must be written `$$`.** This only matters for the two argon2 hashes
  (code-server, Vaultwarden), which contain `$`.
- **Some keys must never change after the first start**, or the app loses data it encrypted with them:
  `AUTHENTIK_SECRET_KEY`, `LITELLM_SALT_KEY`, `N8N_ENCRYPTION_KEY`, OmniRoute's `STORAGE_ENCRYPTION_KEY`,
  Firefly's `APP_KEY`, and every database password once its database exists.
- **Keep a copy of your .env files in Vaultwarden** (or your password manager). They are not in git and
  not in the Postgres backup, so losing the box without a copy means resetting everything.

## Accounts to set up before you start

| What | Where | Goes into |
|---|---|---|
| Cloudflare API token (DNS edit) | dash.cloudflare.com → My Profile → API Tokens → **Edit zone DNS** template, your domain only | `caddy/.env` |
| Cloudflare Tunnel token | one.dash.cloudflare.com → Networks → Tunnels → Create → Docker; copy the long token after `--token` | `cloudflared/.env` |
| NordVPN service credentials | my.nordaccount.com → NordVPN → **Manual setup** → service credentials (not your login) | `media/.env` |
| Groq API key | console.groq.com → API Keys | `ai/.env` |
| OpenRouter API key | openrouter.ai → Keys; set the key's credit limit to $0 | `ai/.env` |
| Gemini API key | aistudio.google.com → Get API key | `ai/.env` |
| ComicVine API key (free) | comicvine.gamespot.com/api (sign in, the key is on that page) | `media/.env`, and Mylar3's settings |
| Discord webhook | your server → a private channel (e.g. #homelab) → Edit Channel → Integrations → Webhooks → New → Copy URL | `ops/.env`, optionally `scrutiny/.env` |
| Discord bot token | discord.com/developers/applications → New Application `Sherpa` → Bot → Reset Token (README: Discord server and Sherpa) | `sherpa/.env` |
| GitHub token (read-only) | github.com/settings/personal-access-tokens → fine-grained, public repositories, read-only | `dashboard/.env` |

---

## postgres  (start this first)

| Variable | Value | |
|---|---|---|
| `TZ`, `APPDATA`, `BACKUP_DIR` | `Europe/Dublin`, `${HOME}/volumes`, `${HOME}/volumes/postgres-backups` | leave |
| `POSTGRES_PASSWORD` | random, 24 letters and digits | auto |
| `AUTHENTIK_DB_PASSWORD` … `YETI_DB_PASSWORD` (15 lines, including Sherpa, Paperless, Mealie and `YETI_DEV_DB_PASSWORD`) | one random password each; the script copies each one into its app's `.env` | auto |

`NEXTCLOUD_DB_PASSWORD` is the one you type by hand, into Nextcloud's web installer (see nextcloud below).

## caddy

| Variable | Value | |
|---|---|---|
| `HOME_DOMAIN` | your domain for local names, e.g. `home.arnavbhattacharya.com` | domain |
| `ACME_EMAIL` | your email (Let's Encrypt writes to it about expiring certificates) | domain |
| `CLOUDFLARE_API_TOKEN` | the DNS-edit token | you |

## cloudflared

| Variable | Value | |
|---|---|---|
| `TUNNEL_TOKEN` | the tunnel token. Make a **new** tunnel: the old token is in the public git history. | you |

## adguard, portainer, uptime-kuma

Nothing to fill in. AdGuard and Portainer ask you to create an admin login on first visit;
Uptime Kuma does too.

## authentik

| Variable | Value | |
|---|---|---|
| `PG_PASS` | same as `AUTHENTIK_DB_PASSWORD` | auto |
| `AUTHENTIK_SECRET_KEY` | random, 64 characters | auto |
| `AUTHENTIK_ERROR_REPORTING__ENABLED`, `COMPOSE_PORT_HTTP`, `COMPOSE_PORT_HTTPS` | `false`, `9000`, `9444` | leave |

First visit: `https://auth.<domain>/if/flow/initial-setup/` to create the admin account.

## dashboard (Glance)

| Variable | Value | |
|---|---|---|
| `HOME_DOMAIN` | same as in caddy | domain |
| `MY_SECRET_TOKEN` | random | auto |
| `GIT_PAT_TOKEN` | the read-only GitHub token | you |
| `ADGUARD_USERNAME`, `ADGUARD_PASSWORD` | the admin login you create in AdGuard | you, after AdGuard's setup |
| `IMMICH_URL` | `http://host.docker.internal:2283` | leave |
| `IMMICH_API_KEY` | Immich → your avatar → Account Settings → API Keys → New | after start |

## monitoring (Prometheus, Grafana)

| Variable | Value | |
|---|---|---|
| `GRAFANA_ROOT_URL` | `https://grafana.<domain>` | domain |
| `AUTHENTIK_URL` | `https://auth.<domain>` | domain |
| `GRAFANA_OAUTH_ENABLED` | `false`; set `true` only if you add the Authentik app below | leave |
| `GRAFANA_OAUTH_CLIENT_ID`, `GRAFANA_OAUTH_CLIENT_SECRET` | optional: from an OAuth2/OpenID provider you create in Authentik for Grafana | you (optional) |

## media

| Variable | Value | |
|---|---|---|
| `TZ`, `PUID`, `PGID`, `APPDATA`, `DATA` | `Europe/Dublin`, `1000`, `1000`, `${HOME}/volumes`, `${HOME}/data` | leave (check `id -u` and `id -g` print 1000) |
| `NORDVPN_SERVICE_USER`, `NORDVPN_SERVICE_PASSWORD` | NordVPN service credentials. Make **new** ones: the old ones are in git history. | you |
| `VPN_COUNTRIES` | `Switzerland,Netherlands` (any NordVPN countries, comma-separated) | leave |
| `RADARR_API_KEY`, `SONARR_API_KEY`, `LIDARR_API_KEY`, `CHAPTARR_API_KEY` | each app → Settings → General → API Key | after start |
| `JELLYDASH_JELLYFIN_API_KEY` | Jellyfin → Dashboard → API Keys → + (name it Jellydash) | after start |
| `SEERR_API_KEY` | Seerr → Settings → General → API Key | after start |
| `JELLYFIN_LINK_URL` | `https://jellyfin.<domain>` | domain |
| `JELLYDASH_ADMIN_USER`, `JELLYDASH_ADMIN_PASSWORD` | `admin`, random | leave / auto |
| `SUWAYOMI_USER`, `SUWAYOMI_PASSWORD` | `admin`, random | leave / auto |
| `KAVITA_API_KEY` | Kavita → your avatar → Settings → API Key | after start |
| `COMICVINE_API_KEY` | your ComicVine key | you |

The media stack starts fine with the "after start" keys empty; only Jellydash, Komf, Recyclarr and
the download-status proxy need them. Fill them in, then `docker compose up -d` again.

## homeassistant

| Variable | Value | |
|---|---|---|
| `TZ`, `APPDATA` | leave | leave |
| `MQTT_USER` | `homeassistant` | leave |
| `MQTT_PASSWORD` | random; you also create this MQTT user with the command in the README | auto |
| `DATA` | optional; Music Assistant reads `${DATA}/media/music` (default `~/data`) | leave |
| `ZIGBEE_DEVICE` | the dongle's path from `ls /dev/serial/by-id/` (only needed once you have the dongle and start Zigbee2MQTT) | you |

## immich

| Variable | Value | |
|---|---|---|
| `UPLOAD_LOCATION`, `DB_DATA_LOCATION`, `TZ`, `IMMICH_VERSION` | leave | leave |
| `DB_PASSWORD` | random, letters and digits only (Immich's own database) | auto |
| `DB_USERNAME`, `DB_DATABASE_NAME` | `postgres`, `immich` | leave |

## nextcloud

Nothing secret in `.env`. On the first visit, Nextcloud's installer asks for the database: choose
**PostgreSQL** and enter user `nextcloud`, the `NEXTCLOUD_DB_PASSWORD` from `postgres/.env`, database
`nextcloud`, host `postgres`.

## firefly

The example is Firefly's full file, but only these lines matter; leave the rest.

| File | Variable | Value | |
|---|---|---|---|
| `.env` | `DB_PASSWORD` | same as `FIREFLY_DB_PASSWORD` | auto |
| `.env` | `APP_KEY` | random, exactly 32 letters and digits | auto |
| `.env` | `STATIC_CRON_TOKEN` | random, exactly 32 characters | auto |
| `.env` | `SITE_OWNER` | your email | domain |
| `.env` | `APP_URL` | `https://firefly.<domain>` | domain |
| `.importer.env` | `VANITY_URL`, `APP_URL` | `https://firefly.<domain>`, `https://importer.<domain>` | domain |
| `.importer.env` | `FIREFLY_III_ACCESS_TOKEN` | Firefly → Options → Profile → OAuth → Personal Access Tokens → Create | after start |

## miniflux

| Variable | Value | |
|---|---|---|
| `BASE_URL` | `https://miniflux.<domain>` | domain |
| `DB_PASSWORD` | same as `MINIFLUX_DB_PASSWORD` | auto |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | `admin`, random (your login) | leave / auto |

## speedtest-tracker

| Variable | Value | |
|---|---|---|
| `APP_KEY` | `base64:` + 32 random bytes | auto |
| `DB_PASSWORD` | same as `SPEEDTEST_DB_PASSWORD` | auto |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | your email, random (your login) | domain / auto |

## obsidian-livesync

| Variable | Value | |
|---|---|---|
| `COUCHDB_USER` | `obsidian` | leave |
| `COUCHDB_PASSWORD` | random. Obsidian's LiveSync plugin needs it too. | auto |
| `VAULT_DIR` | `${HOME}/vault` | leave |

livesync-bridge reads a separate file, `~/volumes/livesync-bridge/dat/config.json` (README:
"Vault copy for YETI"): the CouchDB password above, the database name your LiveSync plugin uses,
and your LiveSync end-to-end encryption passphrase.

## ai (LiteLLM, OmniRoute, SearXNG, llama-swap)

Two files: `.env` and `omniroute.env`.

| File | Variable | Value | |
|---|---|---|---|
| `.env` | `LITELLM_DB_PASSWORD` | same as in `postgres/.env` | auto |
| `.env` | `LITELLM_MASTER_KEY` | `sk-` + random; your LiteLLM admin login | auto |
| `.env` | `LITELLM_SALT_KEY` | `sk-` + random; never change it | auto |
| `.env` | `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `GEMINI_API_KEY` | your provider keys | you |
| `.env` | `OMNIROUTE_API_KEY` | OmniRoute dashboard → API keys → create | after start |
| `.env` | `SEARXNG_BASE_URL` | `https://search.<domain>/` | domain |
| `.env` | `SEARXNG_SECRET` | random | auto |
| `.env` | `OPENWEBUI_SECRET_KEY` | random | auto |
| `.env` | `OPENWEBUI_API_KEY` | a LiteLLM virtual key for Open WebUI (the curl command is in `ai/.env.example`); Open WebUI starts without it but shows no models | after start |
| `.env` | `OPENWEBUI_ENABLE_SIGNUP`, `OPENWEBUI_API_BASE_URL` | `true` until you've made your account, then `false`; leave the URL until YETI runs | leave |
| `omniroute.env` | `JWT_SECRET`, `API_KEY_SECRET`, `STORAGE_ENCRYPTION_KEY` | random each | auto |
| `omniroute.env` | `INITIAL_PASSWORD` | random; first dashboard login, change it afterwards | auto |
| `omniroute.env` | `BASE_URL`, `NEXT_PUBLIC_BASE_URL` | `https://omniroute.<domain>` | domain |

## kan

| Variable | Value | |
|---|---|---|
| `DB_PASSWORD` | same as `KAN_DB_PASSWORD` | auto |
| `BASE_URL` | `https://kan.<domain>` | domain |
| `BETTER_AUTH_SECRET` | random | auto |
| `DISABLE_SIGN_UP` | `false` now; `true` once everyone has an account | leave, then change |
| `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_DISCOVERY_URL` | optional Authentik sign-in | you (optional) |

## n8n

| Variable | Value | |
|---|---|---|
| `N8N_HOST` | `n8n.<domain>` (no https://) | domain |
| `DB_PASSWORD` | same as `N8N_DB_PASSWORD` | auto |
| `N8N_ENCRYPTION_KEY` | random; never change it | auto |

## neohabit

| Variable | Value | |
|---|---|---|
| `DB_PASSWORD` | same as `NEOHABIT_DB_PASSWORD` | auto |
| `JWT_SECRET` | random | auto |
| `FRONTEND_URL` | `https://habits.<domain>` | domain |
| `DISABLE_SIGNUP` | `false` now; `true` once everyone has an account | leave, then change |

## opengym

| Variable | Value | |
|---|---|---|
| `RP_ID` | `gym.<domain>` (no https://) | domain |
| `ORIGIN` | `https://gym.<domain>` | domain |
| everything else | leave as in the example | leave |

## code-server

| Variable | Value | |
|---|---|---|
| `PROXY_DOMAIN` | `code.<domain>` | domain |
| `HASHED_PASSWORD` | an argon2 hash of a password you choose (below) | you |

```bash
echo -n 'the-password-you-want' | docker run --rm -i node:22-alpine npx -y argon2-cli -e
```
Paste the `$argon2id$...` output with every `$` doubled: `$$argon2id$$v=19$$m=...`

## vaultwarden

| Variable | Value | |
|---|---|---|
| `DOMAIN` | `https://vault.<domain>` | domain |
| `DB_PASSWORD` | same as `VAULTWARDEN_DB_PASSWORD` | auto |
| `SIGNUPS_ALLOWED` | `true` until you've made your account, then `false` | leave, then change |
| `ADMIN_TOKEN` | optional: an argon2 hash for the `/admin` page (below); empty turns `/admin` off | you (optional) |

```bash
docker run --rm -it vaultwarden/server /vaultwarden hash      # asks for a password twice
```
Paste the `$argon2id$...` output with every `$` doubled.

## sherpa  (Discord bot for media requests; start after media and postgres)

| Variable | Value | |
|---|---|---|
| `TZ`, `DATA` | `Europe/Dublin`, `${HOME}/data` | leave |
| `DB_PASSWORD` | same as `SHERPA_DB_PASSWORD` | auto |
| `DISCORD_TOKEN` | the Sherpa bot's token | you |
| `DISCORD_GUILD_ID` | right-click the server → Copy Server ID (Developer Mode on) | you |
| `DISCORD_OWNER_ID` | right-click yourself → Copy User ID | you |
| `DISCORD_ADMIN_ROLE_ID`, `DISCORD_HOUSEHOLD_ROLE_ID` | Server Settings → Roles → right-click the role → Copy Role ID | you |
| `DISCORD_ANNOUNCE_CHANNEL_ID` | right-click `#now-available` → Copy Channel ID | you |
| `SEERR_API_KEY`, `RADARR_API_KEY`, `SONARR_API_KEY`, `LIDARR_API_KEY`, `CHAPTARR_API_KEY`, `SUWAYOMI_USER`, `SUWAYOMI_PASSWORD` | the same values as in `media/.env`: fill them there and run the script again | auto (copied) |
| `MYLAR_API_KEY` | Mylar3 → Settings → Web Interface → API → enable, generate | after start |
| `SUWAYOMI_SOURCE` | optional: part of a source's name to search, e.g. `MangaDex`; empty = the first one | leave |
| `LIDARR_ROOT_FOLDER`, `CHAPTARR_EBOOK_ROOT`, `CHAPTARR_AUDIOBOOK_ROOT` | `/data/media/music`, `/data/media/books`, `/data/media/audiobooks` | leave |
| `SHERPA_API_TOKEN` | random; YETI needs the same value later | auto |
| `SYNC_MINUTES` | `15` | leave |

## paperless

| Variable | Value | |
|---|---|---|
| `TZ`, `PUID`, `PGID`, `APPDATA`, `DATA` | `Europe/Dublin`, `1000`, `1000`, `${HOME}/volumes`, `${HOME}/data` | leave |
| `DB_PASSWORD` | same as `PAPERLESS_DB_PASSWORD` | auto |
| `SECRET_KEY` | random | auto |
| `BASE_URL` | `https://docs.<domain>` | domain |
| `ADMIN_USER`, `ADMIN_PASSWORD` | `admin`, random: the first login; change it in the page | leave / auto |

## mealie

| Variable | Value | |
|---|---|---|
| `TZ`, `PUID`, `PGID`, `APPDATA` | `Europe/Dublin`, `1000`, `1000`, `${HOME}/volumes` | leave |
| `DB_PASSWORD` | same as `MEALIE_DB_PASSWORD` | auto |
| `BASE_URL` | `https://recipes.<domain>` | domain |
| `ALLOW_SIGNUP` | `false`; invite people from the admin page | leave |
| `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL` | optional: `http://litellm:4000/v1`, a LiteLLM virtual key, `yeti-fast` | you (optional) |

## ops (Dozzle, Diun)

| Variable | Value | |
|---|---|---|
| `DISCORD_WEBHOOK_URL` | the Discord webhook URL, `https://discord.com/api/webhooks/<id>/<token>` | you |

## scrutiny

| Variable | Value | |
|---|---|---|
| `DISK_1` | your SSD from `lsblk -d -o NAME,MODEL,SIZE`, usually `/dev/nvme0` | leave or check |
| `SCRUTINY_NOTIFY_URLS` | optional Discord alerts: from the same kind of webhook URL `.../webhooks/<id>/<token>`, write `discord://<token>@<id>` | you (optional) |

---

## Checking your work

```bash
python3 scripts/make-env.py            # lists anything still empty
cd docker/<stack> && docker compose config -q && echo ok    # no output but "ok" = every required value is set
```
