import logging
import os
import tempfile
from datetime import datetime
import uuid
import azure.functions as func

def main(name: str) -> str:
    """
    デプロイ用の一時作業ディレクトリを作成する
    """
    logging.info("作業ディレクトリを準備しています")
    
    try:
        # 文字列として渡された場合はJSONとして解析
        if isinstance(name, str):
            import json
            try:
                name = json.loads(name)
            except:
                name = {}
        elif name is None:
            name = {}
            
        # 環境変数から作業ディレクトリのルートを取得するか、デフォルトを使用
        workspace_root = os.environ.get("DEPLOYMENT_WORKSPACE", tempfile.gettempdir())
        
        # 一意の作業ディレクトリ名を生成
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        deploy_id = name.get("deployment_id", str(uuid.uuid4()))
        work_dir_name = f"kouchou-ai-deploy-{timestamp}-{deploy_id}"
        
        # 作業ディレクトリのパスを作成
        work_dir = os.path.join(workspace_root, work_dir_name)
        
        # ディレクトリが存在しない場合は作成
        if not os.path.exists(work_dir):
            os.makedirs(work_dir)
            logging.info(f"作業ディレクトリを作成しました: {work_dir}")
        
        result = {
            "status": "success",
            "path": work_dir,
            "message": f"作業ディレクトリを準備しました: {work_dir}"
        }
        
        # 結果を文字列に変換して返す
        import json
        return json.dumps(result)
        
    except Exception as e:
        error_msg = f"作業ディレクトリの準備中にエラーが発生しました: {str(e)}"
        logging.error(error_msg)
        raise Exception(error_msg)
