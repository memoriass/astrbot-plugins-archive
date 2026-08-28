import hashlib
import time
import urllib.parse
from difflib import SequenceMatcher

MIXIN_KEY_ENC_TAB = [
    46,
    47,
    18,
    2,
    53,
    8,
    23,
    32,
    15,
    50,
    10,
    31,
    58,
    3,
    45,
    35,
    27,
    43,
    5,
    49,
    33,
    9,
    42,
    19,
    29,
    28,
    14,
    39,
    12,
    38,
    41,
    13,
    37,
    48,
    7,
    16,
    24,
    55,
    40,
    61,
    26,
    17,
    0,
    1,
    60,
    51,
    30,
    4,
    22,
    25,
    54,
    21,
    56,
    59,
    6,
    63,
    57,
    62,
    11,
    36,
    20,
    34,
    44,
    52,
]


def get_mixin_key(ae):
    oe = [ae[i] for i in MIXIN_KEY_ENC_TAB]
    return "".join(oe)[:32]


def wbi_sign(params: dict, img_key: str, sub_key: str) -> dict:
    mixin_key = get_mixin_key(img_key + sub_key)
    curr_time = int(time.time())
    params["wts"] = curr_time
    params = dict(sorted(params.items()))
    # 过滤特殊字符
    params = {
        k: "".join(c for c in str(v) if c not in "!'()*") for k, v in params.items()
    }
    query = urllib.parse.urlencode(params)
    w_rid = hashlib.md5((query + mixin_key).encode()).hexdigest()
    params["w_rid"] = w_rid
    return params


def text_similarity(text1: str, text2: str) -> float:
    return SequenceMatcher(None, text1, text2).ratio()


def decode_unicode_escapes(text: str) -> str:
    return text.encode("utf-8").decode("unicode_escape") if text else ""
