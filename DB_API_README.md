# Inspect databases and call local APIs

Run `dsfst_probe.py` **inside the Ubuntu VM** from the project folder after
`bash install_dsfst.sh` and while `dsfst.service` or `bash start_dsfst.sh` is
running. The installer creates `.venv` and `.env`; the databases and APIs bind
to the VM's loopback interface, so running the script on the Windows host will
not reach them unless you have separately configured port forwarding.

```bash
.venv/bin/python dsfst_probe.py status
.venv/bin/python dsfst_probe.py db
.venv/bin/python dsfst_probe.py db --limit 10 --minutes 60
.venv/bin/python dsfst_probe.py api GET 8009 /state
.venv/bin/python dsfst_probe.py api GET 8008 '/experiments?limit=5'
```

`status` sends GET requests to the monitor, metrics API, and orchestrator.
`db` reads `.env` to connect directly to MongoDB, InfluxDB, and Redis. It shows
MongoDB collection counts and recent experiment summaries, recent InfluxDB
metric fields, and Redis experiment state. It never prints database passwords
or the InfluxDB token. Each result has `ok`; the command exits nonzero if any
service fails.

The `api` command accepts GET or POST on ports 8000–8010, always on
`127.0.0.1`. POST can create or start experiments, so choose its path and body
deliberately. For example, this reads a JSON file and creates an experiment;
it does **not** start an injection until `/experiments/<id>/start` is called:

```bash
cat > /tmp/dsfst-experiment.json <<'JSON'
{"name":"Probe example","failure_type":"cpu","target_container":"host","parameters":{"cpu_percent":10,"duration_seconds":10}}
JSON
.venv/bin/python dsfst_probe.py api POST 8009 /experiments --json-file /tmp/dsfst-experiment.json
```

For the routes and accepted request fields, see each service's `/docs` page
inside the VM, such as `http://127.0.0.1:8009/docs`. The API command returns
the HTTP status and response body so failed requests are visible.
