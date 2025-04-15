#!/bin/bash
set -e

# まず、古いデータを削除してクリーンな状態から開始
echo "Cleaning up existing data..."
rm -rf /data/__blobstorage__/* /data/__queuestorage__/* /data/__tablestorage__/*

# ストレージディレクトリを再作成
echo "Creating fresh storage directories..."
mkdir -p /data/__blobstorage__
mkdir -p /data/__queuestorage__
mkdir -p /data/__tablestorage__

# デバッグ情報を表示
echo "===== ENVIRONMENT VARIABLES ====="
env | sort
echo "================================"

echo "===== DATA DIRECTORY STRUCTURE ====="
ls -la /data
echo "=================================="

# Azuriteを起動する
echo "Starting Azurite in debug mode with authentication disabled..."

# 認証を完全に無効化して、デバッグモードでAzuriteを実行
exec azurite \
  --debug \
  --silent \
  --loose \
  --noAuth \
  --location /data \
  --blobPort 10000 \
  --queuePort 10001 \
  --tablePort 10002 \
  --blobHost 0.0.0.0 \
  --queueHost 0.0.0.0 \
  --tableHost 0.0.0.0