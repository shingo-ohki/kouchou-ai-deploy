import azure.functions as func
import json
import logging

def main(req: func.HttpRequest) -> func.HttpResponse:
    # OPTIONSリクエストの処理
    if req.method.lower() == 'options':
        response = func.HttpResponse(status_code=200)
        response.headers['Access-Control-Allow-Origin'] = 'http://127.0.0.1:10000'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response
    
    # 通常のリクエスト処理
    response_data = {
        "message": "CORSテスト成功",
        "received_headers": {k: req.headers.get(k) for k in req.headers},
        "method": req.method
    }
    
    response = func.HttpResponse(
        json.dumps(response_data),
        status_code=200,
        mimetype="application/json"
    )
    
    # CORSヘッダーを設定
    response.headers['Access-Control-Allow-Origin'] = 'http://127.0.0.1:10000'
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    
    return response
