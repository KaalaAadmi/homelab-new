# HomeLab

Docker Compose stacks for the homelab. One folder per stack under `docker/`.
Secrets live in a local `.env` per stack (never committed); each stack has a `.env.example`.

## Where everything lives

```
~/homelab/                      this git repo
  docker/<stack>/compose.yaml   + your local .env
~/volumes/                      app settings and databases (backed up)
~/data/                         downloads and media, one folder so moves are instant
  torrents/{movies,tv,anime,music,comics,books,audiobooks}   Deluge downloads here
  media/{movies,tv,anime,music,comics,manga,books,audiobooks,podcasts}
                                the *arr apps file finished downloads here;
                                Jellyfin, Audiobookshelf and Kavita read it
  tdarr-cache/                  Tdarr's scratch space while it re-encodes
  nextcloud/                    Nextcloud files
  immich/                       Immich photos and videos
~/projects/                     your code (code-server can see it)
~/vault/                        Markdown copy of your Obsidian vault (livesync-bridge, YETI)
```

`~` is resolved with `${HOME}`, so **always run `docker compose` as your own user, never with `sudo`**
(with `sudo`, `${HOME}` becomes `/root` and every path points to the wrong place).

## One-time setup

```bash
# Let your user run docker without sudo (log out and back in afterwards)
sudo usermod -aG docker $USER

# Shared networks: "homelab" for Caddy, cloudflared, Glance, Prometheus and YETI to reach services,
# "db" for apps to reach the shared Postgres
docker network create homelab
docker network create db

# Folders, owned by you
mkdir -p ~/volumes ~/volumes/{n8n,suwayomi,recyclarr,diun,vaultwarden} ~/volumes/opengym/data ~/volumes/models ~/projects
mkdir -p ~/volumes/livesync-bridge/dat ~/vault
mkdir -p ~/data/{torrents,media}/{movies,tv,anime,music,comics,books,audiobooks} ~/data/media/{podcasts,manga}
mkdir -p ~/data/tdarr-cache ~/data/nextcloud ~/data/immich
```

Docker creates any other folder it needs inside `~/volumes` by itself.
On Fedora, SELinux is on: bind mounts carry `:Z` (private) or `:z` (shared) so containers can write.
Ubuntu ignores these flags.

## Stacks

Every web UI is also at `https://<name>.<HOME_DOMAIN>` through Caddy (see "Local HTTPS names").

