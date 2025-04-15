import azure.functions as func
import json
import logging
import azure.durable_functions as df

async def main(req: func.HttpRequest, client: df.DurableOrchestrationClient) -> func.HttpResponse:
    logging.info('StatusCheckAPI HTTP trigger function processed a request.')
    
    try:
        # URLパスからデプロイIDを取得
        deploy_id = req.route_params.get('id')
        
        if not deploy_id:
            return func.HttpResponse(
                json.dumps({"error": "デプロイIDが指定されていません"}, ensure_ascii=False),
                status_code=400,
                mimetype="application/json"
            )
        
        # オーケストレーションの状態を取得
        status = await client.get_status(deploy_id)
        
        if not status:
            return func.HttpResponse(
                json.dumps({"error": "指定されたIDのデプロイが見つかりません"}, ensure_ascii=False),
                status_code=404,
                mimetype="application/json"
            )
        
        # ステータスレスポンスを構築
        response = {
            "id": deploy_id,
            "status": status.runtime_status.name,
            "created_time": status.created_time.isoformat() if status.created_time else None,
            "last_updated_time": status.last_updated_time.isoformat() if status.last_updated_time else None
        }
        
        # カスタムステータスが設定されている場合は追加
        if status.custom_status:
            custom_status = json.loads(status.custom_status)
            response.update(custom_status)
        
        # 完了している場合は出力を含める
        if status.runtime_status.name in ["Completed", "Failed"]:
            response["output"] = status.output
        
        return func.HttpResponse(
            json.dumps(response, ensure_ascii=False),
            status_code=200,
            mimetype="application/json"
        )
        
    except Exception as e:
        logging.error(f"ステータス確認中にエラーが発生しました: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": f"ステータス確認中にエラーが発生しました: {str(e)}"}, ensure_ascii=False),
            status_code=500,
            mimetype="application/json"
        )
