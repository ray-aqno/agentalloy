"""Authoring pipeline: SKILL.md → Author LLM → QA gate → pending-review.

Separate from the runtime retrieval stack. Uses LM Studio for generation
and FastFlowLM for embeddings via OpenAI-compatible endpoints.
"""
