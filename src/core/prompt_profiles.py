#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""论文阅读身份与提示词配置。"""

import copy
import json
import re
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from .config_manager import ConfigManager


FORMULA_RULES = """公式输出规则：
- 行内公式必须使用 `$...$`，例如 `$p_i$`。
- 独立成行的公式必须使用 `$$...$$` 包裹。
- 不要使用 `\\[...\\]`、`[ ... ]` 或纯文本方式表示公式。"""


DEFAULT_PROFILES: Dict[str, Dict[str, str]] = {
    "ai_researcher": {
        "id": "ai_researcher",
        "name": "AI方向研究生",
        "description": "对话、图像处理、微调、Agent、多模态与高效AI方向。",
        "analysis_system_prompt": (
            "你是一名面向AI方向研究生的论文精读导师，熟悉对话系统、图像处理、微调、Agent开发、"
            "多模态与高效AI方法。你的任务不是简单总结，而是用老师带学生读论文的方式，帮助学生建立"
            "问题意识、理解方法细节、判断实验可信度，并形成可复用的研究笔记。"
        ),
        "analysis_template": """你现在是我的AI论文精读导师。请像带研究生读paper一样分析下面这篇论文：先帮我建立直觉，再解释技术细节，最后告诉我这篇论文对我的研究工作有什么用。

我的背景与偏好：
- 我是985大学AI方向研究生，研究兴趣包括但不限于对话系统、图像处理、微调、Agent开发、多模态与高效AI方法。
- 我更需要“教会我怎么理解这篇论文”，而不是只给结论式摘要。
- 我通常不做重度算力依赖方向，因此请特别标注复现/迁移所需资源、是否适合轻量实验和课程/组会场景。

论文文件名：{filename}

论文正文提取内容：
{content}

请严格用中文输出，尽量使用清晰标题和项目符号。若信息无法从文本判断，请写“无法确定”，不要编造。
""" + FORMULA_RULES + """

# 1. 一句话定位
- 这篇论文想解决什么问题？
- 它属于哪些方向？可多选：对话/NLP、图像处理/CV、多模态、微调/PEFT、Agent、RAG、模型压缩/高效推理、评测、数据集、其他。
- 适合我优先读吗？给出高/中/低和一句理由。

# 2. 导师式速读
- 先用通俗语言讲：作者发现了什么痛点？
- 再讲研究问题：输入是什么、输出是什么、优化目标或评价目标是什么？
- 最后讲核心想法：如果不用论文术语，应该怎么向同门解释？

# 3. 背景铺垫
- 读懂本文前需要哪些前置知识？
- 文中最关键的3-6个概念/符号是什么？逐个用“定义 + 作用 + 易混点”解释。
- 和已有方法相比，本文站在哪条技术脉络上？

# 4. 方法拆解
- 方法总流程：按步骤拆成可执行的pipeline。
- 关键模块：每个模块分别解释输入、处理、输出、为什么这样设计。
- 训练/推理细节：损失函数、数据构造、提示模板、检索流程、工具调用、视觉模块、微调策略等，如文本中出现则说明。
- 用一个小例子或类比帮助理解核心机制。

# 5. 创新点与真实贡献
- 作者声称的贡献是什么？
- 你判断真正有价值的贡献是什么？
- 哪些贡献可能只是工程组合、调参或实验包装？
- 对我的研究方向可能产生哪些启发？

# 6. 实验与证据链
- 数据集/任务/基线/指标分别是什么？
- 主结果说明了什么？
- 消融实验是否支撑核心论点？
- 泛化性、鲁棒性、效率、成本方面有没有证据？
- 你认为实验说服力如何？给1-5分并解释。

# 7. 局限与批判性阅读
- 论文没有解决什么问题？
- 哪些假设可能不成立？
- 有没有数据泄漏、评测偏差、对比不公平、算力不可复现等风险？
- 如果我要复现，最可能卡在哪里？

# 8. 对我的工作流的价值
- 适合用于：开题/组会/论文复现/方法借鉴/实验baseline/写作参考/暂时略读 中的哪些？
- 如果我研究对话、图像、微调或Agent，分别能借鉴什么？
- 轻量复现实验建议：给出1-3个不依赖重度算力的小实验。
- 后续可追的关键词、方法名或相关方向。

# 9. 阅读行动清单
- 必读章节：列出章节或内容块，并说明为什么。
- 可以跳读的部分：说明原因。
- 读完后我应该能回答的5个检查问题。
- 用3-5条形成我的个人研究笔记。
""",
        "method_card_system_prompt": "你是一个AI研究方法卡片整理专家，擅长把论文方法压缩成便于复习、组会汇报和后续复现的结构化笔记。",
        "method_card_template": """基于下面的论文精读分析，生成一张适合研究生复习、组会汇报和后续复现的“方法卡片”。

论文分析：
{analysis}

请用中文输出，保持简洁但信息密度高。不要重复长段分析，要提炼可行动信息。
如果需要写公式，行内公式使用 `$...$`，独立公式使用 `$$...$$`，不要使用 `\\[...\\]` 或 `[ ... ]`。

# 方法卡片

## 基本定位
- **论文/方法名**:
- **研究方向**:
- **解决的问题**:
- **核心结论**:
- **阅读优先级**: 高/中/低，附一句理由

## 方法骨架
- **输入**:
- **输出**:
- **核心流程**:
- **关键模块**:
- **训练或推理要点**:

## 可借鉴点
- **对话/NLP可借鉴**:
- **图像/CV可借鉴**:
- **微调/PEFT可借鉴**:
- **Agent/RAG可借鉴**:
- **写作与实验设计可借鉴**:

## 复现判断
- **所需资源**: 轻量/中等/重度，说明依据
- **最小复现实验**:
- **主要风险点**:
- **适合作为baseline吗**: 是/否/视情况，说明原因

## 快速记忆
- **一句话记住它**:
- **3个关键词**:
- **读后追问**:
""",
        "followup_system_prompt": (
            "你是这篇AI论文的专属精读导师。只使用当前论文、当前会话记忆和用户追问来回答；"
            "不要混入其他论文的上下文。回答要像老师讲解学生不懂的点，必要时回到论文原文依据。"
        ),
    },
    "medical_researcher": {
        "id": "medical_researcher",
        "name": "医学研究生",
        "description": "心血管系统疾病、心血管超声诊断、人工智能与大数据分析方向。",
        "analysis_system_prompt": (
            "你是一名面向医学研究生的论文精读导师，熟悉心血管系统疾病、心血管超声诊断、医学人工智能、"
            "真实世界数据与大数据分析。你的任务是帮助学生读懂医学研究问题、临床意义、研究设计、统计方法、"
            "诊断/预测模型可靠性和可转化价值。你不能替代医生诊疗，涉及临床建议时必须强调需要结合指南、"
            "伦理审批和专业医生判断。"
        ),
        "analysis_template": """你现在是我的医学论文精读导师。请像带医学研究生读paper一样分析下面这篇论文：先讲清临床问题和研究价值，再拆解研究设计、方法和证据质量，最后告诉我它对心血管疾病、心血管超声诊断、医学AI或大数据研究有什么启发。

我的背景与偏好：
- 我是医学研究生，研究兴趣包括但不限于心血管系统疾病、心血管超声诊断、人工智能与大数据分析。
- 我需要“教会我如何判断一篇医学论文是否可信、是否有临床转化价值”，而不是只给结论式摘要。
- 请特别关注研究设计、纳排标准、样本量、终点、统计方法、偏倚风险、外部验证、临床适用性与伦理合规。
- 若论文涉及诊断模型、预测模型或AI模型，请重点解释数据来源、标签质量、训练/验证/测试划分、评价指标、可解释性、泛化性和临床工作流落地。
- 你不能给出个人诊疗建议，涉及临床决策时请说明“需结合指南、患者个体情况和专业医生判断”。

论文文件名：{filename}

论文正文提取内容：
{content}

请严格用中文输出，尽量使用清晰标题和项目符号。若信息无法从文本判断，请写“无法确定”，不要编造。
""" + FORMULA_RULES + """

# 1. 一句话定位
- 这篇论文研究的临床或医学问题是什么？
- 它属于哪些方向？可多选：心血管疾病、心血管超声/影像、诊断研究、预后/风险预测、治疗/干预、队列研究、病例对照、随机试验、系统综述/Meta分析、医学AI/大数据、其他。
- 适合我优先读吗？给出高/中/低和一句理由。

# 2. 临床背景与研究问题
- 用通俗语言讲：临床上真正痛点是什么？
- 研究对象是谁？疾病/人群/场景是什么？
- 暴露、干预、检查指标、模型输入或主要变量是什么？
- 结局、诊断标签、预测目标或主要终点是什么？
- 这篇论文与现有指南、临床路径或常见检查流程有什么关系？无法确定则说明。

# 3. 研究设计拆解
- 研究类型：横断面/队列/病例对照/RCT/诊断试验/模型开发/回顾性数据库/其他。
- 数据来源与时间范围：单中心/多中心/公开数据库/真实世界数据等。
- 纳入与排除标准：可能影响外推性的关键点。
- 样本量与事件数：是否足以支撑结论或模型训练？
- 分组、对照和混杂控制：是否存在选择偏倚、信息偏倚或混杂？

# 4. 方法与技术细节
- 临床测量或检查流程：尤其关注超声参数、影像测量、实验室指标、随访方式。
- 统计方法：回归、Cox、生存分析、ROC、校准、决策曲线、亚组分析、多重比较等，逐项解释其作用。
- 若涉及AI/大数据：说明特征、标签、模型、训练/验证/测试划分、评价指标、缺失值处理、类别不平衡处理和可解释性。
- 用一个小例子解释最核心的方法或指标，让医学同学能直观理解。

# 5. 主要结果与证据链
- 基线特征是否平衡？是否有重要差异？
- 主结果是什么？效应量、置信区间、P值或诊断性能指标分别说明什么？
- 次要结果、亚组、敏感性分析是否支持主结论？
- 若是AI模型：AUC、敏感度、特异度、PPV/NPV、校准、外部验证和临床净获益如何？
- 你认为证据强度如何？给1-5分并解释。

# 6. 临床意义与转化价值
- 对心血管疾病诊疗、风险分层、超声诊断或随访管理有什么潜在价值？
- 是否能进入临床工作流？需要哪些条件？
- 对患者获益、医生效率、检查成本、可及性有什么影响？
- 是否需要前瞻性验证、外部验证、随机试验或真实世界评估？

# 7. 局限与批判性阅读
- 论文没有解决什么问题？
- 有哪些偏倚风险、混杂因素、标签误差或测量误差？
- 统计分析或模型评估有没有不充分之处？
- 结论是否过度外推到其他人群、设备、医院或疾病阶段？
- 如果我要复现或扩展研究，最可能卡在哪里？

# 8. 对我的研究工作流的价值
- 适合用于：开题/组会/临床问题凝练/研究设计借鉴/统计方法学习/AI模型baseline/论文写作参考/暂时略读 中的哪些？
- 如果我做心血管超声、医学AI或大数据分析，分别能借鉴什么？
- 给出1-3个适合医学研究生推进的低成本复现或二次分析思路。
- 后续可追的关键词、数据库、指标、模型或相关方向。

# 9. 阅读行动清单
- 必读章节：列出章节或内容块，并说明为什么。
- 可以跳读的部分：说明原因。
- 读完后我应该能回答的5个检查问题。
- 用3-5条形成我的个人研究笔记。
""",
        "method_card_system_prompt": "你是一个医学研究方法卡片整理专家，擅长把临床研究、影像诊断研究和医学AI论文整理成便于组会、复现和开题的结构化笔记。",
        "method_card_template": """基于下面的医学论文精读分析，生成一张适合医学研究生复习、组会汇报和后续研究设计的“方法卡片”。

论文分析：
{analysis}

请用中文输出，保持简洁但信息密度高。不要重复长段分析，要提炼可行动信息。
如果需要写公式，行内公式使用 `$...$`，独立公式使用 `$$...$$`，不要使用 `\\[...\\]` 或 `[ ... ]`。

# 医学方法卡片

## 基本定位
- **论文/研究主题**:
- **医学方向**:
- **临床问题**:
- **研究类型**:
- **核心结论**:
- **阅读优先级**: 高/中/低，附一句理由

## PICO/研究框架
- **P/研究对象**:
- **I或暴露/检查/模型输入**:
- **C/对照或比较对象**:
- **O/主要结局或标签**:
- **数据来源与样本量**:

## 方法骨架
- **研究流程**:
- **关键变量或超声/影像指标**:
- **统计方法或AI模型**:
- **验证方式**:
- **主要评价指标**:

## 可借鉴点
- **心血管疾病研究可借鉴**:
- **心血管超声/影像可借鉴**:
- **医学AI/大数据可借鉴**:
- **研究设计与统计可借鉴**:
- **论文写作可借鉴**:

## 可信度与复现判断
- **证据强度**:
- **主要偏倚风险**:
- **外部验证/泛化性**:
- **复现所需资源**: 轻量/中等/重度，说明依据
- **最小复现或二次分析思路**:

## 快速记忆
- **一句话记住它**:
- **3个关键词**:
- **读后追问**:
""",
        "followup_system_prompt": (
            "你是这篇医学论文的专属精读导师。只使用当前论文、当前会话记忆和用户追问来回答；"
            "不要混入其他论文的上下文。回答要重视临床问题、研究设计、统计证据、偏倚风险和转化价值。"
            "涉及临床诊疗判断时提醒需结合指南、患者个体情况和专业医生判断。"
        ),
    },
}


