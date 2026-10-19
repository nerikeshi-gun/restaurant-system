const body = document.body;
const sessionId = Number(body.dataset.sessionId);
const actor = body.dataset.actor;
const storeId = body.dataset.storeId;
const language = body.dataset.language || 'ja';
const orderMode = body.dataset.orderMode || 'choice';
const menuCategoryJumpKey = `menu-category-jump-${sessionId}`;
const startUrl = body.dataset.startUrl;
const voiceUrl = body.dataset.voiceUrl;
const menuUrl = body.dataset.menuUrl;
let menu = [];
let order = null;
let reviewItems = [];
let interpretationId = null;

const $ = selector => document.querySelector(selector);
const messages = {
  ja:{choose:'注文方法を選択してください',voiceOrder:'何が食べたいですか？',voiceHint:'食べたいもの・飲みたいものと数量を話してください',menuOrder:'メニューから注文',menuHint:'画面を見て商品を選びます',voiceTitle:'何が食べたいですか？',spoken:'注文内容',voiceButton:'🎤 話す',checkSpoken:'注文候補を確認',clear:'消去',menuOpen:'メニューから選ぶ',menuClose:'メニューを閉じる',orderDetails:'ご注文内容',pendingAmount:'今回の注文金額',totalAmount:'現在の合計金額',order:'注文',confirmNote:'確認画面を開いてから注文を確定します。',micNav:'🎤 話す',top:'Topに戻る',changeLanguage:'言語',empty:'ご注文はありません',confirmTitle:'注文を確定しますか？',confirmBody:'確定すると厨房へ送信されます。',back:'戻る',confirm:'確定',examplePrefix:'例：',currency:'円',items:'点'},
  en:{choose:'How would you like to order?',voiceOrder:'Order by voice',voiceHint:'Say the dish name and quantity',menuOrder:'Order from the menu',menuHint:'Choose items on the screen',voiceTitle:'Voice order',spoken:'Order details',voiceButton:'🎤 Tap the microphone',checkSpoken:'Review order candidates',clear:'Clear',menuOpen:'Choose from menu',menuClose:'Close menu',orderDetails:'Your order',pendingAmount:'This order',totalAmount:'Current total',order:'Order',confirmNote:'Review your order before sending it.',micNav:'🎤 Voice order',top:'Back to top',changeLanguage:'Language',empty:'No items have been selected',confirmTitle:'Place this order?',confirmBody:'The order will be sent to the kitchen.',back:'Back',confirm:'Confirm',examplePrefix:'Example: ',currency:'yen',items:'items'},
  zh:{choose:'请选择点餐方式',voiceOrder:'语音点餐',voiceHint:'请说出菜名和数量',menuOrder:'从菜单点餐',menuHint:'在画面上选择菜品',voiceTitle:'语音点餐',spoken:'您说的内容',voiceButton:'🎤 点击麦克风',checkSpoken:'查看点餐候选',clear:'清除',menuOpen:'从菜单选择',menuClose:'关闭菜单',orderDetails:'您的订单',pendingAmount:'本次订单金额',totalAmount:'当前总金额',order:'下单',confirmNote:'确认内容后提交订单。',micNav:'🎤 语音点餐',top:'返回顶部',changeLanguage:'语言',empty:'尚未选择菜品',confirmTitle:'确认下单吗？',confirmBody:'订单将发送到厨房。',back:'返回',confirm:'确认',examplePrefix:'例如：',currency:'日元',items:'件'},
  ko:{choose:'주문 방법을 선택하세요',voiceOrder:'음성으로 주문',voiceHint:'메뉴 이름과 수량을 말씀하세요',menuOrder:'메뉴에서 주문',menuHint:'화면에서 메뉴를 선택합니다',voiceTitle:'음성 주문',spoken:'말한 내용',voiceButton:'🎤 마이크 누르기',checkSpoken:'주문 후보 확인',clear:'지우기',menuOpen:'메뉴에서 선택',menuClose:'메뉴 닫기',orderDetails:'주문 내용',pendingAmount:'이번 주문 금액',totalAmount:'현재 총액',order:'주문',confirmNote:'내용을 확인한 후 주문을 확정합니다.',micNav:'🎤 음성 주문',top:'맨 위로',changeLanguage:'언어',empty:'선택한 메뉴가 없습니다',confirmTitle:'주문을 확정할까요?',confirmBody:'주방으로 주문이 전송됩니다.',back:'돌아가기',confirm:'확정',examplePrefix:'예: ',currency:'엔',items:'개'},
  vi:{choose:'Vui lòng chọn cách gọi món',voiceOrder:'Gọi món bằng giọng nói',voiceHint:'Hãy nói tên món và số lượng',menuOrder:'Chọn từ thực đơn',menuHint:'Chọn món trên màn hình',voiceTitle:'Gọi món bằng giọng nói',spoken:'Nội dung đã nói',voiceButton:'🎤 Nhấn micrô',checkSpoken:'Kiểm tra món gợi ý',clear:'Xóa',menuOpen:'Chọn từ thực đơn',menuClose:'Đóng thực đơn',orderDetails:'Đơn gọi món',pendingAmount:'Số tiền lần này',totalAmount:'Tổng hiện tại',order:'Gọi món',confirmNote:'Kiểm tra trước khi gửi đơn.',micNav:'🎤 Gọi món bằng giọng nói',top:'Lên đầu trang',changeLanguage:'Ngôn ngữ',empty:'Chưa chọn món',confirmTitle:'Xác nhận gọi món?',confirmBody:'Đơn sẽ được gửi tới bếp.',back:'Quay lại',confirm:'Xác nhận',examplePrefix:'Ví dụ: ',currency:'yên',items:'món'},
  ur:{choose:'آرڈر کرنے کا طریقہ منتخب کریں',voiceOrder:'آواز سے کھانا آرڈر کریں',voiceHint:'کھانے کا نام اور تعداد بولیں',menuOrder:'مینو سے آرڈر کریں',menuHint:'اسکرین پر کھانا منتخب کریں',voiceTitle:'آواز سے آرڈر کریں',spoken:'آپ کی کہی ہوئی بات',voiceButton:'🎤 مائیک دبائیں',checkSpoken:'آرڈر کی تجاویز دیکھیں',clear:'صاف کریں',menuOpen:'مینو سے منتخب کریں',menuClose:'مینو بند کریں',orderDetails:'آپ کا آرڈر',pendingAmount:'اس آرڈر کی رقم',totalAmount:'موجودہ کل رقم',order:'آرڈر کریں',confirmNote:'بھیجنے سے پہلے آرڈر چیک کریں۔',micNav:'🎤 آواز سے آرڈر',top:'اوپر جائیں',changeLanguage:'زبان',empty:'ابھی کوئی کھانا منتخب نہیں ہوا',confirmTitle:'آرڈر کی تصدیق کریں؟',confirmBody:'آرڈر کچن کو بھیجا جائے گا۔',back:'واپس',confirm:'تصدیق',examplePrefix:'مثال: ',currency:'ین',items:'آئٹمز'}
};
Object.assign(messages.zh, {spoken: '订单内容'});
Object.assign(messages.ko, {spoken: '주문 내용'});
Object.assign(messages.vi, {spoken: 'Nội dung đơn hàng'});
Object.assign(messages.ur, {spoken: 'آرڈر کی تفصیل'});
const orderInputPlaceholders = {
  ja: 'メニュー名、食べたいものなど',
  en: 'Menu name or what you feel like eating',
  zh: '菜名或想吃的食物等',
  ko: '메뉴 이름이나 먹고 싶은 음식 등',
  vi: 'Tên món hoặc món bạn muốn ăn',
  ur: 'مینو کا نام یا آپ کیا کھانا چاہتے ہیں'
};
const extraMessages = {
  ja:{water:'お冷',inquiry:'🎤 問い合わせ',checkout:'お会計',inquiryLabel:'問い合わせ内容',inquiryPlaceholder:'ご用件を話すか入力してください',voiceInput:'🎤 音声入力',send:'送信',cancel:'取り消し',inquiryHelp:'音声入力を押して話すか、文字で入力してください。',review:'注文候補',addToOrder:'注文へ追加',retry:'やり直す',chooseCandidate:'候補を選んでください',candidateHint:'候補を一つ選んでください。',none:'該当なし',speakAgain:'もう一度話す',processing:'注文内容を整理しています…',notFoundTitle:'商品を見つけられませんでした',notFoundBody:'料理名を確認するか、メニューから選んでください。',sentKitchen:'厨房へ送信しました',sentRequest:'厨房へ伝えました',required:'必須',selectOption:'を選んでください',startOver:'最初から',switchToMenu:'☰ メニューから注文',switchToVoice:'🎤 声で料理を注文'},
  en:{water:'Water',inquiry:'Contact staff',checkout:'Check out',inquiryLabel:'Message to staff',inquiryPlaceholder:'Speak or type your request',voiceInput:'🎤 Voice input',send:'Send',cancel:'Cancel',inquiryHelp:'Tap voice input and speak, or type your message.',review:'Review details',addToOrder:'Add to order',retry:'Start over',chooseCandidate:'Choose the matching item',candidateHint:'Select one menu item for each phrase.',none:'None of these',speakAgain:'Speak again',processing:'Finding menu items…',notFoundTitle:'No matching item found',notFoundBody:'Try saying the dish name again or choose it from the menu.',sentKitchen:'Order sent to the kitchen',sentRequest:'Request sent to the kitchen',required:'Required',selectOption:'Please select ',startOver:'Start over',switchToMenu:'☰ Order from menu',switchToVoice:'🎤 Order by voice'},
  zh:{water:'冰水',inquiry:'联系店员',checkout:'结账',inquiryLabel:'咨询内容',inquiryPlaceholder:'请说出或输入您的需求',voiceInput:'🎤 语音输入',send:'发送',cancel:'取消',inquiryHelp:'点击语音输入说话，或输入文字。',review:'确认内容',addToOrder:'加入订单',retry:'重新操作',chooseCandidate:'请选择对应菜品',candidateHint:'请为每句话选择一个菜品。',none:'都不是',speakAgain:'重新说',processing:'正在查找菜品…',notFoundTitle:'未找到对应菜品',notFoundBody:'请重新说出菜名，或从菜单中选择。',sentKitchen:'订单已发送到厨房',sentRequest:'已通知厨房',required:'必选',selectOption:'请选择',startOver:'从头开始',switchToMenu:'☰ 从菜单点餐',switchToVoice:'🎤 语音点餐'},
  ko:{water:'물',inquiry:'직원 문의',checkout:'계산',inquiryLabel:'문의 내용',inquiryPlaceholder:'요청 사항을 말하거나 입력하세요',voiceInput:'🎤 음성 입력',send:'보내기',cancel:'취소',inquiryHelp:'음성 입력을 누르고 말하거나 직접 입력하세요.',review:'내용 확인',addToOrder:'주문에 추가',retry:'다시 하기',chooseCandidate:'해당 메뉴를 선택하세요',candidateHint:'각 문장에 맞는 메뉴를 선택하세요.',none:'해당 없음',speakAgain:'다시 말하기',processing:'메뉴를 찾고 있습니다…',notFoundTitle:'메뉴를 찾지 못했습니다',notFoundBody:'메뉴 이름을 다시 말하거나 화면에서 선택하세요.',sentKitchen:'주방으로 주문을 보냈습니다',sentRequest:'주방에 전달했습니다',required:'필수',selectOption:'선택해 주세요: ',startOver:'처음부터',switchToMenu:'☰ 메뉴에서 주문',switchToVoice:'🎤 음성으로 주문'},
  vi:{water:'Nước lạnh',inquiry:'Liên hệ nhân viên',checkout:'Thanh toán',inquiryLabel:'Nội dung yêu cầu',inquiryPlaceholder:'Nói hoặc nhập yêu cầu của bạn',voiceInput:'🎤 Nhập bằng giọng nói',send:'Gửi',cancel:'Hủy',inquiryHelp:'Nhấn nhập giọng nói và nói, hoặc nhập bằng chữ.',review:'Kiểm tra nội dung',addToOrder:'Thêm vào đơn',retry:'Làm lại',chooseCandidate:'Chọn món phù hợp',candidateHint:'Chọn một món cho mỗi câu nói.',none:'Không có món nào',speakAgain:'Nói lại',processing:'Đang tìm món…',notFoundTitle:'Không tìm thấy món',notFoundBody:'Hãy nói lại tên món hoặc chọn từ thực đơn.',sentKitchen:'Đã gửi đơn tới bếp',sentRequest:'Đã gửi yêu cầu tới bếp',required:'Bắt buộc',selectOption:'Vui lòng chọn ',startOver:'Bắt đầu lại',switchToMenu:'☰ Chọn từ thực đơn',switchToVoice:'🎤 Gọi món bằng giọng nói'},
  ur:{water:'ٹھنڈا پانی',inquiry:'عملے سے رابطہ',checkout:'بل',inquiryLabel:'آپ کی درخواست',inquiryPlaceholder:'اپنی درخواست بولیں یا لکھیں',voiceInput:'🎤 آواز سے لکھیں',send:'بھیجیں',cancel:'منسوخ',inquiryHelp:'مائیک دباکر بولیں یا متن لکھیں۔',review:'آرڈر چیک کریں',addToOrder:'آرڈر میں شامل کریں',retry:'دوبارہ کریں',chooseCandidate:'متعلقہ کھانا منتخب کریں',candidateHint:'ہر جملے کے لیے ایک کھانا منتخب کریں۔',none:'ان میں سے کوئی نہیں',speakAgain:'دوبارہ بولیں',processing:'کھانا تلاش کیا جا رہا ہے…',notFoundTitle:'کھانا نہیں ملا',notFoundBody:'کھانے کا نام دوبارہ بولیں یا مینو سے منتخب کریں۔',sentKitchen:'آرڈر کچن کو بھیج دیا گیا',sentRequest:'درخواست کچن کو بھیج دی گئی',required:'ضروری',selectOption:'منتخب کریں: ',startOver:'شروع سے',switchToMenu:'☰ مینو سے آرڈر',switchToVoice:'🎤 آواز سے آرڈر'}
};
for (const code of Object.keys(messages)) Object.assign(messages[code], extraMessages[code]);
const t = key => (messages[language] || messages.ja)[key] || messages.ja[key] || key;
const dynamicMessages = {
  ja:{spokenReady:'話した内容を確認し、「注文候補を確認」を押してください。',micPrompt:'「話す」を押して、食べたいもの・飲みたいものと数量を話してください。',recording:'録音中です。話し終えたら「注文候補を確認」を押してください。',recordingMore:'録音中です。続けて話せます。',micPreparing:'マイクを準備しています…',synced:'同期済み',reconnecting:'再接続中…',unconfirmed:'未確定',orderNumber:'注文'},
  en:{spokenReady:'Review what you said, then tap “Review order candidates”.',micPrompt:'Tap the microphone and say the dish name and quantity.',recording:'Listening. When finished, tap “Review order candidates”.',recordingMore:'Listening. You can continue speaking.',micPreparing:'Preparing the microphone…',synced:'Synced',reconnecting:'Reconnecting…',unconfirmed:'Not confirmed',orderNumber:'Order'},
  zh:{spokenReady:'请确认语音内容，然后点击“查看点餐候选”。',micPrompt:'点击麦克风，说出菜名和数量。',recording:'正在录音。说完后请点击“查看点餐候选”。',recordingMore:'正在录音，可以继续说。',micPreparing:'正在准备麦克风…',synced:'已同步',reconnecting:'正在重新连接…',unconfirmed:'未确认',orderNumber:'订单'},
  ko:{spokenReady:'말한 내용을 확인한 후 “주문 후보 확인”을 누르세요.',micPrompt:'마이크를 누르고 메뉴 이름과 수량을 말씀하세요.',recording:'녹음 중입니다. 말한 후 “주문 후보 확인”을 누르세요.',recordingMore:'녹음 중입니다. 계속 말씀하셔도 됩니다.',micPreparing:'마이크 준비 중…',synced:'동기화됨',reconnecting:'재연결 중…',unconfirmed:'미확정',orderNumber:'주문'},
  vi:{spokenReady:'Kiểm tra nội dung đã nói rồi nhấn “Kiểm tra món gợi ý”.',micPrompt:'Nhấn micrô rồi nói tên món và số lượng.',recording:'Đang nghe. Khi nói xong, hãy nhấn “Kiểm tra món gợi ý”.',recordingMore:'Đang nghe. Bạn có thể nói tiếp.',micPreparing:'Đang chuẩn bị micrô…',synced:'Đã đồng bộ',reconnecting:'Đang kết nối lại…',unconfirmed:'Chưa xác nhận',orderNumber:'Đơn'},
  ur:{spokenReady:'اپنی کہی ہوئی بات دیکھیں، پھر ”آرڈر کی تجاویز دیکھیں“ دبائیں۔',micPrompt:'مائیک دبائیں اور کھانے کا نام اور تعداد بولیں۔',recording:'آواز سنی جا رہی ہے۔ بولنے کے بعد تجاویز والا بٹن دبائیں۔',recordingMore:'آواز سنی جا رہی ہے، آپ بولنا جاری رکھ سکتے ہیں۔',micPreparing:'مائیک تیار ہو رہا ہے…',synced:'ہم آہنگ',reconnecting:'دوبارہ رابطہ ہو رہا ہے…',unconfirmed:'تصدیق نہیں ہوئی',orderNumber:'آرڈر'}
};
const dt = key => dynamicMessages[language]?.[key] || dynamicMessages.ja[key] || key;
const yen = value => language === 'ja' ? `${Number(value).toLocaleString('ja-JP')}円` : `${Number(value).toLocaleString()} ${t('currency')}`;
const menuName = item => item?.localized_names?.[language] || item?.name || '';
function emphasizeInterpret(active) {
  const button = $('#interpret');
  if (!button) return;
  button.classList.toggle('next-action', active);
  button.textContent = active ? `➡ ${t('checkSpoken')}` : t('checkSpoken');
}
const categoryTranslations = {
  en:{'セット':'Sets','料理':'Food','カレー単品':'Curry','ナン・ライス':'Naan & Rice','サラダ':'Salads','ドリンク':'Drinks'},
  zh:{'セット':'套餐','料理':'菜品','カレー単品':'单点咖喱','ナン・ライス':'烤饼和米饭','サラダ':'沙拉','ドリンク':'饮料'},
  ko:{'セット':'세트','料理':'요리','カレー単品':'카레 단품','ナン・ライス':'난·밥','サラダ':'샐러드','ドリンク':'음료'},
  vi:{'セット':'Món theo set','料理':'Món ăn','カレー単品':'Cà ri gọi riêng','ナン・ライス':'Naan và cơm','サラダ':'Salad','ドリンク':'Đồ uống'},
  ur:{'セット':'سیٹ','料理':'کھانے','カレー単品':'کری','ナン・ライス':'نان اور چاول','サラダ':'سلاد','ドリンク':'مشروبات'}
};
const categoryName = value => categoryTranslations[language]?.[value] || value;
const groupTranslations = {
  en:{'ビールサイズ':'Beer size','盛り':'Serving size','辛さ':'Spice level'}, zh:{'ビールサイズ':'啤酒杯型','盛り':'份量','辛さ':'辣度'},
  ko:{'ビールサイズ':'맥주 크기','盛り':'양','辛さ':'매운맛'}, vi:{'ビールサイズ':'Cỡ bia','盛り':'Khẩu phần','辛さ':'Độ cay'},
  ur:{'ビールサイズ':'بیئر کا سائز','盛り':'مقدار','辛さ':'مرچ کی سطح'}
};
const optionTranslations = {
  en:{'ビールサイズ':{'小':'Small','中':'Medium','大':'Large'},'盛り':{'普通':'Regular','大盛':'Large portion'},'辛さ':{'小':'Mild','中':'Medium','大':'Hot','激':'Extra hot'}},
  zh:{'ビールサイズ':{'小':'小杯','中':'中杯','大':'大杯'},'盛り':{'普通':'普通','大盛':'大份'},'辛さ':{'小':'微辣','中':'中辣','大':'辣','激':'特辣'}},
  ko:{'ビールサイズ':{'小':'소','中':'중','大':'대'},'盛り':{'普通':'보통','大盛':'곱빼기'},'辛さ':{'小':'순한맛','中':'중간맛','大':'매운맛','激':'아주 매운맛'}},
  vi:{'ビールサイズ':{'小':'Nhỏ','中':'Vừa','大':'Lớn'},'盛り':{'普通':'Thường','大盛':'Phần lớn'},'辛さ':{'小':'Ít cay','中':'Cay vừa','大':'Cay','激':'Rất cay'}},
  ur:{'ビールサイズ':{'小':'چھوٹا','中':'درمیانہ','大':'بڑا'},'盛り':{'普通':'عام','大盛':'زیادہ'},'辛さ':{'小':'کم مرچ','中':'درمیانی مرچ','大':'تیز','激':'بہت تیز'}}
};
const groupName = value => groupTranslations[language]?.[value] || value;
const optionName = (group, value) => optionTranslations[language]?.[group]?.[value] || value;
const statusTranslations = {
  ja:{draft:'確認待ち',confirmed:'厨房へ送信済み',cancel_requested:'取消承認待ち',not_started:'未着手',preparing:'調理中',served:'提供済み',cancelled:'取消'},
  en:{draft:'Waiting for confirmation',confirmed:'Sent to kitchen',cancel_requested:'Cancellation pending',not_started:'Not started',preparing:'Cooking',served:'Served',cancelled:'Cancelled'},
  zh:{draft:'等待确认',confirmed:'已发送到厨房',cancel_requested:'等待取消批准',not_started:'尚未开始',preparing:'烹饪中',served:'已上菜',cancelled:'已取消'},
  ko:{draft:'확인 대기',confirmed:'주방 전송 완료',cancel_requested:'취소 승인 대기',not_started:'조리 전',preparing:'조리 중',served:'제공 완료',cancelled:'취소됨'},
  vi:{draft:'Chờ xác nhận',confirmed:'Đã gửi tới bếp',cancel_requested:'Đang chờ duyệt hủy',not_started:'Chưa bắt đầu',preparing:'Đang nấu',served:'Đã phục vụ',cancelled:'Đã hủy'},
  ur:{draft:'تصدیق کا انتظار',confirmed:'کچن کو بھیج دیا گیا',cancel_requested:'منسوخی کی منظوری زیر التوا',not_started:'ابھی شروع نہیں ہوا',preparing:'تیار ہو رہا ہے',served:'پیش کر دیا گیا',cancelled:'منسوخ'}
};
const statusLabel = value => statusTranslations[language]?.[value] || statusTranslations.ja[value] || value;
const translateModifier = value => {
  const parts = String(value).split(/[：:]/);
  if (parts.length < 2) return value;
  const group = parts.shift().trim();
  const option = parts.join(':').trim();
  return `${groupName(group)}: ${optionName(group, option)}`;
};

