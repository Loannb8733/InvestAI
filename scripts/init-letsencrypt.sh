#!/bin/bash
# InvestAI — Initialize Let's Encrypt certificates
# Usage: ./scripts/init-letsencrypt.sh yourdomain.com your-email@example.com

set -e

DOMAIN=$1
EMAIL=$2

if [ -z "$DOMAIN" ] || [ -z "$EMAIL" ]; then
    echo "Usage: $0 <domain> <email>"
    echo "Example: $0 investai.example.com admin@example.com"
    exit 1
fi

echo "=== InvestAI — Let's Encrypt Setup ==="
echo "Domain: $DOMAIN"
echo "Email: $EMAIL"
echo ""

# 1. Start nginx (HTTP only) for ACME challenge
echo "Starting nginx for ACME challenge..."
docker compose -f docker-compose.prod.yml up -d nginx

# 2. Request certificate
echo "Requesting certificate..."
docker compose -f docker-compose.prod.yml run --rm certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email \
    -d "$DOMAIN"

# 3. Update nginx config
echo ""
echo "=== Certificate obtained! ==="
echo ""
echo "Next steps:"
echo "1. Edit docker/nginx/conf.d/prod.conf:"
echo "   - Uncomment the HTTPS server block"
echo "   - Replace 'yourdomain.com' with '$DOMAIN'"
echo "   - Uncomment 'return 301 https://...' in the HTTP block"
echo "   - Remove/comment the temporary HTTP-only config"
echo ""
echo "2. Update .env.production:"
echo "   - Set CORS_ORIGINS=https://$DOMAIN"
echo ""
echo "3. Restart:"
echo "   docker compose -f docker-compose.prod.yml restart nginx"
echo ""
echo "Certificates will auto-renew via the certbot container."
