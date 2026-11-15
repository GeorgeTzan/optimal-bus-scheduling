#!/usr/bin/env bash
set -euo pipefail

host=${1:?usage: scripts/deploy.sh user@host [remote-dir]}
dir=${2:-ktel-v2}
cd "$(git rev-parse --show-toplevel)"
revision=$(git rev-parse --short HEAD)
git diff --quiet HEAD -- || echo "warning: uncommitted changes are not deployed; deploying $revision"

git archive HEAD | ssh "$host" 'cat > ~/ktel-release.tar'
ssh "$host" bash -s -- "$dir" "$revision" <<'REMOTE'
set -euo pipefail
dir=$1 revision=$2
cd ~
test -f "$dir/secrets/app.env" || { echo "missing ~/$dir/secrets; first install is manual" >&2; exit 1; }
compose() { docker compose -f docker-compose.prod.yml -p ktel "$@" < /dev/null; }
mkdir -p ~/ktel-backups
if (cd "$dir" && compose ps --status running --services | grep -qx db); then
  (cd "$dir" && compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"') | gzip > ~/ktel-backups/ktel-$(date +%Y%m%d-%H%M%S).sql.gz
  ls -t ~/ktel-backups/*.sql.gz | tail -n +15 | xargs -r rm --
fi
find "$dir" -mindepth 1 -maxdepth 1 ! -name secrets -exec rm -rf {} +
tar -x -C "$dir" -f ~/ktel-release.tar && rm ~/ktel-release.tar
echo "$revision" > "$dir/REVISION"
cd "$dir"
compose build
compose up -d db
until compose exec -T db pg_isready -q; do sleep 1; done
compose run --rm --no-deps backend python -m db.migrations upgrade
compose run --rm --no-deps backend python -m db.provision_runtime --refresh-grants
compose up -d --remove-orphans
for _ in $(seq 30); do
  if curl -fsS -o /dev/null http://127.0.0.1:3000/ && [ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3000/api/auth/me)" = 401 ]; then
    echo "deployed $revision"; exit 0
  fi
  sleep 2
done
compose ps
compose logs --tail 30 backend frontend
echo "health check failed" >&2
exit 1
REMOTE
