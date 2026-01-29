#!/bin/bash
set -e

echo "Installing gunicorn and uvicorn..."
pip install gunicorn uvicorn[standard]

echo "Build completed successfully!"
