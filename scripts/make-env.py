#!/usr/bin/env python3
"""
Creates every stack's .env from its .env.example and fills in everything that can be
generated: passwords, secret keys, the shared database passwords (the same value in
docker/postgres/.env and in each app's .env), and every URL that uses your domain.

Safe to run again: it never changes a value that is already filled in, and it never
overwrites an existing .env. It only fills empty lines.

    python3 scripts/make-env.py                         # asks for your domain and email
    python3 scripts/make-env.py --domain home.example.com --email you@example.com

At the end it lists what you still have to fill in by hand (API keys, tokens from other
websites, things that exist only after an app's first start). ENV-SETUP.md explains each one.
"""
import argparse
import os
import re
import secrets
import string
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "docker"
ALNUM = string.ascii_letters + string.digits


def hexkey(n=32):        return secrets.token_hex(n)
def alnum(n=32):         return "".join(secrets.choice(ALNUM) for _ in range(n))
def password(n=24):      return alnum(n)          # letters and digits: safe in URLs and .env files


# ---- the shared database passwords -------------------------------------------------------
# postgres/.env key  ->  (app .env file, key in that file)
DB_LINKS = {
    "AUTHENTIK_DB_PASSWORD":   ("authentik/.env", "PG_PASS"),
    "MINIFLUX_DB_PASSWORD":    ("miniflux/.env", "DB_PASSWORD"),
    "SPEEDTEST_DB_PASSWORD":   ("speedtest-tracker/.env", "DB_PASSWORD"),
    "NEXTCLOUD_DB_PASSWORD":   (None, None),                    # typed into Nextcloud's installer
    "FIREFLY_DB_PASSWORD":     ("firefly/.env", "DB_PASSWORD"),
    "LITELLM_DB_PASSWORD":     ("ai/.env", "LITELLM_DB_PASSWORD"),
    "KAN_DB_PASSWORD":         ("kan/.env", "DB_PASSWORD"),
    "N8N_DB_PASSWORD":         ("n8n/.env", "DB_PASSWORD"),
    "NEOHABIT_DB_PASSWORD":    ("neohabit/.env", "DB_PASSWORD"),
    "VAULTWARDEN_DB_PASSWORD": ("vaultwarden/.env", "DB_PASSWORD"),
    "SHERPA_DB_PASSWORD":      ("sherpa/.env", "DB_PASSWORD"),
    "PAPERLESS_DB_PASSWORD":   ("paperless/.env", "DB_PASSWORD"),
    "MEALIE_DB_PASSWORD":      ("mealie/.env", "DB_PASSWORD"),
    "YETI_DB_PASSWORD":        (None, None),                    # used later by YETI
    "YETI_DEV_DB_PASSWORD":    (None, None),                    # YETI's dev copy
}

# ---- secrets that are generated on the spot -------------------------------------------------
GENERATED = {
    "postgres/.env":          {"POSTGRES_PASSWORD": password},
    "authentik/.env":         {"AUTHENTIK_SECRET_KEY": lambda: secrets.token_urlsafe(48)},
    "ai/.env":                {"LITELLM_MASTER_KEY": lambda: "sk-" + hexkey(24),
                               "LITELLM_SALT_KEY": lambda: "sk-" + hexkey(24),
                               "SEARXNG_SECRET": hexkey, "OPENWEBUI_SECRET_KEY": hexkey},
    "ai/omniroute.env":       {"JWT_SECRET": hexkey, "API_KEY_SECRET": hexkey,
                               "STORAGE_ENCRYPTION_KEY": hexkey, "INITIAL_PASSWORD": password},
    "obsidian-livesync/.env": {"COUCHDB_PASSWORD": password},
    "immich/.env":            {"DB_PASSWORD": password},          # Immich wants letters and digits only
    "kan/.env":               {"BETTER_AUTH_SECRET": lambda: secrets.token_urlsafe(32)},
    "n8n/.env":               {"N8N_ENCRYPTION_KEY": hexkey},
    "neohabit/.env":          {"JWT_SECRET": lambda: secrets.token_urlsafe(32)},
    "speedtest-tracker/.env": {"APP_KEY": lambda: "base64:" + __import__("base64").b64encode(os.urandom(32)).decode(),
                               "ADMIN_PASSWORD": password},
    "firefly/.env":           {"APP_KEY": lambda: alnum(32), "STATIC_CRON_TOKEN": lambda: alnum(32)},
    "homeassistant/.env":     {"MQTT_PASSWORD": password},
    "miniflux/.env":          {"ADMIN_PASSWORD": password},
    "media/.env":             {"JELLYDASH_ADMIN_PASSWORD": password, "SUWAYOMI_PASSWORD": password},
    "dashboard/.env":         {"MY_SECRET_TOKEN": hexkey},
    "sherpa/.env":            {"SHERPA_API_TOKEN": hexkey},
    "paperless/.env":         {"SECRET_KEY": lambda: secrets.token_urlsafe(48), "ADMIN_PASSWORD": password},
}

