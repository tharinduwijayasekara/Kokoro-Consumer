#!/usr/bin/env bash

echo "Restarting docker"
docker compose down && docker compose up -d