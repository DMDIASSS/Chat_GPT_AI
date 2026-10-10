@echo off
cd /d "%~dp0"
"C:\Users\almas\AppData\Local\Programs\Python\Python311\python.exe" hub_eval.py --models smoke_balanced_01 shootingv1 defense1v1 --pairs 20 --decisions 900
pause
