const body = document.body;
const sessionId = Number(body.dataset.sessionId);
let menu = [];
let order = null;
let selectedItem = null;
let selectedOptions = new Set();
let selectedQuantity = 1;
let selectedNotes = '';

const $ = selector => document.querySelector(selector);
const yen = value => `${Number(value || 0).toLocaleString('ja-JP')}円`;
const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[character]));
const statusLabels = {draft:'未送信', confirmed:'送信済み', not_started:'未着手', preparing:'調理中', served:'提供済み'};

async function api(url, options = {}) {
  const response = await fetch(url, {headers:{'Content-Type':'application/json'}, ...options});
  if (!response.ok) {
    let message = '通信に失敗しました';
    try { message = (await response.json()).detail || message; } catch (_) {}
    const error = new Error(message); error.status = response.status; throw error;
  }
  return response.json();
}

function toast(message) {
  const element = $('#toast'); element.textContent = message; element.classList.remove('hidden');
  clearTimeout(toast.timer); toast.timer = setTimeout(() => element.classList.add('hidden'), 2800);
}

function defaultOptions(item) {
  return item.modifiers.flatMap(group => group.required ? [] : group.options.filter(option => option.is_default).map(option => option.id));
}

function renderMenu() {
  const groups = new Map();
  for (const item of menu) {
    if (!groups.has(item.category)) groups.set(item.category, []);
    groups.get(item.category).push(item);
  }
  $('#category-nav').innerHTML = [...groups.keys()].map((category, index) => `<button type="button" data-category-target="category-${index}" class="${index === 0 ? 'selected' : ''}">${escapeHtml(category)}</button>`).join('');
  $('#staff-menu').innerHTML = [...groups.entries()].map(([category, items], index) => `<section id="category-${index}" class="handheld-category"><h2>${escapeHtml(category)}</h2><div>${items.map(item => `<button type="button" class="handheld-menu-item" data-menu-id="${item.id}"><strong>${escapeHtml(item.name)}</strong><span>${yen(item.price)}</span></button>`).join('')}</div></section>`).join('');
  document.querySelectorAll('[data-menu-id]').forEach(button => button.onclick = () => openItem(Number(button.dataset.menuId)));
  document.querySelectorAll('[data-category-target]').forEach(button => button.onclick = () => {
    document.querySelectorAll('[data-category-target]').forEach(value => value.classList.toggle('selected', value === button));
    document.getElementById(button.dataset.categoryTarget).scrollIntoView({behavior:'smooth', block:'start'});
  });
}

function openItem(itemId) {
  selectedItem = menu.find(item => item.id === itemId);
  selectedOptions = new Set(defaultOptions(selectedItem)); selectedQuantity = 1; selectedNotes = '';
  renderSheet(); $('#item-sheet').classList.remove('hidden'); body.classList.add('sheet-open');
}

function closeItem() {
  $('#item-sheet').classList.add('hidden'); body.classList.remove('sheet-open'); selectedItem = null;
}

function requiredMissing() {
  return selectedItem.modifiers.some(group => group.required && !group.options.some(option => selectedOptions.has(option.id)));
}

function itemUnitPrice() {
  return selectedItem.price + selectedItem.modifiers.flatMap(group => group.options).filter(option => selectedOptions.has(option.id)).reduce((sum, option) => sum + option.price_delta, 0);
}

function rerenderSheet() {
  if ($('#item-notes')) selectedNotes = $('#item-notes').value;
  renderSheet();
}

