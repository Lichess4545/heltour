# Previous Deployment Architecture

This document captures the legacy deployment setup for historical reference.

## Service Architecture

The system ran three services per environment (live/staging):

1. **Web Application** - Django app served by Gunicorn (ports 8580/8680)
2. **API Service** - Separate Gunicorn instance for API endpoints (port 8880)
3. **Celery Workers** - Background task processing with beat scheduler

All services ran as user `lichess4545` and were managed by systemd.

## Infrastructure Layout

```
/home/lichess4545/web/
├── www.lichess4545.com/
│   ├── current/        # Symlink to active deployment
│   ├── env/            # Python virtualenv
│   └── htdocs/         # Static files
└── staging.lichess4545.com/
```

## Web Server

Nginx reverse proxy configuration:
- SSL termination on port 443
- Rate limiting (5 req/s general, burst 20)
- Static file serving with aggressive caching
- Maintenance mode via `error503.html` presence
- Upstream load balancing with IP hash

## Database Backups

Automated PostgreSQL backups ran hourly via cron:
- **Retention**: 5 days hourly, 14 days daily, 8 weeks weekly, 12 months monthly
- **Location**: `/home/lichess4545/backups/heltour-sql/`
- **Format**: Compressed SQL dumps (`.sql.bz2`)

## Deployment Process

Deployments used Fabric to:
1. Compile and collect static files
2. Rsync code to server
3. Update virtualenv dependencies
4. Run database migrations
5. Invalidate caches
6. Restart systemd services

## Server

- **Host**: radio.lichess.ovh
- **User**: lichess4545
- **Database**: PostgreSQL (heltour_lichess4545)