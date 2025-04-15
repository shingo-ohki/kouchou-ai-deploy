import logging
import json
import azure.functions as func
import azure.durable_functions as df
import os

async def main(req: func.HttpRequest, starter: str) -> func.HttpResponse:
    """
    ステータス確認エンドポイント - CORS対応と適切な認証を実装
    """
    # OPTIONSリクエストの処理
    if req.method.lower() == 'options':
        response = func.HttpResponse(status_code=200)
        response.headers['Access-Control-Allow-Origin'] = 'http://127.0.0.1:10000'
        response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, x-functions-key'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Max-Age'] = '86400'
        return response
    
    # APIキー認証（開発環境ではスキップ可能）
    is_development = os.environ.get('AZURE_FUNCTIONS_ENVIRONMENT') == 'Development'
    
    # 開発環境以外では基本的な認証チェックを実行
    if not is_development:
        # 簡易的な認証チェック - x-functions-keyヘッダーをチェック
        api_key = req.headers.get('x-functions-key')
        expected_key = os.environ.get('FUNCTION_API_KEY')  # 環境変数から取得
        
        if not api_key or (expected_key and api_key != expected_key):
            response = func.HttpResponse(
                json.dumps({"error": "認証エラー: 有効なAPIキーが必要です"}),
                mimetype="application/json",
                status_code=401
            )
            # CORSヘッダーを設定
            response.headers['Access-Control-Allow-Origin'] = 'http://127.0.0.1:10000'
            response.headers['Access-Control-Allow-Credentials'] = 'true'
            return response
    
    # インスタンスID取得
    instance_id = req.route_params.get('id')
    if not instance_id:
        response = func.HttpResponse(
            json.dumps({"error": "インスタンスIDが指定されていません"}),
            mimetype="application/json",
            status_code=400
        )
    else:
        try:
            # ステータス取得
            client = df.DurableOrchestrationClient(starter)
            logging.info(f"ステータスを取得します: ID={instance_id}")
            instance = await client.get_status(instance_id)
            
            if instance:
                # インスタンスが見つかった場合
                logging.info(f"ステータスが見つかりました: {instance}")
                logging.info(f"runtime_status のタイプ: {type(instance.runtime_status)}")
                
                # OrchestrationRuntimeStatusを文字列に変換
                runtime_status = instance.runtime_status.name if hasattr(instance.runtime_status, 'name') else str(instance.runtime_status)
                logging.info(f"変換したruntime_status: {runtime_status}")
                
                # カスタムステータスの処理
                custom_status = instance.custom_status
                logging.info(f"custom_status: {custom_status}")
                
                status_data = {
                    "id": instance.instance_id,
                    "runtimeStatus": runtime_status,
                    "customStatus": custom_status,
                    "createdTime": instance.created_time.isoformat() if instance.created_time else None,
                    "lastUpdatedTime": instance.last_updated_time.isoformat() if instance.last_updated_time else None
                }
                response = func.HttpResponse(
                    json.dumps(status_data),
                    mimetype="application/json",
                    status_code=200
                )
            else:
                # インスタンスが見つからない場合
                response = func.HttpResponse(
                    json.dumps({"error": "指定されたIDのデプロイインスタンスが見つかりません"}),
                    mimetype="application/json", 
                    status_code=404
                )
        except Exception as e:
            logging.error(f"ステータス確認エラー: {str(e)}")
            response = func.HttpResponse(
                json.dumps({"error": str(e)}),
                mimetype="application/json", 
                status_code=500
            )

    # CORSヘッダーを設定
    response.headers['Access-Control-Allow-Origin'] = 'http://127.0.0.1:10000'
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    
    return response
