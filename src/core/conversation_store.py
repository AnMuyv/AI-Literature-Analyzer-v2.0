#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按论文隔离的对话存储与记忆压缩。"""

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .analyzer import AILiteratureAnalyzer
from .config_manager import ConfigManager


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def safe_filename(filename: str) -> str:
    name = Path(filename).name.strip()
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = re.sub(r"\s+", " ", name)
    return name or "paper.pdf"


class ConversationStore:
    """管理每篇论文独立的会话、消息和压缩记忆。"""

    def __init__(self, config: ConfigManager, analyzer: AILiteratureAnalyzer):
        self.config = config
        self.analyzer = analyzer
        paths = self.config.get_paths_config()
        self.project_root = self.config.project_root
        self.input_dir = Path(paths["input_dir"])
        self.output_dir = Path(paths["output_dir"])
        self.conversations_dir = self.output_dir / "conversations"
        self.conversations_dir.mkdir(parents=True, exist_ok=True)
        self.input_dir.mkdir(parents=True, exist_ok=True)

    def conversation_path(self, conversation_id: str) -> Path:
        return self.conversations_dir / f"{conversation_id}.json"

    def list_conversations(self) -> List[Dict[str, Any]]:
        conversations = []
        for path in self.conversations_dir.glob("*.json"):
            conversation = self.load(path.stem)
            if conversation:
                conversations.append(conversation)
        return sorted(conversations, key=lambda item: item.get("updated_at", ""), reverse=True)

    def load(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        path = self.conversation_path(conversation_id)
        if not path.exists():
            return None
        try:
            conversation = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        conversation.setdefault("profile_id", "ai_researcher")
        conversation.setdefault("profile_name", "AI方向研究生")
        conversation.setdefault("figure_table_analysis", "")
        return conversation

    def save(self, conversation: Dict[str, Any]) -> None:
        conversation["updated_at"] = now_iso()
        path = self.conversation_path(conversation["id"])
        path.write_text(
            json.dumps(conversation, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def delete(self, conversation_id: str) -> None:
        conversation = self.load(conversation_id)
        if conversation:
            for output_path in self.text_paths_for(conversation).values():
                if output_path.exists():
                    try:
                        output_path.unlink()
                    except OSError:
                        pass
            pdf_path = Path(conversation.get("pdf_path", ""))
            if pdf_path.exists() and pdf_path.parent == self.input_dir:
                try:
                    pdf_path.unlink()
                except OSError:
                    pass
        path = self.conversation_path(conversation_id)
        if path.exists():
            path.unlink()

    def delete_by_profile(self, profile_id: str) -> int:
        deleted_count = 0
        for conversation in self.list_conversations():
            if conversation.get("profile_id") == profile_id:
                self.delete(conversation["id"])
                deleted_count += 1
        return deleted_count

    def create_from_upload(self, filename: str, content: bytes, profile_id: str = "ai_researcher", profile_name: str = "AI方向研究生") -> Dict[str, Any]:
        conversation_id = datetime.now().strftime("%Y%m%d%H%M%S") + "_" + uuid4().hex[:8]
        filename = safe_filename(filename)
        pdf_path = self.input_dir / f"{conversation_id}_{filename}"
        pdf_path.write_bytes(content)

        title = Path(filename).stem[:80]
        conversation = {
            "id": conversation_id,
            "title": title,
            "pdf_filename": filename,
            "pdf_path": str(pdf_path),
            "profile_id": profile_id,
            "profile_name": profile_name,
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "analysis": "",
            "method_card": "",
            "figure_table_analysis": "",
            "memory_summary": "",
            "compressed_count": 0,
            "messages": []
        }
        self.save(conversation)
        return conversation

    def attach_existing_pdf(self, pdf_path: Path) -> Dict[str, Any]:
        content = pdf_path.read_bytes()
        return self.create_from_upload(pdf_path.name, content)

    def add_message(self, conversation: Dict[str, Any], role: str, content: str) -> None:
        conversation.setdefault("messages", []).append({
            "role": role,
            "content": content,
            "created_at": now_iso()
        })
        self.save(conversation)

    def update_analysis(self, conversation: Dict[str, Any], analysis: str, method_card: str = "") -> None:
        conversation["analysis"] = analysis
        conversation["method_card"] = method_card
        self.save(conversation)

    def update_figure_table_analysis(self, conversation: Dict[str, Any], analysis: str) -> None:
        conversation["figure_table_analysis"] = analysis
        self.save(conversation)

    def text_paths_for(self, conversation: Dict[str, Any]) -> Dict[str, Path]:
        pdf_path = Path(conversation["pdf_path"])
        safe_name = self.analyzer._safe_filename(pdf_path.stem)
        output_config = self.config.get_output_config()
        return {
            "analysis": self.analyzer.summaries_dir / f"{safe_name}{output_config['summary_suffix']}.md",
            "card": self.analyzer.method_cards_dir / f"{safe_name}{output_config['method_card_suffix']}.md",
            "extracted": self.analyzer.get_extracted_text_path(pdf_path),
        }

    def persist_outputs(self, conversation: Dict[str, Any]) -> None:
        pdf_path = Path(conversation["pdf_path"])
        if conversation.get("analysis"):
            self.analyzer._save_analysis_report(pdf_path, {
                "analysis": conversation["analysis"],
                "success": True
            })
        if conversation.get("method_card"):
            self.analyzer._save_method_card(pdf_path, conversation["method_card"])

    def build_initial_messages(self, pdf_text: str, pdf_filename: str) -> List[Dict[str, str]]:
        content = pdf_text[:self.analyzer.max_text_length]
        analysis_prompt = self.analyzer.analysis_template.format(
            filename=pdf_filename,
            content=content
        )
        return [
            {
                "role": "system",
                "content": "你是一名面向AI方向研究生的论文精读导师。你要像导师带学生读paper一样解释论文，重视直觉、方法细节、实验可信度、局限和可复现实验建议。"
            },
            {"role": "user", "content": analysis_prompt}
        ]

    def build_followup_messages(self, conversation: Dict[str, Any], question: str, profile: Dict[str, Any] = None) -> List[Dict[str, str]]:
        pdf_path = Path(conversation["pdf_path"])
        extracted_text = self.read_extracted_text(conversation)
        paper_context = extracted_text[: min(self.analyzer.max_text_length, 9000)]
        analysis = conversation.get("analysis", "")[:7000]
        method_card = conversation.get("method_card", "")[:3500]
        memory = conversation.get("memory_summary", "")
        recent_messages = conversation.get("messages", [])[-8:]

        system_prompt = (
            profile.get("followup_system_prompt")
            if profile
            else (
                "你是这篇论文的专属精读导师。只使用当前论文、当前会话记忆和用户追问来回答；"
                "不要混入其他论文的上下文。回答要像老师讲解学生不懂的点，必要时回到论文原文依据。"
            )
        )

        messages = [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": (
                    f"当前论文文件：{pdf_path.name}\n\n"
                    f"【论文提取文本节选】\n{paper_context}\n\n"
                    f"【已有精读分析】\n{analysis}\n\n"
                    f"【方法卡片】\n{method_card}\n\n"
                    f"【压缩记忆】\n{memory or '暂无'}"
                )
            }
        ]

        for item in recent_messages:
            if item.get("role") in {"user", "assistant"}:
                messages.append({"role": item["role"], "content": item.get("content", "")})
        messages.append({"role": "user", "content": question})
        return messages

    def read_extracted_text(self, conversation: Dict[str, Any]) -> str:
        pdf_path = Path(conversation["pdf_path"])
        text_path = self.analyzer.get_extracted_text_path(pdf_path)
        if text_path.exists():
            return text_path.read_text(encoding="utf-8", errors="replace")
        pdf_text = self.analyzer.extract_pdf_text(pdf_path)
        if pdf_text:
            self.analyzer.save_extracted_text(pdf_path, pdf_text)
        return pdf_text

    def maybe_compress_memory(self, conversation: Dict[str, Any], threshold_chars: int = 12000) -> None:
        messages = conversation.get("messages", [])
        total_chars = sum(len(item.get("content", "")) for item in messages)
        min_messages = 3 if threshold_chars == 0 else 8
        if total_chars < threshold_chars or len(messages) <= min_messages:
            return

        old_messages = messages[:-6]
        recent_messages = messages[-6:]
        transcript = "\n\n".join(
            f"{item.get('role', 'unknown')}: {item.get('content', '')}"
            for item in old_messages
        )
        prompt = f"""请压缩下面这篇论文专属对话记忆，供后续追问使用。

要求：
- 只保留用户已经问过什么、助手已解释过什么、用户仍可能困惑什么。
- 保留重要术语解释、实验判断、复现建议和用户偏好。
- 不要引入其他论文信息。
- 输出不超过900字。

已有压缩记忆：
{conversation.get('memory_summary') or '暂无'}

需要压缩的旧消息：
{transcript}
"""
        summary = self.analyzer.call_ai_api([
            {"role": "system", "content": "你是论文阅读助手的会话记忆压缩器。"},
            {"role": "user", "content": prompt}
        ])
        if not summary:
            summary = self.local_memory_fallback(old_messages)

        conversation["memory_summary"] = summary
        conversation["compressed_count"] = conversation.get("compressed_count", 0) + len(old_messages)
        conversation["messages"] = recent_messages
        self.save(conversation)

    def local_memory_fallback(self, messages: List[Dict[str, Any]]) -> str:
        snippets = []
        for item in messages[-10:]:
            content = item.get("content", "").strip().replace("\n", " ")
            if content:
                snippets.append(f"{item.get('role', 'unknown')}: {content[:220]}")
        return "\n".join(snippets)

    def copy_pdf_to(self, conversation: Dict[str, Any], target_dir: Path) -> Optional[Path]:
        pdf_path = Path(conversation.get("pdf_path", ""))
        if not pdf_path.exists():
            return None
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / pdf_path.name
        shutil.copy2(pdf_path, target)
        return target
