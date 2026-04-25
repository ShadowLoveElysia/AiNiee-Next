"""Render-side planning helpers for MangaCore."""

from .bubbleAssign import BubbleAssignment, assign_bubbles
from .planner import plan_text_blocks

__all__ = ["BubbleAssignment", "assign_bubbles", "plan_text_blocks"]
