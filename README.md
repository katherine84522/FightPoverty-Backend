# FightPoverty-Backend

## Development

### Environment Setup

Before starting, copy the `.env.example` file to `.env` and fill in your own values.

```bash
cp .env.example .env
```

- `.env` is mainly used by the backend container

- In Docker Compose, Redis must use:

    > REDIS_HOST=redis

### Starting the Development Environment

#### Option A: Use the helper script (recommended)

To start the development environment, make the script executable first:

```bash
chmod +x enter_dev_env.sh
```

Then, run the script:

```bash
./enter_dev_env.sh
```

This script will handle creating, starting, and attaching to the development containers using `docker-compose.dev.yml`.


#### Option B: Use Docker Compose manually

Start all services in detached mode:

```bash
docker compose -f docker-compose.dev.yml up -d

docker compose -f docker-compose.dev.yml up -d --build
```

### Initialize Redis Test Data (Seed Users)

Redis runs inside the Docker Compose network.
Therefore, the seed script must be executed inside the backend container.

```bash
docker exec -it fightpoverty-backend python seed_test_users.py
```

### Access the Services

- Frontend (Vite dev server): http://localhost:5173

- Backend API (FastAPI): http://localhost:3001

  - Health check: http://localhost:3001/health

### Stopping the Development Environment

To stop all development containers (keep Redis data):

```bash
chmod +x stop_dev_env.sh
```

```bash
./stop_dev_env.sh
```

To stop containers and remove volumes (⚠ Redis data will be lost):

```bash
./stop_dev_env.sh clean
```

## Production

To start the production environment (backend only):

```bash
docker compose up -d --build
```
