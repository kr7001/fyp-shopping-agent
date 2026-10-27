# Local WebArena setup

## Running the WebArena environment

The environment is the ServiceNow **WebArena-Verified** shopping distribution, run as two
self-contained Docker images (Magento 2 + MySQL + Elasticsearch + Redis under supervisord,
all inside one container each). Chosen over the original WebArena images because they are
considerably smaller and correct known annotation bugs.

| Container | Image | URL | Purpose |
| --- | --- | --- | --- |
| `webarena-shopping` | `am1n3e/webarena-verified-shopping` | http://localhost:7770 | Storefront. This is the one experiments run against |
| `webarena-shopping-admin` | `am1n3e/webarena-verified-shopping_admin` | http://localhost:7780 | Magento admin. Only needed for authoring products |

Both images are amd64 and run under emulation on Apple Silicon. First boot is slow.

### Everyday start

Docker Desktop must be running first (`open -a Docker` on macOS, then wait for the daemon).

```bash
./env/start.sh            # storefront only
./env/start.sh --admin    # storefront and the admin panel
```

The script starts the container, waits for Elasticsearch, then checks the catalogue
actually returns products. That last check matters: Magento serves a 200 while its search
engine is still booting, and in that window the shop looks empty for no visible reason.
A plain `docker start` cannot tell the two states apart.

By hand, if preferred:

```bash
docker start webarena-shopping
# admin panel, only when authoring products
docker start webarena-shopping-admin
```

Then wait for Elasticsearch to finish booting before touching the site. It is the slow part
and the site looks broken until it is green:

```bash
docker exec -it webarena-shopping wget -qO- "http://localhost:9200/_cluster/health?pretty"
docker exec -it webarena-shopping supervisorctl status
open http://localhost:7770
```

Quick check that the catalogue is actually indexed, not just that the site returns 200.
An empty result here is the Elasticsearch failure below, not a missing product:

```bash
curl -s "http://localhost:7770/catalogsearch/result/?q=cake+topper" | grep -c product-item-link
```

Admin credentials for the admin container are the WebArena documented defaults,
`admin` / `admin1234`. Not verified from a login in this repo yet.

### First-time setup, from nothing

```bash
docker pull am1n3e/webarena-verified-shopping
docker run -d --name webarena-shopping \
  -p 7770:80 -p 7771:8877 \
  am1n3e/webarena-verified-shopping

# admin, optional
docker pull am1n3e/webarena-verified-shopping_admin
docker run -d --name webarena-shopping-admin \
  -p 7780:80 -p 7781:8877 \
  am1n3e/webarena-verified-shopping_admin
```

After the first run the catalogue indexes have to be built once, see the Elasticsearch note below.

### Stopping

```bash
docker stop webarena-shopping webarena-shopping-admin
```

Use `stop`, not `rm`. The container holds the MySQL data directory, so removing it discards
the catalogue and any products authored for the experiments.

---

## Known issue: Elasticsearch appears to hang on Apple Silicon

**Symptom.** Site loads but the catalogue appears almost empty. Category pages show no
products, search returns nothing. `supervisorctl status` reports `elasticsearch RUNNING`,
so the failure is silent. Port 9200 never starts listening.

**Root cause, found 2026-09-08.** Not an Elasticsearch problem. Docker Desktop was running
the amd64 image under QEMU user-mode emulation instead of Rosetta:

```bash
python3 -c "import json;d=json.load(open('$HOME/Library/Group Containers/group.com.docker/settings-store.json'));print(d['UseVirtualizationFrameworkRosetta'])"
# False
```

With Rosetta off, every amd64 instruction is interpreted. The JVM bootstrap is the worst
case for this. Observed here: the pre-launch `qemu-x86_64 .../java` process accumulated
5m52s of CPU time at a pegged 100% of one core without reaching Elasticsearch's first
log line. It is not deadlocked, it is being emulated roughly an order of magnitude slower
than it needs to be. Everything else in the container tolerates that; a 512MB-heap JVM
does not.

**Fix, measured 2026-09-08.** Docker Desktop, Settings, General, enable *Use Rosetta for
x86_64/amd64 emulation on Apple Silicon*, then restart Docker Desktop. Requires macOS 13+.

| | Elasticsearch cold boot to cluster health |
| --- | --- |
| QEMU (Rosetta off) | 19 min, never reached healthy. Three attempts, none completed |
| Rosetta on | **20 s** |

Confirm which translator is actually in use. Under QEMU the process list shows
`qemu-x86_64`; under Rosetta it shows `/run/rosetta/rosetta`:

```bash
docker exec -it webarena-shopping sh -c 'ps -o args | grep -c "[q]emu-x86_64"'   # 0 when Rosetta is on
docker exec -it webarena-shopping sh -c 'ps -o pid,args | grep [j]ava | cut -c1-80'
```

Caveats. Rosetta implements fewer x86 instruction extensions than QEMU, so software using
them crashes rather than running slowly. This container is Alpine/musl, historically the
less reliable case for Rosetta. Nothing in this stack has hit either problem, but the
setting is one checkbox to revert if something does.

**Confirming it is this and not something else:**

```bash
# 9200 never opens
docker exec -it webarena-shopping sh -c 'netstat -tln | grep 9200'
# the JVM is burning CPU rather than blocked
docker exec -it webarena-shopping sh -c 'ps -o pid,etime,time,args | grep [e]lastic'
# the log stops at the seccomp warning and never reaches "version[7.17.0]"
docker exec -it webarena-shopping sh -c 'tail -5 /usr/share/java/elasticsearch/logs/elasticsearch.log'
```

The `seccomp unavailable: CONFIG_SECCOMP not compiled into kernel` warning at the top of
that log is normal inside Docker and is not the problem.

**If the catalogue is still empty once Elasticsearch is up,** the indexes were never
built. Reindex by hand, which is slow but only needed once:

```bash
docker exec -it webarena-shopping php /var/www/magento2/bin/magento indexer:reindex
docker exec -it webarena-shopping php /var/www/magento2/bin/magento cache:flush
docker exec -it webarena-shopping php /var/www/magento2/bin/magento indexer:status
```

Note that all indexers ship in **Update on Save** mode, so any product write triggers an
inline fulltext reindex and will fail while Elasticsearch is down.

`xpack.ml.enabled: false` in `/usr/share/java/elasticsearch/config/elasticsearch.yml` was
tried in August as a fix and did not help. It was reverted.

---

## Database access, for ground truth

Magento's DB is inside the container. Credentials come from
`/var/www/magento2/app/etc/env.php`:

```bash
docker exec -it webarena-shopping grep -A 20 "'db'" /var/www/magento2/app/etc/env.php
```

Working query, catalogue composition:

```bash
docker exec -it webarena-shopping mysql -u magentouser -pMyPassword magentodb -e \
  "SELECT type_id, COUNT(*) FROM catalog_product_entity GROUP BY type_id;"
```

These are the fixed WebArena image credentials, not secrets, and are not reachable from
outside the container.

---