function lockCustomerNavigation() {
  if (actor !== 'customer') return;
  const customerUrl = `${location.pathname}${location.search}${location.hash}`;
  try { sessionStorage.setItem('customer-order-url', customerUrl); } catch (_) {}
  history.replaceState({customerOrder:true}, '', customerUrl);
  history.pushState({customerOrder:true}, '', customerUrl);
  window.addEventListener('popstate', () => {
    history.pushState({customerOrder:true}, '', customerUrl);
  });
  document.addEventListener('click', event => {
    const link = event.target.closest('a[href]');
    if (!link) return;
    const target = new URL(link.href, location.href);
    if (target.origin === location.origin && target.pathname.startsWith('/staff')) {
      event.preventDefault();
      toast('スタッフ画面には移動できません');
    }
  }, true);
}

function applyStoreLayout(layoutOverride = null) {
  const responsiveLayout = layoutOverride || window.STORE_UI_LAYOUT || {};
  const tabletQuery = window.matchMedia('(max-width: 1024px)');
  // 卓上用URLは画面幅に関係なく「タブレット表示」を使う。
  // Androidの横向きはCSS上の幅が1024pxを超える機種があり、
  // 幅だけで判定するとPC側の並びを誤って表示していた。
  const useTabletLayout = actor === 'customer' || tabletQuery.matches;
  const layout = responsiveLayout.desktop ? (useTabletLayout ? responsiveLayout.tablet : responsiveLayout.desktop) : responsiveLayout;
  const order = Array.isArray(layout.block_order) ? layout.block_order : ['input','menu','service'];
  const entry = $('#order-entry');
  for (const key of order) {
    const block = entry.querySelector(`[data-layout-block="${key}"]`);
    if (block) entry.appendChild(block);
  }
  const resultPanel = $('#interpret-result');
  if (resultPanel) entry.appendChild(resultPanel);
  const position = ['right','top','bottom'].includes(layout.order_position) ? layout.order_position : 'right';
  body.classList.remove('order-panel-right','order-panel-top','order-panel-bottom');
  body.classList.add(`order-panel-${position}`);
}

