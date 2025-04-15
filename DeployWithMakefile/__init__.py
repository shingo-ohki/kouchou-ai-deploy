import logging
import os
import time
import requests
import json
import traceback
from datetime import datetime
import azure.functions as func
import base64
import uuid
import subprocess
import concurrent.futures

def main(params: str) -> str:
    """
    Azure REST APIを使用して広聴AIをAzure環境にデプロイする
    """
    logging.info("DeployWithMakefile: Azure REST APIを使用したデプロイを開始します")
    logs = []
    
    try:
        # 文字列として渡された場合はJSONとして解析
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except:
                logging.error("パラメータのJSONパースに失敗しました")
                params = {}
        
        # 必須パラメータのチェック
        required_params = [
            'workdir', 'azure_subscription_id', 'azure_tenant_id', 
            'azure_client_id', 'azure_client_secret', 'openai_api_key',
            'basic_auth_username', 'basic_auth_password'
        ]
        for param in required_params:
            if param not in params or not params[param]:
                raise ValueError(f"必須パラメータ '{param}' が指定されていません")
        
        # step_statusは進捗情報を保持する辞書
        step_status = {
            "step": "デプロイ準備", 
            "progress": 5, 
            "message": "デプロイのための準備を行っています..."
        }
        
        # Gitリポジトリの設定
        git_repo_url = params.get('git_repo_url', 'https://github.com/digitaldemocracy2030/kouchou-ai')
        git_branch = params.get('git_branch', 'main')
        
        # 広聴AIリポジトリのパス
        repo_path = os.path.join(params["workdir"], "kouchou-ai")
        
        # リポジトリディレクトリが存在しない場合、Gitからクローン
        if not os.path.exists(repo_path):
            step_status = {
                "step": "リポジトリ準備", 
                "progress": 5, 
                "message": f"Gitリポジトリ {git_repo_url} をクローンしています..."
            }
            
            logging.info(f"Gitリポジトリのクローンを実行: {git_repo_url} (ブランチ: {git_branch})")
            logs.append(f"Gitリポジトリのクローン中: {git_repo_url} (ブランチ: {git_branch})")
            
            try:
                clone_cmd = f"git clone --branch {git_branch} {git_repo_url} {repo_path}"
                process = subprocess.run(clone_cmd, shell=True, check=True, 
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                                        text=True)
                logs.append(f"リポジトリのクローンが完了しました")
                logging.info(f"リポジトリのクローンが完了")
            except subprocess.CalledProcessError as e:
                error_message = f"Gitクローン中にエラーが発生しました: {e.stderr}"
                logging.error(error_message)
                logs.append(error_message)
                raise Exception(f"Gitリポジトリのクローンに失敗しました: {e.stderr}")
        else:
            logs.append(f"既存のリポジトリディレクトリを使用します: {repo_path}")
            logging.info(f"既存のリポジトリディレクトリを使用: {repo_path}")
        
        # パラメータを取得
        subscription_id = params['azure_subscription_id']
        tenant_id = params['azure_tenant_id']
        client_id = params['azure_client_id']
        client_secret = params['azure_client_secret']
        
        # デプロイ設定の準備
        step_status = {
            "step": "設定ファイル準備", 
            "progress": 8, 
            "message": "デプロイ設定ファイルを準備しています..."
        }
        
        # .envファイルの生成
        env_path = os.path.join(repo_path, ".env")
        with open(env_path, "w") as f:
            f.write(f"""PUBLIC_API_KEY={params.get('public_api_key', 'pub_' + os.urandom(16).hex())}
ADMIN_API_KEY={params.get('admin_api_key', 'adm_' + os.urandom(16).hex())}
OPENAI_API_KEY={params['openai_api_key']}
BASIC_AUTH_USERNAME={params['basic_auth_username']}
BASIC_AUTH_PASSWORD={params['basic_auth_password']}
""")
        
        # .env.azureファイルの生成
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        resource_group = params.get('resource_group', f"kouchou-ai-rg-{timestamp}")
        region = params.get('region', 'japaneast')
        
        # ストレージアカウント名は小文字と数字のみで、3-24文字の制限がある
        # タイムスタンプを短縮して、文字数制限に対応
        short_timestamp = datetime.now().strftime("%y%m%d%H%M")  # YYMMDDhhmm形式で短縮
        storage_account = params.get('storage_account', f"kouchouai{short_timestamp}".lower())
        
        container_name = params.get('container_name', "kouchou-ai-container")
        
        # ACR名は別の短い形式を使用して命名競合を避ける
        acr_short_timestamp = datetime.now().strftime("%y%m%d%H")  # YYMMDDhh形式でさらに短縮
        acr_name = params.get('acr_name', f"kouchouacr{acr_short_timestamp}".lower())
        
        env_azure_path = os.path.join(repo_path, ".env.azure")
        with open(env_azure_path, "w") as f:
            f.write(f"""AZURE_RESOURCE_GROUP={resource_group}
AZURE_LOCATION={region}
AZURE_ACR_NAME={acr_name}
AZURE_ACR_SKU=Basic
AZURE_CONTAINER_ENV=kouchou-ai-env
AZURE_WORKSPACE_NAME=kouchou-ai-logs
AZURE_BLOB_STORAGE_ACCOUNT_NAME={storage_account}
AZURE_BLOB_STORAGE_CONTAINER_NAME={container_name}
""")
        
        # Azure REST APIを使用してデプロイを実行
        # まずはアクセストークンを取得
        step_status = {
            "step": "Azure認証", 
            "progress": 10, 
            "message": "Azure APIにログインしています..."
        }
        
        logging.info("Azure REST APIにアクセスするためのトークンを取得中...")
        
        # トークン取得プロセスを改善し、エラーをより詳細に捉える
        token = None
        try:
            token = get_azure_token_improved(tenant_id, client_id, client_secret)
            if not token:
                raise Exception("認証トークンが空です。クライアントID、シークレットとテナントIDを確認してください。")
            logging.info("Azureアクセストークンを取得しました")
        except Exception as auth_error:
            detail = str(auth_error)
            trace = traceback.format_exc()
            logging.error(f"認証エラー: {detail}\n{trace}")
            raise Exception(f"Azureアクセストークン取得に失敗しました: {detail}")
        
        # 進行状況とログを記録する変数を初期化
        logs = []
        urls = {}
        
        # 既存のリソースを検索して再利用
        existing_resources = find_existing_resources(subscription_id, token)

        # 1. リソースグループの作成
        step_status = {
            "step": "リソースグループ作成", 
            "progress": 12, 
            "message": f"リソースグループ {resource_group} を作成しています..."
        }
        
        logging.info(f"リソースグループ {resource_group} を作成中...")
        logs.append(f"リソースグループ {resource_group} を作成中...")
        
        create_resource_group(subscription_id, resource_group, region, token)
        logs.append(f"リソースグループ {resource_group} の作成完了")
        
        # 2. ストレージアカウントの作成（存在確認後）
        step_status = {
            "step": "ストレージ確認と作成", 
            "progress": 15, 
            "message": f"ストレージアカウント {storage_account} を確認・作成しています..."
        }

        # ストレージアカウントの存在確認
        storage_exists = check_storage_account_exists(subscription_id, resource_group, storage_account, token)
        if storage_exists:
            logging.info(f"既存のストレージアカウントを使用します: {storage_account}")
            logs.append(f"既存のストレージアカウント {storage_account} を使用します")
        else:
            logging.info(f"ストレージアカウント {storage_account} を作成中...")
            logs.append(f"ストレージアカウント {storage_account} を作成中...")
            create_storage_account(subscription_id, resource_group, storage_account, region, token)
            logs.append(f"ストレージアカウント {storage_account} の作成完了")

        # 3. ストレージコンテナの作成
        step_status = {
            "step": "コンテナ作成", 
            "progress": 18, 
            "message": f"ストレージコンテナ {container_name} を作成しています..."
        }
        
        logging.info(f"ストレージコンテナ {container_name} を作成中...")
        logs.append(f"ストレージコンテナ {container_name} を作成中...")
        
        try:
            create_storage_container(subscription_id, resource_group, storage_account, container_name, token)
            logs.append(f"ストレージコンテナ {container_name} の作成完了")
        except Exception as container_error:
            # コンテナ作成エラーがあっても続行（既にコンテナが存在する場合など）
            logs.append(f"注意：ストレージコンテナの作成に問題が発生しましたが、処理を継続します: {str(container_error)}")
        
        # 4. ACRの作成（存在確認後）
        step_status = {
            "step": "ACR確認と作成", 
            "progress": 20, 
            "message": f"ACR {acr_name} を確認・作成しています..."
        }

        # ACRの存在確認と作成（より堅牢な処理）
        max_retries = 2
        for attempt in range(max_retries):
            # ACRの存在確認
            acr_info = check_acr_exists(subscription_id, resource_group, acr_name, token)
            
            if acr_info:
                logging.info(f"既存のACR {acr_name} を使用します")
                logs.append(f"既存のACR {acr_name} を使用します")
                break
            else:
                # ACRが存在しない場合は作成を試みる
                logging.info(f"ACR {acr_name} を作成中... (試行 {attempt+1}/{max_retries})")
                logs.append(f"ACR {acr_name} を作成中...")
                
                try:
                    acr_info = create_acr(subscription_id, resource_group, acr_name, region, "Basic", token)
                    logs.append(f"ACR {acr_name} の作成完了")
                    
                    # 作成直後に確認を行う
                    time.sleep(10)  # 少し待機
                    acr_verify = check_acr_exists(subscription_id, resource_group, acr_name, token)
                    if acr_verify:
                        logging.info(f"ACR {acr_name} の作成を確認しました")
                        acr_info = acr_verify  # より完全な情報に更新
                        break
                    elif attempt < max_retries - 1:
                        logging.warning(f"ACR {acr_name} が作成されましたが、確認できません。再試行します。")
                        time.sleep(30)  # より長く待機して再試行
                except Exception as e:
                    if attempt < max_retries - 1:
                        logging.warning(f"ACR作成エラー: {str(e)}。再試行します。")
                        time.sleep(20)
                    else:
                        raise  # 最後の試行で失敗した場合は例外を投げる
        else:
            error_msg = f"ACR {acr_name} の作成に失敗しました。"
            logging.error(error_msg)
            logs.append(error_msg)
            raise Exception(error_msg)

        # ACRが正常に作成または取得できたことを確認
        if not acr_info:
            error_msg = f"ACR {acr_name} の情報が取得できません。"
            logging.error(error_msg)
            logs.append(error_msg)
            raise Exception(error_msg)
            
        # ACRのログインサーバー取得
        acr_login_server = f"{acr_name}.azurecr.io"
        if isinstance(acr_info, dict) and 'properties' in acr_info and 'loginServer' in acr_info['properties']:
            acr_login_server = acr_info['properties']['loginServer']
        else:
            logging.warning(f"ACRのloginServer情報が取得できません。デフォルト値を使用: {acr_login_server}")
            logs.append(f"警告: ACRのloginServer情報が取得できません。デフォルト値を使用します")

        # ACRへのアクセス権限を設定（前に必ずACRが存在することを確認済み）
        step_status = {
            "step": "ACR権限設定", 
            "progress": 22, 
            "message": f"ACR {acr_name} へのアクセス権限を設定しています..."
        }

        logging.info(f"ACR {acr_name} へのアクセス権限を設定中...")
        logs.append(f"ACR {acr_name} へのアクセス権限を設定中...")

        try:
            # ACRの存在を最終確認
            final_check = check_acr_exists(subscription_id, resource_group, acr_name, token)
            if not final_check:
                # ACRが見つからない場合は、ACRのリソースグループ全体をチェック
                logging.warning(f"権限設定前の確認で ACR {acr_name} が見つかりません。リソースグループ内のACRを検索します...")
                
                # リソースグループ内の全リソースを取得して確認
                resources_url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group}/resources?api-version=2021-04-01"
                headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
                resources_response = requests.get(resources_url, headers=headers, timeout=30)
                
                if resources_response.status_code == 200:
                    all_resources = resources_response.json().get('value', [])
                    acr_resources = [r for r in all_resources if r.get('type') == 'Microsoft.ContainerRegistry/registries']
                    
                    if acr_resources:
                        found_acr = acr_resources[0]['name']
                        logging.info(f"リソースグループ内に別のACR {found_acr} が見つかりました。これを使用します。")
                        logs.append(f"リソースグループ内に別のACR {found_acr} が見つかりました。これを使用します。")
                        acr_name = found_acr
                    else:
                        error_msg = f"リソースグループ内にACRが見つかりません。新しいACRを作成します。"
                        logging.warning(error_msg)
                        logs.append(error_msg)
                        
                        # もう一度ACRを作成する最後の試み
                        acr_info = create_acr(subscription_id, resource_group, acr_name, region, "Basic", token)
                        time.sleep(30)  # 作成完了を待つ
                        
                        # 最終確認
                        final_retry_check = check_acr_exists(subscription_id, resource_group, acr_name, token)
                        if not final_retry_check:
                            error_msg = f"最後の試行でも ACR {acr_name} を作成できませんでした。"
                            logging.error(error_msg)
                            logs.append(error_msg)
                            raise Exception(error_msg)
                            
            # 権限設定を実行
            assign_acr_permissions(subscription_id, resource_group, acr_name, token)
            logs.append(f"ACR {acr_name} へのアクセス権限設定が完了しました")
        except Exception as acr_perm_error:
            # ACR権限設定エラーの場合は処理を中断
            error_msg = f"ACR {acr_name} へのアクセス権限設定に失敗しました: {str(acr_perm_error)}"
            logging.error(error_msg)
            logs.append(error_msg)
            raise Exception(error_msg)
        
        # 5. コンテナイメージのビルドとACRへのプッシュ - 並列処理に変更
        step_status = {
            "step": "イメージビルド", 
            "progress": 25, 
            "message": "サーバー、クライアント、管理用クライアントのイメージを並列ビルドしています..."
        }

        # ビルド対象の定義
        build_targets = [
            {
                "name": "server",
                "dir": "server",
                "tag": "server:latest",
                "message": "サーバーイメージをビルドしてACRにプッシュ"
            },
            {
                "name": "client",
                "dir": "client",
                "tag": "client:latest",
                "message": "クライアントイメージをビルドしてACRにプッシュ"
            },
            {
                "name": "client-admin",
                "dir": "client-admin",
                "tag": "client-admin:latest",
                "message": "管理用クライアントイメージをビルドしてACRにプッシュ"
            }
        ]

        # ビルド結果を格納する辞書
        build_results = {}

        # 単一イメージをビルドする関数
        def build_single_image(target):
            target_name = target["name"]
            target_dir = target["dir"]
            target_tag = target["tag"]
            target_message = target["message"]
            
            logging.info(f"{target_message}: {target_tag}")
            logs.append(f"{target_name}イメージのビルドとプッシュを開始: {target_tag}")
            
            result = build_image_with_azure_cli(
                subscription_id, resource_group, acr_name,
                target_dir,
                target_tag,
                git_repo_url,
                git_branch,
                client_id,
                client_secret,
                tenant_id
            )
            
            logs.append(f"{target_name}イメージのビルドとプッシュが完了: {result['image']}")
            return target_name, result

        # ThreadPoolExecutor を使用して並列処理を実行
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            # すべてのビルドジョブを開始
            future_to_target = {executor.submit(build_single_image, target): target for target in build_targets}
            
            # 各タスクが完了したときの処理
            for future in concurrent.futures.as_completed(future_to_target):
                target = future_to_target[future]
                try:
                    name, result = future.result()
                    build_results[name] = result
                    logging.info(f"{name}イメージのビルドが完了しました")
                except Exception as e:
                    logging.error(f"{target['name']}イメージのビルド中にエラー発生: {str(e)}")
                    # エラーが発生した場合はプロセス全体を中止
                    raise Exception(f"イメージ {target['name']} のビルドに失敗: {str(e)}")

        # すべてのビルドが並列実行され、ここで全部完了している
        logging.info("すべてのイメージの並列ビルドが完了しました")
        logs.append("すべてのイメージの並列ビルドが完了しました")

        # 後続の処理で使用するために個別の変数に結果を代入
        server_build_result = build_results["server"]
        client_build_result = build_results["client"]
        admin_build_result = build_results["client-admin"]

        # ビルド完了ステータスの更新
        step_status = {
            "step": "イメージビルド完了", 
            "progress": 40, 
            "message": "すべてのイメージビルドが完了しました"
        }

        # 6. Azure Container Appsへのデプロイ
        # 6.1 サーバーアプリのデプロイ
        step_status = {
            "step": "サーバーデプロイ", 
            "progress": 55, 
            "message": "サーバーアプリをデプロイしています..."
        }
        
        server_app_name = "kouchou-ai-server"
        server_env_vars = {
            "OPENAI_API_KEY": params['openai_api_key'],
            "PUBLIC_API_KEY": params.get('public_api_key', 'pub_' + os.urandom(16).hex()),
            "ADMIN_API_KEY": params.get('admin_api_key', 'adm_' + os.urandom(16).hex()),
            "AZURE_BLOB_STORAGE_ACCOUNT_NAME": storage_account,
            "AZURE_BLOB_STORAGE_CONTAINER_NAME": container_name
        }
        
        logging.info(f"サーバーアプリをContainer Appsにデプロイ: {server_app_name}")
        logs.append(f"サーバーアプリのデプロイを開始: {server_app_name}")
        
        server_deploy_result = deploy_to_container_apps(
            subscription_id, resource_group, server_app_name, region,
            server_build_result['image'],
            acr_name, acr_login_server,
            token, server_env_vars, 8000
        )
        
        api_url = get_container_app_url(subscription_id, resource_group, server_app_name, token)
        logs.append(f"サーバーアプリのデプロイが完了: {api_url}")
        
        # 6.2 クライアントアプリのデプロイ
        step_status = {
            "step": "クライアントデプロイ", 
            "progress": 70, 
            "message": "クライアントアプリをデプロイしています..."
        }
        
        client_app_name = "kouchou-ai-client"
        client_env_vars = {
            "BASIC_AUTH_USERNAME": params['basic_auth_username'],
            "BASIC_AUTH_PASSWORD": params['basic_auth_password'],
            "NEXT_PUBLIC_API_BASE_URL": api_url
        }
        
        logging.info(f"クライアントアプリをContainer Appsにデプロイ: {client_app_name}")
        logs.append(f"クライアントアプリのデプロイを開始: {client_app_name}")
        
        client_deploy_result = deploy_to_container_apps(
            subscription_id, resource_group, client_app_name, region,
            client_build_result['image'],
            acr_name, acr_login_server,
            token, client_env_vars, 3000
        )
        
        client_url = get_container_app_url(subscription_id, resource_group, client_app_name, token)
        logs.append(f"クライアントアプリのデプロイが完了: {client_url}")
        
        # 6.3 管理用クライアントアプリのデプロイ
        step_status = {
            "step": "管理クライアントデプロイ", 
            "progress": 85, 
            "message": "管理用クライアントアプリをデプロイしています..."
        }
        
        admin_app_name = "kouchou-ai-admin"
        admin_env_vars = {
            "BASIC_AUTH_USERNAME": params['basic_auth_username'],
            "BASIC_AUTH_PASSWORD": params['basic_auth_password'],
            "NEXT_PUBLIC_API_BASE_URL": api_url,
            "ADMIN_API_KEY": server_env_vars["ADMIN_API_KEY"]
        }
        
        logging.info(f"管理用クライアントアプリをContainer Appsにデプロイ: {admin_app_name}")
        logs.append(f"管理用クライアントアプリのデプロイを開始: {admin_app_name}")
        
        admin_deploy_result = deploy_to_container_apps(
            subscription_id, resource_group, admin_app_name, region,
            admin_build_result['image'],
            acr_name, acr_login_server,
            token, admin_env_vars, 4000
        )
        
        admin_url = get_container_app_url(subscription_id, resource_group, admin_app_name, token)
        logs.append(f"管理用クライアントアプリのデプロイが完了: {admin_url}")
        
        # URLs記録
        urls = {
            "client": client_url,
            "admin": admin_url,
            "api": api_url
        }
        
        # 7. 完了
        step_status = {
            "step": "完了", 
            "progress": 100, 
            "message": "広聴AIのデプロイが完了しました！"
        }
        
        # URLが空の場合はデプロイに問題があった可能性を警告
        if not api_url or not client_url or not admin_url:
            warning_msg = "警告: 一部またはすべてのURLが取得できませんでした。デプロイが部分的に失敗した可能性があります。"
            logging.warning(warning_msg)
            logs.append(warning_msg)
            step_status["message"] = "デプロイは完了しましたが、一部機能に問題があります。" 

        logging.info("全てのアプリケーションのデプロイが完了しました")
        logs.append("広聴AIの全コンポーネントがAzureにデプロイされました！")
        logs.append(f"クライアントアプリ: {client_url or '取得できませんでした'}")
        logs.append(f"管理用アプリ: {admin_url or '取得できませんでした'}")
        logs.append(f"APIサーバー: {api_url or '取得できませんでした'}")
        
        result = {
            "status": "success",
            "message": "広聴AIのAzureデプロイが完了しました",
            "resource_group": resource_group,
            "storage_account": storage_account,
            "container_name": container_name,
            "acr_name": acr_name,
            "urls": urls,
            "auth": {
                "username": params["basic_auth_username"],
                "password": params["basic_auth_password"]
            },
            "api_keys": {
                "public": server_env_vars["PUBLIC_API_KEY"],
                "admin": server_env_vars["ADMIN_API_KEY"]
            },
            "logs": logs,
            "step_status": step_status  # ステップ情報を結果に含める
        }
        
        # 結果をJSON文字列として返す
        return json.dumps(result)
    except Exception as e:
        error_msg = f"Makefileを使用したデプロイ中にエラーが発生しました: {str(e)}"
        logging.error(error_msg)
        error_status = {
            "step": "エラー", 
            "progress": 0, 
            "message": error_msg
        }
        return json.dumps({
            "status": "error",
            "message": error_msg,
            "logs": logs[-100:] if logs else [],
            "step_status": error_status  # エラー時のステップ情報も含める
        })


