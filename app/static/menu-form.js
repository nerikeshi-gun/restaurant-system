async function api(url, options={}) {
  const response = await fetch(url, {headers:{'Content-Type':'application/json'}, ...options});
  if (!response.ok) throw new Error((await response.json()).detail || '保存できませんでした');
  return response.json();
}

const itemId = Number(document.body.dataset.menuItemId || 0);
const message = document.querySelector('#menu-form-message');
const escapeHtml = value => String(value).replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
let modifierGroups = [];

function showMessage(text, isError=false) {
  message.textContent = text; message.classList.remove('hidden'); message.classList.toggle('error-text', isError);
}

function values() {
  return {
    menu_code: document.querySelector('#menu-code').value.trim(),
    category_id: Number(document.querySelector('#category-id').value),
    name: document.querySelector('#menu-name').value.trim(),
    short_name: document.querySelector('#short-name').value.trim(),
    reading: document.querySelector('#reading').value.trim(),
    aliases: document.querySelector('#aliases').value.split(/[、,|]/).map(value => value.trim()).filter(Boolean),
    localized_names: Object.fromEntries(['en','zh','ko','vi','ur'].map(code => [code, document.querySelector(`#name-${code}`).value.trim()]).filter(([, value]) => value)),
    price: Number(document.querySelector('#price').value),
    display_order: Number(document.querySelector('#display-order').value),
    size_label: document.querySelector('#size-label').value.trim(),
    set_contents: document.querySelector('#set-contents').value.trim(),
    is_available: document.querySelector('#is-available').checked,
    modifier_groups: [...document.querySelectorAll('[data-menu-modifier]:checked')].map((checkbox, index) => ({group_id:Number(checkbox.value), required:document.querySelector(`[data-menu-required="${checkbox.value}"]`).checked, display_order:index})),
  };
}

function renderModifierGroups(assigned=[]) {
  const assignedById = new Map(assigned.map(value => [value.group_id, value]));
  const container = document.querySelector('#menu-modifier-groups');
  container.innerHTML = modifierGroups.length ? modifierGroups.map(group => {
    const link = assignedById.get(group.id); const checked = Boolean(link);
    return `<div class="menu-modifier-row"><label><input type="checkbox" data-menu-modifier value="${group.id}" ${checked ? 'checked' : ''}><span><strong>${escapeHtml(group.name)}</strong><small>${group.selection_type === 'multiple' ? '複数選択' : '1つ選択'}・${group.options.length}項目</small></span></label><label class="required-toggle"><input type="checkbox" data-menu-required="${group.id}" ${link?.required ? 'checked' : ''} ${checked ? '' : 'disabled'}>必須</label></div>`;
  }).join('') : '<p class="hint">オプションがまだありません。「オプションを作る」から登録してください。</p>';
  document.querySelectorAll('[data-menu-modifier]').forEach(checkbox => checkbox.onchange = () => { const required = document.querySelector(`[data-menu-required="${checkbox.value}"]`); required.disabled = !checkbox.checked; required.checked = checkbox.checked; });
}

function fillItem(item) {
  document.querySelector('#menu-code').value = item.menu_code;
  document.querySelector('#category-id').value = String(item.category_id);
  document.querySelector('#menu-name').value = item.name;
  document.querySelector('#short-name').value = item.short_name;
  document.querySelector('#reading').value = item.reading;
  document.querySelector('#aliases').value = item.aliases.join('、');
  for (const code of ['en','zh','ko','vi','ur']) document.querySelector(`#name-${code}`).value = item.localized_names?.[code] || '';
  document.querySelector('#price').value = item.price;
  document.querySelector('#display-order').value = item.display_order;
  document.querySelector('#size-label').value = item.size_label;
  document.querySelector('#set-contents').value = item.set_contents;
  document.querySelector('#is-available').checked = item.is_available;
  renderModifierGroups(item.modifier_groups || []);
}

async function initialize() {
  const [categories, groups] = await Promise.all([api('/api/v1/admin/menu-categories'), api('/api/v1/admin/modifier-groups')]);
  modifierGroups = groups.filter(group => group.is_active);
  const select = document.querySelector('#category-id');
  select.innerHTML = categories.map(category => `<option value="${category.id}">${escapeHtml(category.name)}</option>`).join('');
  if (!categories.length) { showMessage('先にメニュー管理でカテゴリを登録してください', true); document.querySelector('#save-menu-item').disabled = true; return; }
  if (itemId) fillItem(await api(`/api/v1/admin/menu/${itemId}`)); else renderModifierGroups();
}

document.querySelector('#menu-item-form').onsubmit = async event => {
  event.preventDefault();
  const button = document.querySelector('#save-menu-item'); button.disabled = true; button.textContent = '保存中…';
  try {
    await api(itemId ? `/api/v1/admin/menu/${itemId}` : '/api/v1/admin/menu', {method:itemId ? 'PUT' : 'POST', body:JSON.stringify(values())});
    showMessage('保存しました。注文画面へ反映されています。');
    setTimeout(() => { location.href = '/admin/menu'; }, 650);
  } catch (error) { showMessage(error.message, true); button.disabled = false; button.textContent = '保存する'; }
};

initialize().catch(error => showMessage(error.message, true));
