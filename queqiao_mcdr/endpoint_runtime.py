"""One immutable endpoint generation owns its worker thread and event loop."""
import asyncio
import threading


class EndpointRuntime:
    def __init__(self, endpoint, mode, logger):
        if mode not in {"server", "client"}:
            raise ValueError("unsupported endpoint mode")
        self.endpoint, self.mode, self.logger = endpoint, mode, logger
        self.loop = None
        self.error_type = None
        self._ready = threading.Event()
        self._finished = threading.Event()
        self._stop_lock = threading.Lock()
        self._stop_future = None
        self._stop_event = None
        self._start_task = None
        self._endpoint_stop_task = None
        self.thread = threading.Thread(
            target=self._thread_main, daemon=True, name=f"QueQiao-WebSocket-{mode}"
        )

    def is_alive(self):
        return self.thread.is_alive()

    def start(self, timeout=5):
        if self.thread.ident is not None:
            return self.is_alive() and self.error_type is None
        self.thread.start()
        if not self._ready.wait(timeout):
            self.logger.error("WebSocket runtime startup did not become ready")
            return False
        return self.error_type is None and self.is_alive()

    async def _serve(self):
        self._stop_event = asyncio.Event()
        self._start_task = asyncio.create_task(self.endpoint.start(), name="QueQiao-endpoint")
        try:
            if self.mode == "server":
                await self._start_task
                if not self.endpoint.is_running():
                    raise RuntimeError("WebSocket listener failed to start")
                self._ready.set()
                await self._stop_event.wait()
            else:
                # Let the owned client establish its run-task identity, without
                # claiming that its remote handshake has already succeeded.
                await asyncio.sleep(0)
                self._ready.set()
                await self._start_task
        finally:
            await self._stop_endpoint()

    async def _stop_endpoint(self):
        if self._endpoint_stop_task is None:
            self._endpoint_stop_task = asyncio.create_task(self.endpoint.stop(), name="QueQiao-stop-endpoint")
        await asyncio.shield(self._endpoint_stop_task)

    async def _request_stop(self):
        if self._stop_event is not None:
            self._stop_event.set()
        await self._stop_endpoint()
        if self._start_task is not None and not self._start_task.done():
            self._start_task.cancel()
            await asyncio.gather(self._start_task, return_exceptions=True)

    def _thread_main(self):
        owned_loop = asyncio.new_event_loop()
        self.loop = owned_loop
        asyncio.set_event_loop(owned_loop)
        try:
            owned_loop.run_until_complete(self._serve())
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self.error_type = type(exc).__name__
            self.logger.error(f"WebSocket runtime failed: {self.error_type}")
        finally:
            self._ready.set()
            try:
                pending = asyncio.all_tasks(owned_loop)
                for task in pending:
                    task.cancel()
                if pending:
                    owned_loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                owned_loop.run_until_complete(owned_loop.shutdown_asyncgens())
                owned_loop.close()
            finally:
                self._finished.set()

    def stop(self, timeout=5):
        """Return false on incomplete shutdown and keep ownership references intact."""
        if not self.is_alive():
            return True
        if self.loop is None:
            self._ready.wait(timeout)
        owned_loop = self.loop
        if owned_loop is not None and not owned_loop.is_closed() and owned_loop.is_running():
            with self._stop_lock:
                if self._stop_future is None:
                    coroutine = self._request_stop()
                    try:
                        self._stop_future = asyncio.run_coroutine_threadsafe(coroutine, owned_loop)
                    except RuntimeError:
                        # The owning thread may have completed between checks.
                        coroutine.close()
        if threading.current_thread() is self.thread:
            return False
        self.thread.join(timeout)
        if self.is_alive():
            self.logger.error("WebSocket runtime shutdown is incomplete; ownership retained")
            return False
        return True

    def submit_event(self, event_data):
        """Capture endpoint and loop from the same generation for cross-thread events."""
        owned_loop = self.loop
        if not self.is_alive() or owned_loop is None or owned_loop.is_closed() or not self.endpoint.is_running():
            return None
        coroutine = self.endpoint.broadcast_event(event_data)
        try:
            return asyncio.run_coroutine_threadsafe(coroutine, owned_loop)
        except RuntimeError:
            coroutine.close()
            return None
