import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MenuItem, MenuVersionItem


# MVP用の初期翻訳。管理画面で登録済みの値は上書きしない。
DEFAULT_MENU_TRANSLATIONS: dict[str, dict[str, str]] = {
    "M101": {"en": "Kirin Ichiban Draft Beer", "zh": "麒麟一番榨生啤酒", "ko": "기린 이치방 생맥주", "vi": "Bia tươi Kirin Ichiban", "ur": "کِرن اچیبان ڈرافٹ بیئر"},
    "M102": {"en": "Asahi Super Dry Draft Beer", "zh": "朝日超爽生啤酒", "ko": "아사히 슈퍼드라이 생맥주", "vi": "Bia tươi Asahi Super Dry", "ur": "آساہی سپر ڈرائی ڈرافٹ بیئر"},
    "M103": {"en": "Suntory Draft Beer", "zh": "三得利生啤酒", "ko": "산토리 생맥주", "vi": "Bia tươi Suntory", "ur": "سنٹوری ڈرافٹ بیئر"},
    "M104": {"en": "Salted Edamame", "zh": "盐水毛豆", "ko": "소금 에다마메", "vi": "Đậu nành luộc muối", "ur": "نمکین ایڈامامے"},
    "M105": {"en": "Fried Chicken", "zh": "日式炸鸡", "ko": "닭튀김", "vi": "Gà chiên kiểu Nhật", "ur": "فرائیڈ چکن"},
    "M106": {"en": "Rice", "zh": "米饭", "ko": "밥", "vi": "Cơm", "ur": "چاول"},
    "M001": {"en": "Lunch Set A", "zh": "A套餐", "ko": "A 런치 세트", "vi": "Suất ăn A", "ur": "اے لنچ سیٹ"},
    "M012": {"en": "Fried Horse Mackerel Set", "zh": "炸竹荚鱼套餐", "ko": "전갱이 튀김 정식", "vi": "Suất cá nục chiên", "ur": "فرائیڈ ہارس میکریل سیٹ"},
    "M035": {"en": "Curry Rice", "zh": "咖喱饭", "ko": "카레라이스", "vi": "Cơm cà ri", "ur": "کری چاول"},
    "RPK001": {"en": "Chicken Boti Masala Curry", "zh": "鸡肉块马萨拉咖喱", "ko": "치킨 보티 마살라 카레", "vi": "Cà ri gà Boti Masala", "ur": "چکن بوٹی مسالہ کری"},
    "RPK002": {"en": "Rahi Punjabi Kitchen Chicken Curry", "zh": "拉希旁遮普厨房鸡肉咖喱", "ko": "라히 펀자비 키친 치킨 카레", "vi": "Cà ri gà Rahi Punjabi Kitchen", "ur": "راہِ پنجابی کچن چکن کری"},
    "RPK003": {"en": "Chicken Soup Curry", "zh": "鸡肉汤咖喱", "ko": "치킨 수프 카레", "vi": "Cà ri súp gà", "ur": "چکن سوپ کری"},
    "RPK004": {"en": "Chicken Gizzard Curry", "zh": "鸡胗咖喱", "ko": "닭똥집 카레", "vi": "Cà ri mề gà", "ur": "چکن سنگدان کری"},
    "RPK005": {"en": "Chicken Saagwala Curry", "zh": "菠菜鸡肉咖喱", "ko": "치킨 사그왈라 카레", "vi": "Cà ri gà rau bina", "ur": "چکن ساگ والا کری"},
    "RPK006": {"en": "Chicken Masala", "zh": "鸡肉马萨拉", "ko": "치킨 마살라", "vi": "Gà Masala", "ur": "چکن مسالہ"},
    "RPK007": {"en": "Mutton Masala", "zh": "羊肉马萨拉", "ko": "머튼 마살라", "vi": "Thịt cừu Masala", "ur": "مٹن مسالہ"},
    "RPK008": {"en": "Mutton Dripper", "zh": "羊肉滴滤咖喱", "ko": "머튼 드리퍼", "vi": "Cà ri cừu Dripper", "ur": "مٹن ڈریپر"},
    "RPK009": {"en": "Mutton Keema", "zh": "羊肉末咖喱", "ko": "머튼 키마", "vi": "Cà ri cừu băm", "ur": "مٹن قیمہ"},
    "RPK010": {"en": "Mutton Soup Curry", "zh": "羊肉汤咖喱", "ko": "머튼 수프 카레", "vi": "Cà ri súp thịt cừu", "ur": "مٹن سوپ کری"},
    "RPK011": {"en": "Beef Tendon Masala Curry", "zh": "牛筋马萨拉咖喱", "ko": "소힘줄 마살라 카레", "vi": "Cà ri Masala gân bò", "ur": "بیف ٹینڈن مسالہ کری"},
    "RPK012": {"en": "Beef Tendon Soup Curry", "zh": "牛筋汤咖喱", "ko": "소힘줄 수프 카레", "vi": "Cà ri súp gân bò", "ur": "بیف ٹینڈن سوپ کری"},
    "RPK013": {"en": "Shrimp Curry", "zh": "虾咖喱", "ko": "새우 카레", "vi": "Cà ri tôm", "ur": "جھینگا کری"},
    "RPK014": {"en": "Egg and Bean Curry", "zh": "鸡蛋豆咖喱", "ko": "달걀 콩 카레", "vi": "Cà ri trứng và đậu", "ur": "انڈا اور دال کری"},
    "RPK015": {"en": "Bean Curry", "zh": "豆咖喱", "ko": "콩 카레", "vi": "Cà ri đậu", "ur": "دال کری"},
    "RPK016": {"en": "Daily Vegetable Curry", "zh": "每日蔬菜咖喱", "ko": "오늘의 야채 카레", "vi": "Cà ri rau củ trong ngày", "ur": "روزانہ سبزی کری"},
    "RPK017": {"en": "Plain Naan", "zh": "原味烤饼", "ko": "플레인 난", "vi": "Bánh naan thường", "ur": "سادہ نان"},
    "RPK018": {"en": "Cheese Naan", "zh": "芝士烤饼", "ko": "치즈 난", "vi": "Bánh naan phô mai", "ur": "چیز نان"},
    "RPK019": {"en": "Pitiwala Naan", "zh": "皮蒂瓦拉烤饼", "ko": "피티왈라 난", "vi": "Bánh naan Pitiwala", "ur": "پیٹی والا نان"},
    "RPK020": {"en": "Brown Rice", "zh": "糙米饭", "ko": "현미밥", "vi": "Cơm gạo lứt", "ur": "براؤن رائس"},
    "RPK021": {"en": "Brown Rice Large", "zh": "大份糙米饭", "ko": "현미밥 곱빼기", "vi": "Cơm gạo lứt phần lớn", "ur": "براؤن رائس بڑی پلیٹ"},
    "RPK022": {"en": "Barbecue Salad", "zh": "烧烤沙拉", "ko": "바비큐 샐러드", "vi": "Salad thịt nướng", "ur": "باربی کیو سلاد"},
    "RPK023": {"en": "Green Salad", "zh": "蔬菜沙拉", "ko": "그린 샐러드", "vi": "Salad rau xanh", "ur": "گرین سلاد"},
    "RPK024": {"en": "Mutton Dripper Set", "zh": "羊肉滴滤咖喱套餐", "ko": "머튼 드리퍼 세트", "vi": "Set cà ri cừu Dripper", "ur": "مٹن ڈریپر سیٹ"},
    "RPK025": {"en": "Shrimp Curry Set", "zh": "虾咖喱套餐", "ko": "새우 카레 세트", "vi": "Set cà ri tôm", "ur": "جھینگا کری سیٹ"},
    "RPK026": {"en": "Chicken Gizzard Curry Set", "zh": "鸡胗咖喱套餐", "ko": "닭똥집 카레 세트", "vi": "Set cà ri mề gà", "ur": "چکن سنگدان کری سیٹ"},
    "RPK027": {"en": "Haleem Set", "zh": "哈利姆套餐", "ko": "할림 세트", "vi": "Set Haleem", "ur": "حلیم سیٹ"},
}


def backfill_default_menu_translations(db: Session) -> bool:
    changed = False
    translated_by_item_id: dict[int, str] = {}
    for item in db.scalars(select(MenuItem)):
        defaults = DEFAULT_MENU_TRANSLATIONS.get(item.menu_code or "")
        if not defaults:
            continue
        try:
            localized = json.loads(item.localized_names_json or "{}")
            if not isinstance(localized, dict):
                localized = {}
        except (TypeError, ValueError):
            localized = {}
        before = dict(localized)
        localized.setdefault("ja", item.name)
        for code, value in defaults.items():
            localized.setdefault(code, value)
        serialized = json.dumps(localized, ensure_ascii=False)
        translated_by_item_id[item.id] = serialized
        if localized != before:
            item.localized_names_json = serialized
            changed = True
    for version_item in db.scalars(select(MenuVersionItem)):
        serialized = translated_by_item_id.get(version_item.menu_item_id)
        if serialized and version_item.localized_names_json != serialized:
            version_item.localized_names_json = serialized
            changed = True
    if changed:
        db.commit()
    return changed
