# 第三方来源与许可范围

本清单针对 0.2.36 的本机依赖、素材来源以及本次源码展示快照。版本来自项目固定依赖和已安装分发物；上游具体文件的版权及附带条款始终优先。

作者创作及有权授权的 AI 辅助产出采用非商业源码可见许可，**这不改变任何第三方组件原有的许可证和商业使用权**。AI 生成或加工不会将第三方内容自动转为作者所有。下表描述源码树的分发范围；Release 整合包另外包含运行依赖与资源。

## 软件与字体

| 组件 | 记录版本 | 原许可证／来源 | 本次分发 |
| --- | --- | --- | --- |
| [Qt for Python / PySide6 Essentials](https://doc.qt.io/qtforpython-6/licenses.html) | 6.10.2 | LGPLv3 等上游条款；见 `licenses/Qt-PySide6-NOTICE.txt`、LGPL／GPL 原文 | 仅依赖声明和通知，不附库文件 |
| [MaaFramework](https://github.com/MaaXYZ/MaaFramework) | 5.14.2 | LGPL-3.0；原文见 `licenses/MaaFramework-LICENSE.md` | 仅依赖声明和许可，不附库文件 |
| [MaaAgentBinary](https://github.com/MaaXYZ/MaaAgentBinary) | 1.0.1 | AGPL-3.0；见 `licenses/MaaAgentBinary-LICENSE` | 不附二进制；关联 Android 适配源码／DEX 同样从本次展示快照排除 |
| [MaaTouch](https://github.com/MaaXYZ/MaaTouch) | 随历史设备工具使用 | Apache-2.0 的上游来源；MaaAgentBinary 分发物另有 AGPL 声明 | 仅保留原许可供来源核对，不替代组合分发审查 |
| [OpenCV](https://github.com/opencv/opencv-python) | 4.11.0.86 | Apache-2.0 及所包含第三方条款；见 `licenses/cv2-LICENSE*` | 仅依赖声明和通知 |
| [NumPy](https://github.com/numpy/numpy) | 2.5.3 | BSD-3-Clause，分发物另含 0BSD／MIT／Zlib／CC0 等声明 | 仅依赖声明 |
| [RapidOCR](https://github.com/RapidAI/RapidOCR) | 1.4.4 | Apache-2.0；模型与数据另核对 | 仅依赖声明，不附模型 |
| [ONNX Runtime](https://github.com/microsoft/onnxruntime) | 1.30.0 | MIT；见 `licenses/onnxruntime-LICENSE` | 仅依赖声明和许可 |
| [windows-capture](https://github.com/NiiightmareXD/windows-capture) | 2.0.1 | MIT | 仅依赖声明 |
| [Pillow](https://github.com/python-pillow/Pillow) | 12.3.0 | MIT-CMU 及分发物中的附加通知 | 仅依赖声明 |
| [StrEnum](https://github.com/irgeek/StrEnum) | 0.4.15 | 以上游分发物中的 MIT 声明为准 | 仅依赖声明 |
| [Chiron GoRound TC](https://github.com/chiron-fonts/chiron-go-round-tc) | 本机字库子集 | SIL OFL 1.1；见 `licenses/ChironGoRoundTC-OFL.txt` | 包含三个运行用字体子集和许可；没有追加禁止商用条款 |

构建工具 PyInstaller、FontTools、JDK 和 D8／R8 没有作为运行二进制随本仓库提供。使用或分发它们的输出时仍需核对工具、依赖及输出中实际包含内容的条件。

## 代码来源

作者确认，历史说明中提及的 HoloDream AutoFish 原型属于作者自己的旧项目代码。钓鱼的部分输入和窗口逻辑从该原型沿用，不宣称由本次 AI 协作从零发明。各依赖的实现不因此成为作者原创。

本次展示不包含 `tools/maatouch-display/` 和 `assets/maatouch-display.dex`。本机适配层与 MaaTouch／MaaAgentBinary 的运行类协同使用，不把这些部分重新标为非商业许可。其组成、源代码和对应二进制的分发义务需要独立审查，不能据本仓库推导“完整程序禁止商用”。

## 游戏素材、资料与截图

- 角色图片、名称与图鉴资料曾取自 [TataDex](https://tatadex.org/zh/tatari/)，记录时间为 2026-10-14。TataDex 是玩家资料站，公开可访问不等于允许再分发美术。
- 寻宝关卡事实参考过 [TataDex 寻宝资料](https://tatadex.org/zh/events/treasure-hunt/)，本地求解逻辑独立实现；不宣称复用了资料站的完整算法。
- 游戏截图中的提示、棋盘、按钮、角色与奖励，以及从它们提取的识别模板，保留原权利。
- 部分图标由 AI 辅助抠图、去背景和清理边缘。这样的处理不消除原美术的权利，也不等于可以把原图归为作者原创。
- 本次源码快照不包含原始游戏图包、图鉴集合、识别模板、AI 派生游戏图标或现场诊断截图。具体缺失路径见 `docs/RESOURCE_MANIFEST.json`。
- `docs/media/` 的界面截图用于作品说明；图中第三方美术、字体及标识各自保留权利，不提供独立提取素材再利用的许可。

## 历史与当前范围

`licenses/` 中留存的旧字体、Tcl／Tk 和依赖许可，是来源记录，不代表本次快照实际携带了对应软件。当前字体是 Chiron GoRound TC；当前源码展示不捆绑 Qt、Maa 或 Python 运行时。

整合可执行程序不进入 Git 源码树。Release 中的组件与素材保留原许可和权利；再分发时需核对实际组成、对应源码及素材授权。本清单不是对整合包的合规认证。
