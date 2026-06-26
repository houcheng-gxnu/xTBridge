# xTBridge

> **同一份 .gjf 输入，三个程序均可执行。** 扫描约束自动翻译，结构可视化不离开界面。

xTBridge 是一个面向 **xTB 预优化**的 Gaussian / xTB / ORCA 桌面计算前端。以 xTB 快速粗筛得到合理初始结构，再输入 Gaussian 或 ORCA 做高精度计算。

---

## 三个引擎，一个界面

顶部三个标签页，对应三种使用方式：

| 标签 | 引擎 | 适用场景 |
|---|---|---|
| ⚛️ Gaussian + xTB | External 联用 | xTB 算能量/梯度/Hessian，Gaussian 驱动优化/TS/IRC/频率/扫描 |
| 🚀 xTB 独立 | 纯 xTB | GFN2-xTB 直接优化/频率/扫描，秒级出结果 |
| 🐋 ORCA Submit | 纯 ORCA | SP/OPT/FREQ/NEB-TS/IRC/势能面扫描 |

每个标签页都是 **左侧参数 + 中间 3D 画布 + 右侧日志** 的三栏布局，同一分子在三个 Tab 间自动同步结构。

## 核心功能

### 1. 统一输入层——三个程序，一份输入

加载 `.gjf` 后，分子结构与扫描约束被解析为内部统一表示：
- 切至 **ORCA Tab** 自动生成合法 `.inp`
- 切至 **xTB Tab** 自动生成合法 `xcontrol`

键长 (B)、键角 (A)、二面角 (D) 的原子索引与步数步长全部自动对照，无需人工查语法或换算数值。

### 2. 优化

三种方式执行几何优化：
- **Gaussian + xTB 联用**：External 接口，路径由程序自动注入
- **xTB 独立优化**：`xtb input.xyz --opt --gfn 2`
- **ORCA 内置 XTB2**：`! XTB2 Opt`

优化完成后自动弹出最终结构查看器（支持拖拽旋转、滚轮缩放、右键平移），可一键导出 `.gjf` 接力下一轮高精度计算。

### 3. 扫描：高斯约束一键转 xTB / ORCA

在 `.gjf` 中写入 `modredundant` 约束（如 `D 3 1 5 6 S 6 60.0`），xTBridge 自动：
- 生成 ORCA `%geom Scan` 块
- 生成 xTB `$constrain` + `$scan` 块

扫描结果自带**能量折线图 + 结构联动查看器**，点击图中任一点即可查看对应结构并导出。

### 4. 过渡态

支持三条路径：

| 方式 | 引擎 | 说明 |
|---|---|---|
| TS (eigenvector following) | Gaussian + xTB | xTB 算 Hessian，Gaussian 驱动 TS 优化 |
| QST2 | Gaussian + xTB / ORCA | 给定反应物+产物，自动搜索 TS |
| NEB-TS | ORCA | 弹性带方法，可调 NImages、Free-End |

### 5. 其他特性

- 🎨 清爽浅色界面，中英文双语一键切换
- 💾 配置自动保存（method/basis/cores/memory/路径）
- 🔗 结构接力：扫描/优化/NEB-TS 结果均可一键导出 `.gjf`
- ⌨️ `Ctrl+O` 快速打开文件
- 🔄 **OfakeG 集成**：ORCA 输出可一键转 GaussView 兼容格式

## 适用范围

xTB 为半经验方法，几何结构可接近 DFT 优化结果，但能量与势垒与 DFT 存在系统性偏差。**本工具定位为预处理前端**——以 xTB 快速粗筛得到合理初始结构，再输入 Gaussian 或 ORCA 做高精度计算。

| 适合 | 典型场景 |
|---|---|
| 🧪 有机反应机理研究 | 扫描 + TS 搜索一条龙 |
| ⚗️ ORCA 催化计算 | NEB-TS / 势能面扫描 |
| 📚 计算化学教学 | 界面简单，学生上手快 |
| 🪟 Windows 用户 | 无需 WSL 或虚拟机即可联用 Gaussian + xTB |

## 快速开始

### 本地有 Python 环境

```bash
pip install pyqt5
python xtbridge/main.py
```

### 打包为独立 exe（无需 Python）

```bash
pyinstaller xTBridge.spec
```

项目内含 `xTBridge.spec`，已配置打包规则，直接执行即可。

### 运行环境

- **Windows**（主要平台）
- Gaussian 16 + xTB 程序 + ORCA（按需安装）

---

## 致谢

底层 xTB-Gaussian 接口方案来自以下前辈工作。xTBridge 在此基础上构建了输入格式翻译层与桌面 GUI 封装。

### 致谢与引用

本程序的底层驱动基于：

- **Sobereva 老师**：[将 Gaussian 与 Grimme 的 xtb 程序联用搜索过渡态、产生 IRC、做振动分析](http://sobereva.com/421)——提供 genxyz / extderi / xtb.sh 全套脚本，基于 Gaussian External 接口实现 xtb 算能量/梯度/Hessian，Gaussian 负责 TS 优化、IRC、freq、柔性扫描。

- [Gaussian 的 external 关键词使用方法详解](http://sobereva.com/g09/k_external.htm)——External 接口底层逻辑与文件交互规则。

- **Stardust0831 老师**：[跨平台实现 Gaussian 与 xTB 程序联用搜索过渡态、产生 IRC、做振动分析](http://bbs.keinsci.com/thread-59419-1-1.html) ([GitHub](https://github.com/Stardust0831/gau_xtb))——将 Sob 老师的方案从 Linux 集群移植到 Windows 平台，提供跨平台 Python 版脚本。

如果使用该接口，请引用：

> Tian Lu, gau_xtb: A Gaussian interface for xtb code, http://sobereva.com/soft/gau_xtb (accessed month day, year)

原帖讨论与反馈：http://bbs.keinsci.com/thread-59419-1-1.html

---

## 相关资源

- **xTB 程序**: [github.com/grimme-lab/xtb](https://github.com/grimme-lab/xtb) — Grimme 组开发的半经验量子化学程序
- **ORCA 论坛**: [orcaforum.kofo.mpg.de](https://orcaforum.kofo.mpg.de/app.php/portal) — ORCA 官方社区与文档

## 仓库

- **CNB**: https://cnb.cool/chem311/xTBridge
- **GitHub**: https://github.com/houcheng-gxnu/xTBridge

> 用 xTB 粗筛 → 导出好结构 → 喂给 Gaussian / ORCA 精算。优化、扫描、过渡态，一个界面搞定。
