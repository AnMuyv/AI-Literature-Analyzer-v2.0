# AI Literature Analyzer v2.0

一个面向研究生论文精读工作流的 AI 文献阅读助手。项目以 Streamlit Web 界面为主入口，支持按论文管理对话、不同研究身份切换、导师式精读报告、方法卡片、图表分析和论文内追问。

> 本项目基于 [Yudong Fang](https://github.com/yudongfang-thu) 的开源项目 [AI-Literature-Analyzer](https://github.com/yudongfang-thu/AI-Literature-Analyzer) 修改而来。原项目采用 MIT License，原作者版权声明保留在 [LICENSE](LICENSE) 中。

## 协议与开源说明

原项目使用 MIT License。该协议允许复制、修改、发布、再分发和商用，但要求在所有副本或主要部分中保留原版权声明和许可文本。因此，你可以将本修改版发布到 GitHub 开源，但需要注意：

- 保留仓库中的 [LICENSE](LICENSE)，不要删除原作者版权声明。
- 在 README 中明确说明本项目基于原作者项目修改而来。
- 不要提交真实 API Key、私人论文 PDF、分析结果、会话记录或本地虚拟环境。
- 如果真实 API Key 曾经提交到 Git 历史中，应撤销/轮换该 Key，并在发布前清理 Git 历史。

本 README 不是法律意见；如果后续用于商业发行或机构合规场景，建议再做正式审查。

## 主要功能

- **Streamlit Web 阅读台**：浏览器中上传 PDF、生成精读报告并持续追问。
- **每篇论文一个独立窗口**：像 ChatGPT 侧边栏一样切换、删除论文对话。
- **多身份热插拔**：内置 AI 方向研究生、医学研究生身份，也可以在 Web 中新建身份。
- **自动生成身份 Prompt**：输入身份描述、研究领域和工作流，由大模型生成该身份的阅读提示词。
- **导师式精读报告**：强调背景铺垫、方法拆解、证据链、局限、复现建议和行动清单。
- **方法卡片**：将论文方法压缩成适合复习、组会和后续复现的结构化笔记。
- **图表分析**：抽取 Figure/Table caption 和可解析表格，专门分析图表证据链与读图读表重点。
- **上下文隔离与记忆压缩**：不同论文、不同身份互不污染，长对话会压缩成当前论文专属记忆。
- **公式渲染修正**：自动修正常见 Markdown/LaTeX 公式格式，改善 Streamlit 显示效果。

## 精简后的目录结构

```text
AI-Literature-Analyzer-v2.0/
├── streamlit_app.py              # Streamlit Web 主入口
├── main.py                       # 保留的 CLI 批量分析入口
├── requirements.txt              # Python 依赖
├── config/
│   ├── config.yaml               # 示例配置
│   └── config.yaml.example       # 配置模板
├── src/
│   ├── core/
│   │   ├── analyzer.py           # PDF 文本抽取与 LLM API 调用
│   │   ├── config_manager.py     # 配置加载
│   │   ├── conversation_store.py # 论文窗口、会话和记忆存储
│   │   └── prompt_profiles.py    # 阅读身份与 Prompt 管理
│   └── utils/
│       └── progress_monitor.py   # CLI 进度监控
├── prompts/                      # CLI 兼容的默认 Prompt 模板
├── data/
│   ├── input/.gitkeep            # 本地 PDF 输入目录
│   └── output/                   # 本地分析输出
├── LICENSE                       # 原项目 MIT License
└── README.md
```

## 安装

建议使用虚拟环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

如果你已经有 `.venv`，只需：

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

## 配置 API

编辑 `config/config.yaml`：

```yaml
api:
  api_key: "your-api-key-here"
  base_url: "https://api.siliconflow.cn/v1"
  model: "Pro/deepseek-ai/DeepSeek-R1"
```

如果使用其他 OpenAI-compatible 网关，修改 `base_url` 和 `model` 即可。

安全建议：

- 不要把真实 API Key 提交到 GitHub。
- 建议复制为本地配置文件，例如 `config/my_config.yaml`，并把该文件保持在 `.gitignore` 中。
- 如果 Key 曾经暴露，请到服务商后台轮换。

## 启动 Streamlit

在项目根目录运行：

```bash
.venv/bin/streamlit run streamlit_app.py --server.address 127.0.0.1 --server.port 8501
```

浏览器打开：

```text
http://127.0.0.1:8501
```

如果已经激活虚拟环境，也可以运行：

```bash
streamlit run streamlit_app.py --server.address 127.0.0.1 --server.port 8501
```

### 局域网访问

如果希望同一 Wi-Fi 下的手机或平板访问，把监听地址改成 `0.0.0.0`：

```bash
.venv/bin/streamlit run streamlit_app.py --server.address 0.0.0.0 --server.port 8501
```

然后查看电脑局域网 IP，例如 macOS：

```bash
ipconfig getifaddr en0
```

假设输出为 `192.168.1.23`，手机浏览器访问：

```text
http://192.168.1.23:8501
```

## 关闭 Streamlit

### 方法一：在运行窗口按 Ctrl+C

如果 Streamlit 正在当前终端运行，直接按：

```text
Ctrl+C
```

### 方法二：通过端口查 PID 后关闭

如果终端窗口已经关闭，或提示端口被占用：

```bash
lsof -nP -iTCP:8501 -sTCP:LISTEN
```

输出类似：

```text
COMMAND   PID   USER   FD   TYPE DEVICE SIZE/OFF NODE NAME
Python  40337  user    6u  IPv4 ...    TCP 127.0.0.1:8501 (LISTEN)
```

关闭对应进程：

```bash
kill 40337
```

注意不要带尖括号。错误写法是：

```bash
kill <40337>
```

如果普通 `kill` 后仍然占用，可再确认 PID 是否变化：

```bash
lsof -nP -iTCP:8501 -sTCP:LISTEN
```

然后对新的 PID 再执行 `kill <PID>`。如果只是临时想启动，也可以换端口：

```bash
.venv/bin/streamlit run streamlit_app.py --server.address 127.0.0.1 --server.port 8502
```

## Web 使用流程

1. 打开 Streamlit 页面。
2. 在左侧选择阅读身份。
3. 上传一篇 PDF，新建论文窗口。
4. 系统生成完整精读报告和方法卡片。
5. 在 `精读与追问` 中继续提问。
6. 在 `图表分析` 中生成 Figure/Table 专项分析。
7. 在 `论文材料` 中查看 PDF、提取文本和方法卡片。
8. 在 `记忆` 中查看当前论文专属压缩记忆。

## 阅读身份

默认内置：

- `AI方向研究生`：对话、图像处理、微调、Agent、多模态、高效 AI 等方向。
- `医学研究生`：心血管系统疾病、心血管超声诊断、医学 AI 与大数据分析。

你也可以在 Web 侧边栏新建身份，需要填写：

- 身份名称
- 身份描述
- 核心研究领域
- 读论文工作流

系统会调用当前配置的大模型自动生成该身份的完整 Prompt。身份配置保存在：

```text
data/output/reader_profiles.json
```

该文件是本地数据，默认不提交到 Git。

删除身份时，该身份创建的所有论文窗口、上传 PDF、分析报告、方法卡片、提取文本和会话记忆都会被删除。

## 图表分析说明

当前版本不额外调用视觉模型，而是优先使用 PDF 文本层：

- Figure/Table caption
- 表题、图题和附近说明
- `pdfplumber` 能解析出的表格内容

适合分析图表在论文证据链中的作用、表格指标含义、结果支撑关系和读图读表问题。

如果要分析以下内容，建议后续接入视觉模型：

- 医学影像、心血管超声图
- 扫描版 PDF
- 热力图、注意力图、复杂曲线图
- 图中颜色、坐标轴、标注、病灶或结构形态

## CLI 用法

仍保留原项目的 CLI 入口：

```bash
python main.py --test
python main.py --analyze
python main.py --analyze --limit 5
python main.py --progress
```

CLI 主要用于批量处理 `data/input/` 中的 PDF；日常交互式读论文推荐使用 Streamlit。

## 本地数据与 GitHub 发布注意事项

以下内容不应提交到 GitHub：

- `.venv/`、`.venv-1/` 等虚拟环境
- `__pycache__/`
- `data/input/*.pdf`
- `data/output/**/*.md`
- `data/output/**/*.json`
- `data/output/**/*.txt`
- `data/output/analyzer.log`
- 任何包含真实 API Key 的配置文件

发布前建议检查：

```bash
git status --short
```

确认没有 PDF、分析结果、真实配置或缓存文件进入提交。

## 致谢

本项目基于 Yudong Fang 的 [AI-Literature-Analyzer](https://github.com/yudongfang-thu/AI-Literature-Analyzer) 修改开发。感谢原作者提供的 MIT 开源项目基础，包括 PDF 文本抽取、配置管理、批量分析和提示词模板等核心结构。

原作者版权声明见 [LICENSE](LICENSE)：

```text
Copyright (c) 2024 Yudong Fang (yudongfang55@gmail.com)
```

## License

本项目继续遵循 MIT License。详见 [LICENSE](LICENSE)。
