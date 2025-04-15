import azure.functions as func
import logging
import os
import subprocess
import tempfile
import json
import azure.durable_functions as df

@df.activity_function(name="AuthenticateToAzure")
def authenticate_to_azure(params: dict) -> dict:
    """
    Azureに認証する
    """
    logging.info("Azureにサービスプリンシパルとして認証しています")
    
    try:
        # 必要なパラメータを確認
        required_params = ['azure_subscription_id', 'azure_tenant_id', 'azure_client_id', 'azure_client_secret']
        for param in required_params:
            if param not in params or not params[param]:
                raise ValueError(f"必須パラメータ '{param}' が指定されていません")
        
        # 認証に使用するパラメータを取得
        subscription_id = params["azure_subscription_id"]
        tenant_id = params["azure_tenant_id"]
        client_id = params["azure_client_id"]
        client_secret = params["azure_client_secret"]
        
        # 一時的な認証情報ファイルを作成
        auth_file = os.path.join(params["workdir"], "azure-auth.json")
        auth_data = {
            "clientId": client_id,
            "clientSecret": client_secret,
            "subscriptionId": subscription_id,
            "tenantId": tenant_id,
            "activeDirectoryEndpointUrl": "https://login.microsoftonline.com",
            "resourceManagerEndpointUrl": "https://management.azure.com/",
            "activeDirectoryGraphResourceId": "https://graph.windows.net/",
            "sqlManagementEndpointUrl": "https://management.core.windows.net:8443/",
            "galleryEndpointUrl": "https://gallery.azure.com/",
            "managementEndpointUrl": "https://management.core.windows.net/"
        }
        
        # 認証情報をファイルに書き込む
        with open(auth_file, 'w') as f:
            json.dump(auth_data, f)
        
        # Azure CLIでサービスプリンシパルとして認証
        command = f"az login --service-principal -u {client_id} -p {client_secret} --tenant {tenant_id}"
        process = subprocess.run(command, shell=True, capture_output=True, text=True)
        
        if process.returncode != 0:
            raise Exception(f"Azure認証エラー: {process.stderr}")
        
        # サブスクリプションを設定
        command = f"az account set --subscription {subscription_id}"
        process = subprocess.run(command, shell=True, capture_output=True, text=True)
        
        if process.returncode != 0:
            raise Exception(f"サブスクリプション設定エラー: {process.stderr}")
        
        logging.info("Azureへの認証が完了しました")
        
        return {
            "status": "success",
            "auth_file": auth_file,
            "message": "Azureへの認証が完了しました"
        }
    except Exception as e:
        error_msg = f"Azure認証中にエラーが発生しました: {str(e)}"
        logging.error(error_msg)
        raise Exception(error_msg)

# メイン関数（Functionsトリガー）
main = df.Activity.create(authenticate_to_azure)
