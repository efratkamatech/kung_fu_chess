# Running it on Kubernetes

Nine files, eleven objects, one namespace. This is S6 of
[`Implementation_Plan.md`](../Implementation_Plan.md) — the same system
`docker compose up` runs, on an orchestrator that can replace a shard without
interrupting a game and start another one when the rooms fill up.

None of it is needed to play. `python server_main.py --solo` is still the whole game in
one process, with no infrastructure at all.

## What is here

| File | What |
|---|---|
| `00-namespace.yaml` | `kfchess`, so deleting the namespace is a complete uninstall |
| `10-config.yaml` | where the shared services are (ConfigMap) and the database credential (Secret) |
| `20-postgres.yaml` | accounts and ratings — a StatefulSet, because two processes on one data directory is how a database is destroyed |
| `21-nats.yaml` | the bus |
| `22-redis.yaml` | the state that has to be true across shards |
| `30-shard.yaml` | the games. Drains on SIGTERM; 120 s grace period |
| `31-auth.yaml` | passwords, and nothing else |
| `32-gateway.yaml` | the sockets — the only published port |
| `40-prometheus.yaml` | scrapes by pod annotation, and the RBAC to be allowed to |
| `50-metrics-adapter.yaml` | serves `custom.metrics.k8s.io` so an autoscaler can read `kfc_active_games` |
| `60-autoscale.yaml` | the two HorizontalPodAutoscalers |

## Bringing it up

A cluster. k3d runs K3s inside Docker, which is the closest thing to the real one that
fits on a laptop:

```bash
k3d cluster create kfchess --agents 1 -p "30765:30765@loadbalancer" -p "30090:30090@loadbalancer" --k3s-arg "--disable=traefik@server:*"
```

Traefik is disabled because there is nothing for it to do: what arrives here is a
WebSocket, not HTTP paths, so an ingress controller would be a proxy in front of a proxy.

The image is built locally and imported; nothing in the cluster ever pulls it:

```bash
docker build -t kfchess:local .
```

```bash
k3d image import kfchess:local -c kfchess
```

Then the manifests. The schema is *not* duplicated into a manifest — the ConfigMap is
built from `migrations/`, so there is one copy of the SQL and compose and Kubernetes apply
the same file:

```bash
kubectl apply -f k8s/00-namespace.yaml
```

```bash
kubectl create configmap kfchess-migrations -n kfchess --from-file=migrations/ --dry-run=client -o yaml | kubectl apply -f -
```

```bash
kubectl apply -f k8s/
```

Then play against it exactly as against anything else — the client cannot tell:

```bash
python client_main.py --url ws://localhost:30765
```

Prometheus is on `http://localhost:30090`.

### If the cluster cannot pull images

On a network that inspects TLS — a filter or a corporate proxy re-signing every
connection — the host trusts the interceptor's certificate authority and a fresh K3s node
has never heard of it, so every pull fails with `x509: certificate signed by unknown
authority`. It is the same problem `certs/` already solves for `pip` inside the Docker
build, one layer further out, and the same certificates fix it. Concatenate them and mount
the result into every node at creation time:

```bash
cat certs/*.crt > certs/bundle.crt
```

```bash
k3d cluster create kfchess --agents 1 -p "30765:30765@loadbalancer" -p "30090:30090@loadbalancer" --k3s-arg "--disable=traefik@server:*" -v "$PWD/certs/bundle.crt:/etc/ssl/certs/netfree-bundle.crt@all"
```

`certs/` is git-ignored: which authority someone's traffic passes through describes their
network, not this project.

## Tearing it down

```bash
k3d cluster delete kfchess
```

## What is deliberately not here

**No Agones.** It exists for long-lived match servers that need explicit allocation and a
long graceful shutdown. Games here last thirty to ninety seconds, so a Deployment plus a
shard that drains on SIGTERM gets the same result with nothing new to operate.

**No Ingress.** See above — there is nothing to route on.

**No Grafana.** The plan marked it optional and a dashboard is hundreds of lines of JSON
for less than a PromQL query gives.

**No persistence for Redis or NATS.** Everything in Redis is state about *right now* and
carries a TTL in minutes; everything on NATS is in flight. What must survive a restart is
accounts and ratings, and those are in PostgreSQL.
