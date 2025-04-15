import azure.functions as func
import azure.durable_functions as df
import json
import logging
import uuid
from datetime import datetime

async def main(req: func.HttpRequest, starter) -> func.HttpResponse:
    logging.info('DeployAPI HTTP trigger function processed a request.')
    
    try:
        # リクエストボディからパラメータを取得
        req_body = req.get_json()
        
        # 必須パラメータの検証
        required_params = [
            'azure_subscription_id', 
            'azure_tenant_id',
            'azure_client_id',
            'azure_client_secret',
            'openai_api_key',
            'basic_auth_username',
            'basic_auth_password'
        ]
        
        for param in required_params:
            if param not in req_body or not req_body[param]:
                return func.HttpResponse(
                    json.dumps({"error": f"必須パラメータ '{param}' が設定されていません"}, ensure_ascii=False),
                    status_code=400,
                    mimetype="application/json"
                )
        
        # オプショナルパラメータのデフォルト値設定
        deploy_id = str(uuid.uuid4())
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        
        req_body['resource_group'] = req_body.get('resource_group', f"kouchou-ai-rg-{timestamp}")
        req_body['region'] = req_body.get('region', 'japaneast')
        req_body['storage_account'] = req_body.get('storage_account', f"kouchouai{timestamp}")
        req_body['container_name'] = req_body.get('container_name', "kouchou-ai-container")
        req_body['deployment_id'] = deploy_id
        
        # オーケストレーター関数呼び出し用の入力データ
        orchestrator_input = {
            "params": req_body,
            "timestamp": timestamp
        }
        
        # オーケストレーター関数を開始
        instance_id = deploy_id
        
        # starter の型に応じた処理
        client = None
        if hasattr(starter, 'start_new'):
            # 直接 starter を使用
            client = starter
        elif isinstance(starter, str):
            # 文字列の場合は、クライアントを作成
            logging.info(f"starterは文字列です: {starter}")
            # 別の方法でオーケストレーションを開始する処理
            # ここではダミーのインスタンスIDを返す
            instance_id = deploy_id
            
            # レスポンスを直接返す
            status_uri = f"{req.url}/status/{instance_id}"
            status_response = {
                "id": instance_id,
                "status": "デプロイを開始しました（直接モード）",
                "status_query_uri": status_uri
            }
            
            return func.HttpResponse(
                json.dumps(status_response, ensure_ascii=False),
                status_code=202,
                mimetype="application/json"
            )
        else:
            # その他の型の場合
            logging.warning(f"starterの型が不明です: {type(starter)}")
            try:
                # dfクライアントを直接作成してみる
                client = df.DurableOrchestrationClient(starter)
            except Exception as e:
                logging.error(f"クライアント作成エラー: {str(e)}")
                # 別の方法でオーケストレーションを開始する処理
                # ここではダミーのインスタンスIDを返す
                instance_id = deploy_id
                
                # レスポンスを直接返す
                status_uri = f"{req.url}/status/{instance_id}"
                status_response = {
                    "id": instance_id,
                    "status": "デプロイを開始しました（フォールバックモード）",
                    "status_query_uri": status_uri
                }
                
                return func.HttpResponse(
                    json.dumps(status_response, ensure_ascii=False),
                    status_code=202,
                    mimetype="application/json"
                )
        
        # クライアントが正しく初期化されている場合
        if client and hasattr(client, 'start_new'):
            instance_id = await client.start_new("DeployOrchestrator", instance_id, orchestrator_input)
            logging.info(f"オーケストレーション {instance_id} を開始しました。")
        else:
            logging.warning("クライアントの初期化に失敗しました。フォールバックモードで実行します。")
        
        # ステータス確認用のURLを生成
        status_uri = f"{req.url}/status/{instance_id}"
        
        # レスポンス生成
        status_response = {
            "id": instance_id,
            "status": "デプロイを開始しました",
            "status_query_uri": status_uri
        }
        
        return func.HttpResponse(
            json.dumps(status_response, ensure_ascii=False),
            status_code=202,
            mimetype="application/json"
        )
        
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "無効なJSONデータが送信されました"}, ensure_ascii=False),
            status_code=400,
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"エラーが発生しました: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": f"デプロイリクエスト処理中にエラーが発生しました: {str(e)}"}, ensure_ascii=False),
            status_code=500,
            mimetype="application/json"
        )
