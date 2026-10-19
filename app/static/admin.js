async function api(url, options={}) {
  const response = await fetch(url, {headers:{'Content-Type':'application/json'}, ...options});
  if (!response.ok) throw new Error((await response.json()).detail || '通信に失敗しました');
  return response.json();
}

const escapeHtml = value => String(value).replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
let categories = [];

function showCategoryMessage(message, isError=false) {
  const element = document.querySelector('#category-message');
  element.textContent = message; element.classList.toggle('error-text', isError);
}

async function loadCategories() {
  categories = await api('/api/v1/admin/menu-categories');
  document.querySelector('#category-list').innerHTML = categories.map(category => `
    <div class="category-editor">
      <div class="field-row"><label for="category-name-${category.id}">カテゴリ名</label><input id="category-name-${category.id}" data-category-name="${category.id}" value="${escapeHtml(category.name)}" maxlength="100"></div>
      <div class="field-row"><label for="category-order-${category.id}">表示順</label><input id="category-order-${category.id}" data-category-order="${category.id}" type="number" min="0" max="9999" value="${category.display_order}"></div>
      <div class="category-editor-footer"><span>${category.item_count}品</span><div><button data-category-save="${category.id}">保存</button><button data-category-delete="${category.id}" class="danger" ${category.item_count ? 'disabled title="商品を別カテゴリへ移動してから削除してください"' : ''}>削除</button></div></div>
    </div>`).join('');
  document.querySelectorAll('[data-category-save]').forEach(button => button.onclick = async () => {
    const id = Number(button.dataset.categorySave);
    try {
      await api(`/api/v1/admin/menu-categories/${id}`, {method:'PATCH', body:JSON.stringify({name:document.querySelector(`[data-category-name="${id}"]`).value, display_order:Number(document.querySelector(`[data-category-order="${id}"]`).value)})});
      showCategoryMessage('カテゴリを保存しました'); await loadAll();
    } catch (error) { showCategoryMessage(error.message, true); }
  });
  document.querySelectorAll('[data-category-delete]').forEach(button => button.onclick = async () => {
    if (!confirm('このカテゴリを削除しますか？')) return;
    try { await api(`/api/v1/admin/menu-categories/${button.dataset.categoryDelete}`, {method:'DELETE'}); showCategoryMessage('カテゴリを削除しました'); await loadAll(); }
    catch (error) { showCategoryMessage(error.message, true); }
  });
}

async function loadMenu() {
  const items = await api('/api/v1/admin/menu');
  const options = selected => categories.map(category => `<option value="${category.id}" ${category.id === selected ? 'selected' : ''}>${escapeHtml(category.name)}</option>`).join('');
  document.querySelector('#admin-menu').innerHTML = items.map(item => `<div class="menu-item admin-menu-row"><div><span class="menu-code">${escapeHtml(item.menu_code || '')}</span><strong>${escapeHtml(item.name)}</strong><span class="price"> ${item.price.toLocaleString()}円</span></div><select data-item-category="${item.id}" aria-label="${escapeHtml(item.name)}のカテゴリ">${options(item.category_id)}</select><button class="${item.is_available ? 'sale-active' : 'danger'}" data-availability-id="${item.id}" data-next="${!item.is_available}">${item.is_available ? '販売中' : '売り切れ'}</button><a class="link-button edit-menu-link" href="${item.edit_url}">編集</a><button class="danger" data-menu-delete="${item.id}" data-menu-name="${escapeHtml(item.name)}">削除</button></div>`).join('');
  document.querySelectorAll('[data-item-category]').forEach(select => select.onchange = async () => {
    try { await api(`/api/v1/admin/menu/${select.dataset.itemCategory}/category`, {method:'PATCH', body:JSON.stringify({category_id:Number(select.value)})}); showCategoryMessage('商品のカテゴリを変更しました'); await loadAll(); }
    catch (error) { showCategoryMessage(error.message, true); await loadAll(); }
  });
  document.querySelectorAll('[data-availability-id]').forEach(button => button.onclick = async () => {
    await api(`/api/v1/admin/menu/${button.dataset.availabilityId}/availability`, {method:'PATCH',body:JSON.stringify({is_available:button.dataset.next === 'true'})}); await loadMenu();
  });
  document.querySelectorAll('[data-menu-delete]').forEach(button => button.onclick = async () => {
    if (!confirm(`「${button.dataset.menuName}」を削除しますか？\n注文履歴は残ります。`)) return;
    try { await api(`/api/v1/admin/menu/${button.dataset.menuDelete}`, {method:'DELETE'}); showCategoryMessage('メニューを削除しました'); await loadAll(); }
    catch (error) { showCategoryMessage(error.message, true); }
  });
}

async function loadAll() { await loadCategories(); await loadMenu(); }

document.querySelector('#category-create').onsubmit = async event => {
  event.preventDefault();
  try {
    await api('/api/v1/admin/menu-categories', {method:'POST', body:JSON.stringify({name:document.querySelector('#new-category-name').value, display_order:Number(document.querySelector('#new-category-order').value)})});
    document.querySelector('#new-category-name').value = ''; showCategoryMessage('カテゴリを追加しました'); await loadAll();
  } catch (error) { showCategoryMessage(error.message, true); }
};

document.querySelector('#reset-number').onclick = async () => { const result = await api('/api/v1/admin/display-number/reset', {method:'POST', body:JSON.stringify({next_number:1})}); document.querySelector('#admin-message').textContent = `${result.business_date}：次の注文は1番です`; };
api('/api/v1/admin/ai-status').then(status => { document.querySelector('#ai-status').innerHTML = status.active_provider === 'openai' ? `<strong>OpenAI接続</strong><span>通常：${status.model} → 障害時：${status.fallback_model} → ローカル解析</span>` : `<strong>ローカル解析</strong><span>${status.key_configured ? 'LLMが無効です' : 'APIキー未設定'}</span>`; });

document.querySelector('#menu-import').onsubmit = async event => {
  event.preventDefault();
  const file = document.querySelector('#menu-csv').files[0]; if (!file) return;
  const data = new FormData(); data.append('file', file);
  const response = await fetch('/api/v1/admin/menu/import-csv', {method:'POST', body:data}); const result = await response.json();
  if (!response.ok) { document.querySelector('#import-message').textContent = result.detail || '取込みに失敗しました'; return; }
  document.querySelector('#import-message').textContent = `${result.store_id} / ${result.menu_version}：${result.items}品を取り込みました`; await loadAll();
};

loadAll().catch(error => showCategoryMessage(error.message, true));
