const orders = document.querySelector('#orders');
const requests = document.querySelector('#requests');
const languageSelect = document.querySelector('#kitchen-language');
const supportedLanguages = ['ja', 'en', 'zh', 'ko', 'vi', 'ur'];
let language = supportedLanguages.includes(localStorage.getItem('kitchen-language')) ? localStorage.getItem('kitchen-language') : 'ja';
let latestSnapshot = {shared_orders: [], service_requests: []};
let menuById = new Map();
const translationCache = new Map();
const cancelRequestLabels = {
  ja:{title:'⚠ 取消依頼',approve:'取消を承認',reject:'取消しない'},
  en:{title:'⚠ Cancellation request',approve:'Approve cancellation',reject:'Keep order'},
  zh:{title:'⚠ 取消请求',approve:'批准取消',reject:'保留订单'},
  ko:{title:'⚠ 취소 요청',approve:'취소 승인',reject:'주문 유지'},
  vi:{title:'⚠ Yêu cầu hủy',approve:'Duyệt hủy',reject:'Giữ đơn'},
  ur:{title:'⚠ منسوخی کی درخواست',approve:'منسوخی منظور کریں',reject:'آرڈر برقرار رکھیں'}
};
let kitchenSocket = null;
let reconnectTimer = null;
let heartbeatTimer = null;
let heartbeatDeadline = null;
let connectionState = 'connecting';

const messages = {
  ja:{kitchen:'厨房',language:'言語',connected:'接続済み',connecting:'接続中',reconnecting:'再接続中',orders:'注文',requests:'ご依頼',noOrders:'現在の注文はありません',noRequests:'現在の依頼はありません',order:'注文',table:'番テーブル',not_started:'未着手',preparing:'調理中',served:'提供済み',cancelled:'取消',water:'お冷',spill:'こぼした',wait_time:'あと何分',checkout:'お会計',call_staff:'店員呼び出し',other:'その他',adjustment:'調整',note:'備考',input:'入力',staff:'店員',customer:'お客様',start:'調理開始',markServed:'提供済みにする',cancel:'取消',replyPlaceholder:'返答を入力（Win + Hで音声入力）',reply:'返答',total:'合計',acknowledge:'対応する',complete:'完了',error:'通信に失敗しました'},
  en:{kitchen:'Kitchen',language:'Language',connected:'Connected',connecting:'Connecting',reconnecting:'Reconnecting',orders:'Orders',requests:'Requests',noOrders:'No current orders',noRequests:'No current requests',order:'Order',table:'Table',not_started:'Not started',preparing:'Preparing',served:'Served',cancelled:'Cancelled',water:'Water',spill:'Spill',wait_time:'Wait time',checkout:'Checkout',call_staff:'Call staff',other:'Other',adjustment:'Options',note:'Notes',input:'Entered by',staff:'Staff',customer:'Customer',start:'Start cooking',markServed:'Mark served',cancel:'Cancel',replyPlaceholder:'Enter a reply (Win + H for voice input)',reply:'Reply',total:'Total',acknowledge:'Acknowledge',complete:'Complete',error:'Communication failed'},
  zh:{kitchen:'厨房',language:'语言',connected:'已连接',connecting:'连接中',reconnecting:'重新连接中',orders:'订单',requests:'服务请求',noOrders:'目前没有订单',noRequests:'目前没有请求',order:'订单',table:'号桌',not_started:'未开始',preparing:'制作中',served:'已上菜',cancelled:'已取消',water:'饮用水',spill:'打翻了',wait_time:'还要多久',checkout:'结账',call_staff:'呼叫店员',other:'其他',adjustment:'选项',note:'备注',input:'下单者',staff:'店员',customer:'顾客',start:'开始制作',markServed:'标记为已上菜',cancel:'取消',replyPlaceholder:'输入回复',reply:'回复',total:'合计',acknowledge:'开始处理',complete:'完成',error:'通信失败'},
  ko:{kitchen:'주방',language:'언어',connected:'연결됨',connecting:'연결 중',reconnecting:'재연결 중',orders:'주문',requests:'요청',noOrders:'현재 주문이 없습니다',noRequests:'현재 요청이 없습니다',order:'주문',table:'번 테이블',not_started:'미착수',preparing:'조리 중',served:'제공 완료',cancelled:'취소',water:'물',spill:'쏟음',wait_time:'대기 시간',checkout:'계산',call_staff:'직원 호출',other:'기타',adjustment:'옵션',note:'메모',input:'입력',staff:'직원',customer:'고객',start:'조리 시작',markServed:'제공 완료',cancel:'취소',replyPlaceholder:'답변 입력',reply:'답변',total:'합계',acknowledge:'대응 시작',complete:'완료',error:'통신에 실패했습니다'},
  vi:{kitchen:'Bếp',language:'Ngôn ngữ',connected:'Đã kết nối',connecting:'Đang kết nối',reconnecting:'Đang kết nối lại',orders:'Đơn hàng',requests:'Yêu cầu',noOrders:'Không có đơn hàng hiện tại',noRequests:'Không có yêu cầu hiện tại',order:'Đơn',table:'Bàn',not_started:'Chưa bắt đầu',preparing:'Đang chế biến',served:'Đã phục vụ',cancelled:'Đã hủy',water:'Nước',spill:'Làm đổ',wait_time:'Thời gian chờ',checkout:'Thanh toán',call_staff:'Gọi nhân viên',other:'Khác',adjustment:'Tùy chọn',note:'Ghi chú',input:'Nhập bởi',staff:'Nhân viên',customer:'Khách',start:'Bắt đầu nấu',markServed:'Đánh dấu đã phục vụ',cancel:'Hủy',replyPlaceholder:'Nhập câu trả lời',reply:'Trả lời',total:'Tổng',acknowledge:'Xử lý',complete:'Hoàn tất',error:'Lỗi kết nối'},
  ur:{kitchen:'باورچی خانہ',language:'زبان',connected:'منسلک',connecting:'رابطہ ہو رہا ہے',reconnecting:'دوبارہ رابطہ',orders:'آرڈرز',requests:'درخواستیں',noOrders:'کوئی موجودہ آرڈر نہیں',noRequests:'کوئی موجودہ درخواست نہیں',order:'آرڈر',table:'میز',not_started:'شروع نہیں ہوا',preparing:'تیاری جاری ہے',served:'پیش کر دیا گیا',cancelled:'منسوخ',water:'پانی',spill:'گر گیا',wait_time:'انتظار کا وقت',checkout:'بل',call_staff:'عملہ بلائیں',other:'دیگر',adjustment:'اختیارات',note:'نوٹ',input:'درج کیا',staff:'عملہ',customer:'گاہک',start:'تیاری شروع کریں',markServed:'پیش کیا گیا',cancel:'منسوخ',replyPlaceholder:'جواب درج کریں',reply:'جواب',total:'کل',acknowledge:'جواب دیں',complete:'مکمل',error:'رابطہ ناکام'}
};

