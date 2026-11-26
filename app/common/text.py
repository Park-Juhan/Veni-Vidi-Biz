"""Small Korean text helpers for generated sentences."""


def josa(word, pair):
    """Attach the right particle: josa('우유', '이/가') -> '우유가', josa('망원역', '은/는') -> '망원역은'.

    Words that do not end in a Hangul syllable (numbers, Latin letters) get the form without a final consonant
    unless they end in a digit that is read with one (0, 1, 3, 6, 7, 8)."""
    with_final, without = pair.split('/')
    last = (word or ' ')[-1]
    if '가' <= last <= '힣':
        final = (ord(last) - 0xAC00) % 28
        if pair == '으로/로' and final == 8:      # ㄹ takes 로
            return word + without
        return word + (with_final if final else without)
    return word + (with_final if last in '013678' else without)