def get_azure_token_improved(tenant_id, client_id, client_secret):
    """改善版：Azure REST APIアクセス用のトークンを取得"""
    url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/token"
    
    # クライアントシークレットの前処理（空白除去、シークレットID部分の検証）
    client_secret = client_secret.strip() if client_secret else ""
    
    # URLエンコーディングを確保
    import urllib.parse
    encoded_secret = urllib.parse.quote(client_secret)
    
    # クライアントシークレットのフォーマットをチェック（デバッグ用）
    secret_prefix = client_secret[:4] if len(client_secret) > 4 else client_secret
    secret_length = len(client_secret)
    logging.info(f"クライアントシークレットの形式: 先頭4文字={secret_prefix}***, 長さ={secret_length}文字")
    
    payload = {
        'grant_type': 'client_credentials',
        'client_id': client_id,
        'client_secret': client_secret,  # 元の値（エンコード済み）
        'resource': 'https://management.azure.com/'
    }
    
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    try:
        logging.info(f"Azure AD認証を開始... テナントID: {tenant_id[:4]}***")
        logging.info(f"クライアントID: {client_id[:8]}***")
        
        response = requests.post(url, data=payload, headers=headers, timeout=30)
        
        # レスポンスコードとメッセージをログに記録
        logging.info(f"トークンリクエスト応答コード: {response.status_code}")
        
        if response.status_code == 200:
            token_data = response.json()
            if 'access_token' in token_data:
                # トークンの一部をログに記録（セキュリティのため完全なトークンは記録しない）
                token = token_data['access_token']
                token_start = token[:10] if len(token) > 10 else token
                logging.info(f"トークン取得成功: {token_start}***")
                return token
            else:
                logging.error("応答にアクセストークンが含まれていません")
                return None
        else:
            error_detail = "不明なエラー"
            try:
                error_data = response.json()
                if 'error_description' in error_data:
                    error_detail = error_data['error_description']
                elif 'error' in error_data:
                    error_detail = error_data['error']
            except:
                error_detail = response.text[:200] if response.text else "詳細なエラーメッセージはありません"
                
            logging.error(f"トークン取得に失敗: HTTP {response.status_code} - {error_detail}")
            
            # 401エラーの場合、クライアントシークレットの問題の可能性が高いためより詳細な情報を提供
            if response.status_code == 401:
                logging.error("認証エラー (401): クライアントシークレットが無効である可能性があります。")
                logging.error("- クライアントシークレットの値が正しいことを確認してください")
                logging.error("- シークレットがAzureポータルで有効になっていることを確認してください")
                logging.error("- シークレット値がクリップボードから正しくコピーされていることを確認してください")
                raise Exception(f"Azure AD認証に失敗しました: クライアントシークレットが無効です。詳細: {error_detail}")
            else:
                raise Exception(f"認証エラー (HTTP {response.status_code}): {error_detail}")
    except requests.exceptions.RequestException as e:
        logging.error(f"トークンリクエスト中にネットワークエラー: {str(e)}")
        raise Exception(f"Azure ADへの接続に失敗しました: {str(e)}")
    except Exception as e:
        logging.error(f"トークン取得中に予期せぬエラー: {str(e)}")
        raise Exception(f"認証処理中にエラーが発生しました: {str(e)}")