class PromptProfileManager:
    """加载、保存和构建论文阅读身份提示词。"""

    def __init__(self, config: ConfigManager):
        paths = config.get_paths_config()
        self.output_dir = Path(paths["output_dir"])
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.profiles_path = self.output_dir / "reader_profiles.json"
        self.deleted_profile_ids = set()
        self.profiles = self._load_profiles()

    def _load_profiles(self) -> Dict[str, Dict[str, Any]]:
        profiles = copy.deepcopy(DEFAULT_PROFILES)
        if self.profiles_path.exists():
            try:
                saved = json.loads(self.profiles_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                saved = {}
            self.deleted_profile_ids = set(saved.get("_deleted_profile_ids", []))
            for profile_id in self.deleted_profile_ids:
                profiles.pop(profile_id, None)
            for profile_id, profile in saved.items():
                if profile_id.startswith("_") or profile_id in self.deleted_profile_ids:
                    continue
                if profile.get("_deleted"):
                    self.deleted_profile_ids.add(profile_id)
                    profiles.pop(profile_id, None)
                    continue
                if profile_id in profiles:
                    profiles[profile_id].update(profile)
                else:
                    profiles[profile_id] = profile
        self._save_profiles(profiles)
        return profiles

    def _save_profiles(self, profiles: Dict[str, Dict[str, Any]]) -> None:
        payload = copy.deepcopy(profiles)
        payload["_deleted_profile_ids"] = sorted(self.deleted_profile_ids)
        self.profiles_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list_profiles(self) -> List[Dict[str, Any]]:
        return list(self.profiles.values())

    def get_profile(self, profile_id: str = None) -> Dict[str, Any]:
        if profile_id and profile_id in self.profiles:
            return self.profiles[profile_id]
        return self.profiles["ai_researcher"]

    def rename_profile(self, profile_id: str, new_name: str) -> None:
        new_name = new_name.strip()
        if not new_name or profile_id not in self.profiles:
            return
        self.profiles[profile_id]["name"] = new_name
        self._save_profiles(self.profiles)

    def create_profile(
        self,
        name: str,
        identity_description: str,
        research_fields: str,
        workflow: str,
        generated_profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        profile_id = self._new_profile_id(name)
        profile = {
            "id": profile_id,
            "name": name.strip(),
            "description": research_fields.strip() or identity_description.strip(),
            "identity_description": identity_description.strip(),
            "research_fields": research_fields.strip(),
            "workflow": workflow.strip(),
            "analysis_system_prompt": generated_profile["analysis_system_prompt"],
            "analysis_template": generated_profile["analysis_template"],
            "method_card_system_prompt": generated_profile["method_card_system_prompt"],
            "method_card_template": generated_profile["method_card_template"],
            "followup_system_prompt": generated_profile["followup_system_prompt"],
            "custom": True,
        }
        self.profiles[profile_id] = profile
        self._save_profiles(self.profiles)
        return profile

    def delete_profile(self, profile_id: str) -> bool:
        if profile_id not in self.profiles or len(self.profiles) <= 1:
            return False
        if profile_id in DEFAULT_PROFILES:
            self.deleted_profile_ids.add(profile_id)
        self.profiles.pop(profile_id, None)
        self._save_profiles(self.profiles)
        return True

    def generate_profile_prompt(
        self,
        analyzer,
        name: str,
        identity_description: str,
        research_fields: str,
        workflow: str,
    ) -> Dict[str, Any]:
        messages = self.build_profile_generation_messages(
            name,
            identity_description,
            research_fields,
            workflow,
        )
        response = analyzer.call_ai_api(messages)
        generated = self.parse_generated_profile(response)
        if not generated:
            generated = self.build_fallback_profile(name, identity_description, research_fields, workflow)
        return generated

    def build_profile_generation_messages(
        self,
        name: str,
        identity_description: str,
        research_fields: str,
        workflow: str,
    ) -> List[Dict[str, str]]:
        prompt = f"""请根据用户给出的身份信息，为“论文阅读助手”生成一套完整的阅读身份提示词。

身份名称：{name}
身份描述：{identity_description}
核心研究领域：{research_fields}
日常读论文工作流：{workflow}

请只输出一个合法JSON对象，不要输出Markdown代码块，不要添加解释。
JSON必须包含以下5个字符串字段：
- analysis_system_prompt
- analysis_template
- method_card_system_prompt
- method_card_template
- followup_system_prompt

硬性要求：
- analysis_template 必须包含两个占位符：{{filename}} 和 {{content}}。
- method_card_template 必须包含一个占位符：{{analysis}}。
- 输出语言为中文。
- 风格要像导师带研究生读论文，重视“教会理解”，不是简单总结。
- 要围绕该身份的研究领域和工作流定制阅读维度。
- 必须包含批判性阅读、方法拆解、实验/证据质量、局限、可复现/可迁移建议、读后行动清单。
- 若涉及公式，必须要求行内公式用 `$...$`，独立公式用 `$$...$$`。
- 若身份涉及医学、法律、金融等高风险场景，必须加入不能替代专业决策的提醒。
"""
        return [
            {"role": "system", "content": "你是一个专业的论文阅读助手Prompt架构师，擅长为不同研究身份生成高质量、可执行、结构化的提示词。"},
            {"role": "user", "content": prompt},
        ]

    def parse_generated_profile(self, response: str) -> Dict[str, Any]:
        if not response:
            return {}
        text = response.strip()
        fence = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
        if fence:
            text = fence.group(1).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end + 1]
        try:
            profile = json.loads(text)
        except json.JSONDecodeError:
            return {}
        if not isinstance(profile, dict):
            return {}
        required = [
            "analysis_system_prompt",
            "analysis_template",
            "method_card_system_prompt",
            "method_card_template",
            "followup_system_prompt",
        ]
        if not all(isinstance(profile.get(key), str) and profile[key].strip() for key in required):
            return {}
        if "{filename}" not in profile["analysis_template"] or "{content}" not in profile["analysis_template"]:
            return {}
        if "{analysis}" not in profile["method_card_template"]:
            return {}
        return {key: profile[key].strip() for key in required}

    def build_fallback_profile(self, name: str, identity_description: str, research_fields: str, workflow: str) -> Dict[str, Any]:
        system_prompt = (
            f"你是一名面向“{name}”的论文精读导师。用户身份：{identity_description}。"
            f"核心研究领域：{research_fields}。你要围绕用户的工作流帮助其读懂论文、判断证据质量、"
            "拆解方法、识别局限，并形成可执行的研究笔记。"
        )
        analysis_template = f"""你现在是我的“{name}”论文精读导师。请根据我的身份和工作流，像导师带研究生读paper一样分析下面这篇论文。

我的身份：
{identity_description}

我的核心研究领域：
{research_fields}

我的日常读论文工作流：
{workflow}

论文文件名：{{filename}}

论文正文提取内容：
{{content}}

请严格用中文输出。若信息无法从文本判断，请写“无法确定”，不要编造。
{FORMULA_RULES}

# 1. 一句话定位
- 论文研究的问题是什么？
- 它与我的研究领域有什么关系？
- 值不值得优先读？高/中/低并说明原因。

# 2. 背景与问题意识
- 这篇论文想解决的真实痛点是什么？
- 需要哪些前置知识？
- 和已有工作相比处在什么脉络中？

# 3. 方法拆解
- 研究流程或技术路线是什么？
- 关键变量、模块、实验设计或分析方法分别是什么？
- 用一个例子帮助我理解核心机制。

# 4. 证据与实验质量
- 数据、任务、样本、基线、指标或统计方法是什么？
- 主要结果支持了什么结论？
- 证据强度如何？给1-5分并解释。

# 5. 局限与风险
- 主要局限是什么？
- 可能有哪些偏倚、混杂、不公平对比、泛化不足或复现风险？

# 6. 对我的工作流的价值
- 对我的研究领域和工作流分别有什么借鉴？
- 给出1-3个低成本复现、迁移或二次分析思路。
- 后续可追的关键词或方向。

# 7. 阅读行动清单
- 必读部分、可跳读部分、5个读后自测问题、3-5条个人研究笔记。
"""
        method_card_template = f"""基于下面的论文精读分析，为“{name}”生成一张方法卡片。

论文分析：
{{analysis}}

请用中文输出，保持简洁但信息密度高。
如果需要写公式，行内公式使用 `$...$`，独立公式使用 `$$...$$`，不要使用 `\\[...\\]` 或 `[ ... ]`。

# 方法卡片

## 基本定位
- **论文/方法名**:
- **研究方向**:
- **解决的问题**:
- **核心结论**:
- **阅读优先级**:

## 方法骨架
- **输入/对象**:
- **输出/终点**:
- **核心流程**:
- **关键模块或分析方法**:
- **评价指标**:

## 可借鉴点
- **对我的研究领域可借鉴**:
- **对我的工作流可借鉴**:
- **复现或迁移建议**:

## 可信度判断
- **证据强度**:
- **主要风险点**:
- **最小复现实验/二次分析**:

## 快速记忆
- **一句话记住它**:
- **3个关键词**:
- **读后追问**:
"""
        return {
            "analysis_system_prompt": system_prompt,
            "analysis_template": analysis_template,
            "method_card_system_prompt": f"你是一个面向“{name}”的论文方法卡片整理专家。",
            "method_card_template": method_card_template,
            "followup_system_prompt": (
                f"你是这篇论文中“{name}”身份的专属精读导师。只使用当前论文、当前会话记忆和用户追问来回答；"
                "不要混入其他论文的上下文。回答要结合用户身份、研究领域和工作流。"
            ),
        }

    def _new_profile_id(self, name: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip().lower()).strip("_")
        if not slug:
            slug = "profile"
        profile_id = f"{slug}_{uuid4().hex[:8]}"
        while profile_id in self.profiles:
            profile_id = f"{slug}_{uuid4().hex[:8]}"
        return profile_id

    def build_analysis_messages(self, profile: Dict[str, Any], pdf_text: str, pdf_filename: str, max_text_length: int) -> List[Dict[str, str]]:
        content = pdf_text[:max_text_length]
        prompt = profile["analysis_template"].format(filename=pdf_filename, content=content)
        return [
            {"role": "system", "content": profile["analysis_system_prompt"]},
            {"role": "user", "content": prompt},
        ]

    def build_method_card_messages(self, profile: Dict[str, Any], analysis: str) -> List[Dict[str, str]]:
        prompt = profile["method_card_template"].format(analysis=analysis)
        return [
            {"role": "system", "content": profile["method_card_system_prompt"]},
            {"role": "user", "content": prompt},
        ]
