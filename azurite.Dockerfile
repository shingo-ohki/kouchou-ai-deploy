FROM mcr.microsoft.com/azure-storage/azurite

# Alpine Linuxのパッケージマネージャーapkを使用して、より多くの診断ツールをインストール
RUN apk add --no-cache curl netcat-openbsd bash iproute2 procps socat jq

# ディレクトリを作成
WORKDIR /data
RUN mkdir -p /data/__blobstorage__ /data/__queuestorage__ /data/__tablestorage__
RUN mkdir -p /data/logs

# Azuriteを直接実行（外部スクリプトを使用しない）
# --debugオプションにはログファイルパスを指定する必要がある
CMD ["azurite", "--silent", "--loose", "--debug", "/data/logs/debug.log", "--location", "/data", "--blobPort", "10000", "--queuePort", "10001", "--tablePort", "10002", "--blobHost", "0.0.0.0", "--queueHost", "0.0.0.0", "--tableHost", "0.0.0.0"]

# ヘルスチェックを改良
# より長いstart-periodを設定し、より簡単なチェックを行う
HEALTHCHECK --interval=15s --timeout=10s --start-period=60s --retries=10 \
  CMD nc -z localhost 10000 || exit 1