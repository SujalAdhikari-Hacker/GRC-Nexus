# Deployment

This is the operational guide for running GRC Nexus outside a laptop. For the
security controls themselves see [SECURITY.md](SECURITY.md); for the feature
tour see the [README](../README.md).

## 1. Topology

```
        browser
           │  HTTPS (443)
           ▼
  ┌─────────────────┐        plain HTTP        ┌──────────────────┐
  │ reverse proxy   │ ───────────────────────▶ │ gunicorn (web)   │
  │ Caddy / nginx   │   X-Forwarded-Proto:     │ 127.0.0.1:8000   │
  │ terminates TLS  │   https                  └────────┬─────────┘
  └─────────────────┘                                   │
                                                        ▼
                                              ┌──────────────────┐
                                              │ PostgreSQL (db)  │
                                              └──────────────────┘
```

gunicorn does not terminate TLS. A proxy does, and it must overwrite
`X-Forwarded-Proto` on every request. That is why the proxy is the only public
listener and the app port stays on the private network.

## 2. Turn on HTTPS

In `.env`:

```dotenv
USE_TLS=true
ALLOWED_HOSTS=grc.example.com
CSRF_TRUSTED_ORIGINS=https://grc.example.com
SITE_BASE_URL=https://grc.example.com
```

`USE_TLS=true` sets, in `config/settings/prod.py`:

| Setting | Value |
|---|---|
| `SECURE_SSL_REDIRECT` | `True` |
| `SESSION_COOKIE_SECURE` | `True` |
| `CSRF_COOKIE_SECURE` | `True` |
| `SECURE_HSTS_SECONDS` | `31536000` (one year) |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | `True` |
| `SECURE_HSTS_PRELOAD` | `True` (header only; submission is separate) |
| `SECURE_PROXY_SSL_HEADER` | `('HTTP_X_FORWARDED_PROTO', 'https')` |

Restart the stack:

```bash
docker compose up -d
```

Each switch can still be overridden individually (for example
`SECURE_HSTS_SECONDS=3600` during a staged rollout).

> **Do not enable HSTS before the certificate chain is correct.** Browsers
> cache the policy for the lifetime you set. Start with `SECURE_HSTS_SECONDS=3600`,
> confirm HTTPS works on every hostname, then raise it. The `preload` directive
> in the header only takes effect if you submit the domain to the browser
> preload list - do that only after the domain has served HSTS for months.

## 3. Caddy

Caddy obtains and renews certificates automatically. Copy
`deploy/Caddyfile.example` to `deploy/Caddyfile`, replace the hostname, and
mount it into a Caddy container:

```caddyfile
grc.example.com {
	encode zstd gzip

	# Overwrite, never append: the app trusts this header.
	header_up X-Forwarded-Proto https

	reverse_proxy web:8000
}
```

Compose addition:

```yaml
services:
  caddy:
    image: caddy:2-alpine
    restart: unless-stopped
    ports: ["80:80", "443:443"]
    volumes:
      - ./deploy/Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    depends_on: [web]

volumes:
  caddy_data:
  caddy_config:
```

With Caddy in front, remove the `ports: ["8000:8000"]` mapping from the `web`
service so gunicorn is not reachable from outside Docker.

## 4. nginx

Copy `deploy/nginx.conf.example`, replace the hostname and certificate paths,
and include it from the `http{}` block.

```nginx
server {
    listen 80;
    server_name grc.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name grc.example.com;

    ssl_certificate     /etc/letsencrypt/live/grc.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/grc.example.com/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    client_max_body_size 20m;   # must exceed MAX_EVIDENCE_UPLOAD_SIZE

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    location / {
        proxy_pass http://web:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;   # overwrite
        proxy_read_timeout 120s;
    }
}
```

`client_max_body_size` must be larger than `MAX_EVIDENCE_UPLOAD_SIZE`
(default 10 MB) or uploads fail at the proxy with a 413 before Django sees them.

## 5. Never map /media/ in the proxy

Uploaded evidence is private per department. `/media/` is served by
`core.media.download_media`, which checks that the signed-in user can see a
record referencing the file.

```nginx
# DO NOT ADD THIS
# location /media/ { alias /srv/grc/media/; }
```

The same applies to object storage: do not make the bucket public, and do not
hand out presigned URLs that outlive the request.

## 6. Verify the deployment

```bash
# 1. Redirect and HSTS
curl -sI http://grc.example.com/ | grep -i location          # -> https://...
curl -sI https://grc.example.com/login/ | grep -i strict     # -> max-age=31536000

# 2. Secure cookies
curl -sI https://grc.example.com/login/ | grep -i set-cookie  # -> Secure; HttpOnly

# 3. Django's own deploy checks: expect zero warnings
docker compose exec -T web python manage.py check --deploy

# 4. Application checks
docker compose exec -T web python manage.py check
docker compose exec -T web python manage.py makemigrations --check --dry-run
docker compose exec -T web python manage.py migrate --check
docker compose exec -T web python manage.py test
```

`check --deploy` should now report **no issues**. It still warns about HSTS,
SSL redirect and secure cookies if `USE_TLS` is off, which is correct for a
localhost stack and wrong for a public host.

## 7. Local HTTP vs public HTTPS

| Setting | Local (bundled compose) | Public host |
|---|---|---|
| `USE_TLS` | `false` | `true` |
| `DEBUG` | `false` | `false` |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | your hostname only |
| `CSRF_TRUSTED_ORIGINS` | `http://localhost:8000` | `https://your.host` |
| `SITE_BASE_URL` | `http://localhost:8000` | `https://your.host` |
| Web port published | `8000:8000` | not published; proxy only |
| `CACHES` | default per-process | Redis (rate limits shared) |

## 8. Rate limits behind a proxy

`core.rate_limit.client_ip()` uses `REMOTE_ADDR` by default. Behind a proxy
that means every anonymous request looks like it comes from the proxy, and all
sign-in attempts share one bucket.

Set `TRUSTED_PROXY_HOPS` to the number of proxies between the client and
gunicorn:

```dotenv
TRUSTED_PROXY_HOPS=1        # one Caddy/nginx in front
```

The app then reads `X-Forwarded-For` and takes the address added by the last
trusted hop. Values that are not valid IPs fall back to `REMOTE_ADDR`. Never
raise this without a proxy that overwrites the header: a client-supplied
`X-Forwarded-For` would let an attacker rotate addresses and bypass every
limit.

## 9. Backups and upgrades

```bash
# Database
docker compose exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > grc-$(date +%F).sql

# Uploads
docker run --rm -v grc_media_data:/data -v "$PWD":/backup alpine \
  tar czf /backup/media-$(date +%F).tar.gz -C /data .

# Upgrade
git pull
docker compose build web
docker compose up -d
docker compose exec -T web python manage.py migrate
```

Row-level security policies are re-applied by `post_migrate`. After adding a
new department-owned table, run:

```bash
docker compose exec -T web python manage.py enable_rls
```

## 10. Pre-public checklist

Before making a fork or mirror public:

```bash
python scripts/scan_secrets.py            # tracked files
python scripts/scan_secrets.py --history  # every commit
docker compose exec -T web python manage.py check --deploy
```

Rotate any credential that appears in the history, even if a later commit
deleted it. A deleted secret is still readable in `git log -p`.
