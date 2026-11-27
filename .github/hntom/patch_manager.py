#!/usr/bin/env python3
"""hntom manager (controller) configuration patch.

Applies, on top of the pinned upstream source:
  1. OVERWRITE_SETTINGS  -> ID/relay/API/key preset (same contract as the incoming client)
  2. BUILTIN_SETTINGS    -> hide the whole "Network" settings tab, keep :21114 over HTTPS
  3. UserDefaultConfig   -> default image quality "best", default codec "av1"
HARD_SETTINGS is deliberately left untouched: the manager must stay a full
outgoing-capable client, not an incoming-only build.
"""

import re
from pathlib import Path

CONFIG = Path("libs/hbb_common/src/config.rs")

OVERWRITE = [
    ("custom-rendezvous-server", "hntom.cn"),
    ("relay-server", "hntom.cn"),
    ("key", "RhWHCrir6gLBCZtX8BTdoT04nn+yfAzbh5Fi2SKFtW0="),
    ("api-server", "https://hntom.cn:21114/client"),
]
BUILTIN = [
    ("hide-network-settings", "Y"),
    ("allow-https-21114", "Y"),
]


def map_literal(pairs):
    body = "".join(f'        ("{k}".into(), "{v}".into()),\n' for k, v in pairs)
    return "RwLock::new(HashMap::from([\n" + body + "    ]))"


def patch_decl(text, name, value):
    old = f"pub static ref {name}: RwLock<HashMap<String, String>> = Default::default();"
    assert text.count(old) == 1, f"{name}: expected exactly 1 declaration, got {text.count(old)}"
    return text.replace(old, f"pub static ref {name}: RwLock<HashMap<String, String>> = {value};")


def sub_once(text, pattern, repl, label):
    out, n = re.subn(pattern, repl, text, flags=re.S)
    assert n == 1, f"{label}: expected 1 match, got {n}"
    return out


text = CONFIG.read_text(encoding="utf-8")

text = patch_decl(text, "OVERWRITE_SETTINGS", map_literal(OVERWRITE))
text = patch_decl(text, "BUILTIN_SETTINGS", map_literal(BUILTIN))

# Default image quality: balanced -> best (画质最优化)
text = sub_once(
    text,
    r'(keys::OPTION_IMAGE_QUALITY => \{\n\s*self\.get_string\(key, )"balanced"',
    r'\1"best"',
    "default image quality",
)

# Default codec: auto -> av1
text = sub_once(
    text,
    r'(keys::OPTION_CODEC_PREFERENCE => \{\n\s*self\.get_string\(key, )"auto"',
    r'\1"av1"',
    "default codec",
)

CONFIG.write_text(text, encoding="utf-8", newline="")

final = CONFIG.read_text(encoding="utf-8")

must = [
    '"custom-rendezvous-server".into(), "hntom.cn".into()',
    '"relay-server".into(), "hntom.cn".into()',
    '"key".into(), "RhWHCrir6gLBCZtX8BTdoT04nn+yfAzbh5Fi2SKFtW0=".into()',
    '"api-server".into(), "https://hntom.cn:21114/client".into()',
    '"hide-network-settings".into(), "Y".into()',
    '"allow-https-21114".into(), "Y".into()',
    'self.get_string(key, "best", vec!["best", "low", "custom"])',
    'self.get_string(key, "av1", vec!["vp8", "vp9", "av1", "h264", "h265"])',
]
for needle in must:
    assert needle in final, f"patched value missing: {needle}"

hard = "pub static ref HARD_SETTINGS: RwLock<HashMap<String, String>> = Default::default();"
assert final.count(hard) == 1, "HARD_SETTINGS must stay default (manager is not incoming-only)"

print("manager configuration patch applied")