# ---- values that live in one stack and are copied to another once you've filled them in ------
# (source file, key) -> (target file, key). Run the script again after filling the source.
COPIES = {
    ("media/.env", "SEERR_API_KEY"):     ("sherpa/.env", "SEERR_API_KEY"),
    ("media/.env", "RADARR_API_KEY"):    ("sherpa/.env", "RADARR_API_KEY"),
    ("media/.env", "SONARR_API_KEY"):    ("sherpa/.env", "SONARR_API_KEY"),
    ("media/.env", "LIDARR_API_KEY"):    ("sherpa/.env", "LIDARR_API_KEY"),
    ("media/.env", "CHAPTARR_API_KEY"):  ("sherpa/.env", "CHAPTARR_API_KEY"),
    ("media/.env", "SUWAYOMI_USER"):     ("sherpa/.env", "SUWAYOMI_USER"),
    ("media/.env", "SUWAYOMI_PASSWORD"): ("sherpa/.env", "SUWAYOMI_PASSWORD"),
}


def domain_values(d, email):
    """Values that come from your domain (and email)."""
    return {
        "caddy/.env":            {"HOME_DOMAIN": d, "ACME_EMAIL": email},
        "dashboard/.env":        {"HOME_DOMAIN": d},
        "ai/.env":               {"SEARXNG_BASE_URL": f"https://search.{d}/"},
        "ai/omniroute.env":      {"BASE_URL": f"https://omniroute.{d}", "NEXT_PUBLIC_BASE_URL": f"https://omniroute.{d}"},
        "kan/.env":              {"BASE_URL": f"https://kan.{d}"},
        "paperless/.env":        {"BASE_URL": f"https://docs.{d}"},
        "mealie/.env":           {"BASE_URL": f"https://recipes.{d}"},
        "n8n/.env":              {"N8N_HOST": f"n8n.{d}"},
        "neohabit/.env":         {"FRONTEND_URL": f"https://habits.{d}"},
        "opengym/.env":          {"RP_ID": f"gym.{d}", "ORIGIN": f"https://gym.{d}"},
        "code-server/.env":      {"PROXY_DOMAIN": f"code.{d}"},
        "vaultwarden/.env":      {"DOMAIN": f"https://vault.{d}"},
        "miniflux/.env":         {"BASE_URL": f"https://miniflux.{d}"},
        "monitoring/.env":       {"GRAFANA_ROOT_URL": f"https://grafana.{d}", "AUTHENTIK_URL": f"https://auth.{d}"},
        "firefly/.env":          {"APP_URL": f"https://firefly.{d}", "SITE_OWNER": email},
        "firefly/.importer.env": {"VANITY_URL": f"https://firefly.{d}", "APP_URL": f"https://importer.{d}"},
        "media/.env":            {"JELLYFIN_LINK_URL": f"https://jellyfin.{d}"},
        "speedtest-tracker/.env": {"ADMIN_EMAIL": email},
    }

# Example values that should be replaced by the domain ones above (not "empty", but placeholders)
PLACEHOLDER = re.compile(r"(home\.example\.com|authentik\.example\.com|k8plus:\d+|mail@example\.com)")

