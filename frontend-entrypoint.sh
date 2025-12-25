#!/bin/sh
set -e

echo "📦 Checking node_modules..."

# 如果 node_modules 不存在，才執行 npm install
if [ ! -d "/app/node_modules" ]; then
    echo "⚙️  Installing npm dependencies..."
    npm install
else
    echo "👍  node_modules already exists, skipping install."
fi

echo "🚀 Starting frontend..."
exec "$@"
