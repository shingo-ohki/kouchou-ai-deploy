import logging
import json
import azure.functions as func
import azure.durable_functions as df

async def main(req: func.HttpRequest, starter: str) -> func.HttpResponse:
    # OPTIONSリクエスト（プリフライトリクエスト）を処理
    if req.method.lower() == 'options':
        response = func.HttpResponse(status_code=200)
        # CORSヘッダーを設定
        response.headers['Access-Control-Allow-Origin'] = 'http://127.0.0.1:10000'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Max-Age'] = '86400'  # 24時間キャッシュを有効に
        return response
    
    # 通常のリクエスト処理
    logging.info('デプロイリクエストを受信しました')
    
    try:
        # リクエストボディからデプロイデータを取得
        req_body = req.get_json()
        
        # Durable Functionsのオーケストレーターを開始
        client = df.DurableOrchestrationClient(starter)
        instance_id = await client.start_new("DeployOrchestrator", None, req_body)
        
        # オーケストレーションの状態をチェックするためのURLを生成
        logging.info(f'オーケストレーションが開始されました。ID: {instance_id}')
        
        # オリジナルのステータスレスポンス（参照用）
        original_status_response = client.create_check_status_response(req, instance_id)
        original_status_obj = json.loads(original_status_response.get_body().decode('utf-8'))
        
        # カスタムステータスURLを生成
        # 現在のホスト名を取得（localhost:8080または127.0.0.1:8080など）
        host = req.headers.get('Host', 'localhost:8080')
        scheme = req.headers.get('X-Forwarded-Proto', 'http')
        custom_status_url = f"{scheme}://{host}/api/status/{instance_id}"
        
        # レスポンスを作成
        response = func.HttpResponse(
            json.dumps({
                "id": instance_id,
                "status": "started",
                "status_query_uri": custom_status_url,  # カスタムステータスURLを使用
                "original_uri": original_status_obj.get("statusQueryGetUri", "")  # デバッグ用に元のURLも含める
            }),
            status_code=202,
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f'エラーが発生しました: {str(e)}')
        error_response = {
            "error": str(e),
            "message": "デプロイの開始に失敗しました"
        }
        response = func.HttpResponse(
            json.dumps(error_response),
            status_code=500,
            mimetype="application/json"
        )
    
    # CORSヘッダーを設定
    response.headers['Access-Control-Allow-Origin'] = 'http://127.0.0.1:10000'
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    
    return response