async function refreshStoreLayout() {
  const settings = await api('/api/v1/admin/store-settings', {cache: 'no-store'});
  window.STORE_UI_LAYOUT = settings.layout;
  applyStoreLayout(settings.layout);
  body.style.setProperty('--accent', settings.theme_color);
}

async function api(url, options = {}) {
  const response = await fetch(url, {headers: {'Content-Type': 'application/json'}, ...options});
  if (!response.ok) {
    let message = '通信に失敗しました';
    try { message = (await response.json()).detail || message; } catch (_) {}
    const error = new Error(message); error.status = response.status; throw error;
  }
  return response.json();
}

function toast(message) {
  const element = $('#toast'); element.textContent = message; element.classList.remove('hidden');
  setTimeout(() => element.classList.add('hidden'), 3000);
}

const dismissedReplyKey = `kitchen-reply-dismissed-${sessionId}`;
let dismissedReplyIdInMemory = 0;
function dismissedReplyId() {
  let storedId = 0;
  try { storedId = Number(localStorage.getItem(dismissedReplyKey) || 0); } catch (_) {}
  return Math.max(dismissedReplyIdInMemory, Number.isFinite(storedId) ? storedId : 0);
}
function showKitchenReply(message) {
  if (actor !== 'customer' || !message || Number(message.id) <= dismissedReplyId()) return;
  $('#kitchen-reply-popup').dataset.messageId = message.id;
  $('#kitchen-reply-text').textContent = message.text;
  $('#kitchen-reply-popup').classList.remove('hidden');
  setTimeout(() => $('#close-kitchen-reply').focus(), 0);
}
function showCancelDecision(approved) {
  if (actor !== 'customer') return;
  const copy = {
    ja:approved ? ['取消結果','取り消し完了','注文の取り消しが完了しました'] : ['取消結果','取り消しできません','申し訳ありません、取り消しできません'],
    en:approved ? ['Cancellation result','Cancellation complete','Your order has been cancelled.'] : ['Cancellation result','Unable to cancel','We are sorry, but this order cannot be cancelled.'],
    zh:approved ? ['取消结果','取消完成','订单已取消。'] : ['取消结果','无法取消','很抱歉，此订单无法取消。'],
    ko:approved ? ['취소 결과','취소 완료','주문 취소가 완료되었습니다.'] : ['취소 결과','취소할 수 없습니다','죄송하지만 주문을 취소할 수 없습니다.'],
    vi:approved ? ['Kết quả hủy','Đã hủy','Đơn hàng đã được hủy.'] : ['Kết quả hủy','Không thể hủy','Rất tiếc, không thể hủy đơn hàng này.'],
    ur:approved ? ['منسوخی کا نتیجہ','منسوخی مکمل','آرڈر منسوخ کر دیا گیا ہے۔'] : ['منسوخی کا نتیجہ','منسوخ نہیں ہو سکتا','معذرت، یہ آرڈر منسوخ نہیں کیا جا سکتا۔']
  }[language] || (approved ? ['取消結果','取り消し完了','注文の取り消しが完了しました'] : ['取消結果','取り消しできません','申し訳ありません、取り消しできません']);
  const popup = $('#kitchen-reply-popup');
  popup.dataset.messageId = '0';
  popup.querySelector('.reply-popup-label').textContent = copy[0];
  $('#kitchen-reply-title').textContent = copy[1];
  $('#kitchen-reply-text').textContent = copy[2];
  popup.classList.remove('hidden');
  setTimeout(() => $('#close-kitchen-reply').focus(), 0);
}
function closeKitchenReply() {
  const popup = $('#kitchen-reply-popup');
  const messageId = Number(popup.dataset.messageId || 0);
  if (Number.isFinite(messageId)) dismissedReplyIdInMemory = Math.max(dismissedReplyIdInMemory, messageId);
  try { localStorage.setItem(dismissedReplyKey, String(dismissedReplyIdInMemory)); } catch (_) {}
  popup.classList.add('hidden');
  if (messageId > 0) api(`/api/v1/sessions/${sessionId}/messages/${messageId}/dismiss`, {method:'PATCH'}).catch(() => {});
}
async function loadLatestKitchenReply() {
  if (actor !== 'customer') return;
  try { showKitchenReply(await api(`/api/v1/sessions/${sessionId}/messages/latest`, {cache:'no-store'})); } catch (_) {}
}