| Stack | What | Port(s) | Name(s) |
|---|---|---|---|
| `postgres` | Shared Postgres 17 + pgvector: one database and login per app | – (Docker network `db` only) | – |
| `media` | Gluetun (NordVPN), Deluge, Prowlarr, FlareSolverr, Radarr, Sonarr, Lidarr, Mylar3, Bazarr, Seerr, Jellyfin | 8112, 9696, 7878, 8989, 8686, 8090, 6767, 5055, 8096 | deluge, prowlarr, radarr, sonarr, lidarr, mylar, bazarr, seerr, jellyfin |
| `media` (books) | Chaptarr (ebooks + audiobooks), Audiobookshelf (audiobooks, ebooks), Kavita (comics, manga) | 8789, 13378, 5001 | chaptarr, audiobooks, comics |
| `media` (manga) | Suwayomi (downloads manga, behind the VPN), Komf (series details for Kavita) | 4567, 8086 | manga, komf |
| `media` (profiles) | Recyclarr (TRaSH Guides quality profiles for Sonarr and Radarr, daily) | – | – |
| `media` (discovery) | SuggestArr, Boxarr, Blockbusterr | 5000, 8888, 9091 | suggestarr, boxarr, blockbusterr |
| `media` (extras) | Tdarr (re-encode), Jellydash (Jellyfin stats), arr-readonly (YETI's download status) | 8265, 8094, – | tdarr, jellydash |
| `sherpa` | Sherpa: the Discord bot for media requests (all seven kinds), and YETI's way to request | 8320 (YETI's API, Tailscale only) | – |
| `ai` | LiteLLM, OmniRoute, llama-swap (small local models), SearXNG, Open WebUI | 4000, 20128, 8099, 8089, 3010 | litellm, omniroute, llama, search, chat |
| `homeassistant` | Home Assistant, Music Assistant (music player), ESPHome (Voice PE firmware), Mosquitto, Matter server, Zigbee2MQTT | 8123, 8095, 8097, 6052, 1883, 8080 | ha, music, esphome, zigbee |
| `caddy` | Reverse proxy with a wildcard HTTPS certificate | 80, 443 | – |
| `adguard` | AdGuard Home (DNS + ad blocking) | 53, 3000 | adguard |
| `monitoring` | Prometheus, Grafana, node-exporter, cAdvisor | 1234, 9898, 8282 | grafana, prometheus |
| `dashboard` | Glance + read-only Docker socket proxy | 8081 | glance |
| `portainer` | Portainer | 9443 | portainer |
| `authentik` | Authentik SSO | 9000, 9444 | auth |
| `cloudflared` | Cloudflare Tunnel (public access for chosen apps) | – | – |
| `nextcloud` | Nextcloud + Redis (database on the shared Postgres) | 9875, 9876 | nextcloud |
| `firefly` | Firefly III + importer + cron (database on the shared Postgres) | 1212, 1313 | firefly, importer |
| `immich` | Immich | 2283 | immich |
| `miniflux` | Miniflux RSS reader (YETI's news feeds) | 8085 | miniflux |
| `speedtest-tracker` | Speedtest Tracker | 8070 | speedtest |
| `uptime-kuma` | Uptime Kuma: phone alerts when a service stops answering | 3001 | uptime |
| `kan` | Kan boards (Trello-style) | 3005 | kan |
| `paperless` | Paperless-ngx: searchable scans and PDFs (bills, letters, warranties) | 8010 | docs |
| `mealie` | Mealie: recipes, meal plans, shopping lists | 9925 | recipes |
| `n8n` | n8n automations | 5678 | n8n |
| `opengym` | openGym workout tracker | 8283 | gym |
| `neohabit` | Neohabit habit tracker | 8284 | habits |
| `code-server` | VS Code in the browser (sees `~/homelab` and `~/projects` only) | 8443 | code |
| `vaultwarden` | Vaultwarden password manager (Bitwarden apps) | 8222 | vault |
| `ops` | Dozzle (container logs), Diun (update alerts to Discord), read-only socket proxy | 9999 | logs |
| `scrutiny` | Scrutiny: SSD health, warns before a drive fails | 8087 | disks |
| `obsidian-livesync` | CouchDB + livesync-bridge (Markdown copy of the vault in `~/vault`) | 5984 | couchdb |

**Must run on the box in Dublin:** `homeassistant` (the Zigbee dongle and devices must be in the same house)
and `adguard` + `caddy` if they're your home network's DNS. Everything else can run on either box.

## Start a stack

First create every `.env` at once. The script fills in all passwords, secret keys, matching
database passwords and web addresses, then lists what's left for you
(**ENV-SETUP.md** explains every value and where to get it):
```bash
cd ~/homelab && python3 scripts/make-env.py
```
Then, for each stack:
```bash
cd ~/homelab/docker/<stack>
nano .env                   # fill in anything the script listed for this stack
docker compose up -d
docker compose ps           # everything should say "running" / "healthy"
docker compose logs -f      # if not
```

Suggested order: `adguard`, `caddy`, `postgres`, `monitoring`, `dashboard`, `portainer`, `media`,
`homeassistant`, `ai`, then the rest. `cloudflared` last, once the services it points at are up.
Every stack that uses a database needs `postgres` running first.

**Never put a comment on the same line as a value in `.env`.** Compose reads
`KEY=   # note` as the value `# note`, not as empty. The examples keep comments on their own lines.

## Who can reach what

Docker opens every published port in its own firewall rules, which skip ufw and firewalld.
Without the steps below, anyone on your home Wi-Fi (flatmates, guests) can open Tdarr,
Prometheus, llama-swap and the rest directly. Three layers fix that:

**1. Limit Docker's ports to Tailscale** (`host/firewall`). From the home network only Caddy
(80/443), DNS (53), Jellyfin (8096, for TV apps) and MQTT (1883) stay open; everything else is
reachable only from your Tailscale devices and from other containers.
```bash
sudo install -m 755 host/firewall/docker-user-firewall.sh /usr/local/sbin/
sudo install -m 644 host/firewall/docker-user-firewall.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now docker-user-firewall.service
sudo iptables -S DOCKER-USER          # check the rules are there
```
(Assumes your home network isn't in 172.16.0.0/12; most routers use 192.168.x.x. To open
another port to the home network, add it to `LAN_ALLOWED_TCP` in the script and re-run it.)

**2. Firewall the box itself** (ufw, for SSH and Home Assistant, which uses the host network).
Do this after the Ubuntu reinstall; replace 192.168.1.0/24 with your home network:
```bash
sudo ufw default deny incoming && sudo ufw default allow outgoing
sudo ufw allow in on tailscale0                                   # first, so you don't lock yourself out
sudo ufw allow from 192.168.1.0/24 to any port 22 proto tcp       # SSH from home, key-only
sudo ufw allow from 192.168.1.0/24 to any port 8123 proto tcp     # Home Assistant
sudo ufw allow from 192.168.1.0/24 to any port 5353 proto udp     # mDNS, device discovery
sudo ufw allow from 192.168.1.0/24 to any port 5540 proto udp     # Matter
sudo ufw allow from 192.168.1.0/24 to any port 8097 proto tcp     # Music Assistant: speakers fetch the audio here
sudo ufw enable
```
If a smart-home device stops being found, its integration may need one more port from the LAN.

**3. A login in front of apps that have none.** Caddy asks for an Authentik login before showing
Glance, Prometheus, Tdarr, llama-swap, SearXNG, Komf, Bazarr, Mylar3, Boxarr, Blockbusterr,
SuggestArr, Zigbee2MQTT, Dozzle and Scrutiny (`import protected` in the Caddyfile). Set it up once:
1. Authentik → Applications → Providers → Create → **Proxy Provider** named `homelab-forward-auth`,
   mode **Forward auth (domain level)**, Authentication URL `https://auth.<HOME_DOMAIN>`,
   Cookie domain `<HOME_DOMAIN>`.
2. Applications → Create an application `Homelab` using that provider. Under its Policy bindings,
   allow only your own account (or a `homelab-admins` group), so flatmates' accounts can't get in.
3. Outposts → edit **authentik Embedded Outpost** → add the `Homelab` application.
4. `cd ~/homelab/docker/caddy && docker compose restart`. Opening e.g. `https://tdarr.<HOME_DOMAIN>`
   should now show the Authentik login first.

Apps with their own login (the *arr apps, Seerr, Jellyfin, Nextcloud, Grafana, Portainer and so on)
are left alone, so you don't log in twice.

## fail2ban

Bans an address for an hour after 5 failed logins. It watches SSH and Vaultwarden (where a
password guesser would go). Authentik has its own lockout for repeated failures.
```bash
sudo apt install -y fail2ban
sudo cp host/fail2ban/filter.d/vaultwarden*.conf /etc/fail2ban/filter.d/
sed "s/YOUR_USER/$USER/" host/fail2ban/jail.d/homelab.local | sudo tee /etc/fail2ban/jail.d/homelab.local >/dev/null
sudo systemctl enable --now fail2ban && sudo systemctl restart fail2ban
sudo fail2ban-client status                # should list sshd, vaultwarden, vaultwarden-admin
```
Your own Tailscale and container addresses are never banned. Start Vaultwarden once before
fail2ban, so its log file exists. Unban an address: `sudo fail2ban-client unban <ip>`.

## Shared Postgres

One Postgres 17 (with pgvector) serves Authentik, Miniflux, Speedtest Tracker, Nextcloud, Firefly,
LiteLLM, Kan, n8n, Neohabit and later YETI. Each app has its own database and login and can't
open anyone else's. Immich keeps its own database; CouchDB stays for Obsidian.

1. `cd ~/homelab/docker/postgres && cp .env.example .env && nano .env`: set `POSTGRES_PASSWORD`
   and one password per app (`openssl rand -hex 24` for each).
2. `docker compose up -d`. On the first start it creates every database that has a password.
3. Put each app's password in that app's own `.env` too (each example says which line).
4. Adding an app later: add its line to `init/10-app-databases.sh` and its password to `.env`, then
   ```bash
   docker compose up -d
   docker exec postgres bash /docker-entrypoint-initdb.d/10-app-databases.sh
   ```

**Backups.** `./backup.sh` dumps every database to `~/volumes/postgres-backups` and keeps 14 days.
To run it nightly at 03:30:
```bash
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/postgres-backup.service <<EOF
[Service]
Type=oneshot
ExecStart=%h/homelab/docker/postgres/backup.sh
EOF
cat > ~/.config/systemd/user/postgres-backup.timer <<EOF
[Timer]
OnCalendar=*-*-* 03:30
Persistent=true
[Install]
WantedBy=timers.target
EOF
systemctl --user daemon-reload && systemctl --user enable --now postgres-backup.timer
sudo loginctl enable-linger $USER     # so it runs even when you're not logged in
```
Upgrading Postgres to a new major version upgrades every app's database at once: dump first,
and read the release notes.

## AI stack (LiteLLM, OmniRoute, local models, SearXNG)

1. Download the two small models (about 1.1 GB together):
   ```bash
   cd ~/volumes/models
   curl -LO https://huggingface.co/Qwen/Qwen3-Embedding-0.6B-GGUF/resolve/main/Qwen3-Embedding-0.6B-Q8_0.gguf
   curl -LO https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/main/Qwen3-4B-Q4_K_M.gguf
   ```
2. `cd ~/homelab/docker/ai`, copy both examples (`.env` and `omniroute.env`), fill them in, then
   `docker compose up -d`.
3. **OmniRoute** (`https://omniroute.<HOME_DOMAIN>`): sign in with `INITIAL_PASSWORD` and change it.
   Add only API-key providers (Groq, Cerebras, NVIDIA NIM, Cloudflare). Don't connect any
   subscription login, and leave its stealth mode and no-account pools off. Create an API key
   and put it in `OMNIROUTE_API_KEY` in `.env`, then `docker compose up -d` again.
4. **LiteLLM** (`https://litellm.<HOME_DOMAIN>/ui`, sign in with the master key): create one virtual
   key per caller with its own budget: `yeti-core`, `yeti-coding`, `shotlisted`, `suggestarr`.
   The model roles are in `litellm.yaml`; `yeti-private` and `yeti-embed` never fall back to the cloud.
5. Test it:
   ```bash
   curl -s http://localhost:4000/v1/chat/completions -H "Authorization: Bearer <a virtual key>" \
     -H 'Content-Type: application/json' -d '{"model":"yeti-fast","messages":[{"role":"user","content":"hi"}]}'
   curl -s 'http://localhost:8089/search?q=dublin+weather&format=json' | head -c 300
   ```

## Vault copy for YETI (livesync-bridge)

livesync-bridge keeps `~/vault` (plain Markdown) and your Obsidian vault in sync in both
directions, through CouchDB. YETI reads and writes the Markdown copy.
1. The bridge runs as user 1993 inside its container, so give it and you access to `~/vault`:
   ```bash
   sudo apt install -y acl
   sudo setfacl -R -m u:1993:rwX -m d:u:1993:rwX -m u:$USER:rwX -m d:u:$USER:rwX ~/vault
   ```
2. Copy `docker/obsidian-livesync/livesync-bridge.config.example.json` to
   `~/volumes/livesync-bridge/dat/config.json` and fill in the CouchDB password, the database name
   your LiveSync plugin uses, and your end-to-end encryption passphrase (Obsidian → LiveSync settings).
   It holds secrets, which is why it lives in `~/volumes`, not in the repo.
3. `cd ~/homelab/docker/obsidian-livesync && docker compose up -d --build`. The first build takes
   a few minutes. `docker compose logs -f livesync-bridge` should show notes arriving in `~/vault`.
4. Hourly git commits of `~/vault`, so any change (yours or YETI's) can be undone:
   ```bash
   mkdir -p ~/.config/systemd/user
   cp host/vault-git/vault-git.{service,timer} ~/.config/systemd/user/
   systemctl --user daemon-reload && systemctl --user enable --now vault-git.timer
   ```

## Vaultwarden

1. Add `VAULTWARDEN_DB_PASSWORD` to `docker/postgres/.env`, then run the database script
   (Shared Postgres, step 4). Put the same password in `docker/vaultwarden/.env`.
2. `docker compose up -d`, open `https://vault.<HOME_DOMAIN>`, create your account.
3. Set `SIGNUPS_ALLOWED=false` and `docker compose up -d`. Invite anyone else from `/admin`.
4. In the Bitwarden apps, choose **Self-hosted** and enter `https://vault.<HOME_DOMAIN>`.
   Away from home your phone needs Tailscale on to sync; the apps keep an offline copy meanwhile.
5. Turn on two-step login for your account (Settings → Security → Two-step login).

Your passwords now live on this box, so the nightly Postgres backup matters more than ever.

## Ops: Dozzle, Diun, Scrutiny

- **Dozzle** (`https://logs.<HOME_DOMAIN>`, behind the Authentik login): live logs for every
  container. It reads Docker through a read-only proxy and can't start, stop or enter containers.
- **Diun** posts to a Discord channel when an image you run has a newer version, every 6 hours.
  Create a webhook in a private Discord channel and put its URL in `docker/ops/.env`. It never
  updates anything: read the release notes, then `docker compose pull && docker compose up -d`.
- **Scrutiny** (`https://disks.<HOME_DOMAIN>`): SSD health. Check your drive name with
  `lsblk -d -o NAME,MODEL,SIZE` and set `DISK_1` in `.env` (usually `/dev/nvme0`). When you add a
  second SSD, uncomment its line in the compose file. For Discord alerts, fill `SCRUTINY_NOTIFY_URLS`.

## AdGuard Home: freeing port 53

Fedora and Ubuntu run a local DNS stub on port 53, which blocks AdGuard. Turn the stub off
(the box keeps using its normal DNS servers):

```bash
sudo mkdir -p /etc/systemd/resolved.conf.d
printf '[Resolve]\nDNSStubListener=no\n' | sudo tee /etc/systemd/resolved.conf.d/adguardhome.conf
sudo mv /etc/resolv.conf /etc/resolv.conf.backup
sudo ln -s /run/systemd/resolve/resolv.conf /etc/resolv.conf
sudo systemctl restart systemd-resolved
getent hosts github.com     # must still print an address before you go on
```

Then `docker compose up -d` in `docker/adguard`, open `http://<box>:3000`, and in the wizard set the
**admin web interface to port 3000** (port 80 belongs to Caddy) and DNS to port 53.

## Local HTTPS names (Caddy + AdGuard + Tailscale)

Result: `https://jellyfin.home.<domain>` (and the rest) with a real certificate, from any of your
devices on Tailscale, and nothing exposed to the internet.

1. **Cloudflare:** create an API token with *Zone → DNS → Edit* for your domain only. Put it, your
   email and `HOME_DOMAIN` in `docker/caddy/.env`. Then `docker compose up -d --build` in `docker/caddy`.
2. **AdGuard** → Filters → DNS rewrites: add `*.home.<domain>` → this box's Tailscale IP
   (`tailscale ip -4`).
3. **Tailscale admin console** → DNS → Add nameserver → Custom → this box's Tailscale IP,
   tick **Restrict to domain** and enter `home.<domain>`. Only those names go to AdGuard; the rest of
   your DNS is untouched. (To use AdGuard's ad blocking on all your devices, add it without the
   restriction later.)

## Home Assistant

1. Create the MQTT login before the first start (Mosquitto refuses to start without it):
   ```bash
   cd ~/homelab/docker/homeassistant && cp .env.example .env && nano .env   # set MQTT_PASSWORD
   docker compose run --rm mosquitto sh -c \
     'mosquitto_passwd -c -b /mosquitto/data/passwd homeassistant "YOUR_MQTT_PASSWORD" &&
      chown mosquitto:mosquitto /mosquitto/data/passwd && chmod 0700 /mosquitto/data/passwd'
   docker compose up -d
   ```
2. Open `http://<box>:8123` and create your account.
3. So it works through Caddy, add this to `~/volumes/homeassistant/configuration.yaml`, then restart it:
   ```yaml
   http:
     use_x_forwarded_for: true
     trusted_proxies:
       - 172.16.0.0/12
   ```
4. Integrations: **MQTT** (broker `localhost`, port 1883, the MQTT login) and **Matter**
   (`ws://localhost:5580/ws`).
5. When the ZBT-2 dongle arrives: plug it in, put the path from `ls /dev/serial/by-id/` in
   `ZIGBEE_DEVICE` in `.env`, then `docker compose --profile zigbee up -d`.

## Media stack: wiring inside the apps

Deluge, Prowlarr and FlareSolverr run inside Gluetun's network, so all their traffic goes
through the VPN, and they stop if the VPN drops. Their web UIs are published on Gluetun.

Apps behind the VPN can't look up other containers by name, so the *arr apps have fixed
addresses on the `media` network and Gluetun's firewall allows that subnet:

| App | Address for Prowlarr |
|---|---|
| Radarr | `http://172.30.0.11:7878` |
| Sonarr | `http://172.30.0.12:8989` |
| Lidarr | `http://172.30.0.15:8686` |
| Mylar3 | `http://172.30.0.16:8090` |
| Chaptarr | `http://172.30.0.18:8789` (add it in Prowlarr as a Readarr app) |

1. **Deluge** (port 8112, default password `deluge`: change it).
   Preferences → Downloads: download to `/data/torrents`. Plugins → enable **Label**.
   Preferences → Queue → Seeding: set a share ratio (for example 1.0), tick **Share Ratio Reached**
   and choose **Remove**, so finished torrents stop seeding by themselves. (On a private tracker,
   follow its own ratio rules instead, or you can get banned.)
2. **Prowlarr** (port 9696). Add indexers. Settings → Apps: add Radarr, Sonarr, Lidarr
   and Mylar with the addresses above, and Prowlarr server `http://gluetun:9696` in each.
   Indexer proxy FlareSolverr (only if an indexer needs it): `http://localhost:8191`.
   For anime, add the **Nyaa.si** indexer (public, no account) and let Prowlarr sync it to Sonarr;
   in Sonarr, check its categories include **Anime** (5070).
3. **Radarr / Sonarr / Lidarr**. Root folders `/data/media/movies`, `/data/media/tv`, `/data/media/music`.
   In Sonarr also add `/data/media/anime` as a second root folder. When you add an anime show, pick
   that folder, **Series Type: Anime** (it then uses absolute episode numbers) and the
   **[Anime] Remux-1080p** profile that Recyclarr creates.
   Download client Deluge: host `gluetun`, port `8112`, label `radarr` / `sonarr` / `lidarr`,
   and tick **Remove Completed** so the app clears finished downloads after importing them.
4. **Mylar3** (port 8090). Comic location `/data/media/comics`.
   Download client Deluge: host `gluetun`, port `8112`, label `mylar`.
5. **Bazarr** (port 6767). Radarr `radarr:7878`, Sonarr `sonarr:8989` (API keys from each app's
   Settings → General). It sees the same `/data/media` paths, so no path mapping is needed.
6. **Jellyfin** (port 8096). Libraries: `/data/media/movies`, `/data/media/tv`, `/data/media/music`.
7. **Seerr** (port 5055). Jellyfin `http://jellyfin:8096`, Radarr `http://radarr:7878`,
   Sonarr `http://sonarr:8989`.
8. **Chaptarr** (port 8789). Root folders `/data/media/books` (ebooks) and `/data/media/audiobooks`.
   Download client Deluge: host `gluetun`, port `8112`, label `chaptarr`, **Remove Completed** on.
   It's beta software: expect the odd rough edge.
9. **Audiobookshelf** (port 13378). Create libraries: Audiobooks → `/audiobooks`,
   Books → `/books`, Podcasts → `/podcasts`. Comics and manga go to Kavita instead.
10. **Mylar3 and ComicVine.** Get a free API key at comicvine.gamespot.com/api and paste it into
    Mylar3 → Settings → Web Interface / ComicVine API. Mylar3 can't search or tag comics without it.
    (Mylar3 is for Western comics only; manga comes from Suwayomi.) Put the same key in `.env` as
    `COMICVINE_API_KEY` for Komf.
11. **Kavita** (port 5001, `https://comics.<HOME_DOMAIN>`). Create your admin account, then a library
    of type **Manga** → `/manga` and one of type **Comic** → `/comics` (Mylar3 fills `comics`,
    Suwayomi fills `manga`). In the reader, set manga to right-to-left.
    - **Laptop:** just the browser.
    - **iPhone:** open it in Safari → Share → Add to Home Screen, and it behaves like an app. For a
      native app, Panels or Komic connect to Kavita directly (or use the OPDS link from your Kavita
      user settings). Reading progress syncs between devices because it's kept on the server.
    - Away from home it works over Tailscale, like everything else here.
12. **Suwayomi** (port 4567, `https://manga.<HOME_DOMAIN>`, log in with `SUWAYOMI_USER` /
    `SUWAYOMI_PASSWORD`). It runs inside the VPN, like Deluge.
    - Settings → Browse → Extension repositories: add the extension repository you want to use;
      Suwayomi ships with none. Then install the source extensions.
    - Settings → Library: turn on automatic updates and **download new chapters** for the
      categories you follow, so new chapters arrive by themselves.
    - Chapters land in `~/data/media/manga` as `.cbz` files and show up in Kavita's Manga library
      after its next scan. Read in Kavita; Suwayomi is only the downloader.
13. **Komf** (port 8086). Put `KAVITA_API_KEY` (Kavita → your user → Settings → API Key) and
    `COMICVINE_API_KEY` in `.env`, then `docker compose up -d`. It fills in summaries, genres and
    covers for new series automatically (MangaUpdates first, then AniList, then ComicVine for
    comics). If it picks the wrong series, its browser extension lets you fix the match from
    Kavita's page. Settings: `docker/media/komf/application.yml`.
14. **Recyclarr** (no web page). Once `SONARR_API_KEY` and `RADARR_API_KEY` are in `.env`:
    ```bash
    docker exec recyclarr recyclarr sync --preview   # shows what it would change
    docker exec recyclarr recyclarr sync             # does it now (then daily on its own)
    ```
    It creates the profiles listed in `docker/media/recyclarr.yml`; choose them per show and film.
15. **Jellyfin anime library.** Dashboard → Libraries → Add: type **Shows**, name Anime,
    folder `/data/media/anime`. Keep your TV library on `/data/media/tv` only, so anime
    isn't listed twice.
16. **SuggestArr** (port 5000). Jellyfin `http://jellyfin:8096`, Seerr `http://seerr:5055`.
    For AI suggestions use an OpenAI-compatible endpoint: `http://litellm:4000/v1`, model `yeti-fast`,
    key = the `suggestarr` virtual key from LiteLLM.
17. **Boxarr** (port 8888). Radarr `http://radarr:7878` and its API key.
18. **Blockbusterr** (port 9091). Trakt app credentials (trakt.tv → Settings → Your API Apps), then
    Radarr `http://radarr:7878`, Sonarr `http://sonarr:8989` (or Seerr `http://seerr:5055` if you want
    to approve each title first). Preview a job before scheduling it. YETI's suggestions read the
    same Trakt lists.
19. **Tdarr** (port 8265). It re-encodes your real files. First make a test library that points at
    a folder with copies of two or three titles, run your flow there, check the results play, and only
    then add `/media/movies` and `/media/tv`. Use a VAAPI (`hevc_vaapi`) flow so the iGPU does the work.
20. **Jellydash** (port 8094). Create a Jellyfin API key (Dashboard → API Keys) and put it, Seerr's API
    key and an admin password in `.env`, then `docker compose up -d`.
21. **YETI's download status** (`arr-readonly`). Put the Radarr, Sonarr, Lidarr and Chaptarr API keys
    in `.env` and `docker compose up -d`. YETI reads `http://arr-readonly:8080/radarr/queue` (and
    `/sonarr/queue`, `/lidarr/queue`, `/chaptarr/queue`). Anything other than a GET to those paths is
    refused, so YETI can see what's downloading but can't add, delete or change anything.

Check the VPN: `docker exec gluetun wget -qO- https://ipinfo.io` should show the VPN country, not your home IP.

## Music Assistant, ESPHome and Open WebUI

- **Music Assistant** (`https://music.<HOME_DOMAIN>`, port 8095, in the `homeassistant` stack). Create your
  login on first visit. Add the **Filesystem (local disk)** music provider with the path `/media/music`
  (Lidarr's folder, read-only), and any streaming service you use. In Home Assistant add the
  **Music Assistant** integration (server `http://localhost:8095`): Home Assistant's speakers, including the
  Voice PE with the Edifier on its jack, then show up as players, and YETI can play music through Home
  Assistant. Speakers fetch the audio from port 8097, which is why ufw allows it from the home network.
  On your phone, listen to the same library through Jellyfin (Finamp on iPhone and Android).
- **ESPHome** (`https://esphome.<HOME_DOMAIN>`, port 6052, behind the Authentik login). Used to build and flash
  the Voice PE's firmware, including the custom "Hey Yeti" wake word once it's trained. Adopt the Voice PE
  here after it's set up in Home Assistant.
- **Open WebUI** (`https://chat.<HOME_DOMAIN>`, port 3010, in the `ai` stack). A chat page for trying the
  models. Make a LiteLLM virtual key for it (the command is in `ai/.env.example`), put it in
  `OPENWEBUI_API_KEY`, `docker compose up -d`, create your account, then set
  `OPENWEBUI_ENABLE_SIGNUP=false` and `docker compose up -d` again. Once YETI runs, point
  `OPENWEBUI_API_BASE_URL` at YETI instead and you're chatting with YETI.

## Discord server and Sherpa (media requests)

Sherpa is the one bot the household uses to get things downloaded. It searches the right app for
each kind of thing and sends the request there:

| Command | Searches | Downloads with |
|---|---|---|
| `/movie`, `/series`, `/anime` | TMDB, through Seerr | Radarr / Sonarr (anime goes to Sonarr's anime folder) |
| `/music` | MusicBrainz, through Lidarr. A song request adds the album or single it's on. | Lidarr |
| `/book` (choose ebook or audiobook) | Chaptarr | Chaptarr |
| `/comic` | ComicVine, through Mylar3 | Mylar3 |
| `/manga` | your Suwayomi source | Suwayomi, then new chapters by themselves |
| `/downloads`, `/mine` | what's downloading; what you've asked for and how much space it takes | – |
| `/space`, `/link` (Admin) | disk use per person and what to delete first; tie someone to their Seerr account | – |

You pick a result from a menu and press **Request**. Nothing waits for your approval. When it's
downloaded, Sherpa posts in #now-available and mentions whoever asked. Sherpa can search, request
and read; it has no code that deletes anything, so nobody (YETI included) can remove files through it.

**1. Make the server.** Discord → + → Create My Own → name it `Homelab`. User Settings → Advanced →
turn on **Developer Mode** (so right-click shows Copy ID). Then:

- Roles: **Admin** (you), **Household** (girlfriend, flatmates), **Bots** (Sherpa, later YETI).
  Server Settings → Roles → @everyone: turn off **Create Invite**, so only you invite people.
- Category **Media**, visible to Household: `#requests` (use the commands here), `#now-available`
  (Sherpa posts; for Household turn off **Send Messages** in this channel), `#downloads` (chat about
  what's coming; `/downloads` itself answers privately anywhere).
- Category **Admin**, visible only to Admin and Bots (category → Edit → Permissions → @everyone: no
  View Channel): `#alerts` (Uptime Kuma and Scrutiny webhooks), `#updates` (Diun's webhook,
  `DISCORD_WEBHOOK_URL` in `ops/.env`), `#yeti` (for the YETI bot, later).

**2. Make the bot.** discord.com/developers/applications → New Application `Sherpa` →
- **Bot**: Reset Token, copy it into `sherpa/.env` as `DISCORD_TOKEN`. Turn **Public Bot** off.
  Leave all three Privileged Gateway Intents off: Sherpa doesn't read messages.
- **OAuth2 → URL Generator**: scopes `bot` and `applications.commands`; bot permissions
  **View Channels**, **Send Messages**, **Embed Links**. Open the URL, pick Homelab, then give
  Sherpa the Bots role.

**3. Fill in `sherpa/.env`.** Right-click → Copy ID for the server, yourself, the Admin and
Household roles and `#now-available`. In Mylar3: Settings → Web Interface → API → enable,
generate, copy into `MYLAR_API_KEY`. Run `python3 scripts/make-env.py` again: it copies the Seerr,
*arr and Suwayomi keys from `media/.env`. Then:
```bash
cd ~/homelab/docker/sherpa && docker compose up -d --build
docker compose logs -f          # look for "YETI API listening" and no errors
```
The commands appear in Discord within a minute. Type `/movie` in `#requests` to try one.

**4. Seerr.**
- Sherpa sends film and series requests as the API key's user (you), and approves anything Seerr
  holds, so household requests never wait. To have them show under each person's own name in Seerr
  too, create their Seerr accounts and run `/link @member` (it suggests the Seerr users).
- If someone also requests in Seerr's own page, give their Seerr account **Auto-Approve**
  (Users → edit → Permissions). Sherpa picks those requests up within 15 minutes, so they're
  tracked as well.
- If you set up a Discord notification in Seerr for "Media Available", turn it off: Sherpa already
  posts, and for all seven kinds, not only films and series.

**5. Who asked for what, and running low on space.** Every request is kept with the person who made
it, the first person to ask for an item owns it, and Sherpa updates its size every 15 minutes until
the item is deleted. `/space` shows free space, how much each person's requests take, and a "delete
first" list: other people's items before yours, oldest first. Delete in Radarr, Sonarr, Lidarr,
Chaptarr, Mylar3 or Suwayomi (with "delete files"); Sherpa sees it's gone on its next check and
stops counting it. If someone asks for it again later, it's theirs.

YETI uses the same thing through Sherpa's API (`http://<k8plus>:8320`, Tailscale only,
`Authorization: Bearer $SHERPA_API_TOKEN`): `GET /v1/search?kind=movie&q=…`, `POST /v1/request`,
`GET /v1/requests`, `/v1/downloads`, `/v1/space`. Code and tests: `apps/sherpa`.

## Other apps

- **openGym** (`https://gym.<HOME_DOMAIN>`). Passkeys only work at the exact name in `RP_ID` and
  `ORIGIN`, over HTTPS, so always open it through Caddy. The first account becomes admin;
  `INVITE_ONLY=true` keeps everyone else out unless you invite them. The AI coach is off.
- **Neohabit** (`https://habits.<HOME_DOMAIN>`). After everyone has an account, set
  `DISABLE_SIGNUP=true` and `docker compose up -d`.
- **Kan** (`https://kan.<HOME_DOMAIN>`). Same: set `DISABLE_SIGN_UP=true` once accounts exist.
  Optional Authentik sign-in: fill the three `OIDC_` lines.
- **n8n** (`https://n8n.<HOME_DOMAIN>`). Tailscale only, never through the Cloudflare Tunnel, and update
  it often (`docker compose pull && docker compose up -d`): it has had several critical security bugs.
  Keep `N8N_ENCRYPTION_KEY` safe; losing it loses every saved login.
- **code-server** (`https://code.<HOME_DOMAIN>`). It can edit `~/homelab` and `~/projects` but has
  no Docker socket and no sudo. `~/homelab` holds every stack's `.env`, so treat its password like an
  admin password.
- **Paperless-ngx** (`https://docs.<HOME_DOMAIN>`). Log in with `ADMIN_USER` / `ADMIN_PASSWORD` from `.env`
  and change the password. Create an account for each person who wants one: documents belong to
  whoever uploads them, so flatmates don't see each other's. Drop scans or PDFs into
  `~/data/paperless/consume`, upload them in the page, or use the Paperless mobile apps. For YETI,
  each person makes an API token in their own profile.
- **Mealie** (`https://recipes.<HOME_DOMAIN>`). First login `changeme@example.com` / `MyPassword`:
  change both at once, then invite the others from the admin page. Paste a recipe's link to import it.
  Optional AI help: a LiteLLM virtual key in `OPENAI_API_KEY` and `OPENAI_BASE_URL=http://litellm:4000/v1`.
- **Uptime Kuma** (`https://uptime.<HOME_DOMAIN>`). Add monitors as `http://host.docker.internal:<port>`
  (the ports are in the table above) and a notification (ntfy, Discord or Telegram) for your phone.

## Updating

Most images use `latest` (or a major tag). To update a stack: `docker compose pull && docker compose up -d`
(Caddy: `docker compose build --pull && docker compose up -d`).
Databases are pinned to a major version on purpose: don't bump those without reading the release notes.