def get_azure_token(tenant_id, client_id, client_secret):
    """元のトークン取得関数（互換性のために維持）"""
    return get_azure_token_improved(tenant_id, client_id, client_secret)


def find_existing_resource_group(subscription_id, token):
    """
    既存のkouchou-ai関連のリソースグループを検索して再利用する
    
    Args:
        subscription_id: Azureサブスクリプション ID
        token: Azureアクセストークン
        
    Returns:
        既存のリソースグループ名（見つからなければNone）
    """
    url = f"https://management.azure.com/subscriptions/{subscription_id}/resourcegroups?api-version=2021-04-01"
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    try:
        logging.info(f"既存のリソースグループを検索中...")
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            groups = response.json().get('value', [])
            # kouchou-aiで始まるリソースグループを探す
            kouchou_groups = [
                group for group in groups 
                if 'name' in group and group['name'].startswith('kouchou-ai-')
            ]
            
            # 最新のものを選択（名前に日付が含まれていると仮定）
            if kouchou_groups:
                # 名前でソート（降順）
                kouchou_groups.sort(key=lambda x: x['name'], reverse=True)
                selected_group = kouchou_groups[0]['name']
                logging.info(f"既存のリソースグループを再利用します: {selected_group}")
                return selected_group
            
            logging.info("既存のkouchou-ai関連リソースグループは見つかりませんでした")
            return None
        else:
            logging.warning(f"リソースグループ一覧の取得に失敗: HTTP {response.status_code}")
            return None
    except Exception as e:
        logging.warning(f"既存リソースグループの検索中にエラー: {str(e)}")
        return None


def find_existing_resources(subscription_id, token):
    """
    既存のkouchou-ai関連のリソース（ストレージアカウント、ACR）を検索して再利用する
    
    Args:
        subscription_id: Azureサブスクリプション ID
        token: Azureアクセストークン
        
    Returns:
        既存のリソース情報の辞書
    """
    resources = {
        "storage_account": None,
        "acr_name": None
    }
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    try:
        # 1. リソースグループの一覧を取得
        logging.info("既存のリソースグループを検索中...")
        groups_url = f"https://management.azure.com/subscriptions/{subscription_id}/resourcegroups?api-version=2021-04-01"
        groups_response = requests.get(groups_url, headers=headers, timeout=30)
        
        if groups_response.status_code != 200:
            logging.warning(f"リソースグループ一覧の取得に失敗: HTTP {groups_response.status_code}")
            return resources
            
        groups = groups_response.json().get('value', [])
        kouchou_groups = [
            group for group in groups 
            if 'name' in group and group['name'].startswith('kouchou-ai-')
        ]
        
        if not kouchou_groups:
            logging.info("kouchou-ai関連のリソースグループが見つかりませんでした")
            return resources
            
        # 最新のリソースグループを選択
        kouchou_groups.sort(key=lambda x: x['name'], reverse=True)
        target_group = kouchou_groups[0]['name']
        logging.info(f"検索対象のリソースグループ: {target_group}")
        
        # 2. 指定されたリソースグループ内のリソース一覧を取得
        resources_url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{target_group}/resources?api-version=2021-04-01"
        resources_response = requests.get(resources_url, headers=headers, timeout=30)
        
        if resources_response.status_code != 200:
            logging.warning(f"リソース一覧の取得に失敗: HTTP {resources_response.status_code}")
            return resources
            
        # 3. ストレージアカウントとACRをフィルタリング
        all_resources = resources_response.json().get('value', [])
        
        # ストレージアカウントの検索
        storage_accounts = [
            res for res in all_resources 
            if res.get('type') == 'Microsoft.Storage/storageAccounts' and 
            res.get('name', '').startswith('kouchouai')
        ]
        
        if storage_accounts:
            # 最新のストレージアカウントを使用
            storage_accounts.sort(key=lambda x: x.get('name', ''), reverse=True)
            resources['storage_account'] = storage_accounts[0].get('name')
            logging.info(f"既存のストレージアカウントを使用: {resources['storage_account']}")
        
        # ACRの検索
        acrs = [
            res for res in all_resources 
            if res.get('type') == 'Microsoft.ContainerRegistry/registries' and 
            res.get('name', '').startswith('kouchouacr')
        ]
        
        if acrs:
            # 最新のACRを使用
            acrs.sort(key=lambda x: x.get('name', ''), reverse=True)
            resources['acr_name'] = acrs[0].get('name')
            logging.info(f"既存のACRを使用: {resources['acr_name']}")
            
        return resources
    except Exception as e:
        logging.warning(f"既存リソースの検索中にエラー: {str(e)}")
        return resources


def create_resource_group(subscription_id, resource_group, location, token):
    """リソースグループを作成"""
    url = f"https://management.azure.com/subscriptions/{subscription_id}/resourcegroups/{resource_group}?api-version=2021-04-01"
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    payload = {
        'location': location
    }
    
    try:
        logging.info(f"リソースグループ作成APIを呼び出し中: {resource_group}")
        response = requests.put(url, headers=headers, json=payload, timeout=30)
        
        if response.status_code in [200, 201]:
            logging.info(f"リソースグループ {resource_group} の作成に成功しました (HTTP {response.status_code})")
            return response.json()
        elif response.status_code == 409:
            # 409はリソースグループが既に存在する場合
            logging.info(f"リソースグループ {resource_group} は既に存在します")
            return {"status": "exists", "name": resource_group}
        elif response.status_code == 403:
            # 403はアクセス権限がない場合
            error_detail = "不明なエラー"
            try:
                error_data = response.json()
                if 'error' in error_data and 'message' in error_data['error']:
                    error_detail = error_data['error']['message']
            except:
                error_detail = response.text[:200] if response.text else "詳細なエラーメッセージがありません"
            
            logging.error(f"リソースグループ作成に権限エラー: HTTP 403 - {error_detail}")
            
            # リソースグループが既に存在するか確認
            check_url = f"https://management.azure.com/subscriptions/{subscription_id}/resourcegroups/{resource_group}?api-version=2021-04-01"
            check_response = requests.get(check_url, headers=headers)
            
            if check_response.status_code == 200:
                # リソースグループは存在するが、作成権限がない（おそらく他のユーザーが作成した）
                logging.info(f"リソースグループ {resource_group} は既に存在します。既存のリソースグループを使用します。")
                return {"status": "exists", "name": resource_group}
            else:
                # リソースグループを作成する権限がなく、リソースグループも存在しない
                raise Exception(f"アクセス権限エラー: リソースグループを作成する権限がありません。Azure管理者に問い合わせてください。詳細: {error_detail}")
        else:
            error_detail = response.text
            try:
                error_data = response.json()
                if 'error' in error_data and 'message' in error_data['error']:
                    error_detail = error_data['error']['message']
            except:
                pass
            
            logging.error(f"リソースグループ作成に失敗: HTTP {response.status_code} - {error_detail}")
            raise Exception(f"リソースグループ作成に失敗 (HTTP {response.status_code}): {error_detail}")
    except requests.exceptions.RequestException as e:
        logging.error(f"リソースグループ作成中にネットワークエラー: {str(e)}")
        raise Exception(f"Azure APIへの接続に失敗しました: {str(e)}")
    except Exception as e:
        logging.error(f"リソースグループ作成中にエラー: {str(e)}")
        raise


def create_storage_account(subscription_id, resource_group, storage_account, location, token):
    """ストレージアカウントを作成 (事前確認付き)"""
    # 最初に存在確認を行い、既に存在する場合は早期リターン
    check_url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Storage/storageAccounts/{storage_account}?api-version=2021-04-01"
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    try:
        logging.info(f"ストレージアカウント {storage_account} の存在を確認中...")
        check_response = requests.get(check_url, headers=headers, timeout=10)
        
        if check_response.status_code == 200:
            logging.info(f"ストレージアカウント {storage_account} は既に存在します。既存のリソースを使用します。")
            return True
    except Exception as e:
        logging.warning(f"事前確認中にエラーが発生しました: {str(e)}。アカウント作成を試みます。")
    
    # 存在しない場合は作成処理に進む
    url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Storage/storageAccounts/{storage_account}?api-version=2021-04-01"
    payload = {
        'location': location,
        'sku': {
            'name': 'Standard_LRS'
        },
        'kind': 'StorageV2',
        'properties': {
            'allowBlobPublicAccess': False,
            'minimumTlsVersion': 'TLS1_2'
        }
    }
    
    try:
        logging.info(f"ストレージアカウント {storage_account} を作成中...")
        response = requests.put(url, headers=headers, json=payload, timeout=30)
        
        if response.status_code in [200, 201, 202]:
            logging.info(f"ストレージアカウント {storage_account} の作成要求が受け付けられました")
            
            # ストレージアカウントの作成を待機（短縮：10秒）
            logging.info("作成完了を確認中...")
            time.sleep(10)
            
            # 存在確認
            check_response = requests.get(check_url, headers=headers)
            
            if check_response.status_code == 200:
                logging.info(f"ストレージアカウント {storage_account} が正常に作成されました")
                return True
            else:
                logging.warning(f"ストレージアカウントの確認に失敗: HTTP {check_response.status_code}")
                return True  # 続行
        # 409はストレージアカウントが既に存在する場合
        elif response.status_code == 409:
            logging.info(f"ストレージアカウント {storage_account} は既に存在します")
            return True
        else:
            error_detail = "不明なエラー"
            try:
                error_data = response.json()
                if 'error' in error_data and 'message' in error_data['error']:
                    error_detail = error_data['error']['message']
            except:
                error_detail = response.text[:200] if response.text else "詳細なエラー情報がありません"
            
            logging.error(f"ストレージアカウント作成に失敗: HTTP {response.status_code} - {error_detail}")
            raise Exception(f"ストレージアカウント作成に失敗: {error_detail}")
    except requests.exceptions.RequestException as e:
        logging.error(f"ネットワークエラー: {str(e)}")
        raise Exception(f"Azure APIへの接続に失敗しました: {str(e)}")
    except Exception as e:
        logging.error(f"ストレージアカウント作成中にエラー: {str(e)}")
        raise


