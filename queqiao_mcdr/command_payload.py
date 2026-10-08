"""Bounded text-component validation for server-generated title commands only."""
import json
import re

MAX_COMPONENT_BYTES = 16384
MAX_COMPONENT_NODES = 128
MAX_COMPONENT_DEPTH = 8
MAX_TIMING_TICKS = 120000
COLORS = {
    "black", "dark_blue", "dark_green", "dark_aqua", "dark_red",
    "dark_purple", "gold", "gray", "dark_gray", "blue", "green",
    "aqua", "red", "light_purple", "yellow", "white", "reset",
}
STYLE_KEYS = {"bold", "italic", "underlined", "strikethrough", "obfuscated"}
COMPONENT_KEYS = {"text", "color", "extra", "click_event", "clickEvent", "hover_event", "hoverEvent"} | STYLE_KEYS


def timing(value, field):
    if type(value) is not int or not 0 <= value <= MAX_TIMING_TICKS:
        raise ValueError(f"{field} must be an integer between 0 and {MAX_TIMING_TICKS}")
    return value


def component_json(message):
    """Normalize the supported legacy/native text subset without executing it."""
    visited = 0

    def text(value):
        if not isinstance(value, str) or len(value) > MAX_COMPONENT_BYTES or "\x00" in value:
            raise ValueError("text must be a bounded string without NUL")
        return value

    def visit(value, depth=0):
        nonlocal visited
        visited += 1
        if depth > MAX_COMPONENT_DEPTH or visited > MAX_COMPONENT_NODES:
            raise ValueError("message component nesting or count exceeds its limit")
        if isinstance(value, str):
            return {"text": text(value)}
        if isinstance(value, list):
            if not value or len(value) > MAX_COMPONENT_NODES:
                raise ValueError("component arrays must be nonempty and bounded")
            result = []
            for child in value:
                normalized = visit(child, depth + 1)
                result.extend(normalized if isinstance(normalized, list) else [normalized])
            return result
        if not isinstance(value, dict):
            raise ValueError("message must contain only text strings or text components")
        if "type" in value or "data" in value:
            if set(value) != {"type", "data"} or value["type"] != "text" or not isinstance(value["data"], dict):
                raise ValueError("only the legacy text component wrapper is supported")
            value = value["data"]
        if "text" not in value or set(value) - COMPONENT_KEYS:
            raise ValueError("unsupported text component fields")
        result = {"text": text(value["text"])}
        if "color" in value:
            color = value["color"]
            if not isinstance(color, str) or not (color.lower() in COLORS or re.fullmatch(r"#[0-9a-fA-F]{6}", color)):
                raise ValueError("unsupported text color")
            result["color"] = color.lower()
        for key in STYLE_KEYS & value.keys():
            if type(value[key]) is not bool:
                raise ValueError("text styles must be booleans")
            result[key] = value[key]
        for native, legacy in (("clickEvent", "click_event"), ("hoverEvent", "hover_event")):
            if native in value and legacy in value:
                raise ValueError("ambiguous component event aliases")
            event = value.get(native, value.get(legacy))
            if event is None:
                continue
            if not isinstance(event, dict):
                raise ValueError("component events must be objects")
            if native == "clickEvent":
                if set(event) != {"action", "value"} or event["action"] not in {
                    "open_url", "run_command", "suggest_command", "copy_to_clipboard"
                }:
                    raise ValueError("unsupported click event")
                result[native] = {"action": event["action"], "value": text(event["value"])}
            else:
                if event.get("action") != "show_text" or set(event) - {"action", "contents", "value", "text"}:
                    raise ValueError("only show_text hover events are supported")
                keys = [key for key in ("contents", "value", "text") if key in event]
                if len(keys) != 1:
                    raise ValueError("hover event needs one text payload")
                key = keys[0]
                target = "contents" if key == "contents" else "value"
                result[native] = {"action": "show_text", target: visit(event[key], depth + 1)}
        if "extra" in value:
            if not isinstance(value["extra"], list):
                raise ValueError("extra must be an array")
            result["extra"] = []
            for child in value["extra"]:
                normalized = visit(child, depth + 1)
                result["extra"].extend(normalized if isinstance(normalized, list) else [normalized])
        return result

    result = json.dumps(visit(message), ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    if len(result.encode("utf-8")) > MAX_COMPONENT_BYTES:
        raise ValueError("encoded message exceeds its byte limit")
    return result
