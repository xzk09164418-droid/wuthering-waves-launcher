# 鸣潮启动辅助工具

通过官方启动器启动鸣潮，确认游戏进程稳定出现后退出，适合交给任务调度器串接后续操作。

## 工作方式

1. 按安装目录检查游戏进程；已经运行时等待稳定后直接成功退出。
2. 打开启动器，根据安装路径、进程归属和窗口标题定位窗口。
3. 优先读取 UIA 按钮，失败时在右下角按钮区域进行 RapidOCR 识别。
4. 只点击“开始游戏 / 进入游戏 / 启动游戏”；默认最多三次、间隔至少 20 秒，总超时 180 秒。
5. 成功返回 0，配置错误或超时返回 1。识别在子进程运行，避免 UIA 卡住导致永久等待。

## 安装与配置

Windows 10/11，建议 Python 3.13 x64。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item config.example.yaml config.yaml
```

编辑 `config.yaml` 的 `ww_launcher.launcher_exe` 和 `game_dir`，填入自己的鸣潮安装位置。

```powershell
.\.venv\Scripts\python.exe ww/start_game.py --check
.\.venv\Scripts\python.exe ww/start_game.py
```

`--check` 仅校验路径、配置和模块导入；不会点击启动器，也不证明 OCR 模型和 GPU 已实机可用。依赖清单复用更新器的工作环境，含 GPU 运行时；可用 `$env:OCR_ACCELERATOR='cpu'` 选择 CPU。首次 OCR 初始化可能下载模型，尚未验证全新机器依赖安装。

## 边界

需要已登录的 Windows 桌面，权限等级须与启动器一致。启动器正在更新时，本工具等待开始游戏按钮，不点击更新或预下载。不会为了完成启动而强杀游戏/启动器进程树。

仓库内 `update/updater/disaster/` 是所需 OCR、UIA 和窗口操作模块的源码副本，已随仓库提供，不要求安装完整更新器或调度器。本仓库不包含 OK-WW，也不包含本机专用的配置校正工具。

日志和识别截图写入 `ww/logs/`，默认不提交。

## 隐私、许可与致谢

本项目原创部分采用 [MIT License](LICENSE)。第三方依赖和素材遵守各自许可，详见 [第三方说明](THIRD_PARTY_NOTICES.md)。

感谢 **OpenAI GPT** 与 **DeepSeek** 在开发、排查问题和文档整理中的帮助，详见 [致谢](ACKNOWLEDGEMENTS.md)。本项目为个人工具，与游戏厂商、联想或 AI 模型提供方无官方关联。

真实配置、密钥、日志和截图请留在本机，详见 [隐私说明](PRIVACY.md)。首次发布为源码版本，不包含虚拟环境、游戏文件、驱动或预编译程序。
