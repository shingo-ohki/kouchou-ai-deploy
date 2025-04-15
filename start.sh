#!/bin/bash

# Azurite接続を待機する関数
wait_for_azurite() {
  echo "Waiting for Azurite to be ready..."
  for i in {1..30}; do
    echo "Attempt $i: Testing Azurite connection..."
    # DNSルックアップを実行
    echo -n "DNS lookup: "
    if getent hosts azurite >/dev/null; then
      echo "Success - azurite hostname resolved"
      AZURITE_IP=$(getent hosts azurite | awk "{ print \$1 }")
      echo "Azurite IP: $AZURITE_IP"
      
      # IPアドレスをhostsファイルに追加
      echo "$AZURITE_IP azurite" >> /etc/hosts
      
      # 接続テスト
      echo "Testing connection to azurite:10000..."
      if nc -z azurite 10000; then
        echo "✓ Connection to azurite:10000 successful!"
        return 0
      else
        echo "✗ Connection to azurite:10000 failed. Retrying..."
      fi
    else
      echo "Failed - could not resolve azurite hostname"
    fi
    sleep 2
  done
  echo "Failed to connect to Azurite after multiple attempts"
  return 1
}

echo "===== System Information ====="
echo "Date: $(date)"
echo "Hostname: $(hostname)"
echo "Network interfaces:"
ip addr
echo "Network routes:"
ip route
echo "Current hosts file:"
cat /etc/hosts

echo "===== Environment Variables ====="
env | grep -E "Azure|FUNCTIONS|PYTHON"

echo "===== Waiting for Azurite ====="
wait_for_azurite

echo "===== Azure Storage Connection String ====="
echo $AzureWebJobsStorage

echo "===== Testing Azure Credentials ====="
python -c "
import os
from azure.storage.blob import BlobServiceClient

try:
    conn_str = os.environ['AzureWebJobsStorage']
    service = BlobServiceClient.from_connection_string(conn_str)
    containers = list(service.list_containers())
    print(f'Connected successfully! Found {len(containers)} containers.')
except Exception as e:
    print(f'Error connecting to Azure Storage: {e}')
" || echo "Failed to connect to Azure Storage"

echo "===== Starting Azure Functions ====="
/azure-functions-host/Microsoft.Azure.WebJobs.Script.WebHost

# 診断情報の表示
echo "=== 環境変数の確認 ==="
echo "AzureWebJobsScriptRoot: $AzureWebJobsScriptRoot"
echo "AzureFunctionsJobHost__extensions__durableTask__hubName: $AzureFunctionsJobHost__extensions__durableTask__hubName"
echo "AzureWebJobsFeatureFlags: $AzureWebJobsFeatureFlags"
echo "=== コンテナ情報 ==="
echo "ホスト名: $(hostname)"

# 認証関連の説明を追加
echo "===== 認証設定の注意点 ====="
echo "現在の環境: ${AZURE_FUNCTIONS_ENVIRONMENT:-Development}"

# 環境に応じた設定を行う
if [[ "${AZURE_FUNCTIONS_ENVIRONMENT:-Development}" == "Development" ]]; then
  echo "開発環境用の設定を適用します"
  
  # 開発環境ではシンプルなアクセスキーを使用
  export AzureFunctionsJobHost__extensions__durableTask__notifications__webhookAuthorizationLevel=Function
  export WEBSITE_AUTH_ENABLED=false
  
  # 認証とCORSの診断
  echo "認証レベル: Function (キーによる認証)"
  echo "CORS設定: http://127.0.0.1:10000 からのアクセスを許可"
  echo "注意: 本番環境では、より厳格な認証設定を使用してください"
else
  echo "本番環境用の設定を適用します"
  
  # 本番環境では適切な認証レベルを設定
  export AzureFunctionsJobHost__extensions__durableTask__notifications__webhookAuthorizationLevel=Function
  export WEBSITE_AUTH_ENABLED=true
  
  echo "認証レベル: Function (キーによる認証)"
  echo "注意: 必要に応じてより高いセキュリティレベル(Admin)に設定してください"
fi

# CORS診断
echo "=== CORS設定 ==="
if [ -f host.json ]; then
  echo "host.json CORS設定:"
  cat host.json | grep -A 20 cors
else
  echo "host.json not found"
fi

# Azure Functions Host の起動
echo "=== Azure Functions Host 起動 ==="
cd /home/site/wwwroot && /azure-functions-host/Microsoft.Azure.WebJobs.Script.WebHost