function t(key) { return messages[language]?.[key] || messages.ja[key] || key; }
function setConnectionState(state) { connectionState = state; document.querySelector('#connection').textContent = t(state); }
function escapeHtml(value='') { return String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[char])); }
async function api(url, options={}) { const response = await fetch(url, {headers:{'Content-Type':'application/json'}, ...options}); if (!response.ok) throw new Error((await response.json()).detail || t('error')); return response.json(); }
function time(value) { return value ? new Date(value).toLocaleTimeString(language, {hour:'2-digit', minute:'2-digit'}) : ''; }
function money(value) { return Number(value || 0).toLocaleString(language); }
function dishName(item) { return menuById.get(Number(item.menu_item_id))?.localized_names?.[language] || item.name; }

function orderCards(sharedOrders) {
  const lines = sharedOrders.flatMap(order => order.items.filter(item => ['confirmed','cancel_requested'].includes(item.status) && item.kitchen_status !== 'cancelled').map(item => ({order, item}))).sort((a,b) => Number(b.item.status === 'cancel_requested') - Number(a.item.status === 'cancel_requested') || Number(a.item.kitchen_status === 'served') - Number(b.item.kitchen_status === 'served') || String(a.item.confirmed_at).localeCompare(String(b.item.confirmed_at)) || a.item.id - b.item.id);
  if (!lines.length) return `<p>${t('noOrders')}</p>`;
  return lines.map(({order, item}) => `<article class="ticket ${item.kitchen_status === 'preparing' ? 'preparing' : ''} ${item.kitchen_status === 'served' ? 'served' : ''} ${item.status === 'cancel_requested' ? 'cancel-requested' : ''}">
    ${item.status === 'cancel_requested' ? `<div class="cancel-request-alert">${cancelRequestLabels[language]?.title || cancelRequestLabels.ja.title}</div>` : ''}
    <div class="ticket-title"><h2>${t('order')} ${escapeHtml(order.display_number || '-')}・${language === 'ja' || language === 'ko' || language === 'zh' ? escapeHtml(order.table_number) + t('table') : t('table') + ' ' + escapeHtml(order.table_number)}</h2><span class="status status-${item.kitchen_status}">${t(item.kitchen_status)}</span></div>
    <p class="dish-line"><strong>${escapeHtml(dishName(item))} × ${item.quantity}</strong></p>
    ${item.modifiers.length ? `<p>${t('adjustment')}：${item.modifiers.map(escapeHtml).join('・')}</p>` : ''}${item.notes ? `<p>${t('note')}：${escapeHtml(item.notes)}</p>` : ''}
    <p class="ticket-meta">${t('order')} ${time(item.confirmed_at)}・${t('input')}：${t(item.input_by === 'staff' ? 'staff' : 'customer')}</p>
    <div class="ticket-actions">${item.status === 'cancel_requested' ? `<button class="cancel-approve" data-cancel-decision="${item.id}" data-action="approve">${cancelRequestLabels[language]?.approve || cancelRequestLabels.ja.approve}</button><button data-cancel-decision="${item.id}" data-action="reject">${cancelRequestLabels[language]?.reject || cancelRequestLabels.ja.reject}</button>` : `${item.kitchen_status === 'not_started' ? `<button class="primary" data-item="${item.id}" data-status="preparing">${t('start')}</button><button data-item="${item.id}" data-status="cancelled">${t('cancel')}</button>` : ''}${item.kitchen_status === 'preparing' ? `<button class="primary" data-item="${item.id}" data-status="served">${t('markServed')}</button>` : ''}`}</div>
    <div class="input-row reply-row"><input data-reply-input="${order.session_id}" placeholder="${t('replyPlaceholder')}"><button class="kitchen-mic" data-mic type="button" aria-label="Microphone">🎤</button><button data-reply="${order.session_id}">${t('reply')}</button></div>
  </article>`).join('');
}