function findMenu(id) { return menu.find(item => item.id === Number(id)); }
function defaultOptions(item) {
  return item.modifiers.flatMap(group => group.required ? [] : group.options.filter(option => option.is_default).map(option => option.id));
}

async function loadOrder() {
  order = await api(`/api/v1/sessions/${sessionId}/shared-order`);
  renderSharedOrder();
}

function renderMenu() {
  const groups = new Map();
  for (const item of menu) {
    if (!groups.has(item.category)) groups.set(item.category, []);
    groups.get(item.category).push(item);
  }
  $('#menu').innerHTML = [...groups.entries()].map(([category, items]) =>
    `<section class="menu-category" data-menu-category="${encodeURIComponent(category)}"><h3>${categoryName(category)}</h3><div class="menu-category-grid">${items.map(item =>
      `<button class="menu-choice" data-menu-id="${item.id}"><strong>${menuName(item)}</strong><span>${yen(item.price)}</span></button>`
    ).join('')}</div></section>`
  ).join('');
  document.querySelectorAll('[data-menu-id]').forEach(button => button.onclick = () => {
    const item = findMenu(button.dataset.menuId);
    showReview([{menu_item_id: item.id, quantity: 1, modifier_option_ids: defaultOptions(item), operation: 'add'}]);
  });
  renderVoiceExample();
}

function voiceExampleText() {
  if (!menu.length) return t('voiceHint');
  const examples = {ja:`「${menuName(menu[0])}を1つ」`,en:`“one ${menuName(menu[0])}”`,zh:`“一个${menuName(menu[0])}”`,ko:`“${menuName(menu[0])} 하나”`,vi:`“một ${menuName(menu[0])}”`,ur:`”ایک ${menuName(menu[0])}“`};
  return `${t('examplePrefix')}${examples[language] || examples.ja}`;
}

function renderVoiceExample() {
  if ($('#voice-example')) $('#voice-example').textContent = language === 'ja' ? '例：「ビール」「スタミナ系」' : voiceExampleText();
  if ($('#order-text')) $('#order-text').placeholder = orderInputPlaceholders[language] || orderInputPlaceholders.en;
}

function openMenu(category = null) {
  const panel = $('#menu-panel');
  document.querySelectorAll('[data-menu-category]').forEach(section => {
    section.classList.remove('hidden');
  });
  panel.classList.remove('hidden');
  $('#toggle-menu').setAttribute('aria-expanded', 'true');
  $('#toggle-menu').textContent = t('menuClose');
  const target = category ? [...document.querySelectorAll('[data-menu-category]')].find(section => decodeURIComponent(section.dataset.menuCategory) === category) : null;
  requestAnimationFrame(() => (target || panel).scrollIntoView({behavior:'smooth', block:'start'}));
}

function renderSharedOrder() {
  if (!order) return;
  $('#sync-state').textContent = `${dt('synced')} · ${new Date(order.updated_at).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})}`;
  $('#order-number').textContent = order.display_number ? `${dt('orderNumber')} ${order.display_number}` : dt('unconfirmed');
  const active = order.items.filter(item => item.status !== 'cancelled').sort((a, b) => b.id - a.id);
  const draft = active.filter(item => item.status === 'draft');
  const displayedCurrentTotal = active.reduce((sum, item) => sum + Number(item.line_total || 0), 0);
  const displayedPendingTotal = draft.reduce((sum, item) => sum + Number(item.line_total || 0), 0);
  $('#shared-items').innerHTML = active.length ? active.map(sharedItemHtml).join('') : `<p class="empty-state">${t('empty')}</p>`;
  $('#pending-total').textContent = yen(displayedPendingTotal);
  $('#shared-total').textContent = yen(displayedCurrentTotal);
  const hasDraft = active.some(item => item.status === 'draft');
  $('#confirm-order').disabled = !hasDraft;
  bindSharedActions();
}