# ---- what is left for you, by file: key -> where to get it ------------------------------------
MANUAL = {
    "caddy/.env":         {"CLOUDFLARE_API_TOKEN": "Cloudflare -> My Profile -> API Tokens -> 'Edit zone DNS', your domain only"},
    "cloudflared/.env":   {"TUNNEL_TOKEN": "Cloudflare Zero Trust -> Networks -> Tunnels -> new tunnel -> Docker token"},
    "media/.env":         {"NORDVPN_SERVICE_USER": "nordaccount.com -> NordVPN -> Manual setup -> service credentials",
                           "NORDVPN_SERVICE_PASSWORD": "same page as the user",
                           "RADARR_API_KEY": "after first start: Radarr -> Settings -> General",
                           "SONARR_API_KEY": "after first start: Sonarr -> Settings -> General",
                           "LIDARR_API_KEY": "after first start: Lidarr -> Settings -> General",
                           "CHAPTARR_API_KEY": "after first start: Chaptarr -> Settings -> General",
                           "JELLYDASH_JELLYFIN_API_KEY": "after first start: Jellyfin -> Dashboard -> API Keys",
                           "SEERR_API_KEY": "after first start: Seerr -> Settings -> General",
                           "KAVITA_API_KEY": "after first start: Kavita -> your user -> Settings -> API Key",
                           "COMICVINE_API_KEY": "free: comicvine.gamespot.com/api"},
    "ai/.env":            {"GROQ_API_KEY": "console.groq.com -> API Keys",
                           "OPENROUTER_API_KEY": "openrouter.ai -> Keys (set its credit limit to $0)",
                           "GEMINI_API_KEY": "aistudio.google.com -> Get API key",
                           "OMNIROUTE_API_KEY": "after first start: OmniRoute dashboard -> API keys",
                           "OPENWEBUI_API_KEY": "after LiteLLM starts: make a virtual key (command in ai/.env.example)"},
    "code-server/.env":   {"HASHED_PASSWORD": "echo -n 'pw' | docker run --rm -i node:22-alpine npx -y argon2-cli -e  (double every $)"},
    "vaultwarden/.env":   {"ADMIN_TOKEN": "docker run --rm -it vaultwarden/server /vaultwarden hash  (double every $)"},
    "ops/.env":           {"DISCORD_WEBHOOK_URL": "Discord channel -> Edit -> Integrations -> Webhooks -> Copy URL"},
    "sherpa/.env":        {"DISCORD_TOKEN": "discord.com/developers -> your app -> Bot -> Reset Token",
                           "DISCORD_GUILD_ID": "Discord (Developer Mode on) -> right-click the server -> Copy Server ID",
                           "DISCORD_OWNER_ID": "right-click yourself -> Copy User ID",
                           "DISCORD_ADMIN_ROLE_ID": "Server Settings -> Roles -> right-click Admin -> Copy Role ID",
                           "DISCORD_HOUSEHOLD_ROLE_ID": "same, for the Household role",
                           "DISCORD_ANNOUNCE_CHANNEL_ID": "right-click #now-available -> Copy Channel ID",
                           "MYLAR_API_KEY": "after first start: Mylar3 -> Settings -> Web Interface -> API key",
                           "SEERR_API_KEY": "copied from media/.env: fill it there, run this script again"},
    "dashboard/.env":     {"GIT_PAT_TOKEN": "github.com/settings/personal-access-tokens, read-only, public repos",
                           "ADGUARD_USERNAME": "the login you create in AdGuard's setup",
                           "ADGUARD_PASSWORD": "the login you create in AdGuard's setup",
                           "IMMICH_API_KEY": "after first start: Immich -> Account Settings -> API Keys"},
    "homeassistant/.env": {"ZIGBEE_DEVICE": "ls /dev/serial/by-id/  once the dongle is plugged in"},
    "firefly/.importer.env": {"FIREFLY_III_ACCESS_TOKEN": "after first start: Firefly -> Profile -> OAuth -> Personal Access Token"},
}
OPTIONAL_EMPTY_OK = {
    "kan/.env": {"OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET", "OIDC_DISCOVERY_URL"},
    "mealie/.env": {"OPENAI_BASE_URL", "OPENAI_API_KEY"},
    "monitoring/.env": {"GRAFANA_OAUTH_CLIENT_ID", "GRAFANA_OAUTH_CLIENT_SECRET"},
    "scrutiny/.env": {"SCRUTINY_NOTIFY_URLS"},
    "vaultwarden/.env": {"ADMIN_TOKEN"},
}

LINE = re.compile(r"^([A-Z_][A-Z0-9_]*)=(.*)$")


