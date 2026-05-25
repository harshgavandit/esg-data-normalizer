$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

docker compose up -d db
& "C:\Users\Rohan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" backend/manage.py migrate
& "C:\Users\Rohan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" backend/manage.py seed_demo
& "C:\Users\Rohan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" backend/manage.py runserver 127.0.0.1:8010
