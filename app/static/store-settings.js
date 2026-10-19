const labels={input:'注文入力',menu:'メニューから選ぶ',service:'お冷・問い合わせ・お会計'};
const defaultLayout=()=>({block_order:['input','menu','service'],order_position:'right'});
let layouts={desktop:defaultLayout(),tablet:defaultLayout()};
let activeDevice='desktop';
let blockOrder=[...layouts.desktop.block_order];

async function api(url,options={}){const response=await fetch(url,{headers:{'Content-Type':'application/json'},...options});if(!response.ok){const data=await response.json().catch(()=>({}));throw new Error(data.detail||'保存できませんでした')}return response.json()}
function persistActiveLayout(){layouts[activeDevice]={block_order:[...blockOrder],order_position:document.querySelector('#order-position').value}}
function renderBlocks(){
  const list=document.querySelector('#layout-box-list');
  list.innerHTML=blockOrder.map((key,index)=>`<div class="layout-editor-card" draggable="true" data-layout-key="${key}"><span class="drag-handle">☰</span><strong>${labels[key]}</strong><div><button type="button" data-move="${index}:-1" ${index===0?'disabled':''}>↑</button><button type="button" data-move="${index}:1" ${index===blockOrder.length-1?'disabled':''}>↓</button></div></div>`).join('');
  list.querySelectorAll('[data-move]').forEach(button=>button.onclick=()=>{const [index,delta]=button.dataset.move.split(':').map(Number);const target=index+delta;[blockOrder[index],blockOrder[target]]=[blockOrder[target],blockOrder[index]];persistActiveLayout();renderBlocks()});
  let dragging=null;
  list.querySelectorAll('[data-layout-key]').forEach(card=>{
    card.ondragstart=()=>{dragging=card.dataset.layoutKey;card.classList.add('dragging')};
    card.ondragend=()=>{dragging=null;card.classList.remove('dragging')};
    card.ondragover=event=>event.preventDefault();
    card.ondrop=event=>{event.preventDefault();const target=card.dataset.layoutKey;if(!dragging||dragging===target)return;const from=blockOrder.indexOf(dragging),to=blockOrder.indexOf(target);blockOrder.splice(to,0,blockOrder.splice(from,1)[0]);persistActiveLayout();renderBlocks()};
  });
  renderPreview();
}
function renderPreview(){
  const preview=document.querySelector('#layout-preview');
  const position=document.querySelector('#order-position').value;
  preview.className=`layout-preview preview-${position} preview-device-${activeDevice}`;
  preview.style.setProperty('--preview-accent',document.querySelector('#theme-color').value);
  preview.innerHTML=`<div class="preview-entry">${blockOrder.map(key=>`<div class="preview-box preview-${key}">${labels[key]}</div>`).join('')}</div><div class="preview-order"><strong>ご注文内容</strong><span>合計金額・確定ボタン</span></div>`;
}
function switchDevice(device){
  persistActiveLayout();activeDevice=device;blockOrder=[...layouts[device].block_order];document.querySelector('#order-position').value=layouts[device].order_position;
  document.querySelectorAll('[data-device]').forEach(button=>button.classList.toggle('selected',button.dataset.device===device));
  document.querySelector('#device-layout-help').textContent=`${device==='desktop'?'PC':'タブレット'}での並びを編集中です。箱をドラッグするか、上下ボタンで並べ替えます。`;
  renderBlocks();
}
function showMessage(text,error=false){const element=document.querySelector('#store-settings-message');element.textContent=text;element.classList.remove('hidden');element.classList.toggle('error-text',error)}

document.querySelectorAll('[data-device]').forEach(button=>button.onclick=()=>switchDevice(button.dataset.device));
document.querySelector('#theme-color').oninput=event=>{document.querySelector('#theme-color-code').textContent=event.target.value;renderPreview()};
document.querySelector('#order-position').onchange=()=>{persistActiveLayout();renderPreview()};
document.querySelector('#store-settings-form').onsubmit=async event=>{
  event.preventDefault();persistActiveLayout();const button=event.submitter;button.disabled=true;button.textContent='保存中…';
  try{const result=await api('/api/v1/admin/store-settings',{method:'PATCH',body:JSON.stringify({name:document.querySelector('#store-name').value,theme_color:document.querySelector('#theme-color').value,layout:layouts})});layouts=result.layout;blockOrder=[...layouts[activeDevice].block_order];document.querySelector('#order-position').value=layouts[activeDevice].order_position;renderBlocks();document.querySelector('header strong').textContent=`${result.name} 店舗・画面設定`;showMessage(`保存しました。${activeDevice==='desktop'?'PC':'タブレット'}の順番：${blockOrder.map(key=>labels[key]).join(' → ')}`);button.textContent='保存しました';setTimeout(()=>{button.textContent='設定を保存';button.disabled=false},1200)}catch(error){showMessage(error.message,true);button.textContent='設定を保存';button.disabled=false}
};

api('/api/v1/admin/store-settings').then(settings=>{document.querySelector('#store-name').value=settings.name;document.querySelector('#theme-color').value=settings.theme_color;document.querySelector('#theme-color-code').textContent=settings.theme_color;layouts=settings.layout;blockOrder=[...layouts.desktop.block_order];document.querySelector('#order-position').value=layouts.desktop.order_position;renderBlocks()}).catch(error=>showMessage(error.message,true));
