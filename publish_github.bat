@echo off
chcp 65001 >nul
title Kypetz 一键发布至 GitHub
cd /d "%~dp0"
python publish_to_github.py
pause
