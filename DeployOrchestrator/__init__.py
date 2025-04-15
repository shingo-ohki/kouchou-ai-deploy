import azure.functions as func
import azure.durable_functions as df
import logging
import json
import os

def orchestrator_function(context: df.DurableOrchestrationContext):
    """デプロイのためのオーケストレーション関数"""
    
    # 入力データの取得
    deploy_data = context.get_input()
    logging.info(f"デプロイリクエスト: {deploy_data}")
    
    # 初期ステータスをセット
    initial_status = {
        "step": "開始",
        "progress": 0,
        "message": "デプロイを開始しています..."
    }
    context.set_custom_status(initial_status)
    
    try:
        # 作業ディレクトリを設定
        workdir = "/tmp/kouchou-ai-deploy"
        deploy_data["workdir"] = workdir
        
        # リソースグループ作成
        resource_group_status = {
            "step": "リソースグループ作成", 
            "progress": 20, 
            "message": "リソースグループを作成しています..."
        }
        yield context.call_activity('UpdateDeployStatus', resource_group_status)
        context.set_custom_status(resource_group_status)
        
        # 作業ディレクトリの準備
        workdir_result = yield context.call_activity('PrepareWorkDirectory', deploy_data)
        
        # JSON文字列から辞書に変換
        if isinstance(workdir_result, str):
            try:
                workdir_result = json.loads(workdir_result)
            except:
                logging.warning("作業ディレクトリ結果をJSONとしてパースできませんでした")
                workdir_result = {"status": "success", "path": workdir}
        
        logging.info(f"作業ディレクトリ準備結果: {workdir_result}")
        
        # 得られた作業ディレクトリを使用
        if workdir_result.get("path"):
            workdir = workdir_result["path"]
            deploy_data["workdir"] = workdir
            
        # リポジトリのクローンに必要なパラメータを辞書として渡す
        clone_params = {"workdir": workdir}
        logging.info(f"クローンパラメータ: {clone_params}")
        clone_result = yield context.call_activity('CloneRepository', clone_params)
        
        # JSON文字列から辞書に変換
        if isinstance(clone_result, str):
            try:
                clone_result = json.loads(clone_result)
            except:
                logging.warning("クローン結果をJSONとしてパースできませんでした")
        
        logging.info(f"リポジトリクローン結果: {clone_result}")
        
        # ストレージアカウント作成
        storage_account_status = {
            "step": "ストレージアカウント作成", 
            "progress": 40, 
            "message": "ストレージアカウントを作成しています..."
        }
        yield context.call_activity('UpdateDeployStatus', storage_account_status)
        context.set_custom_status(storage_account_status)
        
        # Function App作成
        function_app_status = {
            "step": "Function App作成", 
            "progress": 60, 
            "message": "Function Appを作成しています..."
        }
        yield context.call_activity('UpdateDeployStatus', function_app_status)
        context.set_custom_status(function_app_status)
        
        # アプリケーションデプロイ - ここでDeployWithMakefileを呼び出す
        deploy_status = {
            "step": "デプロイ", 
            "progress": 80, 
            "message": "アプリケーションをデプロイしています..."
        }
        yield context.call_activity('UpdateDeployStatus', deploy_status)
        context.set_custom_status(deploy_status)
        
        # DeployWithMakefileを呼び出してMakefileによるデプロイを実行
        makefile_deploy_result = yield context.call_activity('DeployWithMakefile', deploy_data)
        
        # JSON文字列から辞書に変換
        if isinstance(makefile_deploy_result, str):
            try:
                makefile_deploy_result = json.loads(makefile_deploy_result)
            except:
                logging.warning("デプロイ結果をJSONとしてパースできませんでした")
                makefile_deploy_result = {"status": "error", "message": "デプロイ結果をパースできませんでした"}
        
        logging.info(f"Makefileによるデプロイ結果: {makefile_deploy_result}")
        
        # デプロイの成功/失敗を確認
        if makefile_deploy_result.get("status") == "error":
            error_message = makefile_deploy_result.get("message", "不明なエラーが発生しました")
            error_status = {
                "step": "エラー", 
                "progress": 0, 
                "message": f"デプロイ中にエラーが発生しました: {error_message}"
            }
            context.set_custom_status(error_status)
            raise Exception(error_message)
        
        # 完了
        complete_status = {
            "step": "完了", 
            "progress": 100, 
            "message": "広聴AIのデプロイが完了しました！"
        }
        yield context.call_activity('UpdateDeployStatus', complete_status)
        context.set_custom_status(complete_status)
        
        return {
            "status": "completed", 
            "result": makefile_deploy_result
        }
    except Exception as e:
        # エラー発生時
        error_status = {
            "step": "エラー", 
            "progress": 0, 
            "message": f"デプロイ中にエラーが発生しました: {str(e)}"
        }
        context.set_custom_status(error_status)
        raise

main = df.Orchestrator.create(orchestrator_function)