function sharedItemHtml(item) {
  const editable = item.status === 'draft';
  const localizedItem = findMenu(item.menu_item_id);
  return `<article class="shared-item ${item.status === 'cancelled' ? 'cancelled' : ''} ${item.status === 'cancel_requested' ? 'cancel-requested' : ''} ${item.kitchen_status === 'served' ? 'served' : ''}">
    <div class="item-main"><strong>${menuName(localizedItem) || item.name}</strong></div>
    ${item.modifiers.length ? `<p class="modifiers">${item.modifiers.map(translateModifier).join(' · ')}</p>` : ''}${item.notes ? `<p>${item.notes}</p>` : ''}
    <div class="item-bottom"><span>${yen(item.unit_price)} × ${item.quantity}</span><strong>${yen(item.line_total)}</strong></div>
    <div class="item-status">${statusLabel(item.status)}${item.status === 'confirmed' ? ` · ${statusLabel(item.kitchen_status)}` : ''}</div>
    ${editable ? `<div class="inline-actions"><button data-minus="${item.id}">−</button><strong>${item.quantity}</strong><button data-plus="${item.id}">＋</button><button data-cancel="${item.id}">${t('cancel')}</button></div>` : item.status === 'confirmed' && item.kitchen_status === 'not_started' ? `<button class="small-cancel" data-cancel="${item.id}">${t('cancel')}</button>` : ''}
  </article>`;
}

function bindSharedActions() {
  document.querySelectorAll('[data-minus]').forEach(button => button.onclick = () => changeQuantity(Number(button.dataset.minus), -1));
  document.querySelectorAll('[data-plus]').forEach(button => button.onclick = () => changeQuantity(Number(button.dataset.plus), 1));
  document.querySelectorAll('[data-cancel]').forEach(button => button.onclick = () => cancelItem(Number(button.dataset.cancel)));
}

async function mutate(callback) {
  try { order = await callback(); renderSharedOrder(); }
  catch (error) { if (error.status === 409) await loadOrder(); toast(error.message); }
}

async function changeQuantity(itemId, delta) {
  const item = order.items.find(value => value.id === itemId);
  const quantity = Math.max(1, item.quantity + delta);
  if (quantity === item.quantity) return;
  await mutate(() => api(`/api/v1/shared-orders/${order.id}/items/${itemId}`, {method:'PATCH', body:JSON.stringify({quantity, expected_version:order.version})}));
}

async function cancelItem(itemId) {
  const item = order.items.find(value => value.id === itemId);
  try {
    order = await api(`/api/v1/shared-orders/${order.id}/items/${itemId}/cancel`, {method:'POST', body:JSON.stringify({expected_version:order.version, input_by:actor})});
    renderSharedOrder();
    if (actor === 'customer' && item?.status === 'confirmed') {
      toast({ja:'厨房へ取消依頼を送りました',en:'Cancellation request sent to the kitchen',zh:'已向厨房发送取消请求',ko:'주방에 취소 요청을 보냈습니다',vi:'Đã gửi yêu cầu hủy đến bếp',ur:'باورچی خانے کو منسوخی کی درخواست بھیج دی گئی'}[language] || '厨房へ取消依頼を送りました');
    }
  } catch (error) {
    if (error.status === 409) await loadOrder();
    toast(error.message);
  }
}

function normalizeReviewItem(value) {
  const item = findMenu(value.menu_item_id);
  const selected = new Set(value.modifier_option_ids || []);
  if ((value.operation || 'add') === 'add') defaultOptions(item).forEach(id => selected.add(id));
  return {...value, quantity:value.quantity || 1, modifier_option_ids:[...selected], operation:value.operation || 'add'};
}

function showReview(items, id = null) {
  body.classList.remove('candidate-selection-open');
  reviewItems = items.map(normalizeReviewItem); interpretationId = id;
  const panel = $('#interpret-result'); panel.classList.remove('hidden');
  const operationText = {add:'追加', change:'数量変更', cancel:'取消'};
  const hasMissingRequired = reviewItems.some(row => {
    if (row.operation !== 'add') return false;
    const item = findMenu(row.menu_item_id); const selected = new Set(row.modifier_option_ids);
    return item.modifiers.some(group => group.required && !group.options.some(option => selected.has(option.id)));
  });
  panel.innerHTML = `<h2>${t('review')}</h2>${reviewItems.map((row, index) => {
    const item = findMenu(row.menu_item_id); const selected = new Set(row.modifier_option_ids);
    return `<article class="review-line"><strong>${menuName(item)}</strong><span class="operation-badge">${operationText[row.operation]}</span>
      ${row.operation !== 'cancel' ? `<div class="stepper"><button data-review-minus="${index}">−</button><strong>${row.quantity}</strong><button data-review-plus="${index}">＋</button></div>` : ''}
      ${row.operation === 'add' ? item.modifiers.map(group => `<div class="option-group ${group.required && !group.options.some(option => selected.has(option.id)) ? 'option-required-missing' : ''}"><strong>${groupName(group.name)}${group.required ? `（${t('required')}）` : ''}</strong><div class="choice-row">${group.options.map(option => `<button data-review-option="${index}:${group.id}:${option.id}" class="${selected.has(option.id) ? 'selected' : ''}">${optionName(group.name, option.name)}${option.price_delta ? ` ${option.price_delta > 0 ? '+' : ''}${yen(option.price_delta)}` : ''}</button>`).join('')}</div>${group.required && !group.options.some(option => selected.has(option.id)) ? `<p class="required-warning">${t('selectOption')}${groupName(group.name)}</p>` : ''}</div>`).join('') : ''}
    </article>`;
  }).join('')}<button id="add-reviewed" class="primary submit" ${hasMissingRequired ? 'disabled' : ''}>${t('addToOrder')}</button><button id="close-review">${t('retry')}</button>`;
  document.querySelectorAll('[data-review-minus]').forEach(button => button.onclick = () => { const row = reviewItems[Number(button.dataset.reviewMinus)]; row.quantity = Math.max(1, row.quantity - 1); showReview(reviewItems, interpretationId); });
  document.querySelectorAll('[data-review-plus]').forEach(button => button.onclick = () => { reviewItems[Number(button.dataset.reviewPlus)].quantity++; showReview(reviewItems, interpretationId); });
  document.querySelectorAll('[data-review-option]').forEach(button => button.onclick = () => {
    const [index, groupId, optionId] = button.dataset.reviewOption.split(':').map(Number); const row = reviewItems[index]; const item = findMenu(row.menu_item_id); const group = item.modifiers.find(value => value.id === groupId);
    if (group.selection_type === 'multiple') {
      row.modifier_option_ids = row.modifier_option_ids.includes(optionId) ? row.modifier_option_ids.filter(id => id !== optionId) : [...row.modifier_option_ids, optionId];
    } else {
      const groupIds = new Set(group.options.map(option => option.id)); row.modifier_option_ids = row.modifier_option_ids.filter(id => !groupIds.has(id)); row.modifier_option_ids.push(optionId);
    }
    showReview(reviewItems, interpretationId);
  });
  $('#add-reviewed').onclick = applyReviewed;
  $('#close-review').onclick = () => panel.classList.add('hidden');
  panel.scrollIntoView({behavior:'smooth', block:'nearest'});
}

