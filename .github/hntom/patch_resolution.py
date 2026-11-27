import re
from pathlib import Path

DART = "flutter/lib/desktop/widgets/remote_toolbar.dart"
WIN = "src/platform/windows.rs"


def sub(path, pattern, repl, count=1):
    p = Path(path)
    t = p.read_text(encoding="utf-8")
    out, n = re.subn(pattern, repl, t, flags=re.S)
    assert n == count, f"{path}: expected {count} match(es), got {n}"
    p.write_text(out, encoding="utf-8", newline="")


# 1) 分辨率子菜单常显
sub(DART, r"    final visible = ffiModel\.keyboard &&\n.*?\n.*?\n    if \(!visible\) return Offstage\(\);\n", "")

# 2) 自定义分辨率输入常显
sub(
    DART,
    r"(Widget _customResolutionMenuButton\(BuildContext context, isVirtualDisplay\) \{\n    return Offstage\(\n      offstage: )!isVirtualDisplay",
    r"\1false",
)

# 3) 原始分辨率不再依赖上报列表
sub(
    DART,
    r"    if \(!resolutions\.any\(\(e\) =>\n.*?\n.*?\n      return Offstage\(\);\n    \}\n    return Offstage\(",
    "    return Offstage(",
)

# 4) 列表为空时“适应本地窗口”用本地分辨率
sub(
    DART,
    r"(    if \(ffiModel\.isVirtualDisplayResolution\) \{\n      return _localResolution!;\n    \}\n\n)(    for \(final r in resolutions\) \{)",
    r"\1    if (resolutions.isEmpty) {\n      return _localResolution;\n    }\n\n\2",
)

# 5) 无最佳匹配时仍显示“适应本地窗口”
sub(DART, r"(    if \(bestFitResolution == null\) \{\n      return )true;", r"\1false;")

# 6) 分隔线常显
sub(DART, r"_menuDivider\(showOriginalBtn, showFitLocalBtn, isVirtualDisplay\)", "_menuDivider(showOriginalBtn, showFitLocalBtn, true)")

# 7) 全部显示器视图下改主显示器
sub(
    DART,
    r"  _onChanged\(String\? value\) async \{\n    if \(pi\.currentDisplay == kAllDisplayValue\) \{\n      return;\n    \}\n    stateGlobal\.setLastResolutionGroupValue\(\n        widget\.id, pi\.currentDisplay, value\);",
    "  _onChanged(String? value) async {\n    final display =\n        pi.currentDisplay == kAllDisplayValue ? 0 : pi.currentDisplay;\n    stateGlobal.setLastResolutionGroupValue(widget.id, display, value);",
)

# 8) 发送切换请求同样落到主显示器
sub(
    DART,
    r"(  _changeResolution\(int w, int h\) async \{\n)    if \(pi\.currentDisplay == kAllDisplayValue\) \{\n      return;\n    \}\n(    await bind\.sessionChangeResolution\(\n      sessionId: ffi\.sessionId,\n      display: )pi\.currentDisplay",
    r"\1    final display =\n        pi.currentDisplay == kAllDisplayValue ? 0 : pi.currentDisplay;\n\2display",
)

# 9) Windows 被控端设备名回退
p = Path(WIN)
t = p.read_text(encoding="utf-8")
anchor = "pub fn resolutions(name: &str) -> Vec<Resolution> {"
assert t.count(anchor) == 1
helper = '''fn resolve_device_name(name: &str) -> [u16; 32] {
    unsafe {
        let mut dm: DEVMODEW = std::mem::zeroed();
        dm.dmSize = std::mem::size_of::<DEVMODEW>() as _;
        let probe = str_to_device_name(name);
        if !name.trim().is_empty()
            && EnumDisplaySettingsW(probe.as_ptr(), ENUM_CURRENT_SETTINGS, &mut dm) != 0
        {
            return probe;
        }
        for i in 1..=8u32 {
            let candidate = format!("\\\\\\\\.\\\\DISPLAY{}", i);
            let buf = str_to_device_name(&candidate);
            if EnumDisplaySettingsW(buf.as_ptr(), ENUM_CURRENT_SETTINGS, &mut dm) != 0 {
                return buf;
            }
        }
        probe
    }
}

'''
t = t.replace(anchor, helper + anchor)
call = "let device_name = str_to_device_name(name);"
assert t.count(call) == 3
t = t.replace(call, "let device_name = resolve_device_name(name);")
p.write_text(t, encoding="utf-8", newline="")

print("resolution patch applied")
