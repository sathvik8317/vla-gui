# Target apps

Four self-hosted apps, brought up with `docker compose up -d --build`:

| Service      | Image                             | Port                    | What it's for                    |
|--------------|------------------------------------|--------------------------|-----------------------------------|
| `todomvc`    | built from `targets/todomvc/`      | http://localhost:8081    | trivial single-page app, ground truth for early smoke tests |
| `gitea`      | `gitea/gitea:1.22`                 | http://localhost:8082    | multi-page CRUD app (issues, repos, PRs) |
| `juice-shop` | `bkimminich/juice-shop:v17.3.0`    | http://localhost:8083    | e-commerce flows (cart, search, forms) |
| `grafana`    | `grafana/grafana:11.3.0`           | http://localhost:8084    | dashboard/data-viz UI |

## Reset-to-known-state

None of the four services mount a volume for app state. Each container's
writable layer holds all mutable state (todos in `todomvc`'s in-browser
localStorage, Gitea's SQLite DB + repos, Juice Shop's in-memory/SQLite
store, Grafana's `/var/lib/grafana`). That state lives only in the
container's ephemeral filesystem, so recreating the container throws it
away and restores the image's baked-in initial state — no app-specific
reset script, migration, or seed step required.

```
docker compose up -d --force-recreate <service>   # reset one target
docker compose up -d --force-recreate               # reset all four
```

`todomvc` state is entirely client-side (`localStorage`), so its reset is
even cheaper: `browser.py`'s `reset()` calls
`page.evaluate("localStorage.clear()")` then reloads, no container restart
needed.

This is a deliberate simplification for a reproducible eval harness, not a
general-purpose deployment pattern — do not add persistent volumes here
without also adding an explicit per-app reset routine.

## Bringing targets up / down

```
docker compose up -d --build     # start all 4 (todomvc image is built locally)
docker compose ps                 # confirm all 4 are Up
docker compose down                # stop and remove all 4
```
