# Caddy with the Cloudflare DNS plugin, so it can get a wildcard HTTPS certificate
# for *.home.<domain> without opening any ports to the internet.
FROM caddy:2-builder AS builder
RUN xcaddy build --with github.com/caddy-dns/cloudflare

FROM caddy:2
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
