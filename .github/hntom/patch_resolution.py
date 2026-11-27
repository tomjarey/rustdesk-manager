import re
from pathlib import Path

DART = "flutter/lib/desktop/widgets/remote_toolbar.dart"
WIN = "src/platform/windows.rs"
VIDEO = "src/server/video_service.rs"


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

# 9) 控制端强制合并完整 16 项分辨率清单（去重并按面积降序排列）
sub(
    DART,
    r"  List<Resolution> get resolutions => pi\.resolutions;",
    """  static final List<Resolution> _kPresetResolutions = [
    Resolution(2560, 1600),
    Resolution(1920, 1200),
    Resolution(1920, 1080),
    Resolution(1680, 1050),
    Resolution(1600, 1200),
    Resolution(1440, 900),
    Resolution(1400, 1050),
    Resolution(1280, 1024),
    Resolution(1280, 960),
    Resolution(1280, 800),
    Resolution(1280, 768),
    Resolution(1280, 720),
    Resolution(1152, 864),
    Resolution(1024, 768),
    Resolution(800, 600),
    Resolution(640, 480),
  ];

  List<Resolution> get resolutions {
    final seen = <String>{};
    final merged = <Resolution>[];
    for (final r in [...pi.resolutions, ..._kPresetResolutions]) {
      final key = '${r.width}x${r.height}';
      if (r.width > 0 && r.height > 0 && seen.add(key)) {
        merged.add(r);
      }
    }
    merged.sort((a, b) {
      final area = (b.width * b.height).compareTo(a.width * a.height);
      return area != 0 ? area : b.width.compareTo(a.width);
    });
    return merged;
  }""",
)

# 10) 被控端 video_service.rs 在 display.name 为空时同样调用 resolutions() 以走设备名回退
sub(
    VIDEO,
    r"                VideoSource::Monitor => \{\n                    if display\.name\.is_empty\(\) \{\n                        vec!\[\]\n                    \} else \{\n                        crate::platform::resolutions\(&display\.name\)\n                    \}\n                \}",
    "                VideoSource::Monitor => crate::platform::resolutions(&display.name),",
)

# 11) Windows 被控端：设备名回退 + 修复 dmSize / EDS_RAWMODE 枚举 + 16 项清单合并 + 多级回退切换分辨率
p = Path(WIN)
t = p.read_text(encoding="utf-8")

old_block = '''pub fn resolutions(name: &str) -> Vec<Resolution> {
    unsafe {
        let mut dm: DEVMODEW = std::mem::zeroed();
        let mut v = vec![];
        let mut num = 0;
        let device_name = str_to_device_name(name);
        loop {
            if EnumDisplaySettingsW(device_name.as_ptr(), num, &mut dm) == 0 {
                break;
            }
            let r = Resolution {
                width: dm.dmPelsWidth as _,
                height: dm.dmPelsHeight as _,
                ..Default::default()
            };
            if !v.contains(&r) {
                v.push(r);
            }
            num += 1;
        }
        v
    }
}

pub fn current_resolution(name: &str) -> ResultType<Resolution> {
    let device_name = str_to_device_name(name);
    unsafe {
        let mut dm: DEVMODEW = std::mem::zeroed();
        dm.dmSize = std::mem::size_of::<DEVMODEW>() as _;
        if EnumDisplaySettingsW(device_name.as_ptr(), ENUM_CURRENT_SETTINGS, &mut dm) == 0 {
            bail!(
                "failed to get current resolution, error {}",
                io::Error::last_os_error()
            );
        }
        let r = Resolution {
            width: dm.dmPelsWidth as _,
            height: dm.dmPelsHeight as _,
            ..Default::default()
        };
        Ok(r)
    }
}

pub(super) fn change_resolution_directly(
    name: &str,
    width: usize,
    height: usize,
) -> ResultType<()> {
    let device_name = str_to_device_name(name);
    unsafe {
        let mut dm: DEVMODEW = std::mem::zeroed();
        dm.dmSize = std::mem::size_of::<DEVMODEW>() as _;
        dm.dmPelsWidth = width as _;
        dm.dmPelsHeight = height as _;
        dm.dmFields = DM_PELSHEIGHT | DM_PELSWIDTH;
        let res = ChangeDisplaySettingsExW(
            device_name.as_ptr(),
            &mut dm,
            NULL as _,
            CDS_UPDATEREGISTRY | CDS_GLOBAL | CDS_RESET,
            NULL,
        );
        if res != DISP_CHANGE_SUCCESSFUL {
            bail!(
                "ChangeDisplaySettingsExW failed, res={}, error {}",
                res,
                io::Error::last_os_error()
            );
        }
        Ok(())
    }
}'''