function renderSheet() {
  const missing = requiredMissing();
  $('#sheet-content').innerHTML = `<h1 id="sheet-title">${escapeHtml(selectedItem.name)}</h1><p class="sheet-price">${yen(itemUnitPrice())}</p>
    ${selectedItem.modifiers.map(group => {
      const groupMissing = group.required && !group.options.some(option => selectedOptions.has(option.id));
      return `<div class="sheet-option-group ${groupMissing ? 'missing' : ''}"><strong>${escapeHtml(group.name)}${group.required ? '（必須）' : ''}</strong>${group.selection_type === 'multiple' ? '<small>複数選択可</small>' : ''}<div>${group.options.map(option => `<button type="button" data-option="${group.id}:${option.id}" class="${selectedOptions.has(option.id) ? 'selected' : ''}">${escapeHtml(option.name)}${option.price_delta ? ` ${option.price_delta > 0 ? '+' : ''}${yen(option.price_delta)}` : ''}</button>`).join('')}</div>${groupMissing ? `<p>${escapeHtml(group.name)}を選んでください</p>` : ''}</div>`;
    }).join('')}
    <div class="sheet-quantity"><span>数量</span><div><button id="quantity-minus" type="button">−</button><strong>${selectedQuantity}</strong><button id="quantity-plus" type="button">＋</button></div></div>
    <label class="sheet-notes">備考<input id="item-notes" maxlength="500" value="${escapeHtml(selectedNotes)}" placeholder="例：取り皿を一緒に"></label>
    <button id="add-item" class="primary handheld-confirm" ${missing ? 'disabled' : ''}>注文内容に追加・${yen(itemUnitPrice() * selectedQuantity)}</button>`;
  document.querySelectorAll('[data-option]').forEach(button => button.onclick = () => {
    const [groupId, optionId] = button.dataset.option.split(':').map(Number);
    const group = selectedItem.modifiers.find(value => value.id === groupId);
    if (group.selection_type === 'multiple') selectedOptions.has(optionId) ? selectedOptions.delete(optionId) : selectedOptions.add(optionId);
    else { group.options.forEach(option => selectedOptions.delete(option.id)); selectedOptions.add(optionId); }
    rerenderSheet();
  });
  $('#quantity-minus').onclick = () => { if (selectedQuantity > 1) { selectedQuantity -= 1; rerenderSheet(); } };
  $('#quantity-plus').onclick = () => { if (selectedQuantity < 99) { selectedQuantity += 1; rerenderSheet(); } };
  $('#add-item').onclick = addItem;
}

async function addItem() {
  const button = $('#add-item'); button.disabled = true;
  try {
    order = await api(`/api/v1/shared-orders/${order.id}/items`, {method:'POST', body:JSON.stringify({menu_item_id:selectedItem.id, quantity:selectedQuantity, modifier_option_ids:[...selectedOptions], input_by:'staff', input_language:'ja', notes:$('#item-notes').value.trim(), expected_version:order.version})});
    const name = selectedItem.name; closeItem(); renderOrder(); toast(`${name}を追加しました`);
  } catch (error) {
    if (error.status === 409) await loadOrder();
    toast(error.message); if ($('#add-item')) $('#add-item').disabled = false;
  }
}

function renderOrder() {
  if (!order) return;
  const active = order.items.filter(item => item.status !== 'cancelled').sort((a, b) => b.id - a.id);
  const draft = active.filter(item => item.status === 'draft');
  $('#order-number').textContent = order.display_number ? `注文 ${order.display_number}` : '未確定';
  $('#pending-total').textContent = yen(order.pending_total);
  $('#current-total').textContent = yen(order.current_total ?? order.draft_total);
  $('#nav-total').textContent = yen(order.pending_total);
  $('#draft-count').textContent = draft.reduce((sum, item) => sum + item.quantity, 0);
  $('#draft-count').classList.toggle('hidden', draft.length === 0);
  $('#confirm-order').disabled = draft.length === 0;
  $('#staff-order-items').innerHTML = active.length ? active.map(item => `<article class="handheld-order-item ${item.status}"><div><strong>${escapeHtml(item.name)}</strong><span>${statusLabels[item.status] || item.status}${item.status === 'confirmed' ? `・${statusLabels[item.kitchen_status] || item.kitchen_status}` : ''}</span></div>${item.modifiers.length ? `<p>${item.modifiers.map(escapeHtml).join('・')}</p>` : ''}${item.notes ? `<p>備考：${escapeHtml(item.notes)}</p>` : ''}<div class="handheld-item-bottom"><span>${yen(item.unit_price)} × ${item.quantity}</span><strong>${yen(item.line_total)}</strong></div>${item.status === 'draft' ? `<div class="handheld-item-actions"><button data-minus="${item.id}">−</button><strong>${item.quantity}</strong><button data-plus="${item.id}">＋</button><button data-cancel="${item.id}">取り消し</button></div>` : item.kitchen_status === 'not_started' ? `<button class="handheld-cancel" data-cancel="${item.id}">取り消し</button>` : ''}</article>`).join('') : '<p class="empty-state">注文内容はまだありません</p>';
  document.querySelectorAll('[data-minus]').forEach(button => button.onclick = () => changeQuantity(Number(button.dataset.minus), -1));
  document.querySelectorAll('[data-plus]').forEach(button => button.onclick = () => changeQuantity(Number(button.dataset.plus), 1));
  document.querySelectorAll('[data-cancel]').forEach(button => button.onclick = () => cancelItem(Number(button.dataset.cancel)));
}

async function loadOrder() { order = await api(`/api/v1/sessions/${sessionId}/shared-order`); renderOrder(); }

