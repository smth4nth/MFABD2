#!/bin/bash
set -e

# 1. 挂载 binderfs（Ubuntu 24.04 / 内核 6.8 方式）
sudo modprobe binder_linux devices=binder,hwbinder,vndbinder
sudo mkdir -p /dev/binderfs
sudo mount -t binder binder /dev/binderfs

# 2. 持久化：重启后自动挂载
grep -q binderfs /etc/fstab || echo 'binder /dev/binderfs binder defaults 0 0' | sudo tee -a /etc/fstab

# 3. 启动 Redroid
cd ~/bd2-deploy
sudo docker compose up -d

echo "=== 等待 Redroid 启动 ==="
sleep 10

# 4. 连接 ADB
adb connect 127.0.0.1:5555
adb devices

echo "=== 部署完成 ===" # auto deploy test
