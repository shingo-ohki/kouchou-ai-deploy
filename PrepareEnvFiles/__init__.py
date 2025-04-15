import azure.functions as func
import logging
import os
import random
import string
import time
import azure.durable_functions as df

@df.activity_function(name="PrepareEnvFiles")
def prepare_env_files(params: dict) -> dict:
    """
    環境変数ファイルを準備する
    """
    logging.info("環境設定ファイルを準備しています")
    
    try:
        # 必須パラメータのチェック
        required_params = ['workdir', 'openai_api_key', 'basic_auth_username', 'basic_auth_password']
        for param in required_params:
            if param not in params or not params[param]:
                raise ValueError(f"必須パラメータ '{param}' が指定されていません")
        
        # クローンされたリポジトリのパスを取得
        repo_path = os.path.join(params["workdir"], "kouchou-ai")
        if not os.path.exists(repo_path):
            raise ValueError(f"リポジトリディレクトリが見つかりません: {repo_path}")
        
        # .env ファイルの作成
        # ランダムなAPIキーを生成
        public_api_key = generate_random_key()
        admin_api_key = generate_random_key()
        
        env_content = f"""PUBLIC_API_KEY={public_api_key}
ADMIN_API_KEY={admin_api_key}
OPENAI_API_KEY={params["openai_api_key"]}
BASIC_AUTH_USERNAME={params["basic_auth_username"]}
BASIC_AUTH_PASSWORD={params["basic_auth_password"]}
"""
        
        env_path = os.path.join(repo_path, ".env")
        with open(env_path, "w") as f:
            f.write(env_content)
        
        logging.info(f".env ファイルを作成しました: {env_path}")
        
        # .env.azure ファイルの作成
        timestamp = int(time.time())
        # リソースグループ、ストレージアカウント、ACR名にパラメータを使用するか、生成する
        resource_group = params.get("resource_group", f"kouchou-ai-rg-{timestamp}")
        region = params.get("region", "japaneast")
        storage_account = params.get("storage_account", f"kouchouai{timestamp}")
        container_name = params.get("container_name", "kouchou-ai-container")
        acr_name = params.get("acr_name", f"kouchouaiacr{timestamp}")
        
        env_azure_content = f"""AZURE_RESOURCE_GROUP={resource_group}
AZURE_LOCATION={region}
AZURE_ACR_NAME={acr_name}
AZURE_ACR_SKU=Basic
AZURE_CONTAINER_ENV=kouchou-ai-env
AZURE_WORKSPACE_NAME=kouchou-ai-logs
AZURE_BLOB_STORAGE_ACCOUNT_NAME={storage_account}
AZURE_BLOB_STORAGE_CONTAINER_NAME={container_name}
"""
        
        env_azure_path = os.path.join(repo_path, ".env.azure")
        with open(env_azure_path, "w") as f:
            f.write(env_azure_content)
        
        logging.info(f".env.azure ファイルを作成しました: {env_azure_path}")
        
        return {
            "status": "success",
            "message": "環境設定ファイルの準備が完了しました",
            "env_files": [env_path, env_azure_path],
            "public_api_key": public_api_key,
            "admin_api_key": admin_api_key,
            "resource_group": resource_group,
            "storage_account": storage_account,
            "acr_name": acr_name
        }
    except Exception as e:
        error_msg = f"環境設定ファイルの準備中にエラーが発生しました: {str(e)}"
        logging.error(error_msg)
        raise Exception(error_msg)

def generate_random_key(length=32):
    """
    ランダムなAPIキーを生成する
    """
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

# メイン関数（Functionsトリガー）
main = df.Activity.create(prepare_env_files)
