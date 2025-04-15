document.addEventListener('DOMContentLoaded', function() {
    // デプロイ状態の詳細表示を改善するスクリプト
    const statusElement = document.getElementById('deploy-status');
    const progressElement = document.getElementById('deploy-progress');
    const logsContainer = document.getElementById('deploy-logs');
    const urlsContainer = document.getElementById('deploy-urls');
    
    // URLクエリパラメータからデプロイIDを取得
    const urlParams = new URLSearchParams(window.location.search);
    const deployId = urlParams.get('id');
    
    if (deployId) {
        let checkInterval;
        
        // デプロイ状態取得関数
        const checkStatus = async function() {
            try {
                const response = await fetch(`/api/status/${deployId}`);
                const data = await response.json();
                
                // 進捗の更新
                const status = data.customStatus || {};
                if (progressElement) {
                    progressElement.style.width = `${status.progress || 0}%`;
                    progressElement.setAttribute('aria-valuenow', status.progress || 0);
                }
                
                if (statusElement) {
                    statusElement.textContent = status.message || 'デプロイを実行中...';
                    if (status.step) {
                        statusElement.innerHTML = `<strong>${status.step}</strong>: ${status.message || '処理中...'}`;
                    }
                }
                
                // ログの表示
                if (logsContainer && data.output && data.output.logs) {
                    logsContainer.innerHTML = '';
                    data.output.logs.forEach(log => {
                        const logLine = document.createElement('div');
                        logLine.className = 'log-line';
                        
                        // エラーメッセージの強調表示
                        if (log.toLowerCase().includes('error') || 
                            log.toLowerCase().includes('failed') || 
                            log.toLowerCase().includes('失敗')) {
                            logLine.className += ' text-danger';
                        }
                        // 警告メッセージの強調表示
                        else if (log.toLowerCase().includes('warning') || 
                                log.toLowerCase().includes('warn') || 
                                log.toLowerCase().includes('警告')) {
                            logLine.className += ' text-warning';
                        }
                        // 成功メッセージの強調表示
                        else if (log.toLowerCase().includes('success') || 
                                log.toLowerCase().includes('completed') || 
                                log.toLowerCase().includes('完了')) {
                            logLine.className += ' text-success';
                        }
                        
                        logLine.textContent = log;
                        logsContainer.appendChild(logLine);
                    });
                    
                    // 最新のログまでスクロール
                    logsContainer.scrollTop = logsContainer.scrollHeight;
                }
                
                // URLの表示
                if (urlsContainer && data.output && data.output.urls) {
                    urlsContainer.innerHTML = '';
                    const urls = data.output.urls;
                    
                    if (urls.client) {
                        const clientLink = document.createElement('a');
                        clientLink.href = urls.client;
                        clientLink.target = '_blank';
                        clientLink.className = 'btn btn-primary m-1';
                        clientLink.textContent = 'ユーザーアプリを開く';
                        urlsContainer.appendChild(clientLink);
                    }
                    
                    if (urls.admin) {
                        const adminLink = document.createElement('a');
                        adminLink.href = urls.admin;
                        adminLink.target = '_blank';
                        adminLink.className = 'btn btn-secondary m-1';
                        adminLink.textContent = '管理者アプリを開く';
                        urlsContainer.appendChild(adminLink);
                    }
                    
                    if (urls.api) {
                        const apiLink = document.createElement('a');
                        apiLink.href = urls.api;
                        apiLink.target = '_blank';
                        apiLink.className = 'btn btn-info m-1';
                        apiLink.textContent = 'API サーバーを開く';
                        urlsContainer.appendChild(apiLink);
                    }
                    
                    // URLが取得できない場合の警告表示
                    if (!urls.client && !urls.admin && !urls.api) {
                        const warningDiv = document.createElement('div');
                        warningDiv.className = 'alert alert-warning';
                        warningDiv.textContent = 'デプロイは完了しましたが、アプリケーションのURLが取得できませんでした。詳細はログを確認してください。';
                        urlsContainer.appendChild(warningDiv);
                    }
                }
                
                // デプロイが完了または失敗した場合、チェックを停止
                if (data.runtimeStatus === 'Completed' || data.runtimeStatus === 'Failed') {
                    clearInterval(checkInterval);
                    
                    if (data.runtimeStatus === 'Failed') {
                        statusElement.innerHTML = '<strong class="text-danger">デプロイに失敗しました</strong>: ' + 
                            (status.message || 'エラーが発生しました。ログを確認してください。');
                    }
                }
            } catch (error) {
                console.error('ステータス取得エラー:', error);
            }
        };
        
        // 初回チェック
        checkStatus();
        
        // 5秒おきにステータスをチェック
        checkInterval = setInterval(checkStatus, 5000);
    }
});
