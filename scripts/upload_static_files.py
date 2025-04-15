#!/usr/bin/env python3

import os
import sys
from azure.storage.blob import BlobServiceClient, ContentSettings, PublicAccess

def upload_static_files(connection_string, container_name="static-web", static_dir="static"):
    """
    Azurite/Azure Blob Storageに静的ファイルをアップロードします
    
    Args:
        connection_string: Azure Storageの接続文字列
        container_name: Blob Storageのコンテナ名（デフォルトはstatic-web）
        static_dir: アップロードする静的ファイルのディレクトリパス
    """
    try:
        # BlobServiceClientを作成
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        
        # コンテナの作成（存在しない場合）- 公開アクセスを許可
        try:
            container_client = blob_service_client.create_container(
                container_name,
                public_access=PublicAccess.CONTAINER  # コンテナレベルで公開アクセスを許可
            )
            print(f"コンテナ '{container_name}' を作成し、公開アクセスを設定しました")
        except Exception as e:
            if "ContainerAlreadyExists" in str(e):
                container_client = blob_service_client.get_container_client(container_name)
                print(f"コンテナ '{container_name}' は既に存在します")
                # 既存のコンテナに公開アクセスを設定
                try:
                    blob_service_client.set_container_access_policy(
                        container_name,
                        public_access=PublicAccess.CONTAINER
                    )
                    print(f"コンテナ '{container_name}' に公開アクセスを設定しました")
                except Exception as e:
                    print(f"公開アクセスの設定中にエラーが発生しました: {str(e)}")
            else:
                raise e
        
        # 指定されたディレクトリ内のファイルをアップロード
        for root, dirs, files in os.walk(static_dir):
            for file in files:
                local_file_path = os.path.join(root, file)
                # アップロード先のパスを算出（static_dirからの相対パス）
                blob_path = os.path.relpath(local_file_path, static_dir)
                blob_path = blob_path.replace("\\", "/")  # Windows対応
                
                # ファイルのMIMEタイプを設定
                content_type = "text/html"
                if file.endswith(".css"):
                    content_type = "text/css"
                elif file.endswith(".js"):
                    content_type = "application/javascript"
                elif file.endswith(".png"):
                    content_type = "image/png"
                elif file.endswith(".jpg") or file.endswith(".jpeg"):
                    content_type = "image/jpeg"
                
                # Blobクライアントを取得し、ファイルをアップロード
                blob_client = container_client.get_blob_client(blob_path)
                with open(local_file_path, "rb") as data:
                    blob_client.upload_blob(
                        data, 
                        overwrite=True,
                        content_settings=ContentSettings(content_type=content_type)
                    )
                print(f"'{local_file_path}' を '{blob_path}' としてアップロードしました")
                
                # 重要: 各Blobの公開URL
                blob_url = f"{blob_client.url}"
                print(f"公開URL: {blob_url}")
                
        print("すべてのファイルのアップロードが完了しました")
        
        # 静的ウェブサイトのURLを表示
        print(f"\nAzureの場合の静的ウェブサイトURL: https://{{storage-account-name}}.blob.core.windows.net/{container_name}/deploy-form.html")
        print(f"Azuriteの場合のアクセスURL: http://127.0.0.1:10000/devstoreaccount1/{container_name}/deploy-form.html")
        
    except Exception as e:
        print(f"エラーが発生しました: {str(e)}")
        return False
        
    return True

if __name__ == "__main__":
    # Azurite用の接続文字列
    connection_string = "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
    
    # コマンドライン引数から静的ファイルのディレクトリとコンテナ名を取得
    static_dir = sys.argv[1] if len(sys.argv) > 1 else "static"
    container_name = sys.argv[2] if len(sys.argv) > 2 else "static-web"  # $webではなく一般的なコンテナ名を使用
    
    # 静的ファイルのアップロード
    success = upload_static_files(connection_string, container_name=container_name, static_dir=static_dir)
    
    if not success:
        sys.exit(1)