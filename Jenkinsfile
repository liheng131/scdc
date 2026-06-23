pipeline {
    agent any

    environment {
        COMPOSE_FILE = 'docker-compose.yml'
    }

    stages {
        stage('Build Images') {
            steps {
                echo '>>> 构建 Docker 镜像...'
                sh '''
                    docker compose -f ${COMPOSE_FILE} build
                '''
            }
        }

        stage('Deploy Services') {
            steps {
                echo '>>> 强制重建并启动所有服务（每次都使用最新镜像和环境变量）...'
                sh '''
                    docker compose -f ${COMPOSE_FILE} up -d --force-recreate --remove-orphans
                '''
            }
        }

        stage('Wait for Backend Ready') {
            steps {
                echo '>>> 等待后端服务就绪...'
                sh '''
                    for i in $(seq 1 30); do
                        if docker exec scdc_backend python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')" 2>/dev/null; then
                            echo "后端已就绪"
                            break
                        fi
                        echo "等待后端启动... ($i/30)"
                        sleep 5
                    done
                '''
            }
        }

        stage('Pull Ollama Models') {
            steps {
                echo '>>> 拉取 Ollama 模型...'
                sh '''
                    docker exec scdc_ollama ollama pull nomic-embed-text || true
                '''
            }
        }

        stage('Seed Database') {
            steps {
                echo '>>> 初始化数据库种子数据...'
                sh '''
                    docker exec scdc_backend python seed_data.py || true
                '''
            }
        }

        stage('Cleanup') {
            steps {
                echo '>>> 清理旧镜像...'
                sh '''
                    docker image prune -f
                '''
            }
        }
    }

    post {
        success {
            echo '>>> 部署成功！访问地址: http://120.79.96.231:6015/'
        }
        failure {
            echo '>>> 部署失败，自动打印日志排查...'
            sh 'docker logs scdc_backend --tail 200 || true'
            sh 'docker logs scdc_frontend --tail 200 || true'
            sh 'docker logs scdc_ollama --tail 50 || true'
            sh 'docker ps -a || true'
            error '部署失败，请根据上方日志修复后重试'
        }
    }
}