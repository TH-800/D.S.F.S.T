#!/usr/bin/env bash
# Systemd runs this as root before the app. The source VM is left untouched.
set -euo pipefail
cd "$(dirname "$(realpath "$0")")"
[[ "$EUID" == 0 ]] || { echo 'This is a systemd root service.' >&2; exit 1; }
[[ -f /etc/dsfst-template-uuid && -f .dsfst/install-complete ]] || exit 1
[[ "$(cat /etc/dsfst-template-uuid)" != "$(cat /sys/class/dmi/id/product_uuid)" ]] || exit 0
[[ ! -e .dsfst/clone-initialized ]] || exit 0

# The cloned copy of the template's test data belongs only to this clone.
docker compose --project-name dsfst-vm --project-directory "$PWD" \
    --env-file "$PWD/.env" -f "$PWD/.dsfst/compose.yaml" down -v

.venv/bin/python - <<'PY'
from pathlib import Path
import secrets
from dotenv import set_key

root = Path.cwd()
values = {
    'MONGO_PASSWORD': secrets.token_urlsafe(24),
    'INFLUX_PASSWORD': secrets.token_urlsafe(24),
    'REDIS_PASSWORD': secrets.token_urlsafe(24),
    'INFLUXDB_TOKEN': secrets.token_urlsafe(48),
}
for name, value in values.items():
    file_name = {'INFLUXDB_TOKEN': 'influx-token'}.get(name, name.lower().replace('_', '-'))
    secret_file = root / '.dsfst' / file_name
    secret_file.write_text(value, encoding='utf-8')
    secret_file.chmod(0o600)
    for env_file in (root / '.env', root / 'database/.env'):
        set_key(env_file, name, value, quote_mode='always')
        env_file.chmod(0o600)
for env_file in (root / '.env', root / 'database/.env'):
    set_key(env_file, 'MONGO_URI',
            f"mongodb://test1234:{values['MONGO_PASSWORD']}@127.0.0.1:27017/?authSource=admin",
            quote_mode='always')
redis_conf = root / '.dsfst/redis.conf'
redis_conf.write_text(
    f"user default off\nuser test1234 on >{values['REDIS_PASSWORD']} ~* &* +@all\n",
    encoding='utf-8')
redis_conf.chmod(0o644)
PY
owner="$(stat -c %U start_dsfst.sh)"
group="$(stat -c %G start_dsfst.sh)"
chown "$owner:$group" .env database/.env .dsfst/{mongo-password,influx-password,redis-password,influx-token,redis.conf}
touch .dsfst/clone-initialized
chown "$owner:$group" .dsfst/clone-initialized
echo 'Clone initialization complete: new database volumes and app secrets.'
