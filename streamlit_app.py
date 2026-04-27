#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Streamlit版论文阅读助手。"""

import base64
import re
import sys
from pathlib import Path
from typing import Dict, List

import pdfplumber
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))

from core.analyzer import AILiteratureAnalyzer
from core.config_manager import ConfigManager
from core.conversation_store import ConversationStore
from core.prompt_profiles import PromptProfileManager


PROJECT_ROOT = Path(__file__).parent


def normalize_math_markdown(content: str) -> str:
    """把常见LLM公式写法修正为Streamlit/KaTeX可渲染的Markdown。"""
    if not content:
        return ""

    content = re.sub(r"\\\[(.*?)\\\]", r"\n$$\1$$\n", content, flags=re.DOTALL)
    content = re.sub(r"\\\((.*?)\\\)", r"$\1$", content, flags=re.DOTALL)

    normalized_lines = []
    in_code_block = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            normalized_lines.append(line)
            continue

        if not in_code_block:
            looks_like_bracket_math = (
                stripped.startswith("[")
                and stripped.endswith("]")
                and "\\" in stripped
                and any(token in stripped for token in ("\\text", "\\frac", "\\sum", "\\operatorname", "_", "^", "="))
            )
            if looks_like_bracket_math:
                math_body = stripped[1:-1].strip()
                normalized_lines.append(f"$$\n{math_body}\n$$")
                continue

        normalized_lines.append(line)

    return "\n".join(normalized_lines)


def render_markdown(content: str) -> None:
    st.markdown(normalize_math_markdown(content))


@st.cache_resource
def load_services():
    config = ConfigManager()
    analyzer = AILiteratureAnalyzer(config)
    store = ConversationStore(config, analyzer)
    profile_manager = PromptProfileManager(config)
    return config, analyzer, store, profile_manager


