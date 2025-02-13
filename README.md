IMAGE_NAME=$(basename $(pwd))
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
sudo docker image tag ${IMAGE_NAME} ${HUB_USER_NAME}/${IMAGE_NAME}:latest
sudo docker image push ${HUB_USER_NAME}/${IMAGE_NAME}:latest
fi
EOF
chmod +x upload