new_block = '''const EDS_RAWMODE_FLAG: u32 = 0x00000002;

const PRESET_RESOLUTIONS: &[(i32, i32)] = &[
    (2560, 1600),
    (1920, 1200),
    (1920, 1080),
    (1680, 1050),
    (1600, 1200),
    (1440, 900),
    (1400, 1050),
    (1280, 1024),
    (1280, 960),
    (1280, 800),
    (1280, 768),
    (1280, 720),
    (1152, 864),
    (1024, 768),
    (800, 600),
    (640, 480),
];

fn resolve_device_name(name: &str) -> [u16; 32] {
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

pub fn resolutions(name: &str) -> Vec<Resolution> {
    unsafe {
        let mut v: Vec<Resolution> = vec![];
        let device_name = resolve_device_name(name);
        for raw in [false, true] {
            let mut num = 0u32;
            loop {
                let mut dm: DEVMODEW = std::mem::zeroed();
                dm.dmSize = std::mem::size_of::<DEVMODEW>() as _;
                let ok = if raw {
                    EnumDisplaySettingsExW(device_name.as_ptr(), num, &mut dm, EDS_RAWMODE_FLAG)
                } else {
                    EnumDisplaySettingsW(device_name.as_ptr(), num, &mut dm)
                };
                if ok == 0 {
                    break;
                }
                if dm.dmPelsWidth > 0 && dm.dmPelsHeight > 0 {
                    let r = Resolution {
                        width: dm.dmPelsWidth as _,
                        height: dm.dmPelsHeight as _,
                        ..Default::default()
                    };
                    if !v.contains(&r) {
                        v.push(r);
                    }
                }
                num += 1;
            }
        }
        for &(w, h) in PRESET_RESOLUTIONS {
            let r = Resolution {
                width: w as _,
                height: h as _,
                ..Default::default()
            };
            if !v.contains(&r) {
                v.push(r);
            }
        }
        v.sort_by(|a, b| {
            let area_b = (b.width as i64) * (b.height as i64);
            let area_a = (a.width as i64) * (a.height as i64);
            area_b.cmp(&area_a).then_with(|| b.width.cmp(&a.width))
        });
        v
    }
}

pub fn current_resolution(name: &str) -> ResultType<Resolution> {
    let device_name = resolve_device_name(name);
    unsafe {
        let mut dm: DEVMODEW = std::mem::zeroed();
        dm.dmSize = std::mem::size_of::<DEVMODEW>() as _;
        if EnumDisplaySettingsW(device_name.as_ptr(), ENUM_CURRENT_SETTINGS, &mut dm) == 0 {
            bail!(
                "failed to get current resolution, error {}",
                io::Error::last_os_error()
            );
        }
        let r = Resolution {
            width: dm.dmPelsWidth as _,
            height: dm.dmPelsHeight as _,
            ..Default::default()
        };
        Ok(r)
    }
}

unsafe fn try_apply_devmode(device_name: &[u16; 32], dm: &mut DEVMODEW) -> i32 {
    let mut res = ChangeDisplaySettingsExW(
        device_name.as_ptr(),
        dm,
        NULL as _,
        CDS_UPDATEREGISTRY | CDS_GLOBAL | CDS_RESET,
        NULL,
    );
    if res != DISP_CHANGE_SUCCESSFUL {
        res = ChangeDisplaySettingsExW(device_name.as_ptr(), dm, NULL as _, CDS_RESET, NULL);
    }
    res
}

unsafe fn find_best_devmode(
    device_name: &[u16; 32],
    width: u32,
    height: u32,
    cur_bpp: u32,
    cur_freq: u32,
) -> Option<DEVMODEW> {
    let mut best: Option<DEVMODEW> = None;
    let mut best_score: (u8, u8, u32) = (0, 0, 0);
    for raw in [false, true] {
        let mut num = 0u32;
        loop {
            let mut dm: DEVMODEW = std::mem::zeroed();
            dm.dmSize = std::mem::size_of::<DEVMODEW>() as _;
            let ok = if raw {
                EnumDisplaySettingsExW(device_name.as_ptr(), num, &mut dm, EDS_RAWMODE)
            } else {
                EnumDisplaySettingsW(device_name.as_ptr(), num, &mut dm)
            };
            if ok == 0 {
                break;
            }
            if dm.dmPelsWidth == width && dm.dmPelsHeight == height {
                let score = (
                    if dm.dmBitsPerPel == cur_bpp { 1 } else { 0 },
                    if dm.dmDisplayFrequency == cur_freq { 1 } else { 0 },
                    dm.dmDisplayFrequency,
                );
                if best.is_none() || score > best_score {
                    best = Some(dm);
                    best_score = score;
                }
            }
            num += 1;
        }
    }
    best
}

pub(super) fn change_resolution_directly(
    name: &str,
    width: usize,
    height: usize,
) -> ResultType<()> {
    let device_name = resolve_device_name(name);
    unsafe {
        let mut cur: DEVMODEW = std::mem::zeroed();
        cur.dmSize = std::mem::size_of::<DEVMODEW>() as _;
        let has_cur = EnumDisplaySettingsW(device_name.as_ptr(), ENUM_CURRENT_SETTINGS, &mut cur) != 0;
        let cur_bpp = if has_cur { cur.dmBitsPerPel } else { 32 };
        let cur_freq = if has_cur { cur.dmDisplayFrequency } else { 60 };

        // 1) 优先使用驱动枚举出的完整 DEVMODEW（含色深、刷新率与 RAWMODE）
        if let Some(mut matched) =
            find_best_devmode(&device_name, width as u32, height as u32, cur_bpp, cur_freq)
        {
            matched.dmFields |= DM_PELSWIDTH | DM_PELSHEIGHT | DM_BITSPERPEL | DM_DISPLAYFREQUENCY;
            if try_apply_devmode(&device_name, &mut matched) == DISP_CHANGE_SUCCESSFUL {
                return Ok(());
            }
        }

        // 2) 继承当前色深与刷新率，直接覆写目标宽高
        if has_cur {
            let mut dm = cur;
            dm.dmPelsWidth = width as _;
            dm.dmPelsHeight = height as _;
            dm.dmFields = DM_PELSWIDTH | DM_PELSHEIGHT | DM_BITSPERPEL | DM_DISPLAYFREQUENCY;
            if try_apply_devmode(&device_name, &mut dm) == DISP_CHANGE_SUCCESSFUL {
                return Ok(());
            }
        }

        // 3) 最小字段兜底（仅宽高），并在最后尝试 NULL 默认设备
        let mut dm: DEVMODEW = std::mem::zeroed();
        dm.dmSize = std::mem::size_of::<DEVMODEW>() as _;
        dm.dmPelsWidth = width as _;
        dm.dmPelsHeight = height as _;
        dm.dmFields = DM_PELSHEIGHT | DM_PELSWIDTH;
        let mut res = try_apply_devmode(&device_name, &mut dm);
        if res != DISP_CHANGE_SUCCESSFUL {
            res = ChangeDisplaySettingsExW(NULL as _, &mut dm, NULL as _, CDS_RESET, NULL);
        }
        if res != DISP_CHANGE_SUCCESSFUL {
            bail!(
                "ChangeDisplaySettingsExW failed, res={}, error {}",
                res,
                io::Error::last_os_error()
            );
        }
        Ok(())
    }
}'''

assert t.count(old_block) == 1, f"{WIN}: expected 1 match for resolution block, got {t.count(old_block)}"
t = t.replace(old_block, new_block)
p.write_text(t, encoding="utf-8", newline="")

print("resolution patch v2 applied")