async function applyReviewed() {
  const applyButton = $('#add-reviewed') || $('#accept-resolved');
  if (applyButton) applyButton.disabled = true;
  try {
    for (const row of reviewItems) {
      const target = [...order.items].reverse().find(item => item.menu_item_id === row.menu_item_id && item.status !== 'cancelled');
      if (row.operation === 'cancel') {
        if (!target) throw new Error(`${menuName(findMenu(row.menu_item_id))}は現在の注文にありません`);
        order = await api(`/api/v1/shared-orders/${order.id}/items/${target.id}/cancel`, {method:'POST', body:JSON.stringify({expected_version:order.version, input_by:actor})});
      } else if (row.operation === 'change' && target && target.status === 'draft') {
        order = await api(`/api/v1/shared-orders/${order.id}/items/${target.id}`, {method:'PATCH', body:JSON.stringify({quantity:row.quantity, expected_version:order.version})});
      } else {
        if (row.operation === 'change' && target) order = await api(`/api/v1/shared-orders/${order.id}/items/${target.id}/cancel`, {method:'POST', body:JSON.stringify({expected_version:order.version, input_by:actor})});
        order = await api(`/api/v1/shared-orders/${order.id}/items`, {method:'POST', body:JSON.stringify({menu_item_id:row.menu_item_id, quantity:row.quantity, modifier_option_ids:row.modifier_option_ids, input_by:actor, input_language:$('#input-language').value, original_text:$('#order-text').value || null, menu_version:row.menu_version || null, llm_candidates:row.llm_candidates || [], selected_candidate:row.selected_candidate || null, expected_version:order.version})});
      }
    }
    const hasDraft = order.items.some(item => item.status === 'draft');
    reviewItems = []; interpretationId = null;
    $('#interpret-result').innerHTML = ''; $('#interpret-result').classList.add('hidden'); $('#order-text').value = ''; $('#japanese-text').value = ''; renderSharedOrder();
    $('.shared-order-panel').scrollIntoView({behavior:'smooth', block:'start'});
    toast(hasDraft ? '内容を確認して「注文を確定」を押してください' : '注文を更新しました');
  } catch (error) { if (error.status === 409) await loadOrder(); toast(error.message); if (applyButton) applyButton.disabled = false; }
}

async function interpret() {
  const source = $('#order-text').value.trim(); const inputLanguage = $('#input-language').value;
  if (!source) return toast('注文内容を入力してください');
  emphasizeInterpret(false);
  const panel = $('#interpret-result'); panel.classList.remove('hidden'); panel.innerHTML = `<p>${t('processing')}</p>`;
  const compactSource = source.replace(/[\s、。！!？?]/g, '');
  const genericPhrases = ['注文お願いします','注文をお願いします','注文したいです','注文したい','オーダーお願いします','お願いします'];
  if (inputLanguage === 'ja' && genericPhrases.includes(compactSource)) {
    panel.innerHTML = `<h2>料理名を話してください</h2><p>「注文お願いします」では商品を選べません。</p><p class="voice-example-large">${voiceExampleText()}</p><button id="retry-generic-voice" class="voice-button" type="button">🎤 もう一度話す</button><button id="generic-open-menu" type="button">メニューから選ぶ</button>`;
    $('#retry-generic-voice').onclick = () => $('#start-voice').click();
    $('#generic-open-menu').onclick = () => openMenu();
    return;
  }
  if (inputLanguage === 'ja' && compactSource.length >= 2) {
    const categories = [...new Set(menu.map(item => item.category).filter(Boolean))];
    const category = categories.find(value => value.replace(/[\s　・･]/g, '').includes(compactSource));
    if (category) {
      sessionStorage.setItem(menuCategoryJumpKey, category);
      location.href = menuUrl;
      return;
    }
  }
  try {
    const serviceWords = {
      ja:[['会計','checkout'],['店員','call_staff']],
      en:[['check out','checkout'],['bill','checkout'],['staff','call_staff']],
      zh:[['结账','checkout'],['买单','checkout'],['店员','call_staff']],
      ko:[['계산','checkout'],['직원','call_staff']],
      vi:[['thanh toán','checkout'],['nhân viên','call_staff']],
      ur:[['بل','checkout'],['عملہ','call_staff']]
    };
    const requests = serviceWords[inputLanguage] || serviceWords.ja;
    const service = requests.find(([word]) => source.includes(word));
    if (service) { await sendRequest(service[1], source); return; }
    const result = await api('/api/ai/resolve-order', {method:'POST', body:JSON.stringify({store_id:storeId, recognized_text:source, input_language:inputLanguage})});
    if (!result.items.length) { panel.innerHTML = `<h2>${t('notFoundTitle')}</h2><p>${t('notFoundBody')}</p>`; openMenu(); return; }
    showResolvedChoices(result);
  } catch (_) { panel.innerHTML = `<h2>${t('notFoundTitle')}</h2><p>${t('notFoundBody')}</p>`; openMenu(); }
}

function showResolvedChoices(result) {
  const selected = new Map();
  const panel = $('#interpret-result');
  body.classList.remove('candidate-selection-open');
  const render = () => {
    panel.innerHTML = `<h2>${t('chooseCandidate')}</h2><p class="hint">${t('candidateHint')}</p>${result.items.map((item, itemIndex) => `<section class="candidate-group"><strong>${item.source_phrase}</strong><div class="choice-row">${item.candidates.map((candidate, candidateIndex) => `<button data-resolved="${itemIndex}:${candidateIndex}" class="${selected.get(itemIndex) === candidateIndex ? 'selected' : ''}">${menuName(findMenu(candidate.menu_item_id)) || candidate.name}${candidate.option_candidates.length ? `（${candidate.option_candidates.join('・')}）` : ''}</button>`).join('')}<button data-none="${itemIndex}">${t('none')}</button></div></section>`).join('')}<button id="accept-resolved" class="primary" ${selected.size === result.items.length ? '' : 'disabled'}>${t('order')}</button><button id="retry-voice">${t('speakAgain')}</button>`;
    document.querySelectorAll('[data-resolved]').forEach(button => button.onclick = () => { const [itemIndex, candidateIndex] = button.dataset.resolved.split(':').map(Number); selected.set(itemIndex, candidateIndex); render(); });
    document.querySelectorAll('[data-none]').forEach(button => button.onclick = () => { selected.delete(Number(button.dataset.none)); openMenu(); });
    $('#retry-voice').onclick = () => {
      body.classList.remove('candidate-selection-open');
      panel.classList.add('hidden');
      const inputBlock = document.querySelector('[data-layout-block="input"]');
      if (inputBlock) inputBlock.scrollIntoView({behavior:'smooth', block:'start'});
      $('#voice').click();
    };
    $('#accept-resolved').onclick = async () => {
      const rows = result.items.map((item, index) => {
        const candidate = item.candidates[selected.get(index)];
        const menuItem = findMenu(candidate.menu_item_id);
        const optionNames = new Set(candidate.option_candidates);
        const optionIds = menuItem.modifiers.flatMap(group => group.options.filter(option => optionNames.has(option.name)).map(option => option.id));
        return {menu_item_id:candidate.menu_item_id, quantity:item.quantity || 1, modifier_option_ids:optionIds, operation:item.operation, menu_version:result.menu_version, llm_candidates:item.candidates, selected_candidate:candidate};
      });
      // 音声・文字解析で商品候補を選んだ後も、必ず数量と
      // 必須オプションの確認画面を通す。DBへはまだ送らない。
      showReview(rows);
    };
  };
  render();
  setTimeout(() => {
    const targetTop = window.scrollY + panel.getBoundingClientRect().top - 12;
    if (targetTop > window.scrollY) window.scrollTo({top:targetTop, behavior:'smooth'});
  }, 120);
}

async function confirmOrder() {
  const draft = order.items.filter(item => item.status === 'draft');
  if (!draft.length) return;
  $('#customer-confirm-items').innerHTML = draft.map(item => `<div><span>${menuName(findMenu(item.menu_item_id)) || item.name} × ${item.quantity}</span><strong>${yen(item.line_total)}</strong></div>`).join('');
  $('#customer-confirm-count').textContent = `${draft.reduce((sum, item) => sum + item.quantity, 0)} ${t('items')}`;
  $('#customer-confirm-total').textContent = yen(order.pending_total);
  $('#customer-confirm-dialog').classList.remove('hidden'); body.classList.add('confirm-open');
  setTimeout(() => $('#submit-customer-confirm').focus(), 0);
}

function closeCustomerConfirm() {
  $('#customer-confirm-dialog').classList.add('hidden'); body.classList.remove('confirm-open');
}

async function submitCustomerConfirm() {
  const button = $('#submit-customer-confirm'); button.disabled = true; button.textContent = '送信中…';
  try {
    order = await api(`/api/v1/shared-orders/${order.id}/confirm`, {method:'POST', body:JSON.stringify({expected_version:order.version, confirmed_by:actor, confirmation_method:'touch_button'})});
    closeCustomerConfirm(); renderSharedOrder(); toast(t('sentKitchen'));
  } catch (error) { if (error.status === 409) await loadOrder(); toast(error.message); renderSharedOrder(); }
  finally { button.disabled = false; button.textContent = '確定'; }
}

