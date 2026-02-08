#!/usr/bin/env bash

echo "Running command"
docker compose down
docker compose up -d 
docker compose exec generator python app/generate_audiobook.py --chapterize