def create_storage_container(subscription_id, resource_group, storage_account, container_name, token):
    """ストレージコンテナを作成"""
    # まずストレージアカウントのキーを取得
    keys_url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Storage/storageAccounts/{storage_account}/listKeys?api-version=2021-04-01"
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    try:
        # キーの取得
        logging.info(f"ストレージアカウントキーを取得中: {storage_account}")
        keys_response = requests.post(keys_url, headers=headers, timeout=30)
        
        if keys_response.status_code != 200:
            logging.error(f"ストレージキーの取得に失敗: HTTP {keys_response.status_code} - {keys_response.text}")
            raise Exception(f"ストレージキー取得に失敗 (HTTP {keys_response.status_code})")
        
        try:
            keys_data = keys_response.json()
            if 'keys' in keys_data and len(keys_data['keys']) > 0:
                key = keys_data['keys'][0]['value']
                logging.info(f"ストレージアカウントキー取得成功")
            else:
                logging.error("ストレージキーが見つかりません")
                raise Exception("ストレージキーの形式が正しくありません")
        except Exception as parse_error:
            logging.error(f"キー情報のパースに失敗: {str(parse_error)}")
            raise Exception(f"ストレージキー情報の解析に失敗しました: {str(parse_error)}")
        
        # Azure Storage REST APIを使用してコンテナを作成（より単純化した方法）
        # 直接管理APIを使用する方法に変更
        container_api_url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Storage/storageAccounts/{storage_account}/blobServices/default/containers/{container_name}?api-version=2021-04-01"
        
        container_payload = {
            "properties": {
                "publicAccess": "None"
            }
        }
        
        logging.info(f"ストレージコンテナ作成APIを呼び出し中: {container_name}")
        container_response = requests.put(container_api_url, headers=headers, json=container_payload, timeout=30)
        
        if container_response.status_code in [200, 201, 202]:
            logging.info(f"ストレージコンテナ {container_name} の作成に成功しました")
            return True
        elif container_response.status_code == 409:
            logging.info(f"ストレージコンテナ {container_name} は既に存在します")
            return True
        else:
            error_detail = container_response.text
            try:
                error_data = container_response.json()
                if 'error' in error_data and 'message' in error_data['error']:
                    error_detail = error_data['error']['message']
            except:
                pass
                
            logging.error(f"コンテナ作成に失敗: HTTP {container_response.status_code} - {error_detail}")
            raise Exception(f"ストレージコンテナ作成に失敗 (HTTP {container_response.status_code}): {error_detail}")
            
    except Exception as e:
        logging.error(f"ストレージコンテナ作成中にエラー: {str(e)}")
        raise


def create_acr(subscription_id, resource_group, acr_name, location, sku, token):
    """
    Azure Container Registry (ACR) を作成する（改善版）
    
    Args:
        subscription_id: Azureサブスクリプション ID
        resource_group: リソースグループ名
        acr_name: ACRの名前
        location: リージョン（例：'japaneast'）
        sku: ACRのSKU（例：'Basic'）
        token: Azureアクセストークン
        
    Returns:
        作成されたACRの情報（辞書）
    """
    # まず存在確認
    acr_info = check_acr_exists(subscription_id, resource_group, acr_name, token)
    if acr_info:
        logging.info(f"既存のACR {acr_name} を使用します")
        return acr_info
        
    # 存在しない場合は作成
    url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.ContainerRegistry/registries/{acr_name}?api-version=2023-07-01"
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    
    # ACR作成用のペイロード（adminUserEnabledを確実にTrueに設定）
    payload = {
        'location': location,
        'sku': {'name': sku},
        'properties': {
            'adminUserEnabled': True,
            'policies': {
                'quarantinePolicy': {'status': 'disabled'},
                'trustPolicy': {'status': 'disabled'},
                'retentionPolicy': {'status': 'disabled'}
            }
        }
    }
    
    try:
        logging.info(f"ACR {acr_name} を作成中...")
        # タイムアウトを少し長めに設定（60秒→90秒）
        response = requests.put(url, headers=headers, json=payload, timeout=90)
        
        # レスポンスの詳細をログに記録
        logging.info(f"ACR作成APIからのHTTPステータス: {response.status_code}")
        logging.info(f"ACR作成APIからのレスポンスヘッダー: {response.headers}")
        
        try:
            response_body = response.json()
            logging.info(f"ACR作成APIからのレスポンス本文（一部）: {json.dumps(response_body)[:300]}...")
        except:
            logging.info(f"ACR作成APIからのレスポンス本文: {response.text[:300]}")
        
        if response.status_code in [200, 201, 202]:
            logging.info(f"ACR {acr_name} の作成リクエストを送信しました。作成完了を待機中...")
            
            # 作成完了までの待機時間を延長（30秒→60秒）
            logging.info("60秒間待機します...")
            time.sleep(60)
            
            # 作成されたACRの情報を取得
            acr_verify_attempts = 3
            for attempt in range(acr_verify_attempts):
                acr_info = check_acr_exists(subscription_id, resource_group, acr_name, token)
                if acr_info:
                    logging.info(f"確認試行 {attempt+1}/{acr_verify_attempts}: ACR {acr_name} の作成を確認しました")
                    
                    # プロビジョニング状態を確認
                    provisioning_state = acr_info.get('properties', {}).get('provisioningState', '')
                    logging.info(f"ACR {acr_name} のプロビジョニング状態: {provisioning_state}")
                    
                    if provisioning_state == 'Succeeded':
                        logging.info(f"ACR {acr_name} が正常に作成されました")
                        return acr_info
                    elif provisioning_state in ['Failed', 'Canceled']:
                        logging.error(f"ACR {acr_name} の作成に失敗しました: {provisioning_state}")
                        raise Exception(f"ACR {acr_name} の作成に失敗しました: {provisioning_state}")
                    else:
                        # まだプロビジョニング中の場合は少し待機
                        if attempt < acr_verify_attempts - 1:
                            logging.info(f"ACR {acr_name} はまだプロビジョニング中です ({provisioning_state})。20秒間待機します...")
                            time.sleep(20)
                else:
                    if attempt < acr_verify_attempts - 1:
                        logging.warning(f"確認試行 {attempt+1}/{acr_verify_attempts}: ACR {acr_name} が見つかりません。20秒間待機して再確認します...")
                        time.sleep(20)
            
            # 複数回の確認試行後も情報が取得できない場合
            logging.warning(f"ACR {acr_name} 作成後の情報取得に失敗。デフォルト情報を返します")
            return {"name": acr_name, "properties": {"loginServer": f"{acr_name}.azurecr.io"}}
            
        elif response.status_code == 409:
            logging.info(f"ACR {acr_name} は既に存在します")
            # 既存のACR情報を再度取得
            acr_info = check_acr_exists(subscription_id, resource_group, acr_name, token)
            return acr_info if acr_info else {"name": acr_name, "properties": {"loginServer": f"{acr_name}.azurecr.io"}}
        else:
            # エラー時の詳細情報を取得
            error_detail = "不明なエラー"
            try:
                error_data = response.json()
                if 'error' in error_data:
                    if 'message' in error_data['error']:
                        error_detail = error_data['error']['message']
                    if 'details' in error_data['error']:
                        error_details = [d.get('message', '') for d in error_data['error']['details']]
                        if error_details:
                            error_detail += f" - 詳細: {'; '.join(error_details)}"
            except:
                error_detail = response.text[:500] if response.text else "詳細情報なし"
                
            error_msg = f"ACR作成に失敗: HTTP {response.status_code} - {error_detail}"
            logging.error(error_msg)
            
            # 命名規則エラーをチェック
            if "registry name invalid" in error_detail.lower() or "not available" in error_detail.lower():
                # ACR名の変更を試みる（タイムスタンプ + ランダム文字列を追加）
                import random
                import string
                random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
                new_acr_name = f"kouchouacr{datetime.now().strftime('%y%m%d%H')}{random_suffix}".lower()
                logging.info(f"ACR名が無効または使用できません。新しい名前で再試行: {new_acr_name}")
                return create_acr(subscription_id, resource_group, new_acr_name, location, sku, token)
            
            raise Exception(f"ACR作成に失敗: {error_detail}")
    except requests.exceptions.RequestException as e:
        logging.error(f"ACR作成中にネットワークエラー: {str(e)}")
        raise Exception(f"ACR作成中にネットワークエラー: {str(e)}")
    except Exception as e:
        logging.error(f"ACR作成中に予期せぬエラー: {str(e)}")
        raise Exception(f"ACR作成中にエラーが発生しました: {str(e)}")


