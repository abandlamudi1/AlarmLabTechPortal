# Docker Compose Profiles

Default (`docker compose up`): starts `web` + `redis` only.

With Celery workers (`docker compose --profile worker up`): also starts `worker` + `beat`.

Note: worker and beat are non-functional stubs until Slice C (Sprint 4).
