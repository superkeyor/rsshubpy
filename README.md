# Build
```
####### global settings
IMAGE_NAME="rsshub_python"

####### git clone
cp ~/Desktop/Dropbox/Apps/Git/config/.ssh/id_ed25519 ~/.ssh/id_ed25519
cp ~/Desktop/Dropbox/Apps/Git/config/.gitconfig ~/.gitconfig
cd ~/Desktop
git clone git@github.com:/superkeyor/${IMAGE_NAME}.git
cd ${IMAGE_NAME}

####### test locally
pip3 install -r requirements.txt
sudo apt install quiterss -y   # brew install --cask fluent-reader

####### ./run
cat <<EOF | tee run >/dev/null
#!/usr/bin/env bash
csd="\$( cd "\$( dirname "\${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "\$csd"
flask run --host=0.0.0.0 --port=1201   # ipython # to debug
EOF
chmod +x run

####### docker hub
IMAGE_NAME=$(basename $(pwd))

####### upload to github and dockerhub
cat <<EOF | tee upload >/dev/null
#!/usr/bin/env bash
csd="\$( cd "\$( dirname "\${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "\$csd"

# git config --global --add safe.directory .
# git reset --hard   # discard local changes
# git pull git@github.com:/superkeyor/${IMAGE_NAME}.git

git add -A 
git commit -m 'update'
git push git@github.com:/superkeyor/${IMAGE_NAME}.git

if [[ $(command -v docker) != "" ]]; then
sudo docker build -t ${IMAGE_NAME} .
sudo docker image tag ${IMAGE_NAME} superkeyor/${IMAGE_NAME}:latest
sudo docker image push superkeyor/${IMAGE_NAME}:latest
fi
EOF
chmod +x upload   # ./upload

echo "Docker Hub Password (formula): "
sudo docker login -u superkeyor
echo "Ready!"
```

# RSSHub

> 🍰 万物皆可 RSS

RSSHub 是一个轻量、易于扩展的 RSS 生成器，可以给任何奇奇怪怪的内容生成 RSS 订阅源

本项目是[原RSSHub](https://github.com/DIYgod/RSSHub)的Python实现。


**其实用Python写爬虫要比JS更方便:p**

DEMO地址：https://pyrsshub.vercel.app


## 交流

Discord Server： [https://discord.gg/4BZBZuyx7p](https://discord.gg/4BZBZuyx7p)

## RSS过滤

你可以通过以下查询字符串来过滤RSS的内容：

- include_title: 搜索标题，支持多关键词
- include_description: 搜索描述
- exclude_title: 排除标题
- exclude_description: 排除描述
- limit: 限制条数

## 贡献 RSS 方法

1. fork这份仓库
2. 在spiders文件夹下创建新的爬虫目录和脚本，编写爬虫，参考我的[爬虫教程](https://juejin.cn/post/6953881777756700709)
3. 在blueprints的main.py中添加对应的路由（按照之前路由的格式）
4. 在templates中的main目录下的feeds.html上写上说明文档，同样可参照格式写
5. 提pr

## 部署

### 本地测试

首先确保安装了[pipenv](https://github.com/pypa/pipenv)

``` bash
git clone https://github.com/alphardex/RSSHub-python
cd RSSHub-python
pipenv install --dev
pipenv shell
flask run
```

### 生产环境

``` bash
gunicorn main:app -b 0.0.0.0:5000
```

### 部署到 Vercel

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2Fhillerliao%2Frsshub-python)

### Docker 部署

创建docker容器 `docker run -dt --name pyrsshub -p 5000:5000 hillerliao/pyrsshub:latest`

## Requirements

- Python 3.8

