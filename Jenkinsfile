pipeline {
    agent any

    environment {
        PROJECT_DIR = '/opt/scdc'
        COMPOSE_FILE = 'docker-compose.yml'
    }

    stages {
        stage('Checkout') {
            steps {
                echo '>>> 拉取最新代码...'
                git branch: 'main',
                    url: 'https://gitee.com/your-username/scdc.git',
                    credentialsId: 'gitee-credentials'
            }
        }

        stage('Build Images') {
            steps {
                echo '>>> 构建 Docker 镜像...'
                sh '''
                    cd ${PROJECT_DIR}
                    docker compose -f ${COMPOSE_FILE} build --no-cache
                '''
            }
        }

        stage('Deploy Services') {
            steps {
                echo '>>> 启动/更新所有服务...'
                sh '''
                    cd ${PROJECT_DIR}
                    docker compose -f ${COMPOSE_FILE} up -d --remove-orphans
                '''
            }
        }

        stage('Wait for Backend Ready') {
            steps {
                echo '>>> 等待后端服务就绪...'
                sh '''
                    cd ${PROJECT_DIR}
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

        stage('Seed Database') {
            steps {
                echo '>>> 初始化数据库种子数据...'
                sh '''
                    cd ${PROJECT_DIR}
                    docker exec scdc_backend python seed_data.py
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
            echo '>>> 部署失败，请检查日志！'
        }
    }
}