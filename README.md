# 広聴AI簡単デプロイサービス

このプロジェクトは、非エンジニアが広聴AIをAzure環境に簡単にデプロイできるようにするためのサービスです。
ユーザーはWebフォームから必要情報を入力するだけで、Azure環境への広聴AIデプロイを自動的に行います。

## 概要

* Azure Functions を使用した全自動デプロイサービス
* Webフォームからのワンストップ操作
* ユーザー独自のAzureリソースを使用

## 前提条件

* Azure アカウント
* OpenAI API キー
* Python 3.9 以上
* Azure Functions Core Tools

## 開発環境のセットアップ

```bash
# 仮想環境の作成
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# または
.venv\Scripts\activate     # Windows

# 依存関係のインストール
pip install -r [requirements.txt](http://_vscodecontentref_/4)

# ローカル実行
func start
```

# デプロイ
Azure Functions へのデプロイは以下のコマンドで実行します：

```bash
func azure functionapp publish <function-app-name>
```

# 詳細ドキュメント
詳細なドキュメントは [広聴AI GitHub リポジトリ](https://github.com/digitaldemocracy2030/kouchou-ai) を参照してください。