import logging
import json
import os
import azure.functions as func
import requests
from datetime import datetime

def main(req: func.HttpRequest) -> func.HttpResponse:
    """
    Azure リソースのクリーンアップを行うAPIエンドポイント
    Makefile の azure-cleanup と同等の処理を実行します
    """
    logging.info('Azure リソースクリーンアップのリクエストを受信しました')
    
    # CORS対応: Originヘッダの確認
    origin = req.headers.get('Origin', '')
    headers = {
        "Access-Control-Allow-Origin": origin or "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization"
    }
    
    # OPTIONSリクエスト（プリフライト）の場合は早期リターン
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=200, headers=headers)
    
    try:
        # リクエストボディを解析
        req_body = req.get_json()
        
        # 必須パラメータのチェック
        required_params = [
            'azure_subscription_id', 'azure_tenant_id', 
            'azure_client_id', 'azure_client_secret',
            'resource_group'
        ]
        
        for param in required_params:
            if param not in req_body or not req_body[param]:
                return func.HttpResponse(
                    json.dumps({
                        "status": "error",
                        "message": f"必須パラメータ '{param}' が指定されていません"
                    }),
                    mimetype="application/json",
                    status_code=400,
                    headers=headers
                )
        
        # パラメータを取得
        subscription_id = req_body['azure_subscription_id']
        tenant_id = req_body['azure_tenant_id']
        client_id = req_body['azure_client_id']
        client_secret = req_body['azure_client_secret']
        resource_group = req_body['resource_group']
        
        # Azure REST API用のアクセストークンを取得
        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/token"
        token_payload = {
            'grant_type': 'client_credentials',
            'client_id': client_id,
            'client_secret': client_secret,
            'resource': 'https://management.azure.com/'
        }
        
        token_headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        token_response = requests.post(token_url, data=token_payload, headers=token_headers)
        
        if token_response.status_code != 200:
            return func.HttpResponse(
                json.dumps({
                    "status": "error",
                    "message": f"Azure認証に失敗しました: HTTP {token_response.status_code}",
                    "details": token_response.text
                }),
                mimetype="application/json",
                status_code=401,
                headers=headers
            )
        
        token = token_response.json().get('access_token')
        
        # リソースグループ削除のAPIを呼び出し
        cleanup_url = f"https://management.azure.com/subscriptions/{subscription_id}/resourcegroups/{resource_group}?api-version=2021-04-01"
        cleanup_headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        # まずリソースグループが存在するか確認
        check_response = requests.get(cleanup_url, headers=cleanup_headers)
        
        if check_response.status_code == 404:
            return func.HttpResponse(
                json.dumps({
                    "status": "warning",
                    "message": f"リソースグループ '{resource_group}' が見つかりません"
                }),
                mimetype="application/json",
                status_code=404,
                headers=headers
            )
        
        # リソースグループの削除を実行
        cleanup_response = requests.delete(cleanup_url, headers=cleanup_headers)
        
        if cleanup_response.status_code not in [200, 202]:
            return func.HttpResponse(
                json.dumps({
                    "status": "error",
                    "message": f"リソースグループの削除に失敗しました: HTTP {cleanup_response.status_code}",
                    "details": cleanup_response.text
                }),
                mimetype="application/json",
                status_code=500,
                headers=headers
            )
        
        # 非同期操作のステータス確認用URL
        status_url = None
        if cleanup_response.status_code == 202:
            # 非同期操作の場合はロケーションヘッダを取得
            status_url = cleanup_response.headers.get('Location')
            # Azureの非同期操作ヘッダを確認
            if not status_url:
                status_url = cleanup_response.headers.get('Azure-AsyncOperation')
        
        result = {
            "status": "success",
            "message": f"リソースグループ '{resource_group}' の削除を開始しました",
            "operation_id": cleanup_response.headers.get('x-ms-request-id', 'unknown'),
            "status_url": status_url
        }
        
        return func.HttpResponse(
            json.dumps(result),
            mimetype="application/json",
            headers=headers
        )
        
    except ValueError as ve:
        return func.HttpResponse(
            json.dumps({
                "status": "error",
                "message": f"リクエストボディの解析に失敗しました: {str(ve)}"
            }),
            mimetype="application/json",
            status_code=400,
            headers=headers
        )
    except Exception as e:
        logging.error(f"Azure リソースクリーンアップ中にエラーが発生しました: {str(e)}")
        return func.HttpResponse(
            json.dumps({
                "status": "error", 
                "message": f"Azure リソースクリーンアップ中にエラーが発生しました: {str(e)}"
            }),
            mimetype="application/json",
            status_code=500,
            headers=headers
        )