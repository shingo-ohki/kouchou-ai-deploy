FROM mcr.microsoft.com/azure-functions/python:4-python3.9

ENV AzureWebJobsScriptRoot=/home/site/wwwroot \
    AzureFunctionsJobHost__Logging__Console__IsEnabled=true \
    PYTHONUNBUFFERED=1 \
    PATH="${PATH}:/home/site/.local/bin" \
    PYTHONPATH="/home/site/wwwroot" \
    AzureFunctionsJobHost__extensions__durableTask__hubName=TaskHub \
    AzureWebJobsFeatureFlags=EnableAuthenticationRequirement,EnableCorsConfiguration \
    AzureFunctionsJobHost__extensions__durableTask__notifications__webhookAuthorizationLevel=Anonymous

# ネットワークツールとデバッグツールをインストール
RUN apt-get update && \
    apt-get install -y --no-install-recommends netcat iputils-ping curl dnsutils iproute2 tcpdump socat vim procps git gnupg lsb-release && \
    curl -sL https://aka.ms/InstallAzureCLIDeb | bash && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 作業ディレクトリを作成
WORKDIR /home/site/wwwroot

# まず依存関係ファイルのみをコピー
COPY requirements.txt .

# 依存関係のインストール
RUN pip install --upgrade pip setuptools wheel && \
    # まず既存のパッケージをクリア
    pip uninstall -y azure-functions azure-functions-durable && \
    # 依存関係をインストール - 互換性の確認済みバージョンを使用
    pip install --no-cache-dir 'azure-functions==1.12.0' && \
    pip install --no-cache-dir 'azure-functions-durable==1.2.4' && \
    # 最新のSDKをインストール
    pip install --no-cache-dir 'azure-identity>=1.12.0' && \
    pip install --no-cache-dir 'azure-mgmt-containerregistry>=10.1.0' && \
    pip install --no-cache-dir -r requirements.txt && \
    # インストール確認
    pip list

# 起動スクリプトをコピー
COPY start.sh /home/site/wwwroot/start.sh
RUN chmod +x /home/site/wwwroot/start.sh

# すべてのファイルをコピー
COPY . .

# 起動スクリプトを実行
ENTRYPOINT ["/bin/bash", "/home/site/wwwroot/start.sh"]