function requestCards(items) {
  if (!items.length) return `<p>${t('noRequests')}</p>`;
  return items.map(item => `<article class="ticket request ${item.request_type === 'spill' ? 'urgent' : ''}"><h2>${language === 'ja' || language === 'ko' || language === 'zh' ? escapeHtml(item.table_number) + t('table') : t('table') + ' ' + escapeHtml(item.table_number)}</h2><p><strong>${t(item.request_type)}</strong></p>${item.message ? `<p data-translate-message="${escapeHtml(item.message)}">${escapeHtml(item.message)}</p>` : ''}${item.bill ? `<p class="total">${t('total')} ${money(item.bill.total)}円</p>` : ''}<div class="ticket-actions"><button class="primary" data-request="${item.id}" data-action="complete">${t('complete')}</button></div><div class="input-row reply-row"><input data-reply-input="${item.session_id}" placeholder="${t('replyPlaceholder')}"><button class="kitchen-mic" data-mic type="button" aria-label="Microphone">🎤</button><button data-reply="${item.session_id}">${t('reply')}</button></div></article>`).join('');
}

async function translateRequestMessages() {
  for (const element of document.querySelectorAll('[data-translate-message]')) {
    const sourceText = element.dataset.translateMessage;
    if (!sourceText || language === 'ja') continue;
    const cacheKey = `${language}\n${sourceText}`;
    if (translationCache.has(cacheKey)) {
      element.textContent = translationCache.get(cacheKey);
      continue;
    }
    try {
      const result = await api('/api/v1/translation/prepare', {method:'POST', body:JSON.stringify({source_text:sourceText, source_language:'auto', target_language:language})});
      if (result.translated_text) {
        translationCache.set(cacheKey, result.translated_text);
        if (element.isConnected) element.textContent = result.translated_text;
      }
    } catch (_) {}
  }
}

function render() {
  document.documentElement.lang = language;
  document.body.dir = language === 'ur' ? 'rtl' : 'ltr';
  languageSelect.value = language;
  document.querySelector('#kitchen-title').textContent = t('kitchen');
  document.querySelector('#language-label').textContent = t('language');
  languageSelect.setAttribute('aria-label', t('language'));
  document.querySelector('#orders-title').textContent = t('orders');
  document.querySelector('#requests-title').textContent = t('requests');
  setConnectionState(connectionState);
  orders.innerHTML = orderCards(latestSnapshot.shared_orders || []);
  requests.innerHTML = requestCards(latestSnapshot.service_requests || []);
  bind();
  translateRequestMessages();
}

