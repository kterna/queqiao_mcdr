"""Minecraft text color and formatting code sanitizer."""

import re
from typing import Optional


class MinecraftColorSanitizer:
    """Sanitizes or strips legacy Minecraft color codes (§0-§f, &0-&f, §k-§r)."""

    SECTION_CODE_REGEX = re.compile(r'§[0-9a-fk-orA-FK-OR]')
    AMPERSAND_CODE_REGEX = re.compile(r'&[0-9a-fk-orA-FK-OR]')

    @classmethod
    def strip_all_colors(cls, text: str) -> str:
        """Completely strip all section and ampersand color codes."""
        if not text:
            return ""
        no_section = cls.SECTION_CODE_REGEX.sub('', text)
        return cls.AMPERSAND_CODE_REGEX.sub('', no_section)

    @classmethod
    def escape_ampersands(cls, text: str) -> str:
        """Escape raw ampersands that could accidentally trigger color codes."""
        return cls.AMPERSAND_CODE_REGEX.sub(lambda m: '\\' + m.group(0), text)

    @classmethod
    def normalize_section_to_ampersand(cls, text: str) -> str:
        """Convert § codes into & codes for safe editor representations."""
        return cls.SECTION_CODE_REGEX.sub(lambda m: '&' + m.group(0)[1:], text)