async function sendRequest(type, message = '') {
  await api('/api/v1/service-requests', {method:'POST', body:JSON.stringify({session_id:sessionId, request_type:type, message})});
  $('#interpret-result').classList.add('hidden'); toast(t('sentRequest'));
}

function setupVoice() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const buttons = [$('#voice')].filter(Boolean); const help = $('#voice-help'); const input = $('#order-text');
  const setHelp = message => { if (help) help.textContent = message; };
  const isVoiceShortcut = () => false;
  const unavailable = message => buttons.forEach(button => button.onclick = () => { if (isVoiceShortcut(button)) $('[data-layout-block="input"]').scrollIntoView({behavior:'smooth', block:'start'}); toast(message); });
  if (location.protocol === 'file:') {
    setHelp('このHTMLファイルを直接開いているため利用できません。http://localhost:8000/table/1 を開いてください。');
    unavailable('localhostで起動した注文画面を開いてください');
    return;
  }
  if (!SpeechRecognition) {
    setHelp('このブラウザは音声認識に対応していません。ChromeまたはAndroidキーボードのマイクを利用してください。');
    unavailable('このブラウザでは音声入力を利用できません');
    return;
  }
  if (!window.isSecureContext) {
    setHelp('Chromeのマイク権限は許可されていますが、この画面がLAN内HTTPのためブラウザに拒否されます。HTTPS化するまで、文字入力またはAndroidキーボードのマイクを利用してください。');
    unavailable('端末権限ではなくHTTP接続が原因です。マイクボタンにはHTTPSが必要です');
    return;
  }
  const recognition = new SpeechRecognition(); recognition.interimResults = true; recognition.continuous = true;
  let active = false; let starting = false; let listening = false; let accumulated = ''; let current = '';
  const showState = state => buttons.forEach(button => {
    button.classList.toggle('recording', state !== 'idle');
    if (button.id === 'start-voice') {
      button.querySelector('strong').textContent = state === 'starting' ? '…' : state === 'recording' ? '●' : t('voiceOrder');
      button.querySelector('small').textContent = state === 'recording' ? t('voiceHint') : (language === 'ja' ? '例：「ビール」「スタミナ系」' : voiceExampleText());
    } else {
      button.textContent = state === 'starting' ? '🎤 …' : state === 'recording' ? '🎤 ●' : button.id === 'voice' ? t('voiceButton') : t('micNav');
    }
  });
  const beginSession = () => {
    if (!listening || active || starting) return;
    recognition.lang = {ja:'ja-JP', en:'en-US', vi:'vi-VN', zh:'zh-CN', ko:'ko-KR', ur:'ur-PK'}[$('#input-language').value] || 'ja-JP';
    try { starting = true; showState('starting'); recognition.start(); }
    catch (error) { starting = false; listening = false; showState('idle'); const message = `マイクを開始できませんでした：${error.message}`; setHelp(message); toast(message); }
  };
  const stopListening = () => {
    if (!listening && !active && !starting) return;
    listening = false; showState('idle');
    setHelp(input.value.trim() ? dt('spokenReady') : dt('micPrompt'));
    try { if (active || starting) recognition.stop(); } catch (_) {}
  };
  recognition.onresult = event => {
    current = Array.from(event.results).map(result => result[0].transcript).join('');
    input.value = [accumulated, current].filter(Boolean).join(' ').trim();
  };
  recognition.onstart = () => {
    starting = false; active = true;
    if (!listening) { recognition.stop(); return; }
    showState('recording'); setHelp(dt('recording'));
  };
  recognition.onend = () => {
    active = false; starting = false;
    if (listening) {
      accumulated = input.value.trim(); current = ''; showState('recording');
      setHelp(dt('recordingMore')); setTimeout(beginSession, 180);
    } else showState('idle');
  };
  recognition.onerror = event => {
    const messages = {
      'not-allowed':window.isSecureContext ? 'マイクが許可されていません。ブラウザのサイト設定でマイクを許可してください。' : 'マイク権限はあっても、LAN内HTTP接続のためChromeに拒否されています。HTTPSが必要です。',
      'service-not-allowed':'この接続では音声認識を利用できません。localhostまたはHTTPSで開いてください。',
      'audio-capture':'端末のマイクを利用できません。マイク権限と他アプリの使用状況を確認してください。',
      'network':'音声認識サービスへ接続できませんでした。文字入力はそのまま利用できます。',
      'no-speech':'音声を待っています。続けて話してください。'
    };
    const message = messages[event.error] || `音声認識に失敗しました（${event.error}）`;
    if (event.error !== 'no-speech') { listening = false; showState('idle'); toast(message); }
    setHelp(message);
  };
  buttons.forEach(button => button.onclick = () => {
    if (isVoiceShortcut(button)) { $('[data-layout-block="input"]').scrollIntoView({behavior:'smooth', block:'start'}); setTimeout(() => input.focus({preventScroll:true}), 250); }
    if (listening || active || starting) { stopListening(); return; }
    accumulated = ''; current = ''; input.value = ''; listening = true; setHelp(dt('micPreparing')); emphasizeInterpret(true); beginSession();
  });
  document.addEventListener('click', event => {
    const clickedButton = event.target.closest('button');
    if (clickedButton && !clickedButton.closest('#voice,#go-voice,#start-voice')) stopListening();
  }, true);
}

function setupInquiryVoice() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const button = $('#inquiry-voice'); const input = $('#inquiry-text'); const help = $('#inquiry-voice-help');
  if (!SpeechRecognition || !window.isSecureContext) {
    help.textContent = !window.isSecureContext ? '音声入力にはHTTPS接続が必要です。文字入力は利用できます。' : 'このブラウザでは音声入力を利用できません。文字で入力してください。';
    button.onclick = () => toast(help.textContent);
    return;
  }
  const recognition = new SpeechRecognition(); recognition.lang = {ja:'ja-JP', en:'en-US', vi:'vi-VN', zh:'zh-CN', ko:'ko-KR', ur:'ur-PK'}[language] || 'ja-JP'; recognition.interimResults = true; recognition.continuous = true;
  let active = false; let starting = false; let listening = false; let accumulated = ''; let current = '';
  const showState = state => { button.classList.toggle('recording',state !== 'idle'); button.textContent = state === 'starting' ? '🎤 …' : state === 'recording' ? '🎤 ●' : t('voiceInput'); };
  const beginSession = () => {
    if (!listening || active || starting) return;
    try { starting = true; showState('starting'); recognition.start(); }
    catch (_) { starting = false; listening = false; showState('idle'); toast('マイクを開始できませんでした'); }
  };
  const stopListening = () => {
    if (!listening && !active && !starting) return;
    listening = false; showState('idle'); help.textContent = input.value.trim() ? 'このまま送信できます。' : '「音声入力」を押すと録音を開始します。';
    try { if (active || starting) recognition.stop(); } catch (_) {}
  };
  recognition.onresult = event => { current = Array.from(event.results).map(result => result[0].transcript).join(''); input.value = [accumulated,current].filter(Boolean).join(' ').trim(); };
  recognition.onstart = () => {
    starting = false; active = true;
    if (!listening) { recognition.stop(); return; }
    showState('recording'); help.textContent = '録音中です。送信など別のボタンを押すと終了します。';
  };
  recognition.onend = () => {
    active = false; starting = false;
    if (listening) { accumulated = input.value.trim(); current = ''; showState('recording'); help.textContent = '録音中です。続けて話せます。'; setTimeout(beginSession,180); }
    else showState('idle');
  };
  recognition.onerror = event => {
    const messages = {'not-allowed':'マイクが許可されていません。','audio-capture':'端末のマイクを利用できません。','network':'音声認識サービスへ接続できませんでした。','no-speech':'音声を待っています。続けて話してください。'};
    help.textContent = messages[event.error] || '音声認識に失敗しました。文字入力は利用できます。';
    if (event.error !== 'no-speech') { listening = false; showState('idle'); toast(help.textContent); }
  };
  button.onclick = () => {
    if (listening || active || starting) { stopListening(); return; }
    accumulated = ''; current = ''; input.value = ''; listening = true; help.textContent = 'マイクを準備しています…'; beginSession();
  };
  document.addEventListener('click', event => {
    const clickedButton = event.target.closest('button');
    if (clickedButton && clickedButton.id !== 'inquiry-voice') stopListening();
  }, true);
}

