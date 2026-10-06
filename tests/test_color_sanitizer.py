"""Unit tests for MinecraftColorSanitizer."""

import pytest
from queqiao_mcdr.color_sanitizer import MinecraftColorSanitizer


def test_strip_colors():
    raw = "§a[Player] §bSteve§r: Hello &cWorld&r!"
    clean = MinecraftColorSanitizer.strip_all_colors(raw)
    assert clean == "[Player] Steve: Hello World!"


def test_escape_ampersands():
    raw = "Use &a for green and &b for aqua"
    escaped = MinecraftColorSanitizer.escape_ampersands(raw)
    assert "\\&a" in escaped
    assert "\\&b" in escaped


def test_normalize_section():
    raw = "§6Gold §cRed"
    norm = MinecraftColorSanitizer.normalize_section_to_ampersand(raw)
    assert norm == "&6Gold &cRed"
