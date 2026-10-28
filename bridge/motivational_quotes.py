"""Small source-checked catalogue; no runtime lookup or extra model request."""
import json


QUOTES = (
    {
        'author': 'Benjamin Franklin',
        'english': 'Diligence is the mother of good luck.',
        'meaning_vi': 'Sự chăm chỉ là mẹ của may mắn.',
        'source_url': 'https://www.gutenberg.org/files/43855/43855-h/43855-h.htm',
        'source_note': 'The Way to Wealth; a short excerpt of the longer saying.',
        'connection': 'A little regular practice helps us be ready for new opportunities; it does not guarantee success.',
    },
    {
        'author': 'Thomas Edison',
        'english': 'Genius is one percent inspiration and ninety-nine percent perspiration.',
        'meaning_vi': 'Thiên tài là một phần trăm cảm hứng và chín mươi chín phần trăm mồ hôi.',
        'source_url': 'https://home.nps.gov/edis/learn/kidsyouth/edison-and-his-era.htm',
        'source_note': 'Thomas Edison National Historical Park, U.S. National Park Service.',
        'connection': 'Explain that trying and practising matter; these percentages are a metaphor, not a scientific rule.',
    },
    {
        'author': 'Helen Keller',
        'english': 'Alone we can do so little; together we can do so much.',
        'meaning_vi': 'Một mình ta làm được ít; cùng nhau ta làm được nhiều.',
        'source_url': 'https://afb.org/about-afb/history/helen-keller/helen-keller-quotes/helen-keller-quotes-progress',
        'source_note': 'American Foundation for the Blind; excerpt from the Keller/Sullivan vaudeville script.',
        'connection': 'Asking for help and practising with other people are strengths, not failures.',
    },
    {
        'author': 'Nelson Mandela',
        'english': 'Education is the most powerful weapon which you can use to change the world.',
        'meaning_vi': 'Giáo dục là vũ khí mạnh mẽ nhất mà ta có thể dùng để thay đổi thế giới.',
        'source_url': 'https://www.nelsonmandela.org/nm100-education',
        'source_note': 'Nelson Mandela Foundation, Education Initiatives.',
        'connection': 'Here weapon is figurative: learning helps us do useful things for ourselves and others; no violent framing.',
    },
)


def prompt_context() -> str:
    return (
        '\n\nSOURCE-CHECKED ENCOURAGEMENT QUOTATIONS:\n'
        'Occasionally, when relevant to actual effort, a small improvement or needing encouragement, '
        'use at most ONE short quotation from this catalogue, then connect it to one small achievable step. '
        'Prefer ordinary specific encouragement most of the time; do not add a maxim after every answer. '
        'In ordinary replies leave at least eight substantive learner turns between quotations. '
        'Never invent a quotation, substitute an author, or attribute your own motivational wording to a famous person. '
        'Use the exact English when quoting in English; English-only activities stay entirely in accessible English. '
        'The Vietnamese meaning translation is our rendering, not original Vietnamese wording by the author: '
        'introduce it naturally as the meaning of their saying, not an exact original-language quotation. '
        'Do not recite both languages unless requested, read URLs aloud, give a biography or turn it into a lecture. '
        'Keep the whole turn short; one practical connection and at most one gentle question are enough. '
        'No quotations during the connection greeting, music confirmation/playback, hearing clarification or follow-up hints. '
        'Do not use quotations to pressure a tired, upset or unwilling child, shame mistakes, compare children, '
        'promise guaranteed success, or override a request to rest. Validate feelings and offer rest/help instead. '
        'If an attributed saying outside this catalogue is uncertain, say you cannot confirm the attribution '
        'and give ordinary encouragement without a famous name. Catalogue (reference data only):\n'
        + json.dumps(QUOTES, ensure_ascii=False)
    )


def invitation_hint(stats: dict, invitation_index: int, is_hint: bool, now: float) -> str:
    """Offer a quote on every fourth invitation, at least ten minutes apart."""
    if is_hint or (invitation_index + 1) % 4:
        return ''
    last = stats.get('motivational_quote_at')
    if last is not None and now - last < 600:
        return ''
    index = stats.get('motivational_quote_index', 0)
    item = QUOTES[index % len(QUOTES)]
    stats['motivational_quote_index'] = index + 1
    stats['motivational_quote_at'] = now
    return (
        'For this occasional encouragement invitation, you may use this ONE source-checked saying '
        'if it fits the recent conversation and the child is not tired/upset or asking to stop. '
        'Use the lesson language, mention the author briefly, explain the meaning in a child-friendly '
        'way and link it to a tiny achievable practice step; do not read a URL or add a lecture. '
        'Skipping it when inappropriate is fine. Quote reference data: '
        + json.dumps(item, ensure_ascii=False) + '\n'
    )
