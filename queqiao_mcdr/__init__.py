"""QueQiao MCDR entry points with explicit ownership of each endpoint generation."""
import copy
import threading
from typing import Optional, Union

from mcdreforged.api.all import *
from queqiao_mcdr.config import Config
from queqiao_mcdr.websocket_server import WebSocketServer
from queqiao_mcdr.websocket_client import WebSocketClient, safe_websocket_target
from queqiao_mcdr.endpoint_runtime import EndpointRuntime
from queqiao_mcdr.event_handler import EventHandler
from queqiao_mcdr.api_handler import ApiHandler
from queqiao_mcdr.command_handler import CommandHandler

PLUGIN_METADATA = {
    "id": "queqiao_mcdr", "version": "1.2.0", "name": "QueQiao MCDR",
    "description": "MCDR WebSocket bridge supporting server and client modes",
    "author": "kterna", "link": "https://github.com/kterna/QueQiao_MCDR",
    "dependencies": {"mcdreforged": ">=2.0.0"},
}

# Preserve ownership handles if a host uses importlib.reload on this module.
config = globals().get("config")
websocket_server = globals().get("websocket_server")
websocket_client = globals().get("websocket_client")
event_handler = globals().get("event_handler")
api_handler = globals().get("api_handler")
command_handler = globals().get("command_handler")
ws_thread = globals().get("ws_thread")
loop = globals().get("loop")
_runtime = globals().get("_runtime")
_lifecycle_lock = globals().get("_lifecycle_lock", threading.RLock())


def on_load(server: PluginServerInterface, prev_module):
    global config, api_handler, event_handler, command_handler
    previous_runtime = getattr(prev_module, "_runtime", None) if prev_module else None
    previous_thread = getattr(prev_module, "ws_thread", None) if prev_module else None
    previous_handler = getattr(prev_module, "event_handler", None) if prev_module else None
    runtimes = {id(r): r for r in (_runtime, previous_runtime) if r is not None}
    was_running = any(r.is_alive() for r in runtimes.values()) or bool(previous_thread and previous_thread.is_alive())
    handlers = {id(h): h for h in (event_handler, previous_handler) if h is not None}
    for handler in handlers.values():
        close = getattr(handler, "close", None)
        if close and not close():
            raise RuntimeError("Previous event workers have not stopped; refusing to replace their owner")
    for runtime in runtimes.values():
        if not runtime.stop():
            raise RuntimeError("Previous endpoint has not stopped; refusing to replace its owner")
    if previous_thread and previous_thread.is_alive() and previous_runtime is None:
        previous_stop = getattr(prev_module, "stop_websocket", None)
        if previous_stop:
            previous_stop(server)
        if previous_thread.is_alive():
            raise RuntimeError("Legacy endpoint thread still runs; refusing a second generation")
    _force_cleanup()
    config = Config(server)
    loaded = config.load_config()
    api_handler = ApiHandler(server, config)
    event_handler = EventHandler(server, config, api_handler)
    command_handler = CommandHandler(server, config)
    command_handler.register_commands()
    event_handler.register_events()
    if loaded and (config.auto_start or was_running):
        start_websocket(server)
    server.logger.info(f"QueQiao loaded; mode={config.mode}, configuration_valid={loaded}")


def on_unload(server: PluginServerInterface):
    workers_stopped = event_handler.close() if event_handler and hasattr(event_handler, "close") else True
    endpoint_stopped = stop_websocket(server)
    if not workers_stopped or not endpoint_stopped:
        server.logger.error("QueQiao unload is incomplete; live ownership handles were retained")
    return workers_stopped and endpoint_stopped


def on_info(server: PluginServerInterface, info: Info):
    # The registered MCDR command tree handles permission checks and dispatch.
    # Do not also invoke the former nonexistent CommandHandler.on_command.
    return None