function bind() {
  document.querySelectorAll('[data-item]').forEach(button => button.onclick = async () => { try { await api(`/api/v1/kitchen/items/${button.dataset.item}/status`, {method:'PATCH', body:JSON.stringify({status:button.dataset.status})}); await load(); } catch(error) { alert(error.message); } });
  document.querySelectorAll('[data-request]').forEach(button => button.onclick = async () => { try { await api(`/api/v1/service-requests/${button.dataset.request}/${button.dataset.action}`, {method:'PATCH'}); await load(); } catch(error) { alert(error.message); } });
  document.querySelectorAll('[data-cancel-decision]').forEach(button => button.onclick = async () => { try { await api(`/api/v1/kitchen/items/${button.dataset.cancelDecision}/cancel-request/${button.dataset.action}`, {method:'POST'}); await load(); } catch(error) { alert(error.message); } });
  document.querySelectorAll('[data-reply]').forEach(button => button.onclick = async () => { const input = button.closest('.ticket').querySelector('[data-reply-input]'); if (!input.value.trim()) return; try { await api('/api/v1/messages', {method:'POST', body:JSON.stringify({session_id:Number(button.dataset.reply), sender_type:'kitchen', text:input.value.trim()})}); input.value=''; } catch(error) { alert(error.message); } });
  document.querySelectorAll('[data-mic]').forEach(button => button.onclick = () => startReplyRecognition(button));
}

function startReplyRecognition(button) {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition) {
    alert(language === 'ja' ? 'このブラウザは音声入力に対応していません' : 'Speech input is not supported by this browser.');
    return;
  }
  const recognition = new Recognition();
  recognition.lang = {ja:'ja-JP',en:'en-US',zh:'zh-CN',ko:'ko-KR',vi:'vi-VN',ur:'ur-PK'}[language] || language;
  recognition.interimResults = false;
  recognition.continuous = false;
  const input = button.closest('.reply-row').querySelector('[data-reply-input]');
  button.classList.add('listening');
  recognition.onresult = event => {
    const text = Array.from(event.results).map(result => result[0].transcript).join('');
    input.value = [input.value.trim(), text.trim()].filter(Boolean).join(' ');
    input.focus();
  };
  recognition.onerror = event => {
    if (event.error !== 'aborted' && event.error !== 'no-speech') alert(language === 'ja' ? '音声を認識できませんでした' : 'Speech could not be recognized.');
  };
  recognition.onend = () => button.classList.remove('listening');
  recognition.start();
}

async function load() { latestSnapshot = await api('/api/v1/kitchen/snapshot'); render(); }
function clearHeartbeat() {
  clearInterval(heartbeatTimer); clearTimeout(heartbeatDeadline);
  heartbeatTimer = null; heartbeatDeadline = null;
}
function sendHeartbeat() {
  if (!kitchenSocket || kitchenSocket.readyState !== WebSocket.OPEN) return;
  kitchenSocket.send('ping');
  clearTimeout(heartbeatDeadline);
  heartbeatDeadline = setTimeout(() => kitchenSocket?.close(), 5000);
}
function scheduleReconnect(delay=1500) {
  clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(connect, delay);
}
function connect() {
  clearTimeout(reconnectTimer);
  if (kitchenSocket && [WebSocket.CONNECTING, WebSocket.OPEN].includes(kitchenSocket.readyState)) return;
  setConnectionState(connectionState === 'connected' ? 'reconnecting' : 'connecting');
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
  const socket = new WebSocket(`${protocol}://${location.host}/api/v1/ws/kitchen`);
  kitchenSocket = socket;
  socket.onopen = () => {
    if (kitchenSocket !== socket) return;
    setConnectionState('connected');
    clearHeartbeat();
    sendHeartbeat();
    heartbeatTimer = setInterval(sendHeartbeat, 10000);
    load().catch(() => {});
  };
  socket.onmessage = event => {
    if (kitchenSocket !== socket) return;
    let data = null;
    try { data = JSON.parse(event.data); } catch (_) {}
    if (data?.type === 'connection.pong') {
      clearTimeout(heartbeatDeadline); heartbeatDeadline = null;
      setConnectionState('connected');
      return;
    }
    load().catch(() => {});
  };
  socket.onerror = () => socket.close();
  socket.onclose = () => {
    if (kitchenSocket !== socket) return;
    clearHeartbeat(); kitchenSocket = null;
    setConnectionState('reconnecting');
    scheduleReconnect();
  };
}

window.addEventListener('offline', () => { setConnectionState('reconnecting'); kitchenSocket?.close(); });
window.addEventListener('online', () => { setConnectionState('reconnecting'); scheduleReconnect(0); });
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState !== 'visible') return;
  if (!kitchenSocket || kitchenSocket.readyState !== WebSocket.OPEN) scheduleReconnect(0);
  else sendHeartbeat();
});

languageSelect.addEventListener('change', () => { language = languageSelect.value; localStorage.setItem('kitchen-language', language); render(); });
Promise.all([api('/api/v1/menu').catch(() => []), api('/api/v1/kitchen/snapshot')]).then(([menu, snapshot]) => { menuById = new Map(menu.map(item => [Number(item.id), item])); latestSnapshot = snapshot; render(); connect(); }).catch(error => { alert(error.message); connect(); });
