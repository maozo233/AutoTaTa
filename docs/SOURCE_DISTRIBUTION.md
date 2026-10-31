# 源码展示与复现边界

仓库提供 **0.2.36 的非商业源码展示**，不包含完整运行资源。Windows x64 all 包见 [Release](https://github.com/maozo233/AutoTaTa/releases/tag/v0.2.36)；源码树与整合包所含内容不同。

## 包含什么

- Python 功能代码、Qt Quick 页面、自制 SVG、应用字标与说明文档，包括作者有权授权的 AI 辅助产出。
- 原测试代码和发布保留策略；包含运行所需素材不代表授予素材版权，因此测试图片没有一并上传。
- 许可明确的 Chiron GoRound TC 字体子集及原 OFL 许可。
- 实际程序的界面截图与中英文两张仓库封面。

## 不包含什么

- `.venv/`、`build/`、`dist/`、`releases/`、临时文件与个人快捷方式。
- 用户配置、设备或账号信息、日志、诊断包、现场截图、录屏和内部历史压缩包。
- 原始游戏素材、图鉴资源与识别模板、从游戏素材派生的 AI 图标。
- AGPL 关联 Android 适配源码、已编译 DEX、MaaAgentBinary／ADB 等第三方二进制、OCR 模型和开发工具安装文件。
- 尚未单独授权公开的可编辑 Figma 原件。

未分发运行资源的相对路径、摘要和类别记录在 [资源清单](RESOURCE_MANIFEST.json) 中。

## 先看哪些代码

- 界面：`assets/ui/AutoTaTa.qml`、`LineupPage.qml`、`Main.qml`、`TreasurePage.qml`、`RaftingPage.qml`。
- 交互与状态：`autotata/app.py`、各功能的 `backend.py`、`lineup/engine.py`。
- 识别与求解：`lineup/vision.py`、`lineup/recognition.py`、`treasure/solver.py`。

## 资源检查

```powershell
python tools/check_source_assets.py
python tools/check_source_assets.py --strict
```

检查器只读取本地资源清单，不连接设备、不发送输入，也不下载素材。正常展示模式列出未分发资源；`--strict` 在缺失或摘要不匹配时返回非零退出码，供尝试运行前核对。

不要把任意下载的图包或他人的现场诊断包放进仓库。只有在有权使用、路径和版本匹配的前提下，才可自行补齐资源；重新分发需要另行核对权利。

## 可以单独研究的计算部分

Windows x64、Python 3.12 是原开发环境。依赖版本固定于 `requirements.txt`，停止维护后不保证新环境仍可安装或兼容。

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m unittest tests.test_treasure_solver tests.test_treasure_enumeration
```

上述测试研究本地求解与枚举，不需要连接游戏。其余 UI／图像测试可能依赖被排除的资源、Windows 图形环境及设备条件；不应直接把缺少资源的展示仓库当作完整测试环境。

## 研究完整运行时

需要合法准备游戏资源、适配组件与第三方依赖后，再参考 [历史使用说明](USAGE.md)。MaaAgentBinary 和关联 Android 适配层的许可证与作者非商业许可不能混为一谈，本快照不提供对整合程序重新分发的许可结论。

再分发整合包前，应核对第三方组件的许可、对应源码义务与素材权利。详见 [授权范围](legal/LICENSE_SCOPE.md) 和 [第三方来源](legal/THIRD_PARTY_NOTICES.md)。项目不提供技术支持或持续维护。