class EnvFile:
    def __init__(self, rel):
        self.rel = rel
        self.path = ROOT / rel
        self.lines = self.path.read_text().splitlines() if self.path.exists() else []

    def get(self, key):
        for l in self.lines:
            m = LINE.match(l)
            if m and m.group(1) == key:
                return m.group(2).strip().strip('"')
        return None

    def set_if_empty(self, key, value, replace_placeholder=False):
        for i, l in enumerate(self.lines):
            m = LINE.match(l)
            if m and m.group(1) == key:
                cur = m.group(2).strip()
                if cur == "" or (replace_placeholder and PLACEHOLDER.search(cur)):
                    self.lines[i] = f"{key}={value}"
                    return True
                return False
        return False

    def save(self):
        self.path.write_text("\n".join(self.lines) + "\n")
        os.chmod(self.path, 0o600)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain")
    ap.add_argument("--email")
    a = ap.parse_args()
    domain = a.domain or input("Your HOME_DOMAIN (e.g. home.example.com): ").strip()
    email = a.email or input("Your email (for Let's Encrypt and app admin accounts): ").strip()
    if not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", domain or ""):
        sys.exit("That doesn't look like a domain.")

    # 1. create .env files from the examples (never overwrite)
    created = []
    for ex in sorted(ROOT.glob("*/*.example")) + sorted(ROOT.glob("*/.*.example")):
        target = ex.with_name(ex.name[: -len(".example")])
        if not target.exists():
            target.write_text(ex.read_text())
            os.chmod(target, 0o600)
            created.append(str(target.relative_to(ROOT)))
    files = {}
    def f(rel):
        if rel not in files:
            files[rel] = EnvFile(rel)
        return files[rel]

    filled, mismatches = [], []

    # 2. shared database passwords: one value, written to both sides
    pg = f("postgres/.env")
    for pkey, (app_file, app_key) in DB_LINKS.items():
        val = pg.get(pkey) or (app_file and f(app_file).get(app_key)) or password()
        if pg.set_if_empty(pkey, val):
            filled.append(f"postgres/.env {pkey}")
        if app_file:
            other = f(app_file).get(app_key)
            if other and other != val:
                mismatches.append(f"{app_file} {app_key} differs from postgres/.env {pkey}")
            elif f(app_file).set_if_empty(app_key, val):
                filled.append(f"{app_file} {app_key}")

    # 3. generated secrets
    for rel, keys in GENERATED.items():
        for key, gen in keys.items():
            if f(rel).set_if_empty(key, gen()):
                filled.append(f"{rel} {key}")

    # 3b. values copied between stacks (only once the source is filled in)
    for (src, skey), (dst, dkey) in COPIES.items():
        val = f(src).get(skey)
        if val and "REPLACE_ME" not in val and f(dst).set_if_empty(dkey, val):
            filled.append(f"{dst} {dkey} (from {src})")

    # 4. domain and email
    for rel, keys in domain_values(domain, email).items():
        for key, val in keys.items():
            if val and f(rel).set_if_empty(key, val, replace_placeholder=True):
                filled.append(f"{rel} {key}")

    for ef in files.values():
        if ef.path.exists():
            ef.save()

    # 5. report
    if created:
        print(f"Created {len(created)} .env files from the examples.")
    print(f"Filled in {len(filled)} values.")
    for m in mismatches:
        print(f"  ! MISMATCH: {m}  (they must be the same)")

    print("\nStill to fill in by hand (see ENV-SETUP.md):")
    todo = 0
    for rel, keys in MANUAL.items():
        ef = EnvFile(rel)
        for key, where in keys.items():
            cur = ef.get(key) if ef.path.exists() else None
            if ef.path.exists() and (not cur or "REPLACE_ME" in cur):
                opt = key in OPTIONAL_EMPTY_OK.get(rel, set())
                print(f"  {rel:<24} {key:<28} {'(optional) ' if opt else ''}{where}")
                todo += 1
    if not todo:
        print("  nothing")
    print("\nThe generated logins (Miniflux, Speedtest, Jellydash, Suwayomi, OmniRoute, CouchDB, Paperless) are in")
    print("each stack's .env. Copy them into your password manager. Every .env is now readable only by you.")


if __name__ == "__main__":
    main()
