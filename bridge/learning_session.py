"""Track English lessons and require useful visuals for concrete vocabulary."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
import unicodedata

import learning_image


def _normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text).casefold().replace("đ", "d"))
    value = "".join(char for char in value if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", value))


LESSON_START_PHRASES = (
    "hoc tieng anh", "day tieng anh", "luyen tieng anh", "on tieng anh",
    "learn english", "english lesson", "practice english",
)
LESSON_STOP_PHRASES = (
    "thoi hoc tieng anh", "dung hoc", "dung day", "doi chu de",
    "stop lesson", "stop learning english", "no more english",
)

VIETNAMESE_VISUAL_QUALIFIERS = (
    (("hai", "2"), "two"), (("ba", "3"), "three"), (("bon", "4"), "four"),
    (("nam", "5"), "five"), (("mot", "1"), "one"),
    (("mau cam",), "orange"), (("mau do",), "red"), (("mau vang",), "yellow"),
    (("mau xanh la",), "green"), (("mau xanh duong",), "blue"),
    (("mau den",), "black"), (("mau trang",), "white"), (("mau hong",), "pink"),
    (("mau tim",), "purple"), (("mau nau",), "brown"), (("mau xam",), "gray"),
    (("hoat hinh",), "cartoon"), (("minh hoa",), "illustration"),
    (("anh chup", "chup anh"), "photo"),
)

# Words that are easy to recognize visually and useful in a young learner's lesson.
ENGLISH_VISUAL_WORDS = {
    "airplane", "apple", "avocado", "banana", "bear", "bee", "bicycle",
    "bird", "boat", "book", "bus", "butterfly", "car", "carrot", "cat",
    "chair", "chicken", "classroom", "clock", "cloud", "coconut", "corn",
    "cow", "crocodile", "deer", "dog", "dolphin", "duck", "elephant",
    "fish", "flower", "forest", "frog", "giraffe", "goat", "grape",
    "helicopter", "horse", "house", "lemon", "lion", "mango", "monkey",
    "moon", "motorcycle", "mountain", "mouse", "mushroom", "orange",
    "papaya", "pencil", "penguin", "pig", "pineapple", "pitaya", "rabbit",
    "rain", "rainbow", "river", "rose", "school", "sea", "shark", "sheep",
    "ship", "snake", "snow", "squirrel", "star", "strawberry", "sun",
    "sunflower", "table", "tiger", "tomato", "train", "tree", "turtle",
    "watermelon", "whale",
}
ENGLISH_VISUAL_WORDS.update(
    word for phrase in learning_image.VN_TO_EN_DIRECT.values()
    for word in _normalize(phrase).split()
    if len(word) > 2 and word not in {"animal", "fruit", "water", "underwater"}
)


def _contains_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    if phrases is _NON_VOCABULARY_COMMANDS:
        # Preserve diacritics for English commands: Vietnamese "sống/sông"
        # must never become the English music keyword "song".
        english = {phrase for phrase in phrases if ' ' not in phrase}
        raw_words = set(re.findall(r'[^\W\d_]+', str(text).casefold()))
        if raw_words & english:
            return True
        phrases = tuple(phrase for phrase in phrases if phrase not in english)
    padded = f" {_normalize(text)} "
    return any(f" {phrase} " in padded for phrase in phrases)


def _canonical_english_subject(english: str) -> str:
    words = _normalize(english).split()
    for word in words:
        if word in ENGLISH_VISUAL_WORDS:
            return word
    return " ".join(words)


def _vietnamese_visual_word(text: str) -> str | None:
    normalized = _normalize(text)
    padded = f" {normalized} "
    # Prefer the longest Vietnamese noun phrase (for example "con ca sau" before "ca").
    raw_words = re.findall(r'[^\W\d_]+', unicodedata.normalize('NFC', str(text)).casefold())
    for phrase, english in sorted(
            learning_image.VN_TO_EN_DIRECT.items(), key=lambda item: len(_normalize(item[0])), reverse=True):
        normalized_phrase = _normalize(phrase)
        # These bare Vietnamese words are also common function words or names
        # ("cho" = for, "ban" = you/table, "cam" = orange/feel).  Their
        # classifier forms such as "con cho" remain safe and are matched first.
        if normalized_phrase in _AMBIGUOUS_BATCH_NOUNS:
            subject = next((_ACCENTED_BATCH_NOUNS[raw] for raw in raw_words
                            if _normalize(raw) == normalized_phrase and raw in _ACCENTED_BATCH_NOUNS), None)
            if subject:
                return subject
            continue
        if f" {normalized_phrase} " in padded:
            return _canonical_english_subject(english)
    return None


def _english_visual_word(text: str) -> str | None:
    # Vietnamese sống/sông, car/cả, etc. must not turn into English nouns.
    words = re.findall(r'[^\W\d_]+', unicodedata.normalize('NFC', str(text)).casefold())
    for word in words:
        candidates = [word]
        if word.endswith('ies'):
            candidates.append(word[:-3] + 'y')
        if word.endswith('es'):
            candidates.append(word[:-2])
        if word.endswith('s'):
            candidates.append(word[:-1])
        for candidate in candidates:
            if candidate in ENGLISH_VISUAL_WORDS:
                return candidate
    return None


def _asks_to_clarify_hearing(text: str) -> bool:
    normalized = _normalize(text)
    unclear = _contains_phrase(normalized, (
        'chua nghe ro', 'nghe chua ro', 'khong nghe ro', 'nghe khong ro',
        'didn t catch what you said', 'did not catch what you said',
        'couldn t hear', 'could not hear', 'didn t hear', 'did not hear',
    ))
    asks = _contains_phrase(normalized, (
        'nhac lai', 'noi lai', 'xac nhan', 'lap lai', 'repeat', 'say that again',
    ))
    first_person = re.search(
        r'(?:^| )(?:(?:wisio|minh) (?:chua nghe ro|nghe chua ro|khong nghe ro|nghe khong ro)'
        r'|i (?:didn t catch what you said|did not catch what you said|couldn t hear|could not hear|didn t hear|did not hear))',
        normalized)
    bare_unclear = normalized.startswith(('chua nghe ro', 'nghe chua ro'))
    # An animal's poor hearing followed by a lesson repeat instruction is not
    # Wisio reporting that it misheard the listener. Explicit self-reports can
    # pause actions before the rest of the question arrives in another chunk.
    return unclear and (first_person is not None or (bare_unclear and asks))


VOCABULARY_CATEGORIES = {
    "animals": (
        "cat", "dog", "elephant", "lion", "tiger", "bear", "rabbit", "monkey",
        "giraffe", "horse", "cow", "pig", "sheep", "goat", "duck", "chicken",
        "bird", "fish", "frog", "turtle", "snake", "crocodile", "dolphin",
        "whale", "shark", "penguin", "deer", "squirrel", "mouse", "bee",
        "butterfly", "zebra", "rhinoceros", "water buffalo", "shrimp", "lobster",
        "octopus", "crab", "squid", "snail", "dinosaur",
    ),
    "fruits": (
        "apple", "banana", "orange", "mango", "grape", "watermelon", "pineapple",
        "strawberry", "lemon", "coconut", "avocado", "papaya", "pitaya", "peach",
        "pear", "cherry", "plum", "kiwi", "blueberry", "raspberry", "guava",
        "lychee", "longan", "rambutan", "durian", "jackfruit", "mangosteen",
        "passion fruit", "pomegranate", "grapefruit", "lime", "apricot", "fig",
        "date fruit", "blackberry", "cranberry", "cantaloupe", "pomelo",
        "star fruit", "persimmon",
    ),
    "vehicles": (
        "car", "bus", "bicycle", "motorcycle", "train", "airplane", "boat",
        "ship", "helicopter", "truck", "taxi", "ambulance", "fire truck", "van",
        "tractor", "scooter", "submarine", "rocket", "sailboat", "canoe", "kayak",
        "tram", "ferry", "school bus", "minibus", "trolleybus", "pickup truck",
        "garbage truck", "cement mixer", "bulldozer", "excavator", "forklift",
        "snowmobile", "jet ski", "hot air balloon", "glider", "race car",
        "golf cart", "tricycle", "rickshaw",
    ),
    "food": (
        "bread", "rice", "noodles", "soup", "egg", "milk", "cheese", "butter",
        "yogurt", "sandwich", "pizza", "hamburger", "salad", "cake", "cookie",
        "ice cream", "chocolate", "candy", "pancake", "sausage", "steak",
        "chicken", "fish", "shrimp", "potato", "tomato", "carrot", "corn",
        "mushroom", "broccoli", "cucumber", "lettuce", "onion", "pumpkin",
        "tofu", "dumpling", "spring roll", "sushi", "porridge", "waffle",
    ),
}
_SEAFOOD_SUBJECTS = {'seafood', 'shrimp', 'prawn', 'lobster', 'crab', 'squid',
                     'octopus', 'fish', 'clam', 'clams', 'mussel', 'oyster', 'scallop'}
_CATEGORY_PHRASES = {
    "animals": ("animal", "animals", "dong vat", "con vat", "loai vat", "thu vat"),
    "fruits": ("fruit", "fruits", "trai cay", "hoa qua"),
    "vehicles": ("vehicle", "vehicles", "transport", "transportation", "phuong tien", "xe co"),
    "food": ("food", "foods", "dish", "dishes", "do an", "thuc an", "mon an"),
}
_BATCH_INTENT = (
    "list", "tell", "name", "teach", "learn", "vocabulary", "words",
    "liet ke", "ke", "noi", "day", "hoc", "cac tu",
    "nhung tu", "tu vung", "tu tieng anh",
)
_NON_VOCABULARY_COMMANDS = (
    "play", "music", "songs", "song", "volume", "playlist", "mo nhac",
    "phat nhac", "nghe nhac", "bai hat", "am luong", "tat nhac", "dung nhac",
)
_NON_LIST_CONVERSATION = (
    "tell me why", "tell me how", "tell me about", "story", "stories",
    "ke chuyen", "cau chuyen", "tai sao", "vi sao", "song o dau",
)
# Bare Vietnamese homographs can be names or ordinary function words. Their
# classifier forms remain available, and specific dish names take priority.
_AMBIGUOUS_BATCH_NOUNS = {
    "cho", "ban", "cam", "bo", "may", "dua", "ca", "nam", "hoa", "sao",
    "ho", "khi", "de", "lon", "song", "mua", "anh", "tao", "nho", "ong", "voi",
}
_ACCENTED_BATCH_NOUNS = {
    "chó": "dog", "bàn": "table", "bò": "cow", "bơ": "avocado",
    "mây": "cloud", "dừa": "coconut", "dứa": "pineapple", "cá": "fish",
    "nấm": "mushroom", "hổ": "tiger", "khỉ": "monkey", "dê": "goat",
    "lợn": "pig", "sông": "river", "mưa": "rain", "táo": "apple",
    "voi": "elephant",
}
_BARE_VIETNAMESE_COLORS = {
    "đỏ": "red", "vàng": "yellow", "đen": "black", "trắng": "white",
    "hồng": "pink", "tím": "purple", "nâu": "brown", "xám": "gray",
}
_COUNT_NAMES = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "hundred": 100,
    "mot": 1, "hai": 2, "ba": 3, "bon": 4, "nam": 5, "sau": 6,
    "bay": 7, "tam": 8, "chin": 9, "muoi": 10, "hai muoi": 20,
    "ba muoi": 30, "bon muoi": 40, "nam muoi": 50, "mot tram": 100,
}
for _unit, _value in tuple(_COUNT_NAMES.items()):
    if _value < 10:
        if _unit in {"one", "two", "three", "four", "five", "six", "seven", "eight", "nine"}:
            _COUNT_NAMES[f"twenty {_unit}"] = 20 + _value
            _COUNT_NAMES[f"thirty {_unit}"] = 30 + _value
        else:
            _COUNT_NAMES[f"muoi {_unit}"] = 10 + _value
            _COUNT_NAMES[f"hai muoi {_unit}"] = 20 + _value
            _COUNT_NAMES[f"ba muoi {_unit}"] = 30 + _value


def _requested_vocabulary_count(text: str) -> int | None:
    names = "|".join(re.escape(name) for name in sorted(_COUNT_NAMES, key=len, reverse=True))
    # A count must lead into vocabulary or a category, not a later unrelated
    # quantity such as a requested volume or number of animals in one picture.
    vocabulary = "|".join(re.escape(phrase) for phrases in _CATEGORY_PHRASES.values() for phrase in phrases)
    pattern = rf"\b([0-9]+|{names})\b(?: [a-z]+){{0,4}} (?:words?|tu|{vocabulary})\b"
    match = re.search(pattern, text)
    if match is None:
        return None
    token = match.group(1)
    count = int(token) if token.isdecimal() else _COUNT_NAMES[token]
    return min(count, 40) if count > 0 else None


def _batch_styles(text: str) -> list[str]:
    styles = [word for word in ("photo", "photograph", "illustration", "drawing", "cartoon", "vector")
              if _contains_phrase(text, (word, word + "s"))]
    styles.extend(english for phrases, english in VIETNAMESE_VISUAL_QUALIFIERS
                  if english in {"cartoon", "illustration", "photo"} and _contains_phrase(text, phrases))
    return list(dict.fromkeys(styles))


def _batch_lexicon() -> dict[str, str]:
    lexicon = {word: word for word in ENGLISH_VISUAL_WORDS}
    for items in VOCABULARY_CATEGORIES.values():
        lexicon.update({word: word for word in items})
    for word, subject in tuple(lexicon.items()):
        # Speech may name several cats or apples while the cache subject remains
        # singular. Avoid rewriting established uncountable vocabulary.
        if word not in {"fish", "rice", "milk", "cheese", "butter", "noodles"}:
            plural = word[:-1] + "ies" if word.endswith("y") and not word.endswith("ey") else word + ("es" if word.endswith("s") else "s")
            lexicon[plural] = subject
    for phrase, translated in learning_image.VN_TO_EN_DIRECT.items():
        phrase = _normalize(phrase)
        subject = re.sub(r"\s+(?:underwater\s+)?(?:animal|fruit)$", "", translated)
        lexicon[phrase] = "rose" if subject == "rose flower" else subject
    lexicon.update({dish: dish for dish in learning_image.VIETNAMESE_DISHES})
    lexicon.update(learning_image.VIETNAMESE_DRINK_ALIASES)
    return lexicon


_BATCH_LEXICON = _batch_lexicon()
_VIETNAMESE_BATCH_ALIASES = {_normalize(phrase) for phrase in learning_image.VN_TO_EN_DIRECT} | set(learning_image.VIETNAMESE_DISHES)
_ITEM_SEPARATOR_PATTERN = re.compile(
    r"[,;\n]|\b(?:and|và|va|rồi|roi|sau đó|sau do|then)\b", re.IGNORECASE)
# Long alternatives come first, so whole dishes and vehicle names consume their
# component nouns. Compile once because this runs on each transcript fragment.
_BATCH_SUBJECT_PATTERN = re.compile(r"(?<!\w)(?:" + "|".join(
    re.escape(phrase) for phrase in sorted(_BATCH_LEXICON, key=len, reverse=True)) + r")(?!\w)")
_BARE_LIST_TOKENS = set(" ".join(_BATCH_LEXICON).split()) | {
    "red", "yellow", "green", "blue", "purple", "pink", "white", "black",
    "gray", "grey", "brown", "cartoon", "photo", "illustration", "drawing",
}


_SCENE_START_PATTERN = re.compile(
    r"\b(?:sitting|standing|running|sleeping|eating|playing|walking|flying|swimming|"
    r"jumping|in|on|at|under|beside|next to|with|dang|ngoi|dung|chay|ngu|bay|boi|"
    r"tren|trong|duoi|ben canh)\b")
_SCENE_TRANSLATIONS = {
    "dang ngu": "sleeping", "dang chay": "running", "dang ngoi": "sitting",
    "dang dung": "standing", "dang an": "eating", "dang choi": "playing",
    "dang di bo": "walking", "dang bay": "flying", "dang boi": "swimming",
    "dang nhay": "jumping", "ngoi": "sitting", "ngu": "sleeping", "chay": "running",
    "tren": "on", "trong": "in", "duoi": "under", "ben canh": "beside",
    "cong vien": "park", "ghe sofa": "sofa", "ghe dai": "sofa", "cai ghe": "chair",
    "cai ban": "table", "truong hoc": "school", "khu rung": "forest",
    "ngoai troi": "outdoors", "san vuon": "garden", "bo bien": "beach",
}
_ITEM_COUNT_PATTERN = re.compile(r"\b(?:[0-9]+|" + "|".join(
    re.escape(name) for name in sorted(_COUNT_NAMES, key=len, reverse=True)) + r")\b")
_UNCONSTRAINED_REQUEST_TOKENS = set(" ".join((*_BATCH_INTENT, *_COUNT_NAMES,
    *[phrase for phrases, _ in VIETNAMESE_VISUAL_QUALIFIERS for phrase in phrases],
    *_SCENE_TRANSLATIONS)).split()) | {
    "me", "us", "the", "a", "an", "these", "those", "about", "please", "show",
    "picture", "pictures", "image", "images", "of", "as", "in", "style", "styles",
    "english", "for", "to", "cho", "xem", "anh", "hinh", "tieng", "cua", "cac",
    "nhung", "tu", "ve", "be", "minh", "toi", "di", "nhe", "con", "chu", "mon", "loai",
    "qua", "trai", "chiec", "cai", "mau", "dang", "dung", "kieu",
    "photo", "photos", "photograph", "photographs", "cartoon", "cartoons",
    "illustration", "illustrations", "drawing", "drawings", "vector", "vectors",
} | {_normalize(color) for color in _BARE_VIETNAMESE_COLORS}


def _batch_subjects(text: str, original: str) -> list[tuple[int, int, str]]:
    subjects = []
    raw_tokens = re.findall(r"\w+", unicodedata.normalize("NFC", original).casefold())
    for match in _BATCH_SUBJECT_PATTERN.finditer(text):
        phrase = match.group()
        subject = _BATCH_LEXICON[phrase]
        if phrase in _AMBIGUOUS_BATCH_NOUNS:
            token_index = len(text[:match.start()].split())
            raw_word = raw_tokens[token_index] if token_index < len(raw_tokens) else ""
            subject = _ACCENTED_BATCH_NOUNS.get(raw_word)
            if subject is None:
                continue
        elif phrase in {'pho', 'che'}:
            token_index = len(text[:match.start()].split())
            raw_word = raw_tokens[token_index] if token_index < len(raw_tokens) else ''
            if raw_word not in ({'pho', 'phở'} if phrase == 'pho' else {'che', 'chè'}):
                continue
        subjects.append((match.start(), match.end(), subject))
    subjects = [item for index, item in enumerate(subjects)
                if not (item[2] == "orange" and index + 1 < len(subjects)
                        and subjects[index + 1][2] not in VOCABULARY_CATEGORIES["fruits"]
                        and not text[item[1]:subjects[index + 1][0]].strip())]
    if subjects:
        # A chair/forest in an individual scene is a setting, not another item.
        scene = _SCENE_START_PATTERN.search(text, subjects[0][1])
        if scene:
            subjects = [item for item in subjects if item[0] < scene.start()]
    return subjects


def _query_colors(text: str, original: str = "", *,
                  english_colors: bool = True, vietnamese_colors: bool = True) -> list[str]:
    colors = [word for word in ("black", "white", "red", "orange", "yellow", "green", "blue", "purple", "pink", "brown", "gray", "grey", "golden", "silver")
              if english_colors and _contains_phrase(text, (word,))]
    colors.extend(english for phrases, english in VIETNAMESE_VISUAL_QUALIFIERS
                  if vietnamese_colors and english not in {"one", "two", "three", "four", "five", "cartoon", "illustration", "photo"}
                  and _contains_phrase(text, phrases))
    colors.extend(english for vietnamese, english in _BARE_VIETNAMESE_COLORS.items()
                  if vietnamese_colors and re.search(rf"\b{vietnamese}\b", original.casefold())
                  and _contains_phrase(text, (_normalize(vietnamese),)))
    return list(dict.fromkeys(colors))


def _query_count(prefix: str) -> str | None:
    matches = list(_ITEM_COUNT_PATTERN.finditer(prefix))
    if not matches:
        return None
    match = matches[-1]
    # Only the local count preceding the subject is an item attribute. A phrase
    # such as "list twenty words about ..." describes the lesson size instead.
    if _contains_phrase(prefix[match.end():], ("words", "word", "tu", "vocabulary")):
        return None
    token = match.group()
    count = int(token) if token.isdecimal() else _COUNT_NAMES[token]
    english = next((name for name, value in _COUNT_NAMES.items()
                    if value == count and name.split()[0] in {
                        "one", "two", "three", "four", "five", "six", "seven", "eight",
                        "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
                        "sixteen", "seventeen", "eighteen", "nineteen", "twenty", "thirty",
                        "forty", "fifty", "hundred"}), str(count))
    return english


def _scene_suffix(text: str) -> str:
    # Style is shared by the list and appended once. Everything in the actual
    # English scene remains in order, including modifiers of its setting.
    text = re.sub(r"\b(?:in |as )?(?:a |an )?(?:photo(?:graph)?s?|cartoons?|illustrations?|drawings?|vectors?)(?: style)?\b", "", text)
    text = re.sub(r"\b(?:dang |dung |kieu )?(?:hoat hinh|minh hoa|anh chup|chup anh)\b", "", text)
    scene = _SCENE_START_PATTERN.search(text)
    if scene is None:
        return ""
    text = text[scene.start():].strip()
    for source in sorted(_SCENE_TRANSLATIONS, key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(source)}\b", _SCENE_TRANSLATIONS[source], text)
    return " ".join(text.split())


def _explicit_vocabulary_items(text: str) -> list[dict[str, str]]:
    segments = _ITEM_SEPARATOR_PATTERN.split(str(text))
    styles = _batch_styles(_normalize(text))
    requests = []
    seen = set()
    for segment in segments:
        normalized_segment = _normalize(segment)
        subjects = _batch_subjects(normalized_segment, segment)
        for index, (start, end, subject) in enumerate(subjects):
            previous_end = subjects[index - 1][1] if index else 0
            prefix = normalized_segment[previous_end:start]
            next_start = subjects[index + 1][0] if index + 1 < len(subjects) else len(normalized_segment)
            trailing = normalized_segment[end:next_start]
            if len(subjects) > 1:
                # English adjectives lead their noun; Vietnamese adjectives
                # usually follow it. A streamed list may contain both forms.
                colors = _query_colors(prefix, segment, vietnamese_colors=False)
                colors.extend(_query_colors(trailing, segment, english_colors=False))
                attribute_text = (normalized_segment[start:next_start]
                                  if normalized_segment[start:end] in _VIETNAMESE_BATCH_ALIASES
                                  else normalized_segment[previous_end:end])
            else:
                attribute_text = normalized_segment
                colors = _query_colors(attribute_text, segment)
            count = _query_count(prefix)
            suffix = _scene_suffix(normalized_segment[end:]) if len(subjects) == 1 else ""
            query_parts = [*([count] if count else []), *colors, subject]
            query = " ".join((*dict.fromkeys(query_parts), *([suffix] if suffix else []), *styles))
            represented = (set(_normalize(query).split()) | _UNCONSTRAINED_REQUEST_TOKENS
                           | set(normalized_segment[start:end].split()))
            unknown = {token for token in attribute_text.split()
                       if not token.isdecimal() and token not in represented}
            if unknown:
                # Preserve uncommon size/breed/scene details for the verifier
                # rather than silently reducing the user's requested subject.
                original_clause = segment.strip() if len(subjects) == 1 else attribute_text.strip()
                query += f"; user scene: {original_clause}"
            key = subject, query
            if key not in seen:
                seen.add(key)
                requests.append({"word": subject, "query": query})
    return requests[:40]


def _counted_category(text: str) -> tuple[str, int] | None:
    normalized = _normalize(text)
    if not _contains_phrase(normalized, _BATCH_INTENT):
        return None
    category = next((category for category, phrases in _CATEGORY_PHRASES.items()
                     if _contains_phrase(normalized, phrases)), None)
    count = _requested_vocabulary_count(normalized) if category else None
    return (category, count) if count else None


def _category_visual_query(text: str, word: str) -> str:
    normalized = _normalize(text)
    colors = _query_colors(normalized, text)
    styles = _batch_styles(normalized)
    query = " ".join((*colors, word, *styles))
    category_tokens = set(" ".join(phrase for phrases in _CATEGORY_PHRASES.values()
                                   for phrase in phrases).split())
    represented = set(_normalize(query).split()) | _UNCONSTRAINED_REQUEST_TOKENS | category_tokens
    if any(token not in represented and not token.isdecimal() for token in normalized.split()):
        query += f"; user scene: {text}"
    return query


def _request_subject(word: str) -> str:
    normalized = _normalize(word)
    dish = learning_image.vietnamese_dish(word)
    if dish is None:
        # Preserve translated dish identities before reducing a phrase to its
        # first animal noun (chicken feet must never become a chicken).
        for name, english in sorted(learning_image.VIETNAMESE_DISHES.items(),
                                    key=lambda item: len(item[1]), reverse=True):
            if name in learning_image.VIETNAMESE_DRINKS:
                # English drink aliases are already handled above. A broad
                # ingredient such as milk is not automatically sữa tươi.
                continue
            translated = re.sub(r'^vietnamese ', '', _normalize(english))
            translated = re.sub(r' dish$', '', translated)
            if f' {translated} ' in f' {normalized} ':
                return name
    return (dish[0] if dish else
            _BATCH_LEXICON.get(normalized, _canonical_english_subject(normalized)))


def _dish_scene_query(text: str, dish: str) -> str:
    """Keep serving/ingredient details while removing surrounding dialogue."""
    scenes = []
    for clause in re.split(r'[.!?;]', text):
        scene = _normalize(clause)
        scene = re.sub(r'^(?:(?:wisio|wisio|robot|oi|u|a|hey)\s+)+', '', scene).strip()
        # Remove only dialogue around the description. Do not slice at the
        # dish or translate a plate's quantity into a number of chicken feet.
        scene = re.sub(r'^(?:toi |be |minh )?(?:muon an|muon xem|thich an)\b', '', scene).strip()
        scene = re.sub(r'\b(?:ban co the )?(?:hay )?cho (?:toi |be |minh )?xem(?: hinh| anh)?\b', '', scene)
        scene = re.sub(r'\b(?:duoc khong|nhe)\s*$', '', scene)
        scene = re.sub(r'\b(?:thi sao|la gi)\s*$', '', scene)
        scene = re.sub(r'\b(?:dang |dung |kieu )?(?:hoat hinh|minh hoa|anh chup|chup anh)\b', '', scene)
        scene = re.sub(r'\b(?:in |as )?(?:a |an )?(?:photo(?:graph)?s?|cartoons?|illustrations?|drawings?|vectors?)(?: style)?\b', '', scene)
        # Strip the image-request label only at the beginning; an attribute
        # such as a white plate in the same or next sentence remains intact.
        scene = re.sub(r'^(?:hinh|anh)\b', '', scene).strip()
        if scene:
            scenes.append(scene)
    styles = _batch_styles(text)
    return ' '.join(' '.join((scenes or [dish]) + (styles or ['photo'])).split())


def vocabulary_prefetch_requests(text: str) -> list[dict[str, str]]:
    """Plan bounded, ordered image searches for an actual vocabulary list.

    This only anticipates known concrete subjects. Gemini can still choose other
    words for a category lesson; prefetching never selects an image to display.
    """
    normalized = _normalize(text)
    if not normalized or _contains_phrase(normalized, _NON_VOCABULARY_COMMANDS):
        return []
    has_intent = _contains_phrase(normalized, _BATCH_INTENT)
    counted_category = _counted_category(normalized)
    styles = _batch_styles(normalized)
    if counted_category:
        category, count = counted_category
        return [{"word": word, "query": _category_visual_query(str(text), word)}
                for word in VOCABULARY_CATEGORIES[category][:count]]
    if _contains_phrase(normalized, _NON_LIST_CONVERSATION):
        return []
    # Separators signal an explicit list, but ordinary declarative conversation
    # ("I like apples and bananas") should not fan out into background searches.
    segments = _ITEM_SEPARATOR_PATTERN.split(str(text))
    if not has_intent and not all(set(_normalize(segment).split()) <= _BARE_LIST_TOKENS
                                  for segment in segments):
        return []
    requests = _explicit_vocabulary_items(text)
    return requests if len(requests) > 1 else []


@dataclass
class LearningVisualState:
    active: bool = False
    turn_word: str | None = None
    turn_query: str | None = None
    visual_required: bool = False
    force_refresh: bool = False
    image_shown: bool = False
    correction_sent: bool = False
    last_image_word: str | None = None
    user_turn_text: str = ""
    _prefetched_requests: set[tuple[str, str]] = field(default_factory=set, repr=False)
    image_attempt_failed: bool = False
    _failed_images: dict[tuple[str, str], str] = field(default_factory=dict, repr=False)
    _shown_images: dict[tuple[str, str], dict] = field(default_factory=dict, repr=False)
    _visible_image_key: tuple[str, str] | None = field(default=None, repr=False)
    _request_text: str = field(default='', repr=False)
    _assistant_turn_text: str = field(default='', repr=False)
    request_epoch: int = 0
    waiting_for_clarification: bool = False

    def request_clarification(self) -> None:
        self.waiting_for_clarification = True
        self.visual_required = False
        self.turn_word = None
        self.turn_query = None
        self.request_epoch += 1

    def begin_proactive_turn(self) -> bool:
        """A robot invitation is distinct from the previous exact user request."""
        if self.waiting_for_clarification:
            return False
        self.request_epoch += 1
        self.finish_turn()
        self._request_text = ''
        return True

    def shown_image(self, word: str, query: str) -> dict | None:
        result = self._shown_images.get((_normalize(word), _normalize(query)))
        return dict(result) if result is not None else None

    def is_image_visible(self, word: str, query: str) -> bool:
        key = (_normalize(word), _normalize(query))
        return key == self._visible_image_key and key in self._shown_images

    def prefetch_requests(self) -> list[dict[str, str]]:
        """Drain newly recognized subjects, including refined streamed queries."""
        fresh = []
        if self.waiting_for_clarification:
            return fresh
        requests = vocabulary_prefetch_requests(self.user_turn_text)
        # One concrete question benefits from the same early preparation as a
        # vocabulary list. Do not wait for Gemini to finish its explanation.
        current = self.automatic_request()
        if current is not None and not requests:
            word, query = current
            requests = [{'word': word, 'query': query}]
        for request in requests:
            key = request["word"], request["query"]
            if key not in self._prefetched_requests:
                self._prefetched_requests.add(key)
                fresh.append(request)
        return fresh

    def prefetch_visual_request(self, word: str, query: str) -> tuple[str, str]:
        """Prepare related upcoming lesson words without relaxing display checks."""
        context = self.user_turn_text or self._request_text
        subject = _request_subject(word)
        items = _explicit_vocabulary_items(context)
        if (self.active and not self.waiting_for_clarification
                and not _contains_phrase(context, _NON_VOCABULARY_COMMANDS)
                and not _counted_category(context) and len(items) == 1
                and items[0]['word'] != subject):
            seed = items[0]['word']
            if any(seed in words and subject in words for words in VOCABULARY_CATEGORIES.values()):
                return subject, query or subject
        return self.authoritative_visual_request(word, query)

    def authoritative_visual_request(self, word: str, query: str) -> tuple[str, str]:
        """Keep tool searches anchored to the actual user's requested scenes."""
        subject = _request_subject(word)
        if self.waiting_for_clarification:
            raise learning_image.LearningImageError('Chưa rõ yêu cầu; hỏi xác nhận và chờ người dùng, không đoán hình ảnh.')
        request_text = self.user_turn_text or self._request_text
        if not request_text or _contains_phrase(request_text, _NON_VOCABULARY_COMMANDS):
            return subject, query
        if (learning_image.seafood_context(request_text)
                and not _counted_category(request_text)
                and len(_explicit_vocabulary_items(request_text)) <= 1):
            if subject in {'sea', 'seafood', 'food'}:
                subject = 'seafood'
                scene = learning_image._replace_normalized_phrase(request_text, 'do bien', 'hải sản')
                scene = learning_image.google_search_query(scene, subject)
                scene = re.sub(r'\s+[áàạa]\s*$', '', scene)
                query = _dish_scene_query(scene, subject)
                query = learning_image._replace_normalized_phrase(query, 'hai san', 'hải sản món ăn')
            elif subject in _SEAFOOD_SUBJECTS:
                query = (query or subject) + ' seafood dish'
            else:
                raise learning_image.LearningImageError(
                    f'The requested subject is seafood for eating; refusing an unrelated {subject} image')
            return subject, query + f'; user scene: {request_text}'
        dish = learning_image.vietnamese_dish(request_text)
        if (dish and not _counted_category(request_text)
                and len(_explicit_vocabulary_items(request_text)) <= 1):
            # A food request must override a generic animal/name supplied by the
            # model. Keep the dish itself in the search, not conversational filler.
            precise_query = _dish_scene_query(request_text, dish[0])
            # Search and verification use the same concise subject description.
            # This also gives automatic and model tool requests a shared cache key.
            precise_query = _normalize(learning_image.google_search_query(precise_query, dish[0]))
            return dish[0], precise_query
        counted_category = _counted_category(request_text)
        if counted_category:
            category, _ = counted_category
            allowed = set(VOCABULARY_CATEGORIES[category])
            if category == "food":
                allowed.update(VOCABULARY_CATEGORIES["fruits"])
            known_subjects = ENGLISH_VISUAL_WORDS | {
                item for words in VOCABULARY_CATEGORIES.values() for item in words}
            if subject in known_subjects and subject not in allowed:
                raise learning_image.LearningImageError(
                    f"The requested category is {category}; refusing an unrelated {subject} image")
            # The prefetch inventory anticipates common vocabulary; Gemini may
            # choose another valid word without inheriting the lesson-size count.
            return subject, _category_visual_query(request_text, subject)
        items = _explicit_vocabulary_items(request_text)
        query_subject = _request_subject(query)
        if (subject == 'chicken' and query_subject.startswith('chan ga')
                and any(item['word'] == query_subject for item in items)):
            # Gemini may label a dish with its broad ingredient, but only a
            # precise feet description can identify this requested list item.
            subject = query_subject
        matches = [item for item in items if item["word"] == subject]
        if matches:
            matching_query = next((item for item in matches
                                   if _normalize(item["query"]) == _normalize(query)), matches[0])
            return subject, matching_query["query"]
        if items:
            expected = ", ".join(dict.fromkeys(item["word"] for item in items))
            raise learning_image.LearningImageError(
                f"The requested subject is {expected}; refusing an unrelated {subject} image")
        if _contains_phrase(request_text, (
                "cho xem", "xem hinh", "xem anh", "hinh anh", "show me", "show",
                "show a picture", "show an image")):
            clause = f"; user scene: {request_text}"
            return subject, query if clause in query else query + clause
        return subject, query

    def observe_user(self, text: str) -> None:
        cleaned = " ".join(str(text).split())
        if not cleaned:
            return
        if cleaned:
            if self.waiting_for_clarification:
                self.finish_turn()
            if not self.user_turn_text:
                self._failed_images.clear()
                self._shown_images.clear()
                self._visible_image_key = None
                self._assistant_turn_text = ''
                self.request_epoch += 1
                self.waiting_for_clarification = False
                self.image_attempt_failed = False
            self.user_turn_text = " ".join(
                part for part in (self.user_turn_text, cleaned) if part)[:500]
        complete_text = self.user_turn_text
        self._request_text = complete_text
        if _contains_phrase(complete_text, _NON_VOCABULARY_COMMANDS):
            self.turn_word = None
            self.turn_query = None
            self.visual_required = False
            return
        if _contains_phrase(complete_text, LESSON_STOP_PHRASES):
            self.active = False
            self.finish_turn()
            return
        if _contains_phrase(complete_text, LESSON_START_PHRASES):
            self.active = True
        dish = learning_image.vietnamese_dish(complete_text)
        visual_word = ('seafood' if learning_image.seafood_context(complete_text) else dish[0] if dish else
                       (_vietnamese_visual_word(complete_text)
                        or _english_visual_word(complete_text)))
        if visual_word:
            self.turn_word = visual_word
            self.turn_query = complete_text[:180]
            # Concrete topics benefit from a visual during both lessons and
            # ordinary conversation. Reuse the previous image for an ongoing
            # topic unless the listener explicitly asks to see a new one.
            explicit_visual = _contains_phrase(complete_text, (
                "cho xem", "xem hinh", "xem anh", "hinh anh", "show me",
                "show a picture", "show an image",
            ))
            self.force_refresh = explicit_visual
            self.visual_required = (visual_word != self.last_image_word or explicit_visual)

    def observe_assistant(self, text: str) -> None:
        self._assistant_turn_text = (self._assistant_turn_text + ' ' + str(text))[-400:]
        if _asks_to_clarify_hearing(self._assistant_turn_text):
            if not self.waiting_for_clarification:
                self.request_clarification()
            return
        context = self.user_turn_text or self._request_text
        if (self.waiting_for_clarification or _contains_phrase(context, _NON_VOCABULARY_COMMANDS)
                or _contains_phrase(context, LESSON_STOP_PHRASES)):
            return
        explain_intent = _contains_phrase(context, (
            'explain', 'tell me about', 'what happens', 'how does', 'why',
            'giai thich', 'ke ve', 'tim hieu', 'la gi', 'nhu the nao', 'tai sao', 'vi sao',
        ))
        topic_intent = explain_intent or _contains_phrase(context, (
            'ke chuyen', 'cau chuyen', 'story', 'stories', 'goi y mon',
            'mon gi', 'an gi', 'goi y do an', 'suggest a dish', 'meal suggestions',
        ))
        if (self.active or topic_intent) and self.turn_word is None:
            dish = learning_image.vietnamese_dish(self._assistant_turn_text)
            self.turn_word = (dish[0] if dish else
                              (_vietnamese_visual_word(self._assistant_turn_text)
                               or _english_visual_word(self._assistant_turn_text)))
            if self.turn_word:
                scene = next((item['query'] for item in _explicit_vocabulary_items(self._assistant_turn_text)
                              if item['word'] == self.turn_word), self.turn_word)
                self.turn_query = scene
                self.visual_required = self.turn_word != self.last_image_word

    def automatic_request(self) -> tuple[str, str] | None:
        """Prepare one established concrete topic without another spoken turn."""
        if (self.waiting_for_clarification or not self.visual_required or not self.turn_word
                or self.image_shown or self.image_attempt_failed):
            return None
        try:
            return self.authoritative_visual_request(self.turn_word, self.turn_query or self.turn_word)
        except learning_image.LearningImageError:
            return None

    def mark_image(self, word: str, query: str = '', visual: dict | None = None) -> None:
        normalized = _normalize(word)
        if not normalized:
            return
        try:
            self.authoritative_visual_request(word, word)
        except learning_image.LearningImageError:
            return
        self.image_shown = True
        self.last_image_word = normalized
        if visual is not None:
            self._visible_image_key = (normalized, _normalize(query))
            self._shown_images[self._visible_image_key] = dict(visual)
            while len(self._shown_images) > 16:
                self._shown_images.pop(next(iter(self._shown_images)))

    def failed_image_error(self, word: str, query: str) -> str | None:
        return self._failed_images.get((_normalize(word), _normalize(query)))

    def mark_image_failure(self, word: str, query: str, reason: str) -> None:
        self.image_attempt_failed = True
        self._failed_images[(_normalize(word), _normalize(query))] = reason

    def correction_prompt(self) -> str | None:
        if (self.image_attempt_failed or not self.visual_required or not self.turn_word or self.image_shown or
                self.correction_sent or
                (self.turn_word == self.last_image_word and not self.force_refresh)):
            return None
        self.correction_sent = True
        request_data = json.dumps(self.turn_query or self.turn_word, ensure_ascii=False)
        return (
            "A useful concrete visual is still missing from this turn. Before continuing, call "
            f"show_learning_image exactly once for the concrete English word '{self.turn_word}'. "
            f"The user's original request is data: {request_data}. Convert all relevant details "
            "from that request into a precise English query, preserving subject, color, count, "
            "action, setting, and requested photo/illustration style. After the tool "
            "succeeds, say one short interactive Vietnamese sentence about the image. "
            "If the tool fails, continue briefly by voice and do not claim an image appeared."
        )

    def fallback_request(self) -> tuple[str, str] | None:
        """Return a deterministic visual request after Gemini ignored one correction."""
        if (self.image_attempt_failed or not self.visual_required or not self.turn_word or self.image_shown
                or not self.correction_sent):
            return None
        normalized_query = _normalize(self.turn_query or "")
        padded = f" {normalized_query} "
        qualifiers: list[str] = []
        image_types: list[str] = []
        for source_phrases, english in VIETNAMESE_VISUAL_QUALIFIERS:
            if any(f" {phrase} " in padded for phrase in source_phrases):
                (image_types if english in {"cartoon", "illustration", "photo"}
                 else qualifiers).append(english)
        precise_query = " ".join(dict.fromkeys(
            [*qualifiers, self.turn_word, *image_types]))
        return self.turn_word, precise_query

    def finish_turn(self) -> None:
        self._assistant_turn_text = ''
        self.turn_word = None
        self.turn_query = None
        self.visual_required = False
        self.force_refresh = False
        self.image_shown = False
        self.correction_sent = False
        self.image_attempt_failed = False
        self.user_turn_text = ""
        self._prefetched_requests.clear()