def assign_acr_permissions(subscription_id, resource_group, acr_name, token):
    """ACRへのアクセス権限を設定（より堅牢なバージョン）"""
    # ACRのリソースIDを取得するためのURL
    url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.ContainerRegistry/registries/{acr_name}?api-version=2023-07-01"
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    try:
        logging.info(f"ACR {acr_name} の存在を確認中...")
        
        # まずACRの存在を確認（最大3回リトライ）
        max_retries = 3
        wait_time = 10  # 秒
        acr_exists = False
        acr_info = None
        
        for attempt in range(max_retries):
            logging.info(f"ACR確認の試行 {attempt+1}/{max_retries}...")
            acr_response = requests.get(url, headers=headers, timeout=30)
            
            if acr_response.status_code == 200:
                acr_exists = True
                acr_info = acr_response.json()
                provisioning_state = acr_info.get('properties', {}).get('provisioningState', '')
                logging.info(f"ACR {acr_name} が見つかりました。状態: {provisioning_state}")
                
                if provisioning_state == 'Succeeded':
                    break  # 正常な状態のACRが見つかった
                elif attempt < max_retries:
                    logging.warning(f"ACRが作成途中です ({provisioning_state})。{wait_time}秒待機して再確認します...")
                    time.sleep(wait_time)
            elif acr_response.status_code == 404:
                if attempt < max_retries:
                    logging.warning(f"ACRが見つかりません。{wait_time}秒待機して再確認します...")
                    time.sleep(wait_time)
            else:
                logging.warning(f"ACRの情報取得に失敗: HTTP {acr_response.status_code}. {wait_time}秒待機して再確認します...")
                if attempt < max_retries:
                    time.sleep(wait_time)
        
        # 全てのリトライを試みてもACRが見つからない場合
        if not acr_exists:
            # ACRが本当に存在するか、リソースグループ内の全リソースをチェック
            resources_url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group}/resources?api-version=2021-04-01"
            resources_response = requests.get(resources_url, headers=headers, timeout=30)
            
            if resources_response.status_code == 200:
                resources = resources_response.json().get('value', [])
                acr_resources = [r for r in resources if r.get('type') == 'Microsoft.ContainerRegistry/registries']
                
                if acr_resources:
                    # ACRが見つかった場合
                    found_acr = acr_resources[0]
                    found_acr_name = found_acr.get('name')
                    logging.warning(f"指定されたACR名 {acr_name} は見つかりませんでしたが、リソースグループ内に別のACR {found_acr_name} が見つかりました。")
                    
                    if found_acr_name and found_acr_name != acr_name:
                        logging.info(f"代わりにACR {found_acr_name} の権限設定を試みます...")
                        acr_name = found_acr_name
                        url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.ContainerRegistry/registries/{acr_name}?api-version=2023-07-01"
                        acr_response = requests.get(url, headers=headers, timeout=30)
                        if acr_response.status_code == 200:
                            acr_exists = True
                            acr_info = acr_response.json()
                    else:
                        logging.error(f"リソースグループ内にACRリソースは見つかりましたが、詳細情報を取得できませんでした。")
                else:
                    logging.error(f"リソースグループ内にACRが見つかりません。デプロイに失敗した可能性があります。")
            else:
                logging.error(f"リソースグループ内のリソース一覧の取得に失敗: HTTP {resources_response.status_code}")
            
            # それでもACRが見つからなければエラー
            if not acr_exists:
                raise Exception(f"ACR {acr_name} が見つかりません。まずACRを作成してください。")
        
        logging.info(f"ACR {acr_name} が見つかりました。ACR設定を行います...")
        
        # ACRの管理者アカウントを有効化
        admin_url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.ContainerRegistry/registries/{acr_name}?api-version=2023-07-01"
        admin_payload = {
            "properties": {
                "adminUserEnabled": True,
                "policies": {
                    "quarantinePolicy": {
                        "status": "disabled"
                    },
                    "trustPolicy": {
                        "status": "disabled"
                    },
                    "retentionPolicy": {
                        "status": "disabled"
                    },
                    "taskRunStatus": {
                        "status": "enabled"  # ACR Tasksの状態管理を有効化
                    }
                }
            }
        }
        
        logging.info(f"ACR {acr_name} の管理者アカウントを有効化中...")
        admin_response = requests.patch(admin_url, headers=headers, json=admin_payload)
        
        if admin_response.status_code not in [200, 201, 202]:
            logging.error(f"ACR管理者アカウントの有効化に失敗: HTTP {admin_response.status_code}")
            logging.error(f"応答内容: {admin_response.text}")
            raise Exception(f"ACR管理者アカウントの有効化に失敗: HTTP {admin_response.status_code}")
        
        logging.info(f"ACR {acr_name} の管理者アカウントを有効化しました")
        logging.info(f"注意: ACR Tasksの使用には適切な権限が必要です。Azure Portalで権限設定を確認してください。")
        
        return True
        
    except Exception as e:
        logging.error(f"ACR {acr_name} への権限付与中にエラー: {str(e)}")
        raise Exception(f"ACR {acr_name} へのアクセス権限設定に失敗しました: {str(e)}")


def get_container_app_url(subscription_id, resource_group, app_name, token):
    """
    Container AppのURLを取得する
    
    Args:
        subscription_id: Azureサブスクリプション ID
        resource_group: リソースグループ名
        app_name: コンテナアプリの名前
        token: Azureアクセストークン
        
    Returns:
        URL（取得できなかった場合は空文字列）
    """
    import requests
    import logging
    import time
    
    app_url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.App/containerApps/{app_name}?api-version=2023-05-01"
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    logging.info(f"コンテナアプリのURL情報を取得中: {app_name}")
    
    # 複数回リトライ
    max_retries = 5
    for retry in range(max_retries):
        try:
            app_get = requests.get(app_url, headers=headers)
            
            if app_get.status_code == 200:
                app_details = app_get.json()
                
                # まず設定からFQDNを取得
                app_fqdn = app_details.get('properties', {}).get('configuration', {}).get('ingress', {}).get('fqdn', '')
                if app_fqdn:
                    url = f"https://{app_fqdn}"
                    logging.info(f"コンテナアプリのURL取得成功: {url}")
                    return url
                
                # FQDNが取得できなかった場合は、latestRevisionのステータスから取得を試みる
                latest_revision = app_details.get('properties', {}).get('latestRevisionName', '')
                if latest_revision:
                    logging.info(f"最新リビジョン名: {latest_revision}")
                    
                    # リビジョンの詳細を取得
                    revision_url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.App/containerApps/{app_name}/revisions/{latest_revision}?api-version=2023-05-01"
                    revision_response = requests.get(revision_url, headers=headers)
                    
                    if revision_response.status_code == 200:
                        revision_data = revision_response.json()
                        rev_fqdn = revision_data.get('properties', {}).get('fqdn', '')
                        
                        if rev_fqdn:
                            url = f"https://{rev_fqdn}"
                            logging.info(f"リビジョンからURL取得成功: {url}")
                            return url
            
            logging.warning(f"URLの取得に失敗しました ({retry+1}/{max_retries})。再試行します...")
            time.sleep(10)  # 待機してから再試行
            
        except Exception as e:
            logging.error(f"URL取得中にエラー ({retry+1}/{max_retries}): {str(e)}")
            time.sleep(10)
    
    # 失敗した場合はデフォルトのURLを返す
    default_url = f"https://{app_name}.azurecontainerapps.io"
    logging.warning(f"URL取得に失敗しました。デフォルトのURLを使用します: {default_url}")
    return default_url


