@echo off
chcp 65001 >nul
title DANTE - install
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_dante.ps1"
