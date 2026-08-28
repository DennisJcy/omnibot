import json, threading, time, uuid, queue, socket, requests, traceback, sys, re
from threading import Timer
from typing import Dict, Any, Optional, List
from simple_websocket_server import WebSocketServer, WebSocket
from bs4 import BeautifulSoup
import bottle, random
from bottle import route, template, request, response
from .logger import log

def _tlog(token, *args, **kwargs):
    """Log with token prefix when token is meaningful."""
    from datetime import datetime
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if token and token != '__default__':
        print(f"[{ts}] [{token}]", *args, file=sys.stderr, flush=True, **kwargs)
    else:
        print(f"[{ts}]", *args, file=sys.stderr, flush=True, **kwargs)

class Session:
    def __init__(self, session_id, info, client=None):
        self.id = session_id
        self.info = info
        self.connect_at = time.time()
        self.disconnect_at = None
        self.type = info.get('type', 'ext_ws')
        self.ws_client = client if self.type == 'ext_ws' else None
        self.http_queue = client if self.type == 'http' else None
        self.created_by_tool = False
        self.client_id = info.get('client_id')
        self.tab_id = str(info.get('tab_id', session_id))
    @property
    def url(self): return self.info.get('url', '')
    def is_active(self):
        if self.type == 'http' and time.time() - self.connect_at > 60: self.mark_disconnected()
        return self.disconnect_at is None
    def reconnect(self, client, info):
        self.info = info
        self.type = info.get('type', 'ext_ws')
        if self.type == 'ext_ws':
            self.ws_client = client
            self.http_queue = None
        elif self.type == 'http':
            self.http_queue = client
        self.client_id = info.get('client_id', self.client_id)
        self.tab_id = str(info.get('tab_id', self.tab_id))
        self.connect_at = time.time()
        self.disconnect_at = None
    def mark_disconnected(self):
        if self.is_active(): log(f"Tab disconnected: {self.url} (Session: {self.id})")
        self.disconnect_at = time.time()


class UserContext:
    """Per-token isolated state: sessions, results, acks."""
    def __init__(self, token: str):
        self.token = token
        self.sessions: Dict[str, Session] = {}
        self.results: Dict[str, Any] = {}
        self.acks: Dict[str, bool] = {}
        self.extension_clients: Dict[str, WebSocket] = {}
        self.latest_extension_client_id: Optional[str] = None
        self.latest_session_id: Optional[str] = None
        self.created_at: float = time.time()
        self.last_active: float = time.time()
        self.grouped_tabs: Dict[str, Timer] = {}
        self.grouped_tab_versions: Dict[str, int] = {}
        self.status_cleanup_deadlines: Dict[str, float] = {}
        self._group_lock = threading.Lock()
        self.tool_created_tabs: set[str] = set()
        self.explicit_target_tabs: set[str] = set()
        from .refs import RefMap
        self.refs = RefMap()
        self.tab_aliases: Dict[str, str] = {}
        self.next_tab_alias_number: int = 1
        self.frame_target: Optional[str] = None
        self.frame_target_tab_id: Optional[str] = None
        self.frame_targets: Dict[str, str] = {}
        self.keyboard_modifiers_by_tab: Dict[str, int] = {}
        self.session_name: str = ""
        self.claimed_tabs: set[str] = set()
        self.visibility_mode: str = "visible"
        self.trace_enabled: bool = False
        self.trace_events: list[dict] = []
        self.recording: bool = False
        self.recorded_actions: list[dict] = []

    def clean_sessions(self):
        sids = list(self.sessions.keys())
        for sid in sids:
            session = self.sessions[sid]
            if not session.is_active() and time.time() - session.disconnect_at > 600:
                del self.sessions[sid]

    def get_all_active_sessions(self):
        return [{
            **session.info,
            'id': session.id,
            'tab_id': session.tab_id,
            'client_id': session.client_id,
        } for session in self.sessions.values()
                if session.is_active()]


class TokenManager:
    """Manages token -> UserContext mapping."""
    def __init__(self, allowed_tokens: Optional[List[str]] = None):
        self.contexts: Dict[str, UserContext] = {}
        self._lock = threading.Lock()
        self.allowed_tokens = set(allowed_tokens) if allowed_tokens else None

    def validate(self, token: str) -> bool:
        if self.allowed_tokens is None:
            return True
        return token in self.allowed_tokens

    def get_context(self, token: str) -> UserContext:
        with self._lock:
            if token not in self.contexts:
                self.contexts[token] = UserContext(token)
            ctx = self.contexts[token]
            ctx.last_active = time.time()
            return ctx

    def cleanup_expired(self, max_idle: float = 3600):
        with self._lock:
            expired = [t for t, ctx in self.contexts.items()
                       if time.time() - ctx.last_active > max_idle and t != '__default__']
            for t in expired:
                _tlog(t, f"[TokenManager] Cleaning expired context")
                del self.contexts[t]