def deploy_to_container_apps(subscription_id, resource_group, app_name, location, image_name, acr_name, acr_login_server, token, env_vars, port):
    """
    Azure Container Appsにコンテナをデプロイする
    
    Args:
        subscription_id: Azureサブスクリプション ID
        resource_group: リソースグループ名
        app_name: コンテナアプリの名前
        location: リージョン（例：'japaneast'）
        image_name: コンテナイメージ名（例：'acr.azurecr.io/image:tag'）
        acr_name: ACRの名前
        acr_login_server: ACRのログインサーバーURL
        token: Azureアクセストークン
        env_vars: 環境変数の辞書
        port: コンテナの公開ポート
        
    Returns:
        デプロイ結果の辞書
    """
    import requests
    import logging
    import time
    import json
    import traceback
    
    # コンテナアプリ環境の名前を設定
    env_name = "kouchou-ai-env"  # 変数が見つからないためハードコード
    
    # 1. ACRの管理者資格情報を取得
    logging.info(f"ACR {acr_name} の管理者資格情報を取得中...")
    acr_creds_url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.ContainerRegistry/registries/{acr_name}/listCredentials?api-version=2023-07-01"
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    try:
        acr_creds_response = requests.post(acr_creds_url, headers=headers)
        
        if acr_creds_response.status_code != 200:
            logging.error(f"ACR資格情報の取得に失敗: HTTP {acr_creds_response.status_code}")
            logging.error(f"応答内容: {acr_creds_response.text}")
            raise Exception(f"ACR資格情報の取得に失敗 (HTTP {acr_creds_response.status_code}): {acr_creds_response.text}")
        
        acr_creds = acr_creds_response.json()
        acr_username = acr_creds.get('username')
        acr_password = None
        
        if 'passwords' in acr_creds and len(acr_creds['passwords']) > 0:
            acr_password = acr_creds['passwords'][0].get('value')
            
        if not acr_username or not acr_password:
            logging.error("ACR資格情報が正しく取得できませんでした")
            logging.error(f"ACR応答: {json.dumps(acr_creds)}")
            raise Exception("ACR資格情報が不完全です")
            
        logging.info(f"ACR資格情報の取得に成功: {acr_username}")
        
        # ACRイメージの存在確認
        image_parts = image_name.split('/')[-1].split(':')
        repo_name = image_parts[0]
        tag = image_parts[1] if len(image_parts) > 1 else "latest"
        
        logging.info(f"ACRからイメージの確認: {repo_name}:{tag}")
        
        # リポジトリとタグの存在確認（REST API経由）
        # ACRにイメージが存在するかをより正確に確認
        repo_check_url = f"https://{acr_login_server}/v2/{repo_name}/manifests/latest"
        tags_check_url = f"https://{acr_login_server}/v2/{repo_name}/tags/list"
        image_exists = False
        
        try:
            # まずリポジトリが存在するか確認
            repo_auth = requests.auth.HTTPBasicAuth(acr_username, acr_password)
            repo_url = f"https://{acr_login_server}/v2/_catalog"
            repo_response = requests.get(repo_url, auth=repo_auth)
            
            if repo_response.status_code == 200:
                repos = repo_response.json().get('repositories', [])
                if repo_name not in repos:
                    logging.warning(f"リポジトリ {repo_name} はACRに存在しません")
                    logging.info(f"利用可能なリポジトリ: {repos}")
                else:
                    # リポジトリが存在する場合、タグを確認
                    tags_url = f"https://{acr_login_server}/v2/{repo_name}/tags/list"
                    tags_response = requests.get(tags_url, auth=repo_auth)
                    
                    if tags_response.status_code == 200:
                        available_tags = tags_response.json().get('tags', [])
                        if tag in available_tags:
                            logging.info(f"イメージ {repo_name}:{tag} はACRに存在します")
                            image_exists = True
                        else:
                            logging.warning(f"タグ {tag} はリポジトリ {repo_name} に存在しません")
                            logging.info(f"利用可能なタグ: {available_tags}")
            else:
                logging.warning(f"ACRリポジトリの確認に失敗: HTTP {repo_response.status_code}")
        except Exception as e:
            logging.warning(f"ACRイメージの確認中にエラー: {str(e)}")
        
        # イメージが存在しない場合、ビルド完了を待機
        if not image_exists:
            logging.info(f"イメージ {repo_name}:{tag} が見つかりません。ビルド完了を待機します...")
            
            # タスクランの一覧を取得してビルド状態を確認
            wait_timeout = 180  # 5分から3分に短縮
            wait_interval = 20  # 30秒から20秒に短縮
            start_wait_time = time.time()
            image_ready = False
            
            while time.time() - start_wait_time < wait_timeout:
                # タスクランの一覧を取得
                task_runs_url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.ContainerRegistry/registries/{acr_name}/taskRuns?api-version=2019-06-01-preview"
                task_response = requests.get(task_runs_url, headers=headers)
                
                if task_response.status_code == 200:
                    tasks = task_response.json().get('value', [])
                    # 最新のタスクから状態を確認
                    for task in tasks:
                        properties = task.get('properties', {})
                        task_status = properties.get('status', '')
                        task_image = None
                        for image in properties.get('imageNames', []):
                            if repo_name in image:
                                task_image = image
                                break
                        
                        if task_image and task_status == 'Succeeded':
                            logging.info(f"イメージビルドが完了しました: {task_image}")
                            image_ready = True
                            break
                    
                    if image_ready:
                        break
                
                # イメージの存在を直接確認
                repo_check_response = requests.head(repo_check_url, auth=repo_auth)
                if repo_check_response.status_code == 200:
                    tags_check_response = requests.head(tags_check_url, auth=repo_auth)
                    if tags_check_response.status_code == 200:
                        logging.info(f"イメージ {repo_name}:{tag} が見つかりました")
                        image_ready = True
                        break
                
                logging.info(f"イメージ {repo_name}:{tag} のビルド完了を待機中... (残り時間: 約{int((wait_timeout - (time.time() - start_wait_time))/60)}分)")
                time.sleep(wait_interval)
            
            if not image_ready:
                warning_msg = f"イメージ {repo_name}:{tag} のビルド完了待機がタイムアウトしました。デプロイを続行します。"
                logging.warning(warning_msg)
        
        # 2. Container Apps環境の確認と作成
        env_url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.App/managedEnvironments/{env_name}?api-version=2023-05-01"

        logging.info(f"コンテナアプリ環境の確認: {env_name}")
        env_check = requests.get(env_url, headers=headers)

        if env_check.status_code == 404:
            logging.info(f"コンテナアプリ環境を作成: {env_name}")
            
            # まずLog Analytics Workspaceを作成または既存のものを検索
            workspace_name = f"kouchou-ai-logs-{resource_group[-8:]}"  # リソースグループ名の末尾を使用
            workspace_url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.OperationalInsights/workspaces/{workspace_name}?api-version=2021-06-01"
            
            # Log Analytics Workspaceの存在確認
            workspace_check = requests.get(workspace_url, headers=headers)
            workspace_id = None
            
            if workspace_check.status_code == 404:
                # Log Analytics Workspaceが存在しない場合は作成
                logging.info(f"Log Analytics Workspace {workspace_name} を作成中...")
                
                workspace_payload = {
                    "location": location,
                    "properties": {
                        "sku": {
                            "name": "PerGB2018"
                        },
                        "retentionInDays": 30
                    }
                }
                
                workspace_response = requests.put(workspace_url, headers=headers, json=workspace_payload)
                
                if workspace_response.status_code in [200, 201, 202]:
                    workspace_data = workspace_response.json()
                    workspace_id = workspace_data.get('id')
                    logging.info(f"Log Analytics Workspace {workspace_name} を作成しました")
                else:
                    logging.error(f"Log Analytics Workspace の作成に失敗: HTTP {workspace_response.status_code}")
                    logging.error(f"応答内容: {workspace_response.text}")
                    # エラーでもデプロイを継続するため、例外は投げない
                    
                    # 既存のワークスペースを探す
                    workspaces_url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.OperationalInsights/workspaces?api-version=2021-06-01"
                    workspaces_response = requests.get(workspaces_url, headers=headers)
                    
                    if workspaces_response.status_code == 200:
                        workspaces = workspaces_response.json().get('value', [])
                        if workspaces:
                            workspace_id = workspaces[0].get('id')
                            logging.info(f"既存のLog Analytics Workspace {workspaces[0].get('name')} を使用します")
            else:
                workspace_data = workspace_check.json()
                workspace_id = workspace_data.get('id')
                logging.info(f"既存のLog Analytics Workspace {workspace_name} を使用します")
            
            # 環境の作成 (Log Analytics ID が取得できた場合のみ設定)
            env_payload = {
                "location": location,
                "properties": {}
            }
            
            # Log Analytics IDが取得できた場合、設定を追加
            if workspace_id:
                env_payload["properties"]["appLogsConfiguration"] = {
                    "destination": "log-analytics",
                    "logAnalyticsConfiguration": {
                        "customerId": workspace_id.split('/')[-1],  # workspaceIdを抽出
                        "sharedKey": ""  # 空文字列を設定（Azureがシステム管理キーを使用）
                    }
                }
            else:
                # workspaceIdが取得できない場合はログ設定を省略
                logging.warning("Log Analytics Workspaceのリソース情報が取得できないため、ログ設定なしで環境を作成します")
            
            env_create = requests.put(env_url, headers=headers, json=env_payload)
            
            if env_create.status_code not in [200, 201, 202]:
                logging.error(f"コンテナアプリ環境の作成に失敗: HTTP {env_create.status_code}")
                logging.error(f"応答内容: {env_create.text}")
                
                # フォールバック: ログ設定を完全に省略して再試行
                logging.info("フォールバック: ログ設定なしで環境作成を再試行します")
                simple_env_payload = {
                    "location": location,
                    "properties": {}
                }
                
                env_create_retry = requests.put(env_url, headers=headers, json=simple_env_payload)
                
                if env_create_retry.status_code not in [200, 201, 202]:
                    # エラーレスポンスの詳細な解析
                    error_detail = "詳細情報なし"
                    try:
                        error_data = env_create_retry.json()
                        if 'error' in error_data:
                            if 'message' in error_data['error']:
                                error_detail = error_data['error']['message']
                            if 'details' in error_data['error']:
                                error_details = [d.get('message', '') for d in error_data['error']['details']]
                                if error_details:
                                    error_detail += f" - 詳細: {'; '.join(error_details)}"
                            if 'code' in error_data['error']:
                                error_detail = f"エラーコード: {error_data['error']['code']} - {error_detail}"
                    except:
                        error_detail = env_create_retry.text[:500] if env_create_retry.text else "詳細情報なし"
                    
                    logging.error(f"コンテナアプリ環境の再作成に失敗: HTTP {env_create_retry.status_code}")
                    logging.error(f"エラー詳細: {error_detail}")
                    
                    # リソースプロバイダーの登録状態を確認
                    try:
                        provider_url = f"https://management.azure.com/subscriptions/{subscription_id}/providers/Microsoft.App?api-version=2023-05-01"
                        provider_response = requests.get(provider_url, headers=headers)
                        if provider_response.status_code == 200:
                            provider_data = provider_response.json()
                            registration_state = provider_data.get('registrationState', 'unknown')
                            logging.error(f"Microsoft.App プロバイダーの登録状態: {registration_state}")
                            if registration_state != 'Registered':
                                logging.error("Microsoft.App プロバイダーが登録されていない可能性があります。")
                    except Exception as provider_error:
                        logging.error(f"プロバイダー状態の確認中にエラー: {str(provider_error)}")
                    
                    raise Exception(f"コンテナアプリ環境の作成に失敗 (HTTP {env_create_retry.status_code}): {error_detail}")
                else:
                    env_result = env_create_retry.json()
                    logging.info(f"コンテナアプリ環境作成のリクエスト受付完了 (フォールバック方式): {env_name}")
            else:
                env_result = env_create.json()
                logging.info(f"コンテナアプリ環境作成のリクエスト受付完了: {env_name}")
            
            # 環境の作成を待機（通常は2-3分かかる）
            timeout = 300  # 5分
            start_time = time.time()
            env_ready = False
            
            while time.time() - start_time < timeout:
                logging.info("コンテナアプリ環境の作成を待機中...")
                time.sleep(30)
                
                env_status = requests.get(env_url, headers=headers)
                if env_status.status_code == 200:
                    env_data = env_status.json()
                    provisioning_state = env_data.get('properties', {}).get('provisioningState', '')
                    
                    logging.info(f"環境の状態: {provisioning_state}")
                    
                    if provisioning_state == 'Succeeded':
                        env_ready = True
                        break
                    elif provisioning_state in ['Failed', 'Canceled']:
                        logging.error(f"環境作成に失敗: {provisioning_state}")
                        raise Exception(f"コンテナアプリ環境の作成に失敗: {provisioning_state}")
                
                if not env_ready:
                    logging.warning("環境作成のタイムアウト。続行を試みます...")
        else:
            logging.info(f"既存のコンテナアプリ環境を使用します: {env_name}")
        
        # 3. コンテナアプリの作成
        app_url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.App/containerApps/{app_name}?api-version=2023-05-01"
        
        # 環境変数のフォーマット変換
        formatted_env_vars = []
        for key, value in env_vars.items():
            formatted_env_vars.append({
                "name": key,
                "value": str(value)
            })
        
        # イメージの取得のためのレジストリ資格情報を追加
        registry_creds = [{
            "server": acr_login_server,
            "username": acr_username,
            "passwordSecretRef": "acr-password"
        }]
        
        # アプリの設定 - デプロイ失敗の問題を修正するための変更
        app_payload = {
            "location": location,
            "properties": {
                "managedEnvironmentId": f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.App/managedEnvironments/{env_name}",
                "configuration": {
                    "ingress": {
                        "external": True,
                        "targetPort": port,
                        "allowInsecure": False,
                        "traffic": [
                            {
                                "latestRevision": True,
                                "weight": 100
                            }
                        ]
                    },
                    "registries": registry_creds,
                    "secrets": [
                        {
                            "name": "acr-password",
                            "value": acr_password
                        }
                    ]
                },
                "template": {
                    "containers": [
                        {
                            "name": app_name,
                            "image": image_name,
                            "env": formatted_env_vars,
                            "resources": {
                                "cpu": 0.5,
                                "memory": "1Gi"
                            },
                            "probes": [
                                {
                                    "type": "Startup",
                                    "httpGet": {
                                        "path": "/",
                                        "port": port,
                                        "scheme": "HTTP"
                                    },
                                    "initialDelaySeconds": 15,
                                    "periodSeconds": 15,
                                    "timeoutSeconds": 5,
                                    "failureThreshold": 10
                                },
                                {
                                    "type": "Liveness",
                                    "httpGet": {
                                        "path": "/",
                                        "port": port,
                                        "scheme": "HTTP"
                                    },
                                    "initialDelaySeconds": 30,
                                    "periodSeconds": 30,
                                    "timeoutSeconds": 5,
                                    "failureThreshold": 3
                                }
                            ]
                        }
                    ],
                    "scale": {
                        "minReplicas": 1,
                        "maxReplicas": 3
                    }
                }
            }
        }
        
        logging.info(f"コンテナアプリを作成/更新中: {app_name}")
        app_create = requests.put(app_url, headers=headers, json=app_payload)
        
        if app_create.status_code not in [200, 201, 202]:
            logging.error(f"コンテナアプリの作成/更新に失敗: HTTP {app_create.status_code}")
            logging.error(f"応答内容: {app_create.text}")
            
            # エラー応答を解析してより詳細な情報を提供
            error_detail = "不明なエラー"
            try:
                error_data = app_create.json()
                if 'error' in error_data and 'message' in error_data['error']:
                    error_detail = error_data['error']['message']
                    
                    # 一般的なエラーパターンのチェック
                    if "could not pull" in error_detail.lower() or "failed to pull" in error_detail.lower():
                        error_detail += " イメージのプルに失敗しました。イメージがACRに存在するか、ACR資格情報が正しいか確認してください。"
                    elif "exited with non-zero" in error_detail.lower():
                        error_detail += " コンテナが異常終了しました。環境変数や設定を確認してください。"
            except:
                error_detail = app_create.text[:500]
                
            raise Exception(f"コンテナアプリの作成/更新に失敗 (HTTP {app_create.status_code}): {error_detail}")
        
        app_result = app_create.json()
        logging.info(f"コンテナアプリの作成/更新要求が受け付けられました: {app_name}")
        
        # デプロイの完了を待機する
        max_retries = 30  # 最大30回まで試行
        retry_interval = 10  # 10秒間隔
        is_deployed = False
        
        for retry in range(max_retries):
            logging.info(f"コンテナアプリのデプロイ状態を確認中... ({retry+1}/{max_retries})")
            app_status_response = requests.get(app_url, headers=headers)
            
            if app_status_response.status_code == 200:
                app_status = app_status_response.json()
                provisioning_state = app_status.get('properties', {}).get('provisioningState', '')
                
                logging.info(f"アプリ状態: {provisioning_state}")
                
                if provisioning_state == 'Succeeded':
                    is_deployed = True
                    logging.info(f"アプリ {app_name} のデプロイが成功しました")
                    break
                elif provisioning_state == 'Failed':
                    # より詳細なエラー情報を収集
                    error_message = "詳細情報なし"
                    error_details = []
                    
                    # 1. アプリの詳細からエラー情報を取得
                    app_error = app_status.get('properties', {}).get('error', {})
                    if app_error:
                        app_error_message = app_error.get('message', '')
                        app_error_code = app_error.get('code', '')
                        app_error_target = app_error.get('target', '')
                        
                        if app_error_message:
                            error_message = app_error_message
                            error_details.append(f"アプリエラー: {app_error_message}")
                        if app_error_code:
                            error_details.append(f"エラーコード: {app_error_code}")
                        if app_error_target:
                            error_details.append(f"対象: {app_error_target}")
                    
                    # Azureログ全体の詳細を出力
                    logging.info("デプロイ失敗の詳細情報を解析:")
                    logging.info(json.dumps(app_status, indent=2)[:2000])  # 最初の2000文字だけログに出力
                    
                    # リビジョン情報のより詳細な取得
                    try:
                        latest_revision_name = app_status.get('properties', {}).get('latestRevisionName', '')
                        if latest_revision_name:
                            logging.info(f"失敗したリビジョン名: {latest_revision_name}")
                            # リビジョンの詳細情報を取得
                            revision_url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.App/containerApps/{app_name}/revisions/{latest_revision_name}?api-version=2023-05-01"
                            revision_response = requests.get(revision_url, headers=headers)
                            
                            if revision_response.status_code == 200:
                                revision_data = revision_response.json()
                                
                                # リビジョンのエラー情報を抽出
                                revision_error = revision_data.get('properties', {}).get('error', {})
                                if revision_error:
                                    revision_error_message = revision_error.get('message', '')
                                    if revision_error_message:
                                        error_details.append(f"リビジョンエラー: {revision_error_message}")
                                
                                # コンテナのステータス情報
                                containers = revision_data.get('properties', {}).get('containers', [])
                                for container in containers:
                                    container_name = container.get('name', 'unknown')
                                    container_image = container.get('image', 'unknown')
                                    container_state = container.get('properties', {}).get('state', 'unknown')
                                    container_reason = container.get('properties', {}).get('reason', '')
                                    container_message = container.get('properties', {}).get('message', '')
                                    
                                    container_info = f"コンテナ[{container_name}] イメージ: {container_image}, 状態: {container_state}"
                                    if container_reason:
                                        container_info += f", 理由: {container_reason}"
                                    if container_message:
                                        container_info += f", メッセージ: {container_message}"
                                    
                                    error_details.append(container_info)
                                    logging.info(container_info)
                                
                                # リビジョンログURLがあれば追加
                                log_url = revision_data.get('properties', {}).get('logsUrl', '')
                                if log_url:
                                    error_details.append(f"ログURL: {log_url}")
                                    logging.info(f"詳細ログURL: {log_url}")
                    except Exception as rev_error:
                        logging.error(f"リビジョン情報の取得中にエラー: {str(rev_error)}")
                        error_details.append(f"リビジョン情報取得エラー: {str(rev_error)}")

                    # すべての詳細を結合
                    if error_details:
                        error_details_text = "\n  - ".join([""] + error_details)
                        error_info = f"アプリ {app_name} のデプロイが失敗しました: 状態={provisioning_state}\n主なエラー: {error_message}{error_details_text}"
                    else:
                        error_info = f"アプリ {app_name} のデプロイが失敗しました: 状態={provisioning_state}\n主なエラー: {error_message}"
                    
                    logging.error(error_info)
                    raise Exception(error_info)
            
            time.sleep(retry_interval)
        
        if not is_deployed:
            logging.warning(f"アプリ {app_name} のデプロイ状態確認がタイムアウトしました。続行します。")
        
        # デプロイメントURL（FQDN）を取得
        app_fqdn = app_result.get('properties', {}).get('configuration', {}).get('ingress', {}).get('fqdn', '')
        app_url_with_protocol = f"https://{app_fqdn}" if app_fqdn else ""
        
        if not app_url_with_protocol:
            # FQDNが取得できない場合、アプリの詳細情報を取得
            time.sleep(10)  # 少し待機してからアプリ情報を取得
            
            app_get = requests.get(app_url, headers=headers)
            if app_get.status_code == 200:
                app_details = app_get.json()
                app_fqdn = app_details.get('properties', {}).get('configuration', {}).get('ingress', {}).get('fqdn', '')
                app_url_with_protocol = f"https://{app_fqdn}" if app_fqdn else ""
                
                if not app_url_with_protocol:
                    logging.warning(f"アプリのURLが取得できません: {app_name}")
                    app_url_with_protocol = f"https://{app_name}.azurecontainerapps.io"  # フォールバック
            else:
                logging.warning(f"アプリの詳細情報の取得に失敗: HTTP {app_get.status_code}")
                app_url_with_protocol = f"https://{app_name}.azurecontainerapps.io"  # フォールバック
        
        logging.info(f"コンテナアプリのURL: {app_url_with_protocol}")
        
        # 結果を返す
        return {
            "status": "success",
            "name": app_name,
            "url": {app_url_with_protocol},
            "resourceGroup": resource_group
        }
        
    except Exception as e:
        error_msg = str(e)
        tb = traceback.format_exc()
        logging.error(f"Container Appsへのデプロイ中にエラー: {error_msg}")
        logging.error(f"スタックトレース: {tb}")
        
        return {
            "status": "error",
            "name": app_name,
            "error": error_msg,
            "traceback": tb,
            "url": ""  # URLキーを追加（空文字列）
        }