def inject_css() -> None:
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1.4rem;
            max-width: 1160px;
        }
        [data-testid="stSidebar"] {
            background: #f6f7f9;
            border-right: 1px solid #d9dee7;
        }
        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3 {
            letter-spacing: 0;
        }
        .paper-title {
            font-size: 1.34rem;
            font-weight: 760;
            line-height: 1.25;
            margin-bottom: .2rem;
        }
        .paper-meta {
            color: #667085;
            font-size: .88rem;
            margin-bottom: .85rem;
        }
        .soft-panel {
            border: 1px solid #d9dee7;
            background: #ffffff;
            border-radius: 8px;
            padding: 14px 16px;
            margin: 10px 0 14px;
        }
        .memory-panel {
            border-left: 3px solid #1f7a68;
            background: #f1f7f5;
            padding: 10px 12px;
            border-radius: 6px;
            color: #24443c;
        }
        .small-muted {
            color: #667085;
            font-size: .84rem;
        }
        .stButton > button {
            width: 100%;
            border-radius: 7px;
            min-height: 36px;
        }
        div[data-testid="stChatMessage"] {
            border-radius: 8px;
        }
        iframe.pdf-frame {
            width: 100%;
            height: 720px;
            border: 1px solid #d9dee7;
            border-radius: 8px;
            background: #eef1f5;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def run_initial_analysis(analyzer: AILiteratureAnalyzer, profile_manager: PromptProfileManager, conversation: Dict) -> Dict[str, str]:
    pdf_path = Path(conversation["pdf_path"])
    pdf_text = analyzer.extract_pdf_text(pdf_path)
    if not pdf_text:
        raise RuntimeError("未能从PDF提取文本。若是扫描版PDF，请先OCR后再上传。")
    analyzer.save_extracted_text(pdf_path, pdf_text)

    profile = profile_manager.get_profile(conversation.get("profile_id"))
    analysis_messages = profile_manager.build_analysis_messages(
        profile,
        pdf_text,
        pdf_path.name,
        analyzer.max_text_length,
    )
    analysis = analyzer.call_ai_api(analysis_messages)
    if not analysis:
        raise RuntimeError("AI分析失败")

    method_card_messages = profile_manager.build_method_card_messages(profile, analysis)
    method_card = analyzer.call_ai_api(method_card_messages)
    return {"analysis": analysis, "method_card": method_card}


def render_pdf(pdf_path: Path) -> None:
    if not pdf_path.exists():
        st.info("PDF文件不存在。")
        return
    encoded = base64.b64encode(pdf_path.read_bytes()).decode("ascii")
    st.markdown(
        f'<iframe class="pdf-frame" src="data:application/pdf;base64,{encoded}"></iframe>',
        unsafe_allow_html=True,
    )


def extract_figure_table_context(pdf_path: Path, max_pages: int = 12, max_chars: int = 18000) -> str:
    """从PDF文本中抽取Figure/Table说明和可解析表格，用于非视觉图表分析。"""
    parts = []
    caption_pattern = re.compile(
        r"(?i)\b(?:fig(?:ure)?\.?|table)\s*\d+[a-z]?\b.*|(?:图|表)\s*\d+.*"
    )

    try:
        with pdfplumber.open(pdf_path) as pdf:
            page_count = min(len(pdf.pages), max_pages if max_pages > 0 else len(pdf.pages))
            for page_index in range(page_count):
                page = pdf.pages[page_index]
                text = page.extract_text() or ""
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                captions = collect_caption_blocks(lines, caption_pattern)
                if captions:
                    parts.append(f"## Page {page_index + 1} Captions")
                    parts.extend(f"- {caption}" for caption in captions[:8])

                tables = page.extract_tables() or []
                for table_index, table in enumerate(tables[:3], 1):
                    markdown_table = table_to_markdown(table, max_rows=8, max_cols=8)
                    if markdown_table:
                        parts.append(f"## Page {page_index + 1} Table {table_index}")
                        parts.append(markdown_table)

                if len("\n".join(parts)) > max_chars:
                    break
    except Exception as exc:
        return f"图表上下文抽取失败：{exc}"

    if not parts:
        return "未从PDF文本层抽取到明确的Figure/Table caption或可解析表格。若论文图像是扫描图、复杂曲线图、医学影像或超声图，建议后续接入视觉模型直接分析页面图像。"
    return "\n\n".join(parts)[:max_chars]


def collect_caption_blocks(lines: List[str], caption_pattern: re.Pattern, continuation_lines: int = 2) -> List[str]:
    captions = []
    seen = set()
    for index, line in enumerate(lines):
        if not caption_pattern.match(line):
            continue
        block = [line]
        for extra in lines[index + 1:index + 1 + continuation_lines]:
            if caption_pattern.match(extra) or re.match(r"^\d+(\.\d+)?\s+", extra):
                break
            if len(extra) > 160:
                block.append(extra)
                break
            block.append(extra)
        caption = " ".join(block)
        caption = re.sub(r"\s+", " ", caption).strip()
        if caption and caption not in seen:
            captions.append(caption)
            seen.add(caption)
    return captions


def table_to_markdown(table: List[List[str]], max_rows: int = 8, max_cols: int = 8) -> str:
    clean_rows = []
    for row in table[:max_rows]:
        clean = [normalize_table_cell(cell) for cell in (row or [])[:max_cols]]
        if any(clean):
            clean_rows.append(clean)
    if not clean_rows:
        return ""

    width = max(len(row) for row in clean_rows)
    clean_rows = [row + [""] * (width - len(row)) for row in clean_rows]
    header = clean_rows[0]
    separator = ["---"] * width
    body = clean_rows[1:]
    rows = [header, separator] + body
    return "\n".join("| " + " | ".join(row) + " |" for row in rows)


def normalize_table_cell(cell) -> str:
    value = "" if cell is None else str(cell)
    value = re.sub(r"\s+", " ", value).strip()
    return value.replace("|", "/")[:120]


def run_figure_table_analysis(
    analyzer: AILiteratureAnalyzer,
    profile_manager: PromptProfileManager,
    conversation: Dict,
) -> str:
    pdf_path = Path(conversation["pdf_path"])
    profile = profile_manager.get_profile(conversation.get("profile_id"))
    figure_table_context = extract_figure_table_context(
        pdf_path,
        max_pages=analyzer.extract_pages if analyzer.extract_pages > 0 else 12,
    )
    paper_analysis = conversation.get("analysis", "")[:6000]
    method_card = conversation.get("method_card", "")[:2500]
    messages = [
        {
            "role": "system",
            "content": (
                f"你是“{profile.get('name', '论文阅读')}”身份下的论文图表解读导师。"
                "你要分析论文Figure/Table说明了什么、如何支撑主结论、读图读表时应关注哪些指标、"
                "以及可能存在的误读、偏倚或证据不足。只能基于提供的caption、表格文本和已有论文分析，"
                "不能编造没有出现的图像细节。"
            ),
        },
        {
            "role": "user",
            "content": f"""当前论文：{pdf_path.name}

【已有精读分析节选】
{paper_analysis or '暂无'}

【方法卡片节选】
{method_card or '暂无'}

【从PDF抽取的Figure/Table上下文】
{figure_table_context}

请用中文输出一个“图表分析”板块，结构如下：

# 图表分析

## 1. 图表总览
- 识别到哪些Figure/Table？分别大概对应什么内容？
- 如果没有抽取到，请明确说明，并解释为什么可能需要视觉模型。

## 2. 逐图/逐表解读
- 每个Figure/Table说明了什么？
- 它在论文证据链中支撑哪个论点？
- 读者应重点看哪些变量、趋势、对照、统计显著性或指标？

## 3. 图表与主结论的关系
- 哪些图表最关键？
- 图表证据是否足以支撑作者结论？

## 4. 批判性读图读表
- 可能有哪些误读风险、展示偏差、统计/可视化问题或缺失信息？
- 如果是医学/影像/超声/AI实验图，指出还需要哪些补充验证。

## 5. 追问清单
- 给出5个我继续读图表时应追问的问题。

公式使用 `$...$` 或 `$$...$$`。
""",
        },
    ]
    result = analyzer.call_ai_api(messages)
    return result or "图表分析失败，请稍后重试。"


def render_sidebar(store: ConversationStore, profile_manager: PromptProfileManager, analyzer: AILiteratureAnalyzer) -> None:
    st.sidebar.title("论文对话")
    st.sidebar.caption("每篇论文一个独立上下文")

    profiles = profile_manager.list_profiles()
    profile_ids = [profile["id"] for profile in profiles]
    profile_names = {profile["id"]: profile["name"] for profile in profiles}

    with st.sidebar.expander("新建论文对话", expanded=not bool(store.list_conversations())):
        selected_profile_id = st.selectbox(
            "阅读身份",
            profile_ids,
            format_func=lambda profile_id: profile_names.get(profile_id, profile_id),
        )
        selected_profile = profile_manager.get_profile(selected_profile_id)
        st.caption(selected_profile.get("description", ""))
        uploaded = st.file_uploader("上传PDF", type=["pdf"], accept_multiple_files=False)
        if st.button("新建并精读", type="primary", disabled=uploaded is None):
            conversation = store.create_from_upload(
                uploaded.name,
                uploaded.getvalue(),
                profile_id=selected_profile["id"],
                profile_name=selected_profile["name"],
            )
            st.session_state.active_conversation_id = conversation["id"]
            st.session_state.pending_initial_analysis = conversation["id"]
            st.rerun()

    with st.sidebar.expander("身份设置", expanded=False):
        edit_profile_id = st.selectbox(
            "选择身份",
            profile_ids,
            format_func=lambda profile_id: profile_names.get(profile_id, profile_id),
            key="profile_settings_select",
        )
        edit_profile = profile_manager.get_profile(edit_profile_id)
        new_name = st.text_input("身份名称", value=edit_profile["name"], key=f"profile_name_{edit_profile_id}")
        st.caption(edit_profile.get("description", ""))
        if st.button("保存身份名称"):
            profile_manager.rename_profile(edit_profile_id, new_name)
            st.rerun()
        delete_related_count = sum(1 for item in store.list_conversations() if item.get("profile_id") == edit_profile_id)
        delete_disabled = len(profiles) <= 1
        st.caption(f"删除该身份会同时删除 {delete_related_count} 个相关论文窗口。")
        confirm_delete = st.checkbox(
            "确认删除该身份及其相关论文",
            key=f"confirm_delete_profile_{edit_profile_id}",
            disabled=delete_disabled,
        )
        if st.button("删除身份", disabled=delete_disabled or not confirm_delete):
            store.delete_by_profile(edit_profile_id)
            profile_manager.delete_profile(edit_profile_id)
            if st.session_state.get("active_conversation_id") and not store.load(st.session_state.active_conversation_id):
                remaining = store.list_conversations()
                st.session_state.active_conversation_id = remaining[0]["id"] if remaining else None
            st.rerun()

    with st.sidebar.expander("新建阅读身份", expanded=False):
        st.caption("例子：身份=医学研究生；领域=心血管疾病、超声诊断、医学AI；工作流=先判断临床问题，再看研究设计、统计方法、偏倚和转化价值。")
        profile_name = st.text_input("身份名称", placeholder="例如：公共卫生研究生 / 机器人方向博士 / 金融工程研究员")
        identity_description = st.text_area(
            "你的身份描述",
            placeholder="例如：我是一名医学研究生，日常需要读临床研究、影像诊断和医学AI论文，用于开题、组会和课题设计。",
            height=88,
        )
        research_fields = st.text_area(
            "核心研究领域",
            placeholder="例如：心血管系统疾病、心血管超声诊断、人工智能与大数据分析、风险预测模型。",
            height=88,
        )
        workflow = st.text_area(
            "读论文工作流",
            placeholder="例如：先看临床问题和PICO，再看纳排标准、样本量、终点、统计方法、偏倚风险、外部验证，最后整理可复现/可迁移的研究想法。",
            height=110,
        )
        can_create = bool(profile_name.strip() and identity_description.strip() and research_fields.strip() and workflow.strip())
        if st.button("调用大模型生成身份Prompt", type="primary", disabled=not can_create):
            with st.spinner("正在生成新身份的提示词..."):
                generated = profile_manager.generate_profile_prompt(
                    analyzer,
                    profile_name,
                    identity_description,
                    research_fields,
                    workflow,
                )
                profile_manager.create_profile(
                    profile_name,
                    identity_description,
                    research_fields,
                    workflow,
                    generated,
                )
            st.success("身份已创建。")
            st.rerun()

    st.sidebar.divider()
    conversations = store.list_conversations()
    if not conversations:
        st.sidebar.info("还没有论文对话。上传一篇PDF开始。")
        return

    active_id = st.session_state.get("active_conversation_id")
    if not active_id or not store.load(active_id):
        st.session_state.active_conversation_id = conversations[0]["id"]
        active_id = conversations[0]["id"]

    for conversation in conversations:
        title = conversation.get("title") or conversation.get("pdf_filename") or "未命名论文"
        profile_label = profile_manager.get_profile(conversation.get("profile_id")).get("name", conversation.get("profile_name", "论文阅读"))
        is_active = conversation["id"] == active_id
        left, right = st.sidebar.columns([0.78, 0.22], gap="small")
        label = ("● " if is_active else "") + f"{title}\n{profile_label}"
        if left.button(label, key=f"select_{conversation['id']}"):
            st.session_state.active_conversation_id = conversation["id"]
            st.rerun()
        if right.button("删", key=f"delete_{conversation['id']}"):
            store.delete(conversation["id"])
            if st.session_state.get("active_conversation_id") == conversation["id"]:
                remaining = store.list_conversations()
                st.session_state.active_conversation_id = remaining[0]["id"] if remaining else None
            st.rerun()

    st.sidebar.divider()
    st.sidebar.caption("记忆压缩：超过阈值后保留最近对话，并把更早追问压缩进当前论文专属记忆。")


def render_conversation(analyzer: AILiteratureAnalyzer, store: ConversationStore, profile_manager: PromptProfileManager, conversation: Dict) -> None:
    pdf_path = Path(conversation["pdf_path"])
    profile = profile_manager.get_profile(conversation.get("profile_id"))
    st.markdown(f'<div class="paper-title">{conversation.get("title", pdf_path.stem)}</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="paper-meta">{profile.get("name", "论文阅读")} · {pdf_path.name} · 创建于 {conversation.get("created_at", "")}</div>',
        unsafe_allow_html=True,
    )

    if st.session_state.get("pending_initial_analysis") == conversation["id"] and not conversation.get("analysis"):
        st.info("正在调用原分析流程生成完整精读报告。完成后会一次性显示，并开放追问。")
        try:
            with st.spinner("正在提取PDF文本并生成精读报告..."):
                result = run_initial_analysis(analyzer, profile_manager, conversation)
        except Exception as exc:
            st.error(f"分析失败：{exc}")
            st.session_state.pending_initial_analysis = None
            st.stop()

        store.update_analysis(conversation, result["analysis"], result["method_card"])
        conversation = store.load(conversation["id"]) or conversation
        store.persist_outputs(conversation)
        st.session_state.pending_initial_analysis = None
        st.rerun()

    tabs = st.tabs(["精读与追问", "图表分析", "论文材料", "记忆"])

    with tabs[0]:
        if conversation.get("analysis"):
            with st.chat_message("assistant"):
                render_markdown(conversation["analysis"])
        else:
            st.info("这篇论文还没有精读分析。")
            if st.button("开始精读", type="primary"):
                st.session_state.pending_initial_analysis = conversation["id"]
                st.rerun()

        for message in conversation.get("messages", []):
            with st.chat_message(message.get("role", "assistant")):
                render_markdown(message.get("content", ""))

        question = st.chat_input("基于这份精读报告继续追问", disabled=not bool(conversation.get("analysis")))
        if question:
            profile = profile_manager.get_profile(conversation.get("profile_id"))
            messages = store.build_followup_messages(conversation, question, profile)
            store.add_message(conversation, "user", question)
            with st.chat_message("user"):
                render_markdown(question)
            with st.chat_message("assistant"):
                with st.spinner("正在回答..."):
                    answer = analyzer.call_ai_api(messages)
                render_markdown(answer or "回答失败，请稍后重试。")
            conversation = store.load(conversation["id"]) or conversation
            store.add_message(conversation, "assistant", answer)
            conversation = store.load(conversation["id"]) or conversation
            store.maybe_compress_memory(conversation)
            st.rerun()

    with tabs[1]:
        if conversation.get("figure_table_analysis"):
            render_markdown(conversation["figure_table_analysis"])
            if st.button("重新生成图表分析"):
                with st.spinner("正在抽取Figure/Table并分析..."):
                    figure_table_analysis = run_figure_table_analysis(analyzer, profile_manager, conversation)
                store.update_figure_table_analysis(conversation, figure_table_analysis)
                st.rerun()
        else:
            st.info("这里会专门分析论文中的 Figure 和 Table。当前版本先基于PDF文本层的图题、表题和可抽取表格分析，不额外调用视觉模型。")
            st.caption("如果图是医学影像、超声图、复杂曲线或PDF没有文本层，后续可以接入视觉模型做页面级图像理解。")
            if st.button("生成图表分析", type="primary", disabled=not bool(conversation.get("analysis"))):
                with st.spinner("正在抽取Figure/Table并分析..."):
                    figure_table_analysis = run_figure_table_analysis(analyzer, profile_manager, conversation)
                store.update_figure_table_analysis(conversation, figure_table_analysis)
                st.rerun()

    with tabs[2]:
        with st.expander("PDF原文", expanded=False):
            render_pdf(pdf_path)
        with st.expander("PDF提取文本", expanded=False):
            extracted_text = store.read_extracted_text(conversation)
            st.text_area("PDF文本", extracted_text, height=520, label_visibility="collapsed")
        with st.expander("方法卡片", expanded=True):
            if conversation.get("method_card"):
                render_markdown(conversation["method_card"])
            else:
                st.info("方法卡片会在完成精读后自动生成。")

    with tabs[3]:
        st.markdown("#### 当前论文专属压缩记忆")
        memory = conversation.get("memory_summary") or "暂无压缩记忆。"
        st.markdown(f'<div class="memory-panel">{memory}</div>', unsafe_allow_html=True)
        st.caption(f"已压缩消息数：{conversation.get('compressed_count', 0)}")
        if st.button("立即压缩当前会话"):
            store.maybe_compress_memory(conversation, threshold_chars=0)
            st.rerun()


def main() -> None:
    st.set_page_config(page_title="论文阅读助手", page_icon="📚", layout="wide")
    inject_css()
    _, analyzer, store, profile_manager = load_services()
    render_sidebar(store, profile_manager, analyzer)

    active_id = st.session_state.get("active_conversation_id")
    conversation = store.load(active_id) if active_id else None
    if not conversation:
        st.title("论文阅读助手")
        st.markdown(
            '<div class="soft-panel">从左侧上传一篇PDF，新建一个独立论文对话。系统会先调用原分析流程生成完整精读报告，之后你可以基于报告继续追问。</div>',
            unsafe_allow_html=True,
        )
        return

    render_conversation(analyzer, store, profile_manager, conversation)


if __name__ == "__main__":
    main()
