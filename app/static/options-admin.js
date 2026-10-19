async function api(url, options={}) {
  const response=await fetch(url,{headers:{'Content-Type':'application/json'},...options});
  if(!response.ok){
    const data=await response.json().catch(()=>({}));
    const detail=Array.isArray(data.detail)?data.detail.map(item=>item.msg).join('、'):data.detail;
    throw new Error(detail||'保存できませんでした');
  }
  return response.json();
}
const escapeHtml=value=>String(value).replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
const message=document.querySelector('#option-admin-message');
function notify(text,error=false){message.textContent=text;message.classList.toggle('error-text',error)}

async function saveWithFeedback(button,action,successText){
  const originalText=button.textContent;
  button.disabled=true;button.textContent='保存中…';
  try{await action();notify(successText);button.textContent='保存しました';setTimeout(()=>{button.textContent=originalText;button.disabled=false},1200)}
  catch(error){notify(error.message,true);button.textContent=originalText;button.disabled=false}
}

function optionRow(option,isNew){
  return `<div class="modifier-option-row ${isNew?'new-admin-row':''}" data-option-row="${option.id}"><input data-option-name="${option.id}" value="${escapeHtml(option.name)}" aria-label="オプション項目名"><div class="price-input"><input data-option-price="${option.id}" type="number" value="${option.price_delta}" aria-label="追加料金"><span>円</span></div><input data-option-order="${option.id}" type="number" min="0" max="9999" value="${option.display_order}" aria-label="表示順"><label><input data-option-default="${option.id}" type="checkbox" ${option.is_default?'checked':''}>標準</label><label><input data-option-available="${option.id}" type="checkbox" ${option.is_available?'checked':''}>使用</label><button data-save-option="${option.id}">保存</button><button class="danger" data-delete-option="${option.id}">削除</button></div>`;
}

async function load({newGroupId=null,newOptionId=null}={}){
  const groups=await api('/api/v1/admin/modifier-groups');
  if(newGroupId){const index=groups.findIndex(group=>group.id===newGroupId);if(index>0)groups.unshift(groups.splice(index,1)[0])}
  document.querySelector('#modifier-group-list').innerHTML=groups.length?groups.map(group=>{
    const options=[...group.options];
    if(newOptionId){const index=options.findIndex(option=>option.id===newOptionId);if(index>0)options.unshift(options.splice(index,1)[0])}
    return `<section class="modifier-admin-card ${group.id===newGroupId?'new-admin-card':''}" data-group-card="${group.id}">
      <div class="modifier-group-fields"><div class="form-field"><label>オプション名</label><input data-group-name="${group.id}" value="${escapeHtml(group.name)}"></div><div class="form-field"><label>選び方</label><select data-group-type="${group.id}"><option value="single" ${group.selection_type==='single'?'selected':''}>1つ選択</option><option value="multiple" ${group.selection_type==='multiple'?'selected':''}>複数選択</option></select></div><div class="form-field"><label>表示順</label><input data-group-order="${group.id}" type="number" min="0" max="9999" value="${group.display_order}"></div><label class="availability-switch compact"><input data-group-active="${group.id}" type="checkbox" ${group.is_active?'checked':''}>使用する</label><button data-save-group="${group.id}">保存</button><button class="danger" data-delete-group="${group.id}">オプション削除</button></div>
      <h2>登録済みの選択ボタン</h2><div class="modifier-option-list">${options.map(option=>optionRow(option,option.id===newOptionId)).join('')||'<p class="hint">選択ボタンはまだありません。</p>'}</div>
      <form class="modifier-option-create" data-add-option="${group.id}"><input name="name" required placeholder="新しい選択ボタン名（例：中辛）"><input name="price_delta" type="number" value="0" aria-label="追加料金"><input name="display_order" type="number" min="0" max="9999" value="10" aria-label="表示順"><label><input name="is_default" type="checkbox">標準</label><button class="primary" type="submit">選択ボタンを追加</button></form>
    </section>`;
  }).join(''):'<p>オプションはまだありません。</p>';
  bind();
  const target=newOptionId?document.querySelector(`[data-option-row="${newOptionId}"]`):newGroupId?document.querySelector(`[data-group-card="${newGroupId}"]`):null;
  if(target)setTimeout(()=>target.scrollIntoView({behavior:'smooth',block:'center'}),0);
}

function bind(){
  document.querySelectorAll('[data-save-group]').forEach(button=>button.onclick=async()=>{const id=button.dataset.saveGroup;await saveWithFeedback(button,()=>api(`/api/v1/admin/modifier-groups/${id}`,{method:'PATCH',body:JSON.stringify({name:document.querySelector(`[data-group-name="${id}"]`).value,selection_type:document.querySelector(`[data-group-type="${id}"]`).value,display_order:Number(document.querySelector(`[data-group-order="${id}"]`).value),is_active:document.querySelector(`[data-group-active="${id}"]`).checked})}),'オプションを保存しました')});
  document.querySelectorAll('[data-save-option]').forEach(button=>button.onclick=async()=>{const id=button.dataset.saveOption;await saveWithFeedback(button,()=>api(`/api/v1/admin/modifier-options/${id}`,{method:'PATCH',body:JSON.stringify({name:document.querySelector(`[data-option-name="${id}"]`).value,price_delta:Number(document.querySelector(`[data-option-price="${id}"]`).value),display_order:Number(document.querySelector(`[data-option-order="${id}"]`).value),is_default:document.querySelector(`[data-option-default="${id}"]`).checked,is_available:document.querySelector(`[data-option-available="${id}"]`).checked})}),'選択ボタンを保存しました')});
  document.querySelectorAll('[data-add-option]').forEach(form=>form.onsubmit=async event=>{event.preventDefault();const values=new FormData(form);try{const created=await api(`/api/v1/admin/modifier-groups/${form.dataset.addOption}/options`,{method:'POST',body:JSON.stringify({name:values.get('name'),price_delta:Number(values.get('price_delta')),display_order:Number(values.get('display_order')),is_default:values.get('is_default')==='on',is_available:true})});notify('選択ボタンを追加しました');await load({newGroupId:Number(form.dataset.addOption),newOptionId:created.id})}catch(error){notify(error.message,true)}});
  document.querySelectorAll('[data-delete-option]').forEach(button=>button.onclick=async()=>{if(!confirm('この選択ボタンを削除しますか？'))return;try{await api(`/api/v1/admin/modifier-options/${button.dataset.deleteOption}`,{method:'DELETE'});notify('選択ボタンを削除しました');await load()}catch(error){notify(error.message,true)}});
  document.querySelectorAll('[data-delete-group]').forEach(button=>button.onclick=async()=>{if(!confirm('このオプションと選択ボタンを削除しますか？'))return;try{await api(`/api/v1/admin/modifier-groups/${button.dataset.deleteGroup}`,{method:'DELETE'});notify('オプションを削除しました');await load()}catch(error){notify(error.message,true)}});
}

document.querySelector('#modifier-group-create').onsubmit=async event=>{event.preventDefault();try{const created=await api('/api/v1/admin/modifier-groups',{method:'POST',body:JSON.stringify({name:document.querySelector('#new-group-name').value,selection_type:document.querySelector('#new-group-type').value,display_order:Number(document.querySelector('#new-group-order').value),is_active:true})});document.querySelector('#new-group-name').value='';notify('オプションを追加しました');await load({newGroupId:created.id})}catch(error){notify(error.message,true)}};
load().catch(error=>notify(error.message,true));
