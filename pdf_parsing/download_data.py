#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SCOW 赛题数据下载脚本
# 使用方法: python download_data.py

import os
import sys

# 配置
SERVER_HOST = "221.226.39.110"
SFTP_PORT = 2222
USERNAME = "download"
PASSWORD = "CuT9THeWX7hQSoYiFkhQ7ITuOAO4R9eX"
REMOTE_FILE = "/07-智能风控与量化建模赛道-东吴证券-基于多智能体协同的港股IPO招股书解析与上市后风险预警探索.zip"
LOCAL_FILE = "07-智能风控与量化建模赛道-东吴证券-基于多智能体协同的港股IPO招股书解析与上市后风险预警探索.zip"

print("=" * 50)
print("SCOW 赛题数据下载工具")
print("=" * 50)
print(f"服务器: {SERVER_HOST}:{SFTP_PORT}")
print(f"文件: {REMOTE_FILE}")
print("=" * 50)

try:
    import paramiko
except ImportError:
    print("\n[错误] 需要先安装 paramiko 库")
    print("请运行: pip install paramiko")
    input("按回车键退出...")
    sys.exit(1)

def download_with_progress():
    transport = paramiko.Transport((SERVER_HOST, SFTP_PORT))
    transport.connect(username=USERNAME, password=PASSWORD)

    sftp = paramiko.SFTPClient.from_transport(transport)

    # 获取文件大小
    remote_stat = sftp.stat(REMOTE_FILE)
    total_size = remote_stat.st_size
    downloaded = 0

    print(f"\n文件大小: {total_size / 1024 / 1024:.1f} MB")
    print("开始下载...\n")

    def callback(curr, total):
        percent = (curr / total) * 100
        bar = "█" * int(percent / 5) + "░" * (20 - int(percent / 5))
        print(f"\r{bar} {percent:.1f}% ({curr/1024/1024:.1f}MB / {total/1024/1024:.1f}MB)", end="", flush=True)

    sftp.get(REMOTE_FILE, LOCAL_FILE, callback=callback)

    print("\n\n✓ 下载完成!")
    print(f"文件保存为: {os.path.abspath(LOCAL_FILE)}")

    sftp.close()
    transport.close()

if __name__ == "__main__":
    try:
        download_with_progress()
    except Exception as e:
        print(f"\n[错误] 下载失败: {e}")
        input("按回车键退出...")
