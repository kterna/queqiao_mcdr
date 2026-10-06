"""conftest.py: Stub mcdreforged runtime to enable fast offline unit testing."""

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if "mcdreforged" not in sys.modules:
    mcd = types.ModuleType("mcdreforged")
    api = types.ModuleType("mcdreforged.api")
    all_mod = types.ModuleType("mcdreforged.api.all")
    rtext_mod = types.ModuleType("mcdreforged.api.rtext")

    class PluginServerInterface:
        def register_command(self, *a, **k): pass
        def register_event_listener(self, *a, **k): pass
        def logger(self): return types.SimpleNamespace(info=print, error=print, warning=print, debug=print)

    class CommandSource:
        pass

    class Info:
        pass

    class RText(str):
        def set_click_event(self, *a, **k): return self
        def set_hover_text(self, *a, **k): return self

    class RTextList(list):
        def to_plain_text(self): return "".join(str(x) for x in self)

    rtext_mod.RText = RText
    rtext_mod.RTextList = RTextList
    rtext_mod.RColor = types.SimpleNamespace(green="", red="", yellow="", blue="", white="", gray="", dark_gray="")
    rtext_mod.RStyle = types.SimpleNamespace(bold="", italic="", underlined="", strikethrough="", obfuscated="")
    rtext_mod.RAction = types.SimpleNamespace(open_url="", run_command="", suggest_command="")

    all_mod.PluginServerInterface = PluginServerInterface
    all_mod.CommandSource = CommandSource
    all_mod.Info = Info
    all_mod.RText = RText
    all_mod.RTextList = RTextList
    all_mod.RColor = rtext_mod.RColor
    all_mod.RStyle = rtext_mod.RStyle
    all_mod.RAction = rtext_mod.RAction

    api.all = all_mod
    api.rtext = rtext_mod
    mcd.api = api
    sys.modules["mcdreforged"] = mcd
    sys.modules["mcdreforged.api"] = api
    sys.modules["mcdreforged.api.all"] = all_mod
    sys.modules["mcdreforged.api.rtext"] = rtext_mod
