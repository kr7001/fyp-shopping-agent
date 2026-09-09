#!/usr/bin/env bash
# Start the WebArena shop and wait until it is genuinely usable.
#
# "Usable" is not the same as "responding". Magento serves a 200 while its search engine
# is still booting, and in that window categories and search are empty for no visible
# reason. So this waits for Elasticsearch to bind, then checks the catalogue actually
# returns products, and says which step failed rather than leaving a silent empty shop.
#
#   ./env/start.sh            storefront only
#   ./env/start.sh --admin    storefront and the admin panel
set -u

STORE=webarena-shopping
ADMIN=webarena-shopping-admin
WANT_ADMIN=${1:-}

if ! docker info >/dev/null 2>&1; then
  echo "Docker is not running. Start Docker Desktop first:  open -a Docker"
  exit 1
fi

echo "starting $STORE"
docker start "$STORE" >/dev/null || { echo "no such container. See README, first-time setup"; exit 1; }
if [ "$WANT_ADMIN" = "--admin" ]; then
  echo "starting $ADMIN"
  docker start "$ADMIN" >/dev/null || echo "  admin container not found, skipping"
fi

printf "waiting for Elasticsearch "
for _ in $(seq 1 60); do
  if docker exec "$STORE" wget -qO- "http://localhost:9200/_cluster/health" 2>/dev/null | grep -q status; then
    echo " up"
    break
  fi
  printf "."
  sleep 2
done

printf "waiting for the storefront "
for _ in $(seq 1 60); do
  if [ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:7770/)" = "200" ]; then
    echo " up"
    break
  fi
  printf "."
  sleep 2
done

# A 200 proves the web server answers. This proves the catalogue is indexed, which is the
# thing that silently breaks.
found=$(curl -s "http://localhost:7770/catalogsearch/result/?q=Rivenhall" | grep -c product-item-link)
echo
if [ "$found" -gt 0 ]; then
  echo "catalogue indexed, search page returned $found product links"
  echo "storefront   http://localhost:7770"
  if [ "$WANT_ADMIN" = "--admin" ]; then
    echo "admin        http://localhost:7780   admin / admin1234"
  fi
else
  echo "storefront answers but search found nothing."
  echo "Elasticsearch is probably still indexing, or hung. See the Rosetta note in README."
  echo "  docker exec -it $STORE supervisorctl status"
  exit 1
fi