def check_storage_account_exists(subscription_id, resource_group, storage_account, token):
    """
    ストレージアカウントが既に存在するか確認する関数
    
    Args:
        subscription_id: Azureサブスクリプション ID
        resource_group: リソースグループ名
        storage_account: ストレージアカウント名
        token: Azureアクセストークン
        
    Returns:
        bool: ストレージアカウントが存在する場合はTrue、存在しない場合はFalse
    """
    import requests
    import logging
    
    check_url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Storage/storageAccounts/{storage_account}?api-version=2021-04-01"
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    try:
        logging.info(f"ストレージアカウント {storage_account} の存在を確認中...")
        check_response = requests.get(check_url, headers=headers, timeout=30)
        
        if check_response.status_code == 200:
            logging.info(f"ストレージアカウント {storage_account} は既に存在します")
            return True
        elif check_response.status_code == 404:
            logging.info(f"ストレージアカウント {storage_account} は存在しません")
            return False
        else:
            logging.warning(f"ストレージアカウント確認中にエラー発生: HTTP {check_response.status_code}")
            # エラーが発生した場合は保守的にFalseを返す
            return False
    except Exception as e:
        logging.error(f"ストレージアカウント確認中に例外発生: {str(e)}")
        # 例外が発生した場合も保守的にFalseを返す
        return False


def check_acr_exists(subscription_id, resource_group, acr_name, token):
    """
    Azure Container Registry (ACR) が既に存在するか確認する関数
    
    Args:
        subscription_id: Azureサブスクリプション ID
        resource_group: リソースグループ名
        acr_name: ACRの名前
        token: Azureアクセストークン
        
    Returns:
        dict or None: ACRが存在する場合はACR情報の辞書、存在しない場合はNone
    """
    import requests
    import logging
    
    url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.ContainerRegistry/registries/{acr_name}?api-version=2023-07-01"
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    
    try:
        logging.info(f"ACR {acr_name} の存在を確認中...")
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            acr_info = response.json()
            logging.info(f"ACR {acr_name} は既に存在します")
            return acr_info
        elif response.status_code == 404:
            logging.info(f"ACR {acr_name} は存在しません")
            return None
        else:
            logging.warning(f"ACR確認中にエラー発生: HTTP {response.status_code}")
            # エラーが発生した場合は保守的にNoneを返す
            return None
    except Exception as e:
        logging.error(f"ACR確認中に例外発生: {str(e)}")
        # 例外が発生した場合も保守的にNoneを返す
        return None


