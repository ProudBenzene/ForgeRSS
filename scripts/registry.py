#!/usr/bin/env python3
# Copyright (C) 2026 ForgeRSS Contributors
# Licensed under AGPL-3.0

"""
Central registry of all feed generators.
Used by both run_single.py and run_all.py.
"""

from generators.medical.idsociety import IDSocietyGenerator
from generators.medical.nmpa_drug import NMPADrugGenerator
from generators.ai.anthropic_news import AnthropicNewsGenerator
from generators.ai.anthropic_research import AnthropicResearchGenerator
from generators.ai.anthropic_engineering import AnthropicEngineeringGenerator
from generators.ai.openai_research import OpenAIResearchGenerator
from generators.ai_coding_docs.openai_codex import OpenAICodexDocsGenerator
from generators.ai_coding_docs.claude_code import ClaudeCodeDocsGenerator
from generators.ai_coding_docs.cursor_docs import CursorDocsGenerator
from generators.ai_coding_docs.qwen_code import QwenCodeDocsGenerator
from generators.finance.cninfo_announcements import CninfoAnnouncementsGenerator
from generators.social.zhihu.generator_hot import ZhihuHotGenerator
from generators.social.zhihu.generator_user import ZhihuUserGenerator
from generators.social.bilibili.generator import BilibiliUPGenerator
from generators.social.xiaohongshu.generator import XiaohongshuUserGenerator
from generators.social.zsxq.generator import ZSXQTopicsGenerator
from generators.social.youtube.generator import YouTubeChannelGenerator
from generators.social.tiktok.generator import TikTokUserGenerator

# NOTE: weixin_channels has been earmarked to be split out into its own repository
# due to the reverse-engineering / decryption risk profile. Not registered here.


GENERATORS = {
    # Medical / Government
    "idsociety": IDSocietyGenerator,
    "nmpa_drug": NMPADrugGenerator,
    # Finance
    "cninfo_announcements": CninfoAnnouncementsGenerator,
    # AI
    "anthropic_news": AnthropicNewsGenerator,
    "anthropic_research": AnthropicResearchGenerator,
    "anthropic_engineering": AnthropicEngineeringGenerator,
    "openai_research": OpenAIResearchGenerator,
    # AI Coding Docs
    "openai_codex_docs": OpenAICodexDocsGenerator,
    "claude_code_docs": ClaudeCodeDocsGenerator,
    "cursor_docs": CursorDocsGenerator,
    "qwen_code_docs": QwenCodeDocsGenerator,
    # Social (requires login + desktop)
    "zhihu_hot": ZhihuHotGenerator,
    "zhihu_user": ZhihuUserGenerator,
    "bilibili_up": BilibiliUPGenerator,
    "xiaohongshu_user": XiaohongshuUserGenerator,
    "zsxq_topics": ZSXQTopicsGenerator,
    # Social (no login required)
    "youtube_channel": YouTubeChannelGenerator,
    "tiktok_user": TikTokUserGenerator,
}


# Generators requiring desktop environment (non-headless browser + login session)
DESKTOP_ONLY_GENERATORS = {
    "nmpa_drug",
    "zhihu_hot",
    "zhihu_user",
    "bilibili_up",
    "xiaohongshu_user",
    "zsxq_topics",
}

# Documentation generators (update less frequently, run in separate workflow)
DOCS_GENERATORS = {
    "openai_codex_docs",
    "claude_code_docs",
    "cursor_docs",
    "qwen_code_docs",
}
