# 轻量 LaTeX 环境

使用官方 Tectonic 0.17.0 Linux x86_64 musl 二进制，在 `BDCI/tools/bin/tectonic`。
不安装全局 TeX Live，不修改 Git 或 `activate.sh`。编译器约25.2 MiB。
Tectonic 自身 MIT 许可，衍生组件及宏包采用各自许可证；保留 `BDCI/tools/TECTONIC-LICENSE`。

官方说明：https://tectonic-typesetting.github.io/book/latest/installation/
发布版本：https://github.com/tectonic-typesetting/tectonic/releases/tag/tectonic%400.17.0
下载包 SHA-256（与 GitHub release asset digest 核对一致）：
`8533d07f9ccbd7a65824b9e0459041bca34af1eb33daba48f59215593753a3b7`

从项目根目录运行：

```bash
bash BDCI/setup/latex-install.sh  # 仅重装时需要，下载约9.7 MiB压缩包
BDCI/tools/compile-latex.sh --keep-logs BDCI/validation/latex/smoke.tex
# 所需宏包已缓存后可以离线编译
BDCI/tools/compile-latex.sh --only-cached --keep-logs BDCI/validation/latex/smoke.tex
```

`compile-latex.sh` 明确调用 Tectonic 原生参数；未创建伪装为 `pdflatex` 或
`latexmk` 的命令。上游如果硬编码这两个命令，必须增加显式 Tectonic 后端，
不能只修改 PATH。Tectonic 自动执行多轮排版和 BibTeX；未验证 Biber、shell-escape
或其他外部绘图工具。普通英文论文优先使用标准宏包及预先生成的图表。

缓存默认在 `BDCI/tools/tectonic-cache`，可以用 `TECTONIC_CACHE_DIR` 覆盖。
首次编译会联网按需下载包，后续同文档可 `--only-cached` 离线复现；新宏包仍需联网。
不打包完整 bundle，以控制磁盘占用。缓存和二进制无需纳入源码贡献。

## 官方 ICLR 模板

来源：https://iclr.cc/Conferences/2026/AuthorGuide 链接的官方包：
https://raw.githubusercontent.com/ICLR/Master-Template/master/iclr2026.zip

原始 ZIP 保存在 `BDCI/tools/iclr2026-official.zip`；解包于
`BDCI/validation/latex/iclr-template/iclr2026/`，仅用于格式兼容验证。
这是 ICLR 2026 模板，不代表比赛指定年份或完整格式验收；正式提交前按比赛要求确认。
模板自带示例文字和参考文献属于官方示例，不能当成我们的论文或实验结果。
保留原文件版权/许可说明，不将模板标为本项目原创；模板 ZIP 本身未包含统一 LICENSE。

```bash
mkdir -p BDCI/validation/latex/iclr-build
BDCI/tools/compile-latex.sh --keep-logs --outdir BDCI/validation/latex/iclr-build \
  BDCI/validation/latex/iclr-template/iclr2026/iclr-tectonic.tex
```

编译输出独立放到 `iclr-build`，避免将模板包预装 PDF 误报为本地编译成果。

## 验证结果

- 最小英文正文、公式与表格：`validation/latex/smoke.pdf`，1 页，25,163 字节。
- 官方 ICLR 模板直接编译成功，但默认 TU 编码导致 Times 字体替代，不能用于严格格式验收。
- 增加独立 `iclr-tectonic.tex` 编译入口，先加载 `\RequirePackage[T1]{fontenc}`，再输入官方模板；官方模板文件保持原样。
- T1 入口生成 `validation/latex/iclr-build/iclr-tectonic.pdf`，7 页，67,048 字节，日志无字体形状替代警告。仍有官方示例 Underfull vbox 警告。
- 上述三个编译均退出 0，随后用 `--only-cached` 在无网络沙箱重复编译均退出 0。
- 二进制 26,401,904 字节；缓存约 44 MiB（详细字节数见 `latex-validation.json`），按需增加。
- 校验 PDF 文件头与 EOF，记录 SHA-256；未进行人工逐页视觉审稿，也未证明最终比赛格式合规。
- 日志：`latex-smoke*.log`、`latex-iclr*.log`；结构化结果：`latex-validation.json`。

后续生成 ICLR 文档时，在加载 ICLR 样式前显式启用 T1 字体编码；普通 `article` 文档不需要这个兼容处理。
