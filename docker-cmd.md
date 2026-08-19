# Docker Commands & Database Migration Guide
=============================================

This file contains instructions on how to open a command line inside your running Docker container to run the Alembic database migrations, as well as troubleshooting steps for connecting to your host PostgreSQL database.

## 1. Quick Migration Commands

If you just want to run the migrations directly without opening an interactive command line, you can run one of these commands from your host terminal (PowerShell or WSL terminal) in the directory where `docker-compose.yml` is located:

### If the containers are already running:
```bash
docker compose exec wings_retrival_ai alembic upgrade head
```

### If the containers are NOT running:
```bash
docker compose run --rm wings_retrival_ai alembic upgrade head
```

---

## 2. How to Open the Command Line (Interactive Terminal) in Docker

If you want to open a bash shell inside the Docker container to run migrations manually or execute other Python commands:

### Step 1: Open the interactive shell
* **If the container is already running:**
  ```bash
  docker compose exec wings_retrival_ai bash
  ```
  *(Note: You can also use `docker exec -it wings_retrival_ai bash` if using standard Docker commands)*

* **If the container is NOT running:**
  ```bash
  docker compose run --rm wings_retrival_ai bash
  ```

### Step 2: Run your migration syntax
Once you are inside the container's shell (you will see a prompt like `root@<container-id>:/app#`), run:
```bash
alembic upgrade head
```

### Step 3: Exit the container
To leave the container's command line and return to your host terminal, simply type:
```bash
exit
```

---

## 3. Important Setup for Host PostgreSQL (Linux/WSL)

Since your Postgres database lives on the host (local Linux machine) and your FastAPI app is running inside a Docker container, you must configure PostgreSQL on Linux to accept connections from the Docker network.

If you get a connection timeout or connection refused error when running migrations, follow these steps on your Linux host:

### Step A: Configure PostgreSQL to listen on all interfaces
1. Open the PostgreSQL config file (path depends on your PostgreSQL version, e.g., v16):
   ```bash
   sudo nano /etc/postgresql/16/main/postgresql.conf
   ```
2. Find the line:
   `#listen_addresses = 'localhost'`
3. Uncomment it and change it to:
   `listen_addresses = '*'`
4. Save and exit (Ctrl+O, Enter, Ctrl+X).

### Step B: Allow connections from the Docker network
1. Open the client authentication file:
   ```bash
   sudo nano /etc/postgresql/16/main/pg_hba.conf
   ```
2. Scroll to the bottom and add this line to allow connection from all IP addresses:
   ```
   host    all             all             0.0.0.0/0               scram-sha-256
   ```
   *(Note: Use `md5` instead of `scram-sha-256` if using an older Postgres version or if authentication fails).*
3. Save and exit.

### Step C: Restart the PostgreSQL service
Apply changes by restarting the PostgreSQL service on your Linux host:
```bash
sudo systemctl restart postgresql
# OR
sudo service postgresql restart
```

---

## 4. Useful Alembic Commands

Here are other helpful commands you can run inside the container shell:
* **Check current migration status:**
  ```bash
  alembic current
  ```
* **View migration history:**
  ```bash
  alembic history
  ```
* **Generate a new migration script (if you change SQLAlchemy models):**
  ```bash
  alembic revision --autogenerate -m "description of changes"
  ```