class TMWebDriver:
    _TRANSIENT_TAB_STATUS_TITLES = {
        "读取中", "导航中", "等待中", "截图中", "批量操作中",
        "下滑中", "上滑中", "点击中", "移动中", "拖动中",
        "执行中", "创建中", "已读取", "已导航", "等待完成",
        "已截图", "已操作", "已下滑", "已上滑", "已点击",
        "已移动", "已拖动", "已执行", "已创建",
    }

    def __init__(self, host: str = '127.0.0.1', port: int = 18765, multi_user: bool = False, allowed_tokens: Optional[List[str]] = None):
        self.host, self.port = host, port
        self.multi_user = multi_user

        if multi_user:
            self.token_manager = TokenManager(allowed_tokens=allowed_tokens)
        else:
            self._default_ctx = UserContext("__default__")

        # Legacy attributes for backward compat (delegate to default context in single-user mode)
        self.is_remote = self._is_compatible_remote_bridge(host, port)
        if not self.is_remote:
            self.start_ws_server()
            self.start_http_server()
            self.start_status_cleanup_sweeper()
        else:
            self.remote = f'http://{self.host}:{self.port+1}/link'

    @staticmethod
    def _is_compatible_remote_bridge(host: str, port: int) -> bool:
        try:
            resp = requests.get(f'http://{host}:{port+1}/api/health', timeout=0.3)
            return bool(resp.ok)
        except Exception:
            return False

    def get_context(self, token: Optional[str] = None) -> UserContext:
        if not self.multi_user:
            return self._default_ctx
        if not token:
            return self.token_manager.get_context("__default__")
        if not self.token_manager.validate(token):
            raise ValueError(f"Token rejected: {token}")
        return self.token_manager.get_context(token)

    def _sessions_context(self, token: Optional[str] = None) -> UserContext:
        ctx = self.get_context(token)
        if not self.multi_user or token in (None, "", "__default__") or ctx.sessions or getattr(ctx, 'extension_clients', None):
            return ctx
        return self.get_context("__default__")

    # Backward-compatible properties that delegate to default context
    @property
    def sessions(self):
        return self._default_ctx.sessions if not self.multi_user else {}
    @property
    def results(self):
        return self._default_ctx.results if not self.multi_user else {}
    @property
    def acks(self):
        return self._default_ctx.acks if not self.multi_user else {}
    @property
    def latest_session_id(self):
        return self._default_ctx.latest_session_id if not self.multi_user else None
    @latest_session_id.setter
    def latest_session_id(self, value):
        if not self.multi_user:
            self._default_ctx.latest_session_id = value

    def start_http_server(self):
        self.app = app = bottle.Bottle()

        @app.route('/api/longpoll', method=['GET', 'POST'])
        def long_poll():
            data = request.json
            token = data.get('token', '__default__') if self.multi_user else '__default__'
            ctx = self.get_context(token)
            session_id = data.get('sessionId')
            session_info = {'url': data.get('url'), 'title': data.get('title', ''), 'type': 'http'}
            if session_id not in ctx.sessions:
                session = Session(session_id, session_info, queue.Queue())
                _tlog(token, f"Browser http connected: {session.url} (Session: {session_id})")
                ctx.sessions[session_id] = session
            session = ctx.sessions[session_id]
            if session.disconnect_at is not None and session.type != 'http': session.reconnect(queue.Queue(), session_info)
            session.disconnect_at = None
            if session.type == 'http': msgQ = session.http_queue
            else: return json.dumps({"id": "", "ret": "use ws"})
            session.connect_at = start_time = time.time()
            while time.time() - start_time < 5:
                try:
                    msg = msgQ.get(timeout=0.2)
                    try: ctx.acks[json.loads(msg).get('id','')] = True
                    except: traceback.print_exc()
                    return msg
                except queue.Empty: continue
            return json.dumps({"id": "", "ret": "next long-poll"})

        @app.route('/api/result', method=['GET','POST'])
        def result():
            data = request.json
            token = data.get('token', '__default__') if self.multi_user else '__default__'
            ctx = self.get_context(token)
            if data.get('type') == 'result':
                ctx.results[data.get('id')] = {'success': True, 'data': data.get('result'), 'newTabs': data.get('newTabs', []), 'browserClientId': data.get('browserClientId')}
            elif data.get('type') == 'error':
                ctx.results[data.get('id')] = {'success': False, 'data': data.get('error'), 'newTabs': data.get('newTabs', []), 'browserClientId': data.get('browserClientId')}
            return 'ok'

        @app.route('/link', method=['GET','POST'])
        def link():
            data = request.json
            token = data.get('token') if self.multi_user else None
            if data.get('cmd') == 'get_all_sessions': return json.dumps({'r': self.get_all_sessions(token=token)}, ensure_ascii=False)
            if data.get('cmd') == 'find_session':
                url_pattern = data.get('url_pattern', '')
                return json.dumps({'r': self.find_session(url_pattern, token=token)}, ensure_ascii=False)
            if data.get('cmd') == 'execute_js':
                session_id = data.get('sessionId')
                code = data.get('code')
                timeout = float(data.get('timeout', 10.0))
                try:
                    result = self.execute_js(
                        code,
                        timeout=timeout,
                        session_id=session_id,
                        token=token,
                        group_status=data.get('groupStatus'),
                        status_tab_id=data.get('statusTabId'),
                    )
                    _tlog(token, '[remote result]', (str(code)[:50] + ' RESULT:' +str(result)[:50]).replace('\n', ' '))
                    return json.dumps({'r': result}, ensure_ascii=False)
                except Exception as e:
                    return json.dumps({'r': {'error': str(e)}}, ensure_ascii=False)
            return 'ok'

        @app.route('/api/health', method=['GET'])
        def health():
            response.content_type = 'application/json'
            return json.dumps({'ok': True}, ensure_ascii=False)

        def run():
            from wsgiref.simple_server import make_server, WSGIServer, WSGIRequestHandler
            from socketserver import ThreadingMixIn
            class _T(ThreadingMixIn, WSGIServer): pass
            class _H(WSGIRequestHandler):
                def log_request(self, *a): pass
            make_server(self.host, self.port+1, app, server_class=_T, handler_class=_H).serve_forever()
        http_thread = threading.Thread(target=run, daemon=True)
        http_thread.start()  

    @staticmethod
    def _expired_status_tabs(ctx, now: float) -> list[str]:
        return [
            tab_id
            for tab_id, deadline in list(ctx.status_cleanup_deadlines.items())
            if deadline <= now and tab_id not in ctx.grouped_tabs
        ]

    @classmethod
    def _is_transient_tab_status_title(cls, title: str) -> bool:
        value = re.sub(r"^[^\w]+", "", str(title or "").strip(), flags=re.UNICODE)
        return value in cls._TRANSIENT_TAB_STATUS_TITLES or bool(re.fullmatch(r"\d+s", value))

    def _status_is_managed(self, tab_id: str) -> bool:
        contexts = (
            [self._default_ctx]
            if not self.multi_user
            else list(self.token_manager.contexts.values())
        )
        raw_tab_id = str(tab_id).rsplit(":", 1)[-1]
        for ctx in contexts:
            managed = self._status_managed_tab_ids(ctx)
            if str(tab_id) in managed:
                return True
            if any(item.rsplit(":", 1)[-1] == raw_tab_id for item in managed):
                return True
        return False

    def _reconcile_stale_status_tabs(self, tabs: list[dict], client_id: str, token=None) -> None:
        """Remove transient status groups whose owning daemon lifecycle is gone."""
        for tab in tabs:
            raw_tab_id = str(tab.get("id", ""))
            if not raw_tab_id or tab.get("groupId", -1) in (-1, None):
                continue
            tab_id = f"{client_id}:{raw_tab_id}"
            if self._status_is_managed(tab_id):
                continue
            try:
                result = self.execute_js(
                    json.dumps(
                        {"cmd": "tabGroups", "method": "get", "tabId": int(raw_tab_id)},
                        ensure_ascii=False,
                    ),
                    timeout=5,
                    session_id=tab_id,
                    token=token,
                )
                data = result.get("data", result) if isinstance(result, dict) else {}
                if isinstance(data, dict) and isinstance(data.get("data"), dict):
                    data = data["data"]
                title = data.get("title", "") if isinstance(data, dict) else ""
                if not self._is_transient_tab_status_title(title):
                    continue
                # An operation may have started while the group query was in
                # flight. Re-check immediately before removing browser state.
                if self._status_is_managed(tab_id):
                    continue
                _tlog(token, f"Cleaning stale tab status after daemon startup: {tab_id} ({title})")
                self.cleanup_tab_status(tab_id, token=token)
            except Exception as exc:
                _tlog(token, f"Failed to reconcile stale tab status for {tab_id}: {exc}")

    def start_status_cleanup_sweeper(self) -> None:
        def run():
            while True:
                time.sleep(5)
                contexts = [self._default_ctx] if not self.multi_user else list(self.token_manager.contexts.values())
                now = time.time()
                for ctx in contexts:
                    if not hasattr(ctx, 'status_cleanup_deadlines'):
                        continue
                    expired = []
                    with ctx._group_lock:
                        # A scheduled tab lifecycle owns its status until it
                        # finishes waiting/counting down and performs the cleanup
                        # itself.  Generic expiry must never ungroup it early.
                        expired = self._expired_status_tabs(ctx, now)
                    for tab_id in expired:
                        self.cleanup_tab_status(tab_id, token=ctx.token)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

    def clean_sessions(self, token=None):
        ctx = self.get_context(token)
        ctx.clean_sessions()

    def _cancel_tab_status_timers(self, tab_id: str, token=None) -> None:
        ctx = self.get_context(token)
        with ctx._group_lock:
            timers = ctx.grouped_tabs.pop(tab_id, None)
            if isinstance(timers, Timer):
                timers.cancel()
            elif isinstance(timers, list):
                for t in timers:
                    t.cancel()
            ctx.grouped_tab_versions[tab_id] = ctx.grouped_tab_versions.get(tab_id, 0) + 1
            if hasattr(ctx, 'status_cleanup_deadlines'):
                ctx.status_cleanup_deadlines.pop(tab_id, None)

    def start_ws_server(self) -> None:
        driver = self
        class JSExecutor(WebSocket):
            def handle(self) -> None:
                try:
                    data = json.loads(self.data)
                    if data.get('type') in ['ext_ready', 'tabs_update']:
                        token = data.get('token', '__default__') if driver.multi_user else '__default__'
                        ctx = driver.get_context(token)
                        self._token = token
                        client_id = data.get('browserClientId') or 'unknown-client'
                        ctx.extension_clients[client_id] = self
                        ctx.latest_extension_client_id = client_id
                        extension_id = data.get('extensionId')
                        extension_version = data.get('extensionVersion')
                        # Keep the version on the live client as well as on each
                        # tab session so doctor can distinguish a current
                        # worker from a legacy connection.
                        self.extension_version = extension_version or ''
                        browser = data.get('browser')
                        tabs = data.get('tabs', [])
                        current_tab_ids = {f"{client_id}:{tab['id']}" for tab in tabs}
                        _tlog(token, f"Received tabs update from {client_id}: {current_tab_ids}")
                        disconnected = []
                        for sid in list(ctx.sessions.keys()):
                            sess = ctx.sessions[sid]
                            if sess.type == 'ext_ws' and sess.client_id == client_id and sid not in current_tab_ids:
                                sess.mark_disconnected()
                                if sid not in ctx.tool_created_tabs:
                                    driver._cancel_tab_status_timers(sid, token=token)
                                raw_tab_id = sid.split(':', 1)[1] if ':' in sid else sid
                                disconnected.append(raw_tab_id)
                        if disconnected:
                            try:
                                self.send_message(json.dumps({'type': 'tabs_disconnected', 'tab_ids': disconnected}))
                            except Exception as e:
                                log(f"Failed to send tabs_disconnected: {e}")
                        raw_ids = {str(tab['id']) for tab in tabs}
                        driver._reconcile_cross_client_duplicates(client_id, raw_ids, token=token)
                        for tab in tabs:
                            raw_tab_id = str(tab['id'])
                            session_id = f"{client_id}:{raw_tab_id}"
                            session_info = {'url': tab.get('url'), 'title': tab.get('title', ''), 'connected_at': time.time(), 'type': 'ext_ws', 'client_id': client_id, 'tab_id': raw_tab_id, 'extension_id': extension_id, 'extension_version': extension_version, 'browser': browser}
                            sess = ctx.sessions.get(session_id)
                            if sess and sess.is_active(): sess.info = session_info
                            else: driver._register_client(session_id, self, session_info, token=token)
                        if data.get('type') == 'ext_ready':
                            # The browser can outlive the daemon, while status
                            # timers cannot. Reconcile only on the initial ready
                            # handshake; ordinary tabs_update events must not
                            # disturb an operation already in flight.
                            reconcile_thread = threading.Thread(
                                target=driver._reconcile_stale_status_tabs,
                                args=(list(tabs), client_id, token),
                                daemon=True,
                            )
                            reconcile_thread.start()
                    elif data.get('type') == 'ack':
                        token = getattr(self, '_token', '__default__')
                        ctx = driver.get_context(token)
                        ctx.acks[data.get('id','')] = True
                    elif data.get('type') == 'result':
                        token = getattr(self, '_token', '__default__')
                        ctx = driver.get_context(token)
                        ctx.results[data.get('id')] = {'success': True, 'data': data.get('result'), 'newTabs': data.get('newTabs', []), 'browserClientId': data.get('browserClientId')}
                    elif data.get('type') == 'error':
                        token = getattr(self, '_token', '__default__')
                        ctx = driver.get_context(token)
                        ctx.results[data.get('id')] = {'success': False, 'data': data.get('error'), 'newTabs': data.get('newTabs', []), 'browserClientId': data.get('browserClientId')}
                except Exception as e:
                    _tlog(getattr(self, '_token', None), f"Error handling message: {e}")
                    if hasattr(self, 'data'): _tlog(getattr(self, '_token', None), self.data)
            def connected(self):
                log(f"New WS connection from {self.address}")
            def handle_close(self):
                _tlog(getattr(self, '_token', None), f"WS Connection closed: {self.address}")
                driver._unregister_client(self)

        max_port_attempts = 3
        for attempt in range(max_port_attempts):
            try:
                port = self.port + attempt
                self.server = WebSocketServer(self.host, port, JSExecutor)
                if attempt > 0:
                    self.port = port
                break
            except OSError:
                if attempt == max_port_attempts - 1:
                    raise
                log(f"Port {self.port + attempt} in use, trying {self.port + attempt + 1}")

        server_thread = threading.Thread(target=self.server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        log(f"WebSocket server running on ws://{self.host}:{self.port}")

    def _reconcile_cross_client_duplicates(self, reporting_client_id: str, raw_tab_ids: set, token: Optional[str] = None) -> None:
        """Demote other clients' active ext_ws sessions that share a raw tab id with the
        reporting client, so that when two extensions (e.g. dev + store) are connected to
        the same daemon, transport selection never sees the same Chrome tab twice under
        different browserClientIds.
        """
        if not raw_tab_ids:
            return
        ctx = self.get_context(token)
        for sid, sess in list(ctx.sessions.items()):
            if not sess.is_active() or sess.type != 'ext_ws':
                continue
            if sess.client_id == reporting_client_id:
                continue
            if sess.tab_id in raw_tab_ids:
                sess.mark_disconnected()
                self._cancel_tab_status_timers(sid, token=token)
                _tlog(token, f"Cross-client duplicate demoted: {sid} (raw tab {sess.tab_id}) now owned by {reporting_client_id}")

    def _register_client(self, session_id: str, client: WebSocket, session_info, token: Optional[str] = None) -> None:
        ctx = self.get_context(token)
        is_new_session = session_id not in ctx.sessions

        if is_new_session:
            session = Session(session_id, session_info, client)
            if session_id in ctx.tool_created_tabs:
                session.created_by_tool = True
            ctx.sessions[session_id] = session
            _tlog(token, f"New tab connected: {session.url} (Session: {session_id})")
        else:
            session = ctx.sessions[session_id]
            session.reconnect(client, session_info)
            if session_id in ctx.tool_created_tabs:
                session.created_by_tool = True
            _tlog(token, f"Tab reconnected: {session.url} (Session: {session_id})")

        ctx.latest_session_id = session_id

    def _unregister_client(self, client: WebSocket) -> None:
        if self.multi_user:
            for ctx in self.token_manager.contexts.values():
                for session in ctx.sessions.values():
                    if session.ws_client == client: session.mark_disconnected()
                for client_id, ext_client in list(getattr(ctx, 'extension_clients', {}).items()):
                    if ext_client == client:
                        del ctx.extension_clients[client_id]
                        if ctx.latest_extension_client_id == client_id:
                            ctx.latest_extension_client_id = next(iter(ctx.extension_clients), None)
        else:
            for session in self._default_ctx.sessions.values():
                if session.ws_client == client: session.mark_disconnected()
            for client_id, ext_client in list(getattr(self._default_ctx, 'extension_clients', {}).items()):
                if ext_client == client:
                    del self._default_ctx.extension_clients[client_id]
                    if self._default_ctx.latest_extension_client_id == client_id:
                        self._default_ctx.latest_extension_client_id = next(iter(self._default_ctx.extension_clients), None)

    def broadcast_extension_event(self, payload: Dict[str, Any], token=None) -> None:
        """Send a structured event to active extension WebSocket sessions."""
        ctx = self.get_context(token)
        message = json.dumps(payload, ensure_ascii=False)
        if payload.get('type') == 'mouse_visual':
            # Visual events are extension-level messages addressed by raw
            # tabId.  A tab can be temporarily absent from tabs_update while
            # it is opening/reloading, so routing through its Session drops
            # the event even though the extension WebSocket is healthy.
            targets = []
            seen_clients = set()
            client_contexts = [ctx]
            if self.multi_user and not getattr(ctx, 'extension_clients', {}):
                # The browser extension connects without an agent token and
                # therefore lives in __default__, while actions are commonly
                # dispatched in a token-scoped context.
                client_contexts.append(self.get_context('__default__'))
            for client_context in client_contexts:
                for client in getattr(client_context, 'extension_clients', {}).values():
                    if client is not None and id(client) not in seen_clients:
                        seen_clients.add(id(client))
                        targets.append(client)
        else:
            targets = [session.ws_client for session in list(ctx.sessions.values())
                       if session.is_active() and session.type == 'ext_ws' and session.ws_client]
        if payload.get('type') == 'mouse_visual':
            _tlog(token, f"mouse_visual broadcast targets={len(targets)} tab={payload.get('tabId')} event={payload.get('event', {}).get('type')}")
        for client in targets:
            try:
                client.send_message(message)
            except Exception as e:
                _tlog(token, f"Failed to broadcast extension event: {e}")

    def execute_js(self, code, timeout=15, session_id=None, token=None, group_status=None, status_tab_id=None) -> Any:
        ctx = self.get_context(token)
        session_ctx = self._sessions_context(token)
        explicit_session = session_id is not None
        if session_id is None:
            if not self._is_extension_command(code):
                raise ValueError("session_id is required for page scripts")
            session_id = self._default_transport_session_id(token=token)
            if session_id is None:
                client = self._extension_client_for_command(code, token=token)
                if client is not None:
                    return self._execute_extension_command_via_client(client, code, timeout=timeout, token=token)
        if self.is_remote:
            _tlog(token, 'remote_execute_js')
            cmd = {"cmd": "execute_js", "sessionId": session_id,
                   "code": code, "timeout": str(timeout)}
            if token: cmd["token"] = token
            if group_status: cmd["groupStatus"] = group_status
            if status_tab_id is not None: cmd["statusTabId"] = str(status_tab_id)
            response = self._remote_cmd(cmd).get('r', {})
            if response.get('error'): raise Exception(response['error'])
            return response

        session = session_ctx.sessions.get(session_id)
        is_tool_tab = session_id in ctx.tool_created_tabs
        if not session or not session.is_active():
            wait_time = 5 if is_tool_tab else 3
            time.sleep(wait_time)
            session = session_ctx.sessions.get(session_id)
            if not session or not session.is_active():
                if explicit_session:
                    if is_tool_tab:
                        raise ValueError(f"工具创建的标签页 {session_id} 尚未连接到扩展，可能正在加载中")
                    raise ValueError(f"会话ID {session_id} 未连接")
                if self._is_extension_command(code):
                    session_id = self._default_transport_session_id(token=token)
                    session = session_ctx.sessions.get(session_id) if session_id else None
                    if not session or not session.is_active():
                        client = self._extension_client_for_command(code, token=token)
                        if client is not None:
                            return self._execute_extension_command_via_client(client, code, timeout=timeout, token=token)
                if not session or not session.is_active():
                    raise ValueError(f"会话ID {session_id} 未连接")

        tp = session.type
        if tp not in ('http', 'ext_ws'):
            raise ValueError(f"Unsupported session type: {tp}")
        exec_id = str(uuid.uuid4())
        payload_dict = {'id': exec_id, 'code': code}
        payload_dict['tabId'] = int(session.tab_id)
        if group_status: payload_dict['groupStatus'] = group_status
        if group_status and status_tab_id is None:
            status_tab_id = session.tab_id
        if status_tab_id is not None: payload_dict['statusTabId'] = int(status_tab_id)
        payload = json.dumps(payload_dict)

        if group_status:
            _tlog(token, f"execute_js routing transport={session.tab_id} status_target={status_tab_id} group_status={group_status}")

        if tp == 'ext_ws': session.ws_client.send_message(payload)
        elif tp == 'http': session.http_queue.put(payload)

        start_time = time.time()
        session_ctx.clean_sessions()
        hasjump = acked = False

        while exec_id not in session_ctx.results:
            time.sleep(0.2)
            if not acked and exec_id in session_ctx.acks:
                acked = True; start_time = time.time()
            if tp == 'ext_ws':
                if not session.is_active(): hasjump = True
                if hasjump and session.is_active():
                    return {'result': f"Session {session_id} reloaded.", "closed":1}
            if time.time() - start_time > timeout:
                if tp == 'ext_ws':
                    if hasjump: return {'result': f"Session {session_id} reloaded and new page is loading...", 'closed':1}
                    if acked: return {"result": f"No response data in {timeout}s (ACK received, script may still be running)"}
                    return {"result": f"No response data in {timeout}s (no ACK, script may not have been delivered)"}
                elif tp == 'http':
                    if acked: return {"result": f"Session {session_id} no response in {timeout}s (delivered but no result)"}
                    return {"result": f"Session {session_id} no response in {timeout}s (script not polled)"}

        result = session_ctx.results.pop(exec_id)
        if exec_id in session_ctx.acks: session_ctx.acks.pop(exec_id)
        if not result['success']: raise Exception(result['data'])
        rr = {'data': result['data']}
        newtabs = result.get('newTabs', []); [x.pop('ts', None) for x in newtabs]
        if newtabs: rr['newTabs'] = newtabs
        if result.get('browserClientId'):
            rr['browserClientId'] = result.get('browserClientId')
        return rr

    def _extension_client_for_command(self, code: str | dict, token=None):
        ctx = self._sessions_context(token)
        clients = getattr(ctx, 'extension_clients', {})
        if not clients:
            return None
        data = code if isinstance(code, dict) else None
        if data is None:
            try:
                data = json.loads(code)
            except Exception:
                data = {}
        tab_id = str(data.get('tabId', '')) if isinstance(data, dict) else ''
        if ':' in tab_id:
            client_id = tab_id.split(':', 1)[0]
            if client_id in clients:
                return clients[client_id]
        latest_client_id = getattr(ctx, 'latest_extension_client_id', None)
        if latest_client_id in clients:
            return clients[latest_client_id]
        return next(iter(clients.values()), None)

    def _execute_extension_command_via_client(self, client, code, timeout=15, token=None):
        session_ctx = self._sessions_context(token)
        exec_id = str(uuid.uuid4())
        payload = json.dumps({'id': exec_id, 'code': code}, ensure_ascii=False)
        client.send_message(payload)

        start_time = time.time()
        acked = False
        while exec_id not in session_ctx.results:
            time.sleep(0.2)
            if not acked and exec_id in session_ctx.acks:
                acked = True; start_time = time.time()
            if time.time() - start_time > timeout:
                if acked: return {"result": f"No response data in {timeout}s (ACK received, script may still be running)"}
                return {"result": f"No response data in {timeout}s (no ACK, script may not have been delivered)"}

        result = session_ctx.results.pop(exec_id)
        if exec_id in session_ctx.acks: session_ctx.acks.pop(exec_id)
        if not result['success']: raise Exception(result['data'])
        rr = {'data': result['data']}
        newtabs = result.get('newTabs', []); [x.pop('ts', None) for x in newtabs]
        if newtabs: rr['newTabs'] = newtabs
        if result.get('browserClientId'):
            rr['browserClientId'] = result.get('browserClientId')
        return rr

    def _remote_cmd(self, cmd):
        try:
            session = requests.Session()
            session.trust_env = False
            resp = session.post(self.remote, headers={"Content-Type": "application/json"}, json=cmd, timeout=30)
            resp.raise_for_status()
            if not resp.text.strip():
                raise RuntimeError(f"TMWebDriver master returned an empty response for {cmd.get('cmd')}")
            try:
                return resp.json()
            except ValueError as e:
                snippet = resp.text[:200].replace("\n", " ")
                raise RuntimeError(f"TMWebDriver master returned non-JSON response for {cmd.get('cmd')}: {snippet}") from e
        except (ConnectionError, requests.exceptions.ConnectionError):
            raise ConnectionError("TMWebDriver master未运行，看tmwebdriver_sop启动master")

    def get_all_sessions(self, token=None):
        if self.is_remote:
            cmd = {"cmd": "get_all_sessions"}
            if token: cmd["token"] = token
            return self._remote_cmd(cmd).get('r', [])
        ctx = self._sessions_context(token)
        return ctx.get_all_active_sessions()

    def count_extension_clients(self) -> int:
        if self.is_remote:
            return 0
        if not self.multi_user:
            return len(getattr(self._default_ctx, 'extension_clients', {}))
        total = 0
        for ctx in self.token_manager.contexts.values():
            total += len(getattr(ctx, 'extension_clients', {}))
        return total

    def extension_versions(self) -> list[str]:
        """Return versions reported by connected extension clients.

        An empty string means the client predates version reporting; retaining
        that value lets diagnostics distinguish an old worker from a current
        worker instead of treating both as merely "connected".
        """
        versions: set[str] = set()
        contexts = [self._default_ctx] if not self.multi_user else list(self.token_manager.contexts.values())
        for ctx in contexts:
            for client in getattr(ctx, 'extension_clients', {}).values():
                versions.add(str(getattr(client, 'extension_version', '') or ''))
        return sorted(versions)

    def get_session_dict(self, token=None):
        return {session['id']: session['url'] for session in self.get_all_sessions(token=token)}

    def get_ext_ws_transport_session_id(self, token=None, client_id: Optional[str] = None, avoid_tabs: Optional[set] = None) -> Optional[str]:
        """Return the id of any active ext_ws session suitable for sending commands.

        Preference order when ``avoid_tabs`` is provided:
        1. an ext_ws session NOT in ``avoid_tabs`` (i.e. not currently being badged/counted down);
        2. any ext_ws session (last resort).

        Without ``avoid_tabs`` the behaviour is unchanged from historical code so that
        transport-only callers (no target) keep working.
        """
        ctx = self._sessions_context(token)
        avoid = avoid_tabs or set()
        fallback: Optional[str] = None
        for session in ctx.sessions.values():
            if not (session.is_active() and session.type == 'ext_ws'):
                continue
            if client_id is not None and session.client_id != client_id:
                continue
            if session.id in avoid:
                if fallback is None:
                    fallback = session.id
                continue
            return session.id
        return fallback

    def _default_transport_session_id(self, token=None) -> Optional[str]:
        """Pick a transport-only session for extension commands. Never a page target."""
        ctx = self._sessions_context(token)
        if ctx.latest_session_id:
            session = ctx.sessions.get(ctx.latest_session_id)
            if session and session.is_active() and session.type == "ext_ws":
                return session.id
        return self.get_ext_ws_transport_session_id(token=token)

    def _transport_session_id(self, target_tab_id: str, token=None) -> Optional[str]:
        """Pick the WebSocket transport session for a command targeting target_tab_id.

        If target_tab_id itself is an active ext_ws session, use it directly.
        Otherwise find any available ext_ws session to route the command through,
        preferring one from the same browser client and AVOIDING tabs that are
        currently under status management (being badged or counted down) so that
        an unrelated user tab never receives another tab's operation badge.
        """
        ctx = self._sessions_context(token)
        session = ctx.sessions.get(str(target_tab_id))
        if session and session.is_active() and session.type == 'ext_ws':
            return str(target_tab_id)
        client_id = session.client_id if session else None
        avoid = self._status_managed_tab_ids(ctx)
        # Never avoid the target itself (it may be under its own countdown; that's fine,
        # we'll only hit this branch when the target is NOT an active ext_ws anyway).
        avoid.discard(str(target_tab_id))
        if client_id:
            same_client = self.get_ext_ws_transport_session_id(token=token, client_id=client_id, avoid_tabs=avoid)
            if same_client:
                return same_client
        chosen = self.get_ext_ws_transport_session_id(token=token, avoid_tabs=avoid)
        if chosen is None:
            # Last resort: ignore avoid set entirely, prefer same client then any client.
            chosen = self.get_ext_ws_transport_session_id(token=token, client_id=client_id)
        if chosen is None:
            chosen = self.get_ext_ws_transport_session_id(token=token)
        return chosen

    @staticmethod
    def _status_managed_tab_ids(ctx) -> set:
        """Canonical session ids currently being badged or counted down."""
        ids = set(ctx.status_cleanup_deadlines.keys()) if hasattr(ctx, 'status_cleanup_deadlines') else set()
        ids |= set(ctx.grouped_tabs.keys()) if hasattr(ctx, 'grouped_tabs') else set()
        return {str(i) for i in ids}

    def _raw_tab_id(self, tab_id: str | int, token=None) -> str:
        """Return the raw Chrome tab id for a canonical session id or raw tab id."""
        raw = str(tab_id)
        ctx = self._sessions_context(token)
        session = ctx.sessions.get(raw)
        if session:
            return session.tab_id
        if ":" in raw:
            return raw.rsplit(":", 1)[1]
        return raw

    def find_session(self, url_pattern: str, token=None):
        ctx = self._sessions_context(token)
        if url_pattern == '':
            session = ctx.sessions.get(ctx.latest_session_id)
            return [(session.id, session.info)] if session else []
        matching_sessions = []
        for session in ctx.sessions.values():
            if not session.is_active(): continue
            if 'url' in session.info and url_pattern in session.info['url']:
                matching_sessions.append((session.id, session.info))
        return matching_sessions

    def set_session(self, url_pattern: str, token=None) -> Optional[str]:
        ctx = self._sessions_context(token)
        if self.is_remote:
            cmd = {"cmd": "find_session", "url_pattern": url_pattern}
            if token: cmd["token"] = token
            matched = self._remote_cmd(cmd).get('r', [])
        else:
            matched = self.find_session(url_pattern, token=token)
        if not matched:
            _tlog(token, f"警告: 未找到URL包含 '{url_pattern}' 的会话")
            return None
        if len(matched) > 1: _tlog(token, f"警告: 找到多个URL包含 '{url_pattern}' 的会话，选择第一个")
        session_id, info = matched[0]
        _tlog(token, f"匹配会话: {session_id}: {info['url']}")
        return session_id

    def jump(self, url, timeout=10, token=None, group_status=None, session_id=None):
        if session_id is None:
            raise ValueError("session_id is required for navigation")
        return self.execute_js(f"window.location.href='{url}'", timeout=timeout, token=token, group_status=group_status, session_id=session_id)

    def new_tab(self, url, timeout=15, token=None) -> Any:
        try:
            result = self.execute_js(
                json.dumps({"cmd": "tabs", "method": "create", "url": url}, ensure_ascii=False),
                timeout=timeout, token=token
            )
            data = result.get('data', result)
            browser_client_id = result.get('browserClientId')
            if isinstance(data, dict) and 'id' in data:
                raw_tab_id = str(data['id'])
                session_id = f"{browser_client_id}:{raw_tab_id}" if browser_client_id else raw_tab_id
                data = {
                    **data,
                    'id': session_id,
                    'tab_id': raw_tab_id,
                }
                if browser_client_id:
                    data['browserClientId'] = browser_client_id
                ctx = self.get_context(token)
                ctx.tool_created_tabs.add(session_id)
                session = ctx.sessions.get(session_id)
                if session:
                    session.created_by_tool = True
            return data
        except Exception:
            _tlog(token, f"new_tab failed for url {url}")
            raise

    def new_window(self, url, timeout=15, token=None) -> Any:
        try:
            result = self.execute_js(
                json.dumps({"cmd": "windows", "method": "create", "url": url}, ensure_ascii=False),
                timeout=timeout, token=token
            )
            data = result.get('data', result)
            browser_client_id = result.get('browserClientId')
            if isinstance(data, dict):
                tab = data.get('tab') or {}
                raw_tab_id = str(tab.get('id', ''))
                session_id = f"{browser_client_id}:{raw_tab_id}" if browser_client_id and raw_tab_id else raw_tab_id
                normalized_tab = {**tab, 'id': session_id, 'tab_id': raw_tab_id}
                if browser_client_id:
                    normalized_tab['browserClientId'] = browser_client_id
                data = {**data, 'tab': normalized_tab}
                if session_id:
                    ctx = self.get_context(token)
                    ctx.tool_created_tabs.add(session_id)
                    session = ctx.sessions.get(session_id)
                    if session:
                        session.created_by_tool = True
            return data
        except Exception:
            _tlog(token, f"new_window failed for url {url}")
            raise

    @staticmethod
    def _is_extension_command(code: str | dict) -> bool:
        if isinstance(code, dict):
            data = code
        else:
            try:
                data = json.loads(code)
            except Exception:
                return False
        return isinstance(data, dict) and data.get("cmd") in {"tabs", "windows", "tabGroups", "tabStatus", "tabFavicon", "cdp", "batch", "management", "contentSettings", "mouseVisualState", "clipboard", "history", "bookmarks", "downloads", "sessions", "topSites", "notifications"}

    @staticmethod
    def _infer_js_action(script: str) -> str:
        s = script.strip()
        m = re.search(r'scrollBy\s*\(\s*0\s*,\s*(-?\d+)', s)
        if m:
            return 'scroll_down' if int(m.group(1)) > 0 else 'scroll_up'
        m = re.search(r'scrollTo\s*\(\s*0\s*,\s*(-?\d+)', s)
        if m:
            return 'scroll_down' if int(m.group(1)) > 0 else 'scroll_up'
        if '.click()' in s:
            return 'click'
        return 'js_execute'

    def update_tab_group(self, tab_id: str, group_name: str, token=None) -> None:
        try:
            raw_tab_id = self._raw_tab_id(tab_id, token=token)
            transport_sid = self._transport_session_id(tab_id, token=token)
            ctx = self.get_context(token)
            if hasattr(ctx, 'status_cleanup_deadlines'):
                with ctx._group_lock:
                    ctx.status_cleanup_deadlines[str(tab_id)] = time.time() + 60
            transport_raw = None
            tsession = self._sessions_context(token).sessions.get(transport_sid) if transport_sid else None
            if tsession:
                transport_raw = tsession.tab_id
            result = self.execute_js(
                json.dumps({"cmd": "tabGroups", "method": "group", "tabId": int(raw_tab_id), "title": group_name}, ensure_ascii=False),
                timeout=5,
                session_id=transport_sid,
                token=token,
                group_status=group_name,
                status_tab_id=raw_tab_id,
            )
            _tlog(token, f"update_tab_group ok status_target={raw_tab_id} transport={transport_raw or transport_sid} label={group_name}")
            return result.get('data', result)
        except Exception:
            _tlog(token, f"update_tab_group failed for tab {tab_id}")
            pass

    def cleanup_tab_status(self, tab_id: str, token=None) -> None:
        try:
            raw_tab_id = self._raw_tab_id(tab_id, token=token)
            transport_sid = self._transport_session_id(tab_id, token=token)
            result = self.execute_js(
                json.dumps({"cmd": "tabStatus", "method": "cleanup", "tabId": int(raw_tab_id)}, ensure_ascii=False),
                timeout=5, session_id=transport_sid, token=token
            )
            data = result.get('data', result)
            cleanup_ok = isinstance(data, dict) and (data.get('ok') is True or data.get('gone') is True)
            if not cleanup_ok:
                if isinstance(data, dict) and data.get('ok') is False:
                    _tlog(token, f"cleanup_tab_status returned error for tab {tab_id}: {data.get('error')}")
                else:
                    _tlog(token, f"cleanup_tab_status did not confirm cleanup for tab {tab_id}: {data}")
            ctx = self.get_context(token)
            if cleanup_ok and hasattr(ctx, 'status_cleanup_deadlines'):
                with ctx._group_lock:
                    ctx.status_cleanup_deadlines.pop(str(tab_id), None)
            return data
        except Exception as exc:
            _tlog(token, f"cleanup_tab_status failed for tab {tab_id}: {exc}")

    def remove_tab_group(self, tab_id: str, token=None) -> None:
        return self.cleanup_tab_status(tab_id, token=token)

    def close_tab(self, tab_id: str, token=None) -> bool:
        try:
            raw_tab_id = self._raw_tab_id(tab_id, token=token)
            transport_sid = self._transport_session_id(tab_id, token=token)
            _tlog(token, f"close_tab: canonical={tab_id} raw={raw_tab_id} transport={transport_sid}")
            result = self.execute_js(
                json.dumps({"cmd": "tabs", "method": "close", "tabId": int(raw_tab_id)}, ensure_ascii=False),
                timeout=5, session_id=transport_sid, token=token
            )
            data = result.get('data', result) if isinstance(result, dict) else result
            close_ok = isinstance(data, dict) and data.get('ok') is True
            close_gone = isinstance(data, dict) and (data.get('gone') is True or 'No tab with id' in str(data.get('error', '')))
            if not (close_ok or close_gone):
                _tlog(token, f"close_tab did not confirm close for tab {tab_id}: {data}")
            return bool(close_ok or close_gone)
        except Exception as exc:
            if 'No tab with id' in str(exc):
                _tlog(token, f"close_tab: tab {tab_id} is already gone")
                return True
            _tlog(token, f"close_tab failed for tab {tab_id}: {exc}")
            return False

    def _schedule_tab_close(self, tab_id: str, timeout: float = 60, token=None, close: bool = True) -> None:
        ctx = self.get_context(token)
        with ctx._group_lock:
            if tab_id in ctx.grouped_tabs:
                timers = ctx.grouped_tabs[tab_id]
                if isinstance(timers, Timer):
                    timers.cancel()
                elif isinstance(timers, list):
                    for t in timers:
                        t.cancel()

            generation = ctx.grouped_tab_versions.get(tab_id, 0) + 1
            ctx.grouped_tab_versions[tab_id] = generation
            timers = []
            ctx.grouped_tabs[tab_id] = timers

            def _is_current_schedule():
                with ctx._group_lock:
                    return (
                        ctx.grouped_tab_versions.get(tab_id) == generation
                        and ctx.grouped_tabs.get(tab_id) is timers
                    )

            def _update_waiting():
                if not _is_current_schedule():
                    return
                try:
                    _tlog(token, f"_schedule_tab_close: update_waiting for {tab_id}")
                    self.update_tab_group(tab_id, "等待中", token=token)
                except Exception:
                    pass

            def _countdown(remaining):
                if not _is_current_schedule():
                    return
                if remaining > 0:
                    try:
                        self.update_tab_group(tab_id, f"{remaining}s", token=token)
                    except Exception:
                        pass
                    if not _is_current_schedule():
                        try:
                            self.remove_tab_group(tab_id, token=token)
                        except Exception:
                            pass
                        return
                    t = Timer(1.0, lambda: _countdown(remaining - 1))
                    t.daemon = True
                    with ctx._group_lock:
                        if (
                            ctx.grouped_tab_versions.get(tab_id) == generation
                            and ctx.grouped_tabs.get(tab_id) is timers
                        ):
                            timers.append(t)
                            t.start()
                else:
                    # Keep countdown and close on one serial chain.  Group/status
                    # updates can take noticeable time in Chromium, so an
                    # independent absolute close timer could fire around 3s and
                    # race with later 2s/1s updates, recreating a group after it
                    # had already been cleaned up.
                    _fire_and_cleanup()

            def _start_countdown():
                if not _is_current_schedule():
                    return
                _countdown(10)

            def _fire_and_cleanup():
                if not _is_current_schedule():
                    return
                try:
                    _tlog(token, f"_schedule_tab_close: fire_and_cleanup for {tab_id} close={close} in_tool_created={tab_id in ctx.tool_created_tabs}")
                    self.remove_tab_group(tab_id, token=token)
                    should_close = close and tab_id in ctx.tool_created_tabs
                    close_ok = False
                    if should_close:
                        close_result = self.close_tab(tab_id, token=token)
                        close_ok = close_result is not False
                        if not close_ok:
                            _tlog(token, f"_schedule_tab_close: close failed for {tab_id}; retrying")
                            self._schedule_tab_close(tab_id, timeout=5, token=token, close=True)
                    else:
                        _tlog(token, f"_schedule_tab_close: skipping close for {tab_id} (close={close}, in_tool_created={tab_id in ctx.tool_created_tabs})")
                finally:
                    with ctx._group_lock:
                        if ctx.grouped_tab_versions.get(tab_id) == generation:
                            ctx.grouped_tabs.pop(tab_id, None)
                            if close and (not should_close or close_ok):
                                ctx.tool_created_tabs.discard(tab_id)

            if close and timeout > 10:
                waiting_timer = Timer(8.0, _update_waiting)
                waiting_timer.daemon = True
                waiting_timer.start()
                timers.append(waiting_timer)

                countdown_start = timeout - 10
                countdown_timer = Timer(countdown_start, _start_countdown)
                countdown_timer.daemon = True
                countdown_timer.start()
                timers.append(countdown_timer)

            if not (close and timeout > 10):
                close_timer = Timer(timeout, _fire_and_cleanup)
                close_timer.daemon = True
                close_timer.start()
                timers.append(close_timer)

    def _cancel_tab_close(self, tab_id: str, token=None) -> None:
        ctx = self.get_context(token)
        with ctx._group_lock:
            if tab_id in ctx.grouped_tabs:
                timers = ctx.grouped_tabs[tab_id]
                if isinstance(timers, Timer):
                    timers.cancel()
                elif isinstance(timers, list):
                    for t in timers:
                        t.cancel()
                del ctx.grouped_tabs[tab_id]
            ctx.grouped_tab_versions[tab_id] = ctx.grouped_tab_versions.get(tab_id, 0) + 1
        self.remove_tab_group(tab_id, token=token)
    
if __name__ == "__main__":
    driver = TMWebDriver(host='127.0.0.1', port=18765)
