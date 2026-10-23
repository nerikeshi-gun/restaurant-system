// 自動再接続つきWebSocket（卓上・店員・お客様画面で共通利用）
//
// 端末のスリープ復帰やWi-Fi切替では、切れたことに気づけない「半開き」接続が残る。
// そのため次の3つで復旧する。
//  1. 10秒ごとにpingを送り、5秒以内にpongが来なければ切断して再接続する
//  2. 画面が見える状態に戻った時、ネットワークがオンラインに戻った時に即座に再接続する
//  3. 再接続するたびに指数バックオフ（1.5秒→最大10秒）で待つ
//
// state: 'connecting' | 'connected' | 'reconnecting' | 'offline' | 'server_unreachable'
//   offline            … 端末自身がネットワークにつながっていない（Wi-Fi切断など）
//   server_unreachable … ネットワークはあるが、親機PC（サーバー）に届かない
window.createReconnectingSocket = function createReconnectingSocket({ path, onOpen, onMessage, onState }) {
  const HEARTBEAT_INTERVAL_MS = 10000;
  const HEARTBEAT_TIMEOUT_MS = 5000;
  const BASE_DELAY_MS = 1500;
  const MAX_DELAY_MS = 10000;

  let socket = null;
  let state = 'connecting';
  let attempt = 0;
  let reconnectTimer = null;
  let heartbeatTimer = null;
  let heartbeatDeadline = null;
  let stopped = false;

  function setState(next) {
    if (state === next) return;
    state = next;
    if (onState) onState(next);
  }

  function clearHeartbeat() {
    clearInterval(heartbeatTimer); clearTimeout(heartbeatDeadline);
    heartbeatTimer = null; heartbeatDeadline = null;
  }

  function sendHeartbeat() {
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    try { socket.send('ping'); } catch (_) { socket.close(); return; }
    clearTimeout(heartbeatDeadline);
    heartbeatDeadline = setTimeout(() => { if (socket) socket.close(); }, HEARTBEAT_TIMEOUT_MS);
  }

  // 切れた原因を切り分けて表示用の状態にする
  async function diagnose() {
    if (!navigator.onLine) { setState('offline'); return; }
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 3000);
      const response = await fetch('/api/v1/health', { cache: 'no-store', signal: controller.signal });
      clearTimeout(timer);
      setState(response.ok ? 'reconnecting' : 'server_unreachable');
    } catch (_) {
      setState(navigator.onLine ? 'server_unreachable' : 'offline');
    }
  }

  function scheduleReconnect(delay) {
    clearTimeout(reconnectTimer);
    const wait = delay !== undefined ? delay : Math.min(BASE_DELAY_MS * 2 ** attempt, MAX_DELAY_MS);
    attempt += 1;
    reconnectTimer = setTimeout(connect, wait);
  }

  function connect() {
    clearTimeout(reconnectTimer);
    if (stopped) return;
    if (socket && [WebSocket.CONNECTING, WebSocket.OPEN].includes(socket.readyState)) return;
    if (state !== 'connected') setState(state === 'connecting' ? 'connecting' : 'reconnecting');

    const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
    const current = new WebSocket(`${protocol}://${location.host}${path}`);
    socket = current;

    current.onopen = () => {
      if (socket !== current) return;
      attempt = 0;
      setState('connected');
      clearHeartbeat();
      sendHeartbeat();
      heartbeatTimer = setInterval(sendHeartbeat, HEARTBEAT_INTERVAL_MS);
      if (onOpen) onOpen();
    };
    current.onmessage = event => {
      if (socket !== current) return;
      let data = null;
      try { data = JSON.parse(event.data); } catch (_) {}
      if (data && data.type === 'connection.pong') {
        clearTimeout(heartbeatDeadline); heartbeatDeadline = null;
        return;
      }
      if (onMessage) onMessage(event, data);
    };
    current.onerror = () => current.close();
    current.onclose = () => {
      if (socket !== current) return;
      clearHeartbeat(); socket = null;
      setState('reconnecting');
      diagnose();
      scheduleReconnect();
    };
  }

  window.addEventListener('offline', () => { setState('offline'); if (socket) socket.close(); });
  window.addEventListener('online', () => { attempt = 0; setState('reconnecting'); scheduleReconnect(0); });
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState !== 'visible') return;
    if (!socket || socket.readyState !== WebSocket.OPEN) { attempt = 0; scheduleReconnect(0); }
    else sendHeartbeat();   // 復帰直後に生存確認。応答がなければ5秒で切断→再接続
  });

  connect();
  return { close() { stopped = true; clearTimeout(reconnectTimer); clearHeartbeat(); if (socket) socket.close(); } };
};
