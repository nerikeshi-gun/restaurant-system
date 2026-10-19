async function api(url, options={}) {
  const response = await fetch(url, {headers:{'Content-Type':'application/json'}, ...options});
  if (!response.ok) throw new Error((await response.json()).detail || '通信に失敗しました');
  return response.json();
}

const escapeHtml = value => String(value).replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
const yen = value => `${Number(value || 0).toLocaleString('ja-JP')}円`;

function showMessage(message, isError=false) {
  const element = document.querySelector('#table-reset-message');
  element.textContent = message;
  element.classList.remove('hidden');
  element.classList.toggle('error-text', isError);
  element.scrollIntoView({behavior:'smooth', block:'nearest'});
}

async function loadTables() {
  const tables = await api('/api/v1/admin/table-reset-status', {cache:'no-store'});
  document.querySelector('#table-reset-list').innerHTML = tables.map(table => {
    const stateClass = table.unserved_item_count ? 'blocked' : table.has_activity ? 'active' : 'available';
    const stateLabel = table.unserved_item_count ? '提供待ち' : table.has_activity ? '使用中' : '空席';
    const resetControl = !table.has_activity
      ? '<p class="table-reset-ready">準備中</p>'
      : `${table.block_reason ? `<p class="table-reset-warning">${escapeHtml(table.block_reason)}</p>` : '<p class="table-reset-ready">空席にできます</p>'}
         <button class="danger table-reset-button" data-table-reset="${table.table_id}" data-session-id="${table.session_id || ''}" data-table-number="${escapeHtml(table.table_number)}" data-draft-count="${table.draft_item_count}" ${table.can_reset ? '' : 'disabled'}>このテーブルを空席にする</button>`;
    return `<article class="table-reset-card ${stateClass}">
      <div class="table-reset-title"><h2>${escapeHtml(table.table_number)}番</h2><span class="table-state ${stateClass}">${stateLabel}</span></div>
      <div class="table-reset-amount"><span>会計対象</span><strong>${yen(table.confirmed_total)}</strong></div>
      <dl><div><dt>未送信</dt><dd>${table.draft_item_count}点</dd></div><div><dt>未提供</dt><dd class="${table.unserved_item_count ? 'danger-text' : ''}">${table.unserved_item_count}点</dd></div><div><dt>未処理依頼</dt><dd>${table.pending_request_count}件</dd></div></dl>
      ${resetControl}
    </article>`;
  }).join('');
  document.querySelectorAll('[data-table-reset]').forEach(button => button.onclick = async () => {
    const draftNote = Number(button.dataset.draftCount) ? `\n未送信の注文${button.dataset.draftCount}点は取り消されます。` : '';
    if (!confirm(`${button.dataset.tableNumber}番テーブルの会計と退店は完了していますか？${draftNote}\n注文履歴を残したまま、次のお客様用の空状態へ切り替えます。`)) return;
    button.disabled = true;
    try {
      await api(`/api/v1/admin/tables/${button.dataset.tableReset}/reset`, {method:'POST', body:JSON.stringify({expected_session_id:Number(button.dataset.sessionId)})});
      showMessage(`${button.dataset.tableNumber}番テーブルを空席にしました`);
      await loadTables();
    } catch (error) { showMessage(error.message, true); await loadTables(); }
  });
}

loadTables().catch(error => showMessage(error.message, true));