function connect() {
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws'; const socket = new WebSocket(`${protocol}://${location.host}/api/v1/ws/orders/${sessionId}`);
  socket.onopen = () => { $('#sync-state').textContent = dt('synced'); loadOrder().catch(() => {}); };
  socket.onmessage = async event => {
    const data = JSON.parse(event.data);
    if (data.type.startsWith('shared_order.') || data.type === 'kitchen.status_changed') { order = data.data; renderSharedOrder(); }
    if (data.type === 'shared_order.cancel_approved') { await loadOrder().catch(() => {}); showCancelDecision(true); }
    if (data.type === 'shared_order.cancel_rejected') { await loadOrder().catch(() => {}); showCancelDecision(false); }
    if (data.type === 'menu.availability_changed') api('/api/v1/menu').then(data => {menu=data; renderMenu();});
    if (data.type === 'store.settings_changed') {
      window.STORE_UI_LAYOUT = data.data.layout;
      body.style.setProperty('--accent', data.data.theme_color);
      document.querySelector('header strong').textContent = data.data.name;
      applyStoreLayout(data.data.layout);
      toast('画面設定を更新しました');
    }
    if (data.type === 'message.created' && data.data.sender_type === 'kitchen') { if (actor === 'customer') showKitchenReply(data.data); else toast(`厨房から：${data.data.text}`); }
    if (data.type === 'message.dismissed' && actor === 'customer') {
      dismissedReplyIdInMemory = Math.max(dismissedReplyIdInMemory, Number(data.data.id) || 0);
      const popup = $('#kitchen-reply-popup');
      if (Number(popup.dataset.messageId || 0) <= dismissedReplyId()) popup.classList.add('hidden');
    }
    if (data.type === 'table.session_reset') location.replace(body.dataset.languageUrl);
  };
  socket.onclose = () => { $('#sync-state').textContent = dt('reconnecting'); setTimeout(connect, 1500); };
}

function applyLanguageText() {
  document.documentElement.lang = language;
  document.documentElement.dir = language === 'ur' ? 'rtl' : 'ltr';
  try { localStorage.setItem('customer-language', language); } catch (_) {}
  const set = (selector, value) => { const element = $(selector); if (element) element.textContent = value; };
  set('#customer-start-title', t('choose'));
  set('#start-voice strong', t('voiceOrder'));
  set('#start-voice-prompt', language === 'ja' ? '話してください' : t('voiceHint'));
  set('#start-voice small', language === 'ja' ? '例：「ビール」「スタミナ系」' : t('voiceHint'));
  set('#start-menu strong', t('menuOrder'));
  set('#start-menu small', t('menuHint'));
  set('[data-layout-block="input"] h1', t('voiceTitle'));
  set('#voice-prompt', language === 'ja' ? '話してください' : t('voiceHint'));
  set('#source-label', t('spoken'));
  set('#voice', t('voiceButton'));
  set('#interpret', t('checkSpoken'));
  set('#clear-order-text', t('clear'));
  set('#voice-help', t('voiceHint'));
  set('#toggle-menu', t('menuOpen'));
  set('.shared-heading h1', t('orderDetails'));
  set('.pending-total span', t('pendingAmount'));
  set('.shared-total:not(.pending-total) span', t('totalAmount'));
  set('#confirm-order', t('order'));
  set('.confirm-note', t('confirmNote'));
  set('#go-voice', t('micNav'));
  set('#switch-order-mode', orderMode === 'voice' ? t('switchToMenu') : t('switchToVoice'));
  set('#start-over', t('startOver'));
  set('#change-language-label', t('changeLanguage'));
  set('[data-request="water"]', t('water'));
  set('#toggle-inquiry', `🎤 ${t('inquiry').replace(/^🎤\s*/, '')}`);
  set('[data-request="checkout"]', t('checkout'));
  set('label[for="inquiry-text"]', t('inquiryLabel'));
  set('#inquiry-voice', t('voiceInput'));
  set('#send-inquiry', t('send'));
  set('#clear-inquiry', t('cancel'));
  set('#inquiry-voice-help', t('inquiryHelp'));
  set('#customer-confirm-title', t('confirmTitle'));
  set('#customer-confirm-title + p', t('confirmBody'));
  set('#cancel-customer-confirm', t('back'));
  set('#submit-customer-confirm', t('confirm'));
  $('#order-text').placeholder = orderInputPlaceholders[language] || orderInputPlaceholders.en;
  $('#inquiry-text').placeholder = t('inquiryPlaceholder');
}

$('#input-language').onchange = () => {};
$('#toggle-menu').onclick = () => {
  const panel = $('#menu-panel');
  const opening = panel.classList.contains('hidden');
  panel.classList.toggle('hidden', !opening);
  $('#toggle-menu').setAttribute('aria-expanded', String(opening));
  $('#toggle-menu').textContent = opening ? t('menuClose') : t('menuOpen');
};
$('#toggle-inquiry').onclick = () => {
  const panel = $('#inquiry-panel'); const opening = panel.classList.contains('hidden');
  panel.classList.toggle('hidden', !opening); $('#toggle-inquiry').setAttribute('aria-expanded', String(opening));
  if (opening) setTimeout(() => $('#inquiry-text').focus(), 0);
};
$('#clear-inquiry').onclick = () => { $('#inquiry-text').value = ''; $('#inquiry-text').focus(); };
$('#send-inquiry').onclick = async () => {
  const message = $('#inquiry-text').value.trim();
  if (!message) return toast('問い合わせ内容を入力してください');
  try { await sendRequest('other', message); $('#inquiry-text').value = ''; toast('問い合わせを厨房へ送りました'); }
  catch (error) { toast(error.message); }
};
$('#close-kitchen-reply').onclick = closeKitchenReply;
$('#kitchen-reply-popup').onclick = event => { if (event.target.id === 'kitchen-reply-popup') closeKitchenReply(); };
window.addEventListener('storage', event => {
  if (event.key !== dismissedReplyKey) return;
  const dismissedId = Number(event.newValue || 0);
  const popup = $('#kitchen-reply-popup');
  if (Number.isFinite(dismissedId)) dismissedReplyIdInMemory = Math.max(dismissedReplyIdInMemory, dismissedId);
  if (Number(popup.dataset.messageId || 0) <= dismissedReplyId()) popup.classList.add('hidden');
});
$('#interpret').onclick = interpret; $('#confirm-order').onclick = confirmOrder;
$('#submit-customer-confirm').onclick = submitCustomerConfirm;
$('#cancel-customer-confirm').onclick = closeCustomerConfirm;
$('#customer-confirm-backdrop').onclick = closeCustomerConfirm;
if ($('#clear-order-text')) $('#clear-order-text').onclick = () => {
  $('#order-text').value = '';
  $('#japanese-text').value = '';
  reviewItems = [];
  interpretationId = null;
  const panel = $('#interpret-result');
  panel.innerHTML = '';
  panel.classList.add('hidden');
  emphasizeInterpret(false);
  $('#order-text').focus();
};
document.querySelectorAll('[data-request]').forEach(button => button.onclick = () => sendRequest(button.dataset.request));
$('#switch-order-mode').onclick = () => { location.href = orderMode === 'voice' ? menuUrl : voiceUrl; };
$('#start-over').onclick = () => { location.href = startUrl; };

applyLanguageText();
lockCustomerNavigation();
applyStoreLayout();
Promise.all([api('/api/v1/menu'), api(`/api/v1/sessions/${sessionId}/shared-order`), refreshStoreLayout().catch(() => null)]).then(([menuData, orderData]) => {
  menu = menuData; order = orderData; renderMenu(); renderSharedOrder(); connect(); loadLatestKitchenReply();
  if (orderMode === 'menu') {
    const category = sessionStorage.getItem(menuCategoryJumpKey);
    sessionStorage.removeItem(menuCategoryJumpKey);
    openMenu(category);
  }
}).catch(error => toast(error.message));
if (orderMode === 'voice') setupVoice();
if (orderMode !== 'choice') setupInquiryVoice();