def _start_endpoint(server, mode):
    global _runtime, websocket_server, websocket_client, ws_thread, loop
    with _lifecycle_lock:
        if config is None or api_handler is None:
            server.logger.error("QueQiao configuration and API handler must be loaded first")
            return False
        if _runtime is not None and _runtime.is_alive():
            if _runtime.mode != mode:
                server.logger.warning("Stop the current endpoint before switching modes")
                return False
            return True
        _force_cleanup()
        snapshot = copy.copy(config)
        snapshot.config = copy.deepcopy(config.config)
        try:
            if mode == "client":
                endpoint = WebSocketClient(server, snapshot.websocket_url, api_handler, snapshot,
                    reconnect_interval=snapshot.reconnect_interval, reconnect_max_times=snapshot.reconnect_max_times)
            else:
                endpoint = WebSocketServer(server, snapshot.websocket_host, snapshot.websocket_port,
                                           snapshot.websocket_path, api_handler, snapshot)
            runtime = EndpointRuntime(endpoint, mode, server.logger)
            _runtime = runtime
            websocket_client = endpoint if mode == "client" else None
            websocket_server = endpoint if mode == "server" else None
            ws_thread = runtime.thread
            started = runtime.start()
            loop = runtime.loop
            if not started:
                server.logger.error("WebSocket endpoint did not start successfully")
                return False
            target = safe_websocket_target(snapshot.websocket_url) if mode == "client" else f"{snapshot.websocket_host}:{snapshot.websocket_port}"
            server.logger.info(f"WebSocket {mode} runtime started: {target}")
            return True
        except Exception as exc:
            server.logger.error(f"WebSocket runtime startup failed: {type(exc).__name__}")
            _force_cleanup()
            return False


def start_websocket(server):
    return _start_endpoint(server, config.mode) if config else False


def start_websocket_server(server):
    return _start_endpoint(server, "server")


def start_websocket_client(server):
    return _start_endpoint(server, "client")


def _stop_endpoint(server, mode=None):
    with _lifecycle_lock:
        owned = _runtime
        if owned is None or (mode is not None and owned.mode != mode):
            return True
        if not owned.stop():
            server.logger.error("WebSocket shutdown is incomplete; replacement remains blocked")
            return False
        return _force_cleanup()


def stop_websocket(server):
    return _stop_endpoint(server)


def stop_websocket_server(server):
    return _stop_endpoint(server, "server")


def stop_websocket_client(server):
    return _stop_endpoint(server, "client")


def reload_configuration(server):
    """Reject invalid input before stopping; restore the previous settings on restart failure."""
    with _lifecycle_lock:
        if config is None:
            return False
        try:
            candidate = config.load_candidate()
        except (OSError, ValueError, TypeError) as exc:
            server.logger.error(f"Reload rejected before stopping the endpoint: {type(exc).__name__}")
            return False
        previous = copy.deepcopy(config.config)
        was_running = bool(_runtime and _runtime.is_alive())
        if was_running and not stop_websocket(server):
            return False
        try:
            # Publish the validated candidate in memory first so the new
            # generation can be started without changing the durable file.
            # The file is committed only after that generation owns a live
            # endpoint. This keeps a failed handover from exposing a state no
            # running generation can serve.
            config.install(candidate, persist=False)
            if was_running and not start_websocket(server):
                raise RuntimeError("Replacement endpoint did not start")
            config.persist(candidate)
            return True
        except Exception as exc:
            server.logger.error(f"Reload failed: {type(exc).__name__}")
            if _runtime is not None and _runtime.is_alive() and not stop_websocket(server):
                server.logger.error("Reload rollback cannot replace the still-owned live endpoint")
                return False
            try:
                config.install(previous)
            except (OSError, ValueError, TypeError):
                config.install(previous, persist=False)
                server.logger.error("Previous runtime settings restored, but configuration persistence failed")
            if was_running:
                start_websocket(server)
            return False


def _force_cleanup():
    """Clear only stopped handles. Never hide a live thread behind empty globals."""
    global _runtime, websocket_server, websocket_client, ws_thread, loop
    if _runtime is not None and _runtime.is_alive():
        return False
    _runtime = None
    websocket_server = websocket_client = ws_thread = loop = None
    return True


def get_websocket_runtime():
    with _lifecycle_lock:
        return _runtime if _runtime and _runtime.is_alive() else None


def get_websocket_server() -> Optional[WebSocketServer]:
    return websocket_server


def get_websocket_client() -> Optional[WebSocketClient]:
    return websocket_client


def get_websocket_endpoint() -> Optional[Union[WebSocketServer, WebSocketClient]]:
    runtime = get_websocket_runtime()
    return runtime.endpoint if runtime else None
