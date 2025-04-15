#!/usr/bin/env python3
"""
APIリクエストをプロキシするためのシンプルなHTTPサーバー
"""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import urllib.request
import urllib.error
from urllib.parse import parse_qs, urlparse

class ProxyHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Content-Length, Authorization')
        self.end_headers()

    def do_POST(self):
        path = self.path
        target_url = 'http://localhost:8080/api/deploy'

        # リクエストボディを取得
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)

        print(f"Proxying request to {target_url}")
        print(f"Request data: {post_data.decode('utf-8')}")

        try:
            # ターゲットURLにリクエストを転送
            req = urllib.request.Request(target_url, data=post_data)
            req.add_header('Content-Type', 'application/json')
            
            with urllib.request.urlopen(req) as response:
                response_data = response.read()
                
                # レスポンスを返す
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(response_data)
                print(f"Response: {response_data.decode('utf-8')}")
        except urllib.error.HTTPError as e:
            # エラーレスポンスを返す
            self.send_response(e.code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            error_message = {'error': f'API error: {str(e)}', 'status': e.code}
            self.wfile.write(json.dumps(error_message).encode('utf-8'))
            print(f"Error: {json.dumps(error_message)}")
        except Exception as e:
            # その他のエラー
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            error_message = {'error': f'Proxy error: {str(e)}', 'status': 500}
            self.wfile.write(json.dumps(error_message).encode('utf-8'))
            print(f"Error: {json.dumps(error_message)}")

    def do_GET(self):
        if self.path.startswith('/api/deploy/status/'):
            # ステータス確認エンドポイント
            deployment_id = self.path.split('/')[-1]
            target_url = f'http://localhost:8080/api/deploy/status/{deployment_id}'
            
            try:
                with urllib.request.urlopen(target_url) as response:
                    response_data = response.read()
                    
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(response_data)
                    print(f"Status response: {response_data.decode('utf-8')}")
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                
                error_message = {'error': f'Status check error: {str(e)}', 'status': 500}
                self.wfile.write(json.dumps(error_message).encode('utf-8'))
        else:
            # その他のGETリクエスト
            self.send_response(404)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            self.wfile.write(json.dumps({'error': 'Endpoint not found'}).encode('utf-8'))

def run(server_class=HTTPServer, handler_class=ProxyHTTPRequestHandler, port=8000):
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    print(f'Starting proxy server on port {port}...')
    httpd.serve_forever()

if __name__ == "__main__":
    run()