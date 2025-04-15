import azure.functions as func
import logging
import subprocess
import os

def main(params: dict) -> dict:
    """
    リソースグループを作成する
    """
    logging.info(f"リソースグループ '{params['resource_group']}' を作成しています")
    
    try:
        # 必須パラメータのチェック
        required_params = ['resource_group', 'region']
        for param in required_params:
            if param not in params or not params[param]:
                raise ValueError(f"必須パラメータ '{param}' が指定されていません")
        
        resource_group = params["resource_group"]
        region = params["region"]
        workdir = params["workdir"]
        
        # リソースグループが存在するか確認
        check_command = [
            "az", "group", "exists",
            "--name", resource_group
        ]
        
        check_result = subprocess.run(
            check_command,
            check=True,
            capture_output=True,
            text=True,
            cwd=workdir
        )
        
        exists = check_result.stdout.strip().lower() == "true"
        
        if exists:
            logging.info(f"リソースグループ '{resource_group}' は既に存在します")
            return {
                "status": "success",
                "message": f"リソースグループ '{resource_group}' は既に存在します",
                "resource_group": resource_group
            }
        
        # リソースグループを作成
        create_command = [
            "az", "group", "create",
            "--name", resource_group,
            "--location", region
        ]
        
        create_result = subprocess.run(
            create_command,
            check=True,
            capture_output=True,
            text=True,
            cwd=workdir
        )
        
        logging.info(f"リソースグループ '{resource_group}' を作成しました")
        
        return {
            "status": "success",
            "message": f"リソースグループ '{resource_group}' を作成しました",
            "resource_group": resource_group
        }
    except subprocess.CalledProcessError as e:
        error_msg = f"リソースグループの作成に失敗しました: {e.stderr}"
        logging.error(error_msg)
        raise Exception(error_msg)
    except Exception as e:
        error_msg = f"リソースグループ作成中にエラーが発生しました: {str(e)}"
        logging.error(error_msg)
        raise Exception(error_msg)