async function mutate(callback) {
  try { order = await callback(); renderOrder(); }
  catch (error) { if (error.status === 409) await loadOrder(); toast(error.message); }
}

async function changeQuantity(itemId, delta) {
  const item = order.items.find(value => value.id === itemId); const quantity = Math.max(1, item.quantity + delta);
  if (quantity === item.quantity) return;
  await mutate(() => api(`/api/v1/shared-orders/${order.id}/items/${itemId}`, {method:'PATCH', body:JSON.stringify({quantity, expected_version:order.version})}));
}

async function cancelItem(itemId) {
  await mutate(() => api(`/api/v1/shared-orders/${order.id}/items/${itemId}/cancel`, {method:'POST', body:JSON.stringify({expected_version:order.version, input_by:'staff'})}));
}

async function confirmOrder() {
  const draft = order.items.filter(item => item.status === 'draft');
  if (!draft.length) return;
  $('#confirm-item-count').textContent = `${draft.reduce((sum, item) => sum + item.quantity, 0)}点`;
  $('#confirm-total').textContent = yen(order.pending_total);
  $('#confirm-dialog').classList.remove('hidden'); body.classList.add('sheet-open');
  setTimeout(() => $('#submit-confirm').focus(), 0);
}

function closeConfirmDialog() {
  $('#confirm-dialog').classList.add('hidden'); body.classList.remove('sheet-open');
}

async function submitConfirmOrder() {
  const button = $('#submit-confirm'); button.disabled = true; button.textContent = '送信中…';
  try {
    order = await api(`/api/v1/shared-orders/${order.id}/confirm`, {method:'POST', body:JSON.stringify({expected_version:order.version, confirmed_by:'staff', confirmation_method:'touch_button'})});
    closeConfirmDialog(); renderOrder(); toast('厨房へ送信しました');
  } catch (error) { if (error.status === 409) await loadOrder(); toast(error.message); renderOrder(); }
  finally { button.disabled = false; button.textContent = '確定'; }
}

function showView(name) {
  $('#menu-view').classList.toggle('hidden', name !== 'menu'); $('#cart-view').classList.toggle('hidden', name !== 'cart');
  $('#show-menu').classList.toggle('selected', name === 'menu'); $('#show-cart').classList.toggle('selected', name === 'cart');
  window.scrollTo({top:0, behavior:'smooth'});
}

const SYNC_STATE_LABEL = { connecting: '接続中…', reconnecting: '再接続中…', offline: 'Wi-Fi未接続（端末の通信を確認）', server_unreachable: '親機PCに届きません（PC・サーバーを確認）' };
function connect() {
  // 再接続・生存確認・スリープ復帰対応は ws-client.js が担当する
  createReconnectingSocket({
    path: `/api/v1/ws/orders/${sessionId}`,
    onState: state => { if (state !== 'connected') $('#sync-state').textContent = SYNC_STATE_LABEL[state] || '再接続中…'; },
    onOpen: () => { $('#sync-state').textContent = '同期済み'; loadOrder().catch(() => {}); },
    onMessage: (event, data) => {
    if (!data) return;
    if (data.type.startsWith('shared_order.') || data.type === 'kitchen.status_changed') { order = data.data; renderOrder(); }
    if (data.type === 'menu.availability_changed') api('/api/v1/menu').then(data => { menu = data; renderMenu(); });
    if (data.type === 'store.settings_changed') { body.style.setProperty('--accent', data.data.theme_color); }
    if (data.type === 'message.created' && data.data.sender_type === 'kitchen') toast(`厨房から：${data.data.text}`);
    if (data.type === 'table.session_reset') location.replace('/staff');
    },
  });
}

$('#show-menu').onclick = () => showView('menu');
$('#show-cart').onclick = () => showView('cart');
$('#confirm-order').onclick = confirmOrder;
$('#submit-confirm').onclick = submitConfirmOrder;
$('#cancel-confirm').onclick = closeConfirmDialog; $('#confirm-backdrop').onclick = closeConfirmDialog;
$('#close-sheet').onclick = closeItem; $('#sheet-backdrop').onclick = closeItem;
document.addEventListener('keydown', event => {
  if (event.key !== 'Escape') return;
  if (!$('#confirm-dialog').classList.contains('hidden')) closeConfirmDialog();
  else if (!$('#item-sheet').classList.contains('hidden')) closeItem();
});
Promise.all([api('/api/v1/menu'), api(`/api/v1/sessions/${sessionId}/shared-order`)]).then(([menuData, orderData]) => { menu = menuData; order = orderData; renderMenu(); renderOrder(); connect(); }).catch(error => toast(error.message));
