"""Track English lessons and require useful visuals for concrete vocabulary."""

from __future__ import annotations

from dataclasses import dataclass
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
    if len(word) > 2 and word not in {"animal", "fruit", "water"}
)


def _contains_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    padded = f" {_normalize(text)} "
    return any(f" {phrase} " in padded for phrase in phrases)


def _vietnamese_visual_word(text: str) -> str | None:
    normalized = _normalize(text)
    padded = f" {normalized} "
    # Prefer the longest Vietnamese noun phrase (for example "con ca sau" before "ca").
    for phrase, english in sorted(
            learning_image.VN_TO_EN_DIRECT.items(), key=lambda item: len(_normalize(item[0])), reverse=True):
        normalized_phrase = _normalize(phrase)
        # These bare Vietnamese words are also common function words or names
        # ("cho" = for, "ban" = you/table, "cam" = orange/feel).  Their
        # classifier forms such as "con cho" remain safe and are matched first.
        if normalized_phrase in {"cho", "ban", "cam", "bo", "may", "dua", "ca"}:
            continue
        if f" {normalized_phrase} " in padded:
            return _normalize(english)
    return None


def _english_visual_word(text: str) -> str | None:
    words = _normalize(text).split()
    for word in words:
        if word in ENGLISH_VISUAL_WORDS:
            return word
    return None


@dataclass
class LearningVisualState:
    active: bool = False
    turn_word: str | None = None
    image_shown: bool = False
    correction_sent: bool = False
    last_image_word: str | None = None

    def observe_user(self, text: str) -> None:
        if _contains_phrase(text, LESSON_STOP_PHRASES):
            self.active = False
            self.finish_turn()
            return
        if _contains_phrase(text, LESSON_START_PHRASES):
            self.active = True
        if self.active:
            self.turn_word = _vietnamese_visual_word(text) or self.turn_word

    def observe_assistant(self, text: str) -> None:
        if self.active and self.turn_word is None:
            self.turn_word = _english_visual_word(text)

    def mark_image(self, word: str) -> None:
        normalized = _normalize(word)
        if not normalized:
            return
        self.image_shown = True
        self.last_image_word = normalized

    def correction_prompt(self) -> str | None:
        if (not self.active or not self.turn_word or self.image_shown or
                self.correction_sent or self.turn_word == self.last_image_word):
            return None
        self.correction_sent = True
        return (
            "You are still in the same English lesson turn. Before continuing, call "
            f"show_learning_image exactly once for the concrete word '{self.turn_word}' "
            f"with query='{self.turn_word}' and word='{self.turn_word}'. After the tool "
            "succeeds, say one short interactive Vietnamese sentence about the image. "
            "If the tool fails, continue briefly by voice and do not claim an image appeared."
        )

    def finish_turn(self) -> None:
        self.turn_word = None
        self.image_shown = False
        self.correction_sent = False