def build_image_with_azure_sdk(subscription_id, resource_group, acr_name, 
                               source_dir_or_subdir, image_tag, git_repo_url, 
                               git_branch, client_id, client_secret, tenant_id):
    """
    Azure SDK for Python を使用してイメージをビルドする (バージョン非依存の実装)
    """
    import logging
    import time
    import json
    import sys
    from azure.identity import ClientSecretCredential
    from azure.mgmt.containerregistry import ContainerRegistryManagementClient
    from azure.core.exceptions import ResourceNotFoundError
    
    # 認証情報の作成
    try:
        credential = ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret
        )
        logging.info("Azure 認証情報を準備しました")
    except Exception as auth_error:
        logging.error(f"認証情報の作成に失敗: {str(auth_error)}")
        raise Exception(f"Azure SDK認証に失敗しました: {str(auth_error)}")
    
    # ACR管理クライアントの初期化
    try:
        acr_client = ContainerRegistryManagementClient(
            credential=credential,
            subscription_id=subscription_id
        )
        logging.info(f"ACR管理クライアントを初期化しました: {acr_name}")
    except Exception as client_error:
        logging.error(f"ACR管理クライアントの初期化に失敗: {str(client_error)}")
        raise Exception(f"ACRクライアント初期化エラー: {str(client_error)}")
    
    # 完全なイメージ名を構築
    acr_login_server = f"{acr_name}.azurecr.io"
    full_image_name = f"{acr_login_server}/{image_tag}"
    
    # Dockerfileパス
    dockerfile_path = f"{source_dir_or_subdir}/Dockerfile"
    
    try:
        # 単純なディクショナリを使って汎用的なAPIペイロードを構築
        build_request = {
            "location": "japaneast",
            "type": "Microsoft.ContainerRegistry/registries/runs",
            "is_archive_enabled": False,
            "source": {
                "type": "Git",
                "repository": git_repo_url,
                "branch": git_branch,
                "sourceControlType": "Github"
            },
            "platform": {
                "os": "Linux", 
                "architecture": "amd64"
            },
            "docker_file_path": dockerfile_path,
            "image_names": [full_image_name],
            "is_push_enabled": True,
            "timeout": 7200  # 2時間のタイムアウト
        }
        
        logging.info(f"イメージビルドを開始: {dockerfile_path} -> {full_image_name}")
        logging.info(f"ビルド設定: Git={git_repo_url}#{git_branch}, Dockerfile={dockerfile_path}")
        
        # ビルドリクエストの送信 - バージョン依存のメソッド呼び出しを回避
        try:
            # メソッドの存在確認と呼び出し
            if hasattr(acr_client.registries, 'begin_schedule_run'):
                logging.info("begin_schedule_run メソッドを使用します")
                build_poller = acr_client.registries.begin_schedule_run(
                    resource_group_name=resource_group,
                    registry_name=acr_name,
                    run_request=build_request
                )
            elif hasattr(acr_client.registries, 'schedule_run'):
                logging.info("schedule_run メソッドを使用します")
                build_poller = acr_client.registries.schedule_run(
                    resource_group_name=resource_group,
                    registry_name=acr_name,
                    run_request=build_request
                )
            else:
                raise AttributeError("ビルドを開始するためのAPIメソッドが見つかりませんでした")
                
            logging.info(f"ビルドリクエストを送信しました、結果を待機中...")
        except AttributeError as attr_error:
            logging.error(f"APIメソッド呼び出しエラー: {str(attr_error)}")
            # インストールされているモジュールのバージョン情報をログに出力
            logging.error(f"azure-mgmt-containerregistryのバージョン: {sys.modules.get('azure.mgmt.containerregistry').__version__ if 'azure.mgmt.containerregistry' in sys.modules else '不明'}")
            logging.error("使用可能なモジュールを確認します...")
            # 使用可能なモジュールを確認
            for name in dir(acr_client.registries):
                if name.startswith('_'):
                    continue
                logging.info(f"使用可能なメソッド: {name}")
            raise Exception(f"Azure ACR APIメソッドが見つかりません: {str(attr_error)}")
        
        # ビルドの完了を待機
        # LROポーラーの場合はresult()を使用、それ以外の場合はそのまま取得
        try:
            if hasattr(build_poller, 'result'):
                run_response = build_poller.result()
                logging.info("LROポーラーから結果を取得しました")
            else:
                run_response = build_poller
                logging.info("直接レスポンスを取得しました")
        except Exception as wait_error:
            logging.error(f"ビルド結果の取得に失敗: {str(wait_error)}")
            # エラーが発生しても、ビルドはバックグラウンドで継続している可能性がある
            return {
                "status": "warning",
                "image": full_image_name,
                "message": f"ビルドリクエストは送信されましたが、結果の確認に失敗しました: {str(wait_error)}"
            }
        
        # run_idを安全に取得
        run_id = None
        try:
            if hasattr(run_response, 'run_id'):
                run_id = run_response.run_id
            elif hasattr(run_response, 'id'):
                run_id = run_response.id
            elif hasattr(run_response, 'name'):
                run_id = run_response.name
            elif isinstance(run_response, dict):
                run_id = run_response.get('runId') or run_response.get('id') or run_response.get('name')
            
            if not run_id:
                # 最終手段としてUUIDを生成
                import uuid
                run_id = str(uuid.uuid4())
                logging.warning(f"ビルドIDが取得できないため、生成したIDを使用します: {run_id}")
        except Exception as id_error:
            # 例外が発生した場合もUUIDを生成
            import uuid
            run_id = str(uuid.uuid4())
            logging.warning(f"ビルドID取得中にエラー、生成したIDを使用: {run_id} (エラー: {str(id_error)})")
            
        logging.info(f"ビルドID: {run_id} の状態を監視中...")
        
        # ビルドステータスの監視
        status_check_interval = 30  # 30秒間隔
        max_checks = 20  # 最大20回（約10分）
        build_completed = False
        build_success = False
        check_count = 0
        last_status = ""
        
        while check_count < max_checks and not build_completed:
            check_count += 1
            time.sleep(status_check_interval)
            
            # 実行状態の取得
            try:
                run_status = acr_client.runs.get(
                    resource_group_name=resource_group,
                    registry_name=acr_name,
                    run_id=run_id
                )
                
                # 汎用的な方法でステータスを取得
                current_status = None
                
                # 直接のstatus属性を確認
                if hasattr(run_status, 'status'):
                    current_status = run_status.status
                    
                # propertiesの中にあるかもしれないstatus属性を確認
                if current_status is None and hasattr(run_status, 'properties'):
                    properties = run_status.properties
                    if isinstance(properties, dict):
                        current_status = properties.get('status')
                    elif hasattr(properties, 'status'):
                        current_status = properties.status
                
                # 辞書の場合
                if current_status is None and isinstance(run_status, dict):
                    current_status = run_status.get('status')
                    if current_status is None and 'properties' in run_status:
                        props = run_status['properties']
                        if isinstance(props, dict):
                            current_status = props.get('status')
                
                # ステータスが見つからない場合はデバッグ情報を出力
                if current_status is None:
                    logging.warning(f"ステータス情報が取得できません。利用可能なプロパティ: {dir(run_status)}")
                    if hasattr(run_status, 'as_dict'):
                        logging.warning(f"run_status辞書: {json.dumps(run_status.as_dict(), default=str)[:500]}")
                    else:
                        logging.warning(f"run_statusの型: {type(run_status)}")
                    current_status = "Unknown"
                
                # ステータスが変わった場合のみログ出力
                if current_status != last_status:
                    logging.info(f"ビルドステータス ({check_count}/{max_checks}): {current_status}")
                    last_status = current_status
                
                # ビルド完了の確認（大文字小文字を区別しない比較）
                completed_statuses = ['succeeded', 'failed', 'canceled', 'error', 'timeout']
                if str(current_status).lower() in completed_statuses:
                    build_completed = True
                    build_success = str(current_status).lower() == 'succeeded'
                    
                    if build_success:
                        logging.info(f"ビルド成功: {full_image_name}")
                        return {
                            "status": "success",
                            "runId": run_id,
                            "image": full_image_name,
                            "message": "ビルドが正常に完了しました"
                        }
                    else:
                        # エラーメッセージの取得（汎用的アプローチ）
                        error_msg = f"ビルド失敗: ステータス = {current_status}"
                        
                        try:
                            # error情報の取得を試みる
                            if hasattr(run_status, 'run_result') and hasattr(run_status.run_result, 'error'):
                                error_msg += f" - {run_status.run_result.error}"
                            elif hasattr(run_status, 'properties'):
                                properties = run_status.properties
                                if isinstance(properties, dict) and 'runResult' in properties:
                                    if isinstance(properties['runResult'], dict) and 'error' in properties['runResult']:
                                        error_msg += f" - {properties['runResult']['error']}"
                                elif hasattr(properties, 'run_result') and hasattr(properties.run_result, 'error'):
                                    error_msg += f" - {properties.run_result.error}"
                        except Exception as extract_error:
                            logging.warning(f"エラー詳細の取得中に例外: {str(extract_error)}")
                            
                        logging.error(error_msg)
                        raise Exception(f"イメージビルドに失敗: {error_msg}")
                
            except ResourceNotFoundError:
                logging.warning(f"実行ID {run_id} が見つかりません。まだ作成中かもしれません")
            except Exception as status_error:
                logging.error(f"ステータス確認中にエラー: {str(status_error)}")
        
        # 監視終了後の処理
        if not build_completed:
            # タイムアウト警告
            logging.warning(f"ビルド監視がタイムアウトしました ({max_checks}回のチェック後)")
            # ビルド継続前提で情報を返す
            return {
                "status": "warning",
                "runId": run_id,
                "image": full_image_name,
                "message": "ビルド監視がタイムアウトしました。バックグラウンドでビルドは継続されている可能性があります。"
            }
        
    except Exception as e:
        logging.error(f"イメージビルド中にエラー: {str(e)}")
        # 「イメージビルドに失敗」のプレフィックスがない場合のみ追加
        if not str(e).startswith("イメージビルドに失敗"):
            raise Exception(f"イメージビルドに失敗: {str(e)}")
        else:
            raise


def build_image_with_azure_cli(subscription_id, resource_group, acr_name, 
                               source_dir_or_subdir, image_tag, git_repo_url, 
                               git_branch, client_id, client_secret, tenant_id):
    """
    Azure CLI を使用してイメージをビルドする
    """
    import subprocess
    import logging
    import time
    import uuid
    
    # Docker イメージのフルパス
    acr_login_server = f"{acr_name}.azurecr.io"
    full_image_name = f"{acr_login_server}/{image_tag}"
    
    # GitリポジトリURLの組み立て - サブディレクトリをコンテキストとして指定
    git_source = f"{git_repo_url}#{git_branch}:{source_dir_or_subdir}"
    logging.info(f"イメージビルドを開始: {git_source} の Dockerfile")
    
    try:
        # Azure CLI への認証
        azure_cli_login(client_id, client_secret, tenant_id, subscription_id)
        
        # ACRビルドコマンドを実行
        build_result, build_cmd = execute_acr_build_command(acr_name, image_tag, git_source)
        
        # ジョブIDを取得 (または生成)
        build_id = str(uuid.uuid4())[:8]
        logging.info(f"イメージビルドを開始しました。監視ID: {build_id}")
        
        # ビルド状態の監視
        build_success = monitor_build_status(acr_name, image_tag)
        
        # 結果を返す
        return format_build_result(build_success, build_id, full_image_name)
    
    except subprocess.CalledProcessError as e:
        handle_subprocess_error(e)
    
    except Exception as e:
        logging.error(f"イメージビルド中に予期せぬエラー: {str(e)}")
        raise Exception(f"イメージビルドに失敗: {str(e)}")


def azure_cli_login(client_id, client_secret, tenant_id, subscription_id):
    """Azure CLI にサービスプリンシパルでログインする"""
    import subprocess
    import logging
    
    # Azure CLI でログイン
    logging.info("Azure CLI でサービスプリンシパルログインを実行...")
    login_cmd = f"az login --service-principal -u {client_id} -p '{client_secret}' --tenant {tenant_id}"
    login_result = subprocess.run(login_cmd, shell=True, check=True, capture_output=True, text=True)
    logging.info("Azure CLI ログインに成功しました")
    
    # サブスクリプションを設定
    logging.info(f"サブスクリプション {subscription_id} を設定...")
    sub_cmd = f"az account set --subscription {subscription_id}"
    subprocess.run(sub_cmd, shell=True, check=True, capture_output=True, text=True)


def execute_acr_build_command(acr_name, image_tag, git_source):
    """ACRビルドコマンドを実行する"""
    import subprocess
    import logging
    
    # 正しいコマンド形式で実行 - Dockerfileは相対パスで指定
    build_cmd = (
        f"az acr build "
        f"--registry {acr_name} "
        f"--image {image_tag} "
        f"--file Dockerfile "  # サブディレクトリがコンテキストになるため、相対パスは単純に「Dockerfile」
        f"--no-format "
        f"--no-logs "
        f"--no-wait "
        f"{git_source}"  # サブディレクトリを指定したGitソース
    )
    
    logging.info(f"ACR ビルドコマンドを実行: {build_cmd}")
    build_result = subprocess.run(build_cmd, shell=True, check=True, capture_output=True, text=True)
    return build_result, build_cmd


def monitor_build_status(acr_name, image_tag):
    """ビルド状態を監視する"""
    import subprocess
    import logging
    import time
    
    logging.info("ビルド状態の監視を開始...")
    status_check_interval = 30  # 30秒間隔
    max_checks = 20  # 最大20回（約10分）
    build_success = False
    
    for check in range(max_checks):
        time.sleep(status_check_interval)
        
        # イメージの存在を確認
        check_cmd = f"az acr repository show --name {acr_name} --image {image_tag} --query 'changeableAttributes.deleteEnabled'"
        try:
            check_result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True)
            if check_result.returncode == 0:
                logging.info(f"イメージ {image_tag} が ACR に存在することを確認しました")
                build_success = True
                break
        except:
            logging.info(f"ビルド監視中... ({check + 1}/{max_checks})")
    
    return build_success


def format_build_result(build_success, build_id, full_image_name):
    """ビルド結果を整形する"""
    import logging
    
    if build_success:
        logging.info(f"イメージビルドが完了しました: {full_image_name}")
        return {
            "status": "success",
            "runId": build_id,
            "image": full_image_name,
            "message": "ビルドが正常に完了しました"
        }
    else:
        logging.warning(f"タイムアウト: イメージがまだ ACR に存在しません。バックグラウンドでビルド継続中...")
        return {
            "status": "warning",
            "runId": build_id,
            "image": full_image_name,
            "message": "ビルド監視がタイムアウトしましたが、バックグラウンドで処理は継続しています"
        }


def handle_subprocess_error(error):
    """サブプロセスエラーを処理する"""
    import logging
    
    logging.error(f"コマンド実行エラー: {error.cmd}")
    if hasattr(error, 'stdout') and error.stdout:
        logging.error(f"標準出力: {error.stdout}")
    if hasattr(error, 'stderr') and error.stderr:
        logging.error(f"エラー出力: {error.stderr}")
    raise Exception(f"イメージビルドに失敗: {error.stderr if hasattr(error, 'stderr') and error.stderr else str(error)}")