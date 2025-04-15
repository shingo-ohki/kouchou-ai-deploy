import logging
import os
import git
import azure.functions as func
import json

def main(params: str) -> str:
    """
    広聴AIリポジトリをクローンする
    """
    logging.info("広聴AIリポジトリをクローンしています")
    
    try:
        # 文字列として渡された場合はJSONとして解析
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except:
                params = {}
        elif params is None:
            params = {}
        
        # 作業ディレクトリを取得
        workdir = params.get("workdir")
        if not workdir:
            raise ValueError("workdirパラメータが指定されていません")
        
        # 環境変数からリポジトリURLを取得するか、デフォルトを使用
        repo_url = os.environ.get(
            "GITHUB_REPO", 
            "https://github.com/digitaldemocracy2030/kouchou-ai.git"
        )
        
        # クローン先のパス
        clone_path = os.path.join(workdir, "kouchou-ai")
        
        # Gitコマンドを使用してリポジトリをクローン
        logging.info(f"リポジトリ {repo_url} を {clone_path} にクローンしています")
        
        git.Repo.clone_from(repo_url, clone_path)
        
        logging.info("リポジトリのクローンが完了しました")
        
        result = {
            "status": "success",
            "path": clone_path,
            "message": f"リポジトリ {repo_url} のクローンが完了しました"
        }
        
        return json.dumps(result)
    except git.GitCommandError as e:
        error_msg = f"Gitコマンドエラー: {str(e)}"
        logging.error(error_msg)
        raise Exception(error_msg)
    except Exception as e:
        error_msg = f"リポジトリのクローン中にエラーが発生しました: {str(e)}"
        logging.error(error_msg)
        raise Exception(error_msg)
