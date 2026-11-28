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

# ---------------------------------------------------------------------------
# 4. src/virtual_display_manager.rs — Amyuni 虚拟显示器动态分辨率回退
#    当物理/基础显示驱动（如 Microsoft Basic Display Driver）拒绝切换分辨率
#    （DISP_CHANGE_BADMODE）时，自动安装/挂载 WHQL 签名的 Amyuni 虚拟显示器，
#    将目标分辨率写入 WUDF\Services\usbmmIdd\Parameters\Monitors 注册表，
#    应用目标分辨率并设为主屏；若原屏为 Microsoft Basic Display Driver 则将其分离。
# ---------------------------------------------------------------------------
VDM = Path("src/virtual_display_manager.rs")
t = VDM.read_text(encoding="utf-8")

old_vdm_amyuni = '''    #[inline]
    pub fn is_my_display(name: &str) -> bool {
        windows::get_device_names(Some(super::AMYUNI_IDD_DEVICE_STRING))
            .iter()
            .any(|s| windows::is_device_name(s, name))
    }
}'''

new_vdm_amyuni = '''    #[inline]
    pub fn is_my_display(name: &str) -> bool {
        windows::get_device_names(Some(super::AMYUNI_IDD_DEVICE_STRING))
            .iter()
            .any(|s| windows::is_device_name(s, name))
    }

    lazy_static::lazy_static! {
        static ref RES_FALLBACK_LOCK: Mutex<()> = Mutex::new(());
    }

    const MONITORS_REG_PATH: &str =
        r#"SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\WUDF\\Services\\usbmmIdd\\Parameters\\Monitors"#;

    const DEFAULT_MONITOR_POOL: [(usize, usize); 10] = [
        (2560, 1600),
        (1920, 1200),
        (1920, 1080),
        (1680, 1050),
        (1600, 1200),
        (1440, 900),
        (1280, 1024),
        (1280, 800),
        (1280, 720),
        (1024, 768),
    ];

    fn write_monitors_reg(width: usize, height: usize) -> ResultType<()> {
        let hklm = winreg::RegKey::predef(winreg::enums::HKEY_LOCAL_MACHINE);
        let (key, _) = hklm.create_subkey(MONITORS_REG_PATH)?;
        let target = format!("{},{}", width, height);
        key.set_value("", &target)?;
        key.set_value("0", &target)?;
        let mut slot = 1usize;
        for &(pw, ph) in DEFAULT_MONITOR_POOL.iter() {
            if pw == width && ph == height {
                continue;
            }
            if slot > 9 {
                break;
            }
            key.set_value(&slot.to_string(), &format!("{},{}", pw, ph))?;
            slot += 1;
        }
        Ok(())
    }

    fn plug_in_monitor_raw(wait_timeout: Option<Duration>) -> ResultType<()> {
        let timeout = Duration::from_secs(4);
        let now = Instant::now();
        loop {
            match plug_monitor_(true, wait_timeout) {
                Ok(_) => return Ok(()),
                Err(e) => {
                    if now.elapsed() < timeout {
                        std::thread::sleep(Duration::from_millis(150));
                        continue;
                    }
                    return Err(e.into());
                }
            }
        }
    }

    fn wait_amyuni_device(timeout: Duration) -> Option<String> {
        let start = Instant::now();
        while start.elapsed() < timeout {
            let devs = windows::get_device_names(Some(super::AMYUNI_IDD_DEVICE_STRING));
            if let Some(d) = devs.into_iter().next() {
                return Some(d.trim_end_matches('\\0').to_string());
            }
            std::thread::sleep(Duration::from_millis(100));
        }
        None
    }

    pub fn ensure_resolution_via_virtual_display(
        orig_name: &str,
        width: usize,
        height: usize,
    ) -> ResultType<String> {
        let _guard = RES_FALLBACK_LOCK.lock().unwrap();

        let mut is_async = false;
        if let Err(e) = check_install_driver(&mut is_async) {
            bail!("Failed to install Amyuni virtual display driver: {}", e);
        }
        if is_async {
            std::thread::sleep(Duration::from_millis(1200));
        }

        if let Err(e) = write_monitors_reg(width, height) {
            log::warn!(
                "Failed to write usbmmIdd Monitors registry for {}x{}: {:?}",
                width,
                height,
                e
            );
        }

        let orig_is_basic = windows::get_device_string(orig_name)
            .map(|s| s.to_ascii_lowercase().contains("microsoft basic display"))
            .unwrap_or(false);

        let existing = windows::get_device_names(Some(super::AMYUNI_IDD_DEVICE_STRING));
        let mut vdev_opt: Option<String> = None;

        if let Some(first) = existing.into_iter().next() {
            let clean = first.trim_end_matches('\\0').to_string();
            if crate::platform::change_resolution(&clean, width, height).is_ok() {
                vdev_opt = Some(clean);
            } else {
                // 目标分辨率不在当前已挂载虚拟显示器的 10 槽列表内：热拔插一次以重载注册表
                let _ = plug_monitor_(false, Some(Duration::from_millis(1500)));
                std::thread::sleep(Duration::from_millis(300));
                plug_in_monitor_raw(Some(Duration::from_millis(3_000)))?;
                vdev_opt = wait_amyuni_device(Duration::from_millis(3_500));
            }
        } else {
            plug_in_monitor_raw(Some(Duration::from_millis(3_000)))?;
            vdev_opt = wait_amyuni_device(Duration::from_millis(3_500));
        }

        let Some(vdev) = vdev_opt else {
            bail!("Amyuni virtual display device did not appear after plug-in");
        };

        // 等待 WDDM 完成模式初始化并显式应用目标分辨率
        let mut applied = false;
        for _ in 0..8 {
            if crate::platform::change_resolution(&vdev, width, height).is_ok() {
                applied = true;
                break;
            }
            std::thread::sleep(Duration::from_millis(200));
        }
        if !applied {
            log::warn!(
                "Explicit change_resolution on virtual display '{}' to {}x{} did not return Ok; continuing with topology promote",
                &vdev,
                width,
                height
            );
        }

        // 若原屏为 Microsoft Basic Display Driver 且与虚拟屏不同，则将虚拟屏设为主屏并分离原基础驱动屏
        let orig_clean = orig_name.trim_end_matches('\\0');
        if orig_is_basic && !orig_clean.eq_ignore_ascii_case(&vdev) {
            windows::promote_display_and_maybe_detach(&vdev, Some(orig_clean), width as u32, height as u32);
        } else if !orig_clean.eq_ignore_ascii_case(&vdev) {
            windows::promote_display_and_maybe_detach(&vdev, None, width as u32, height as u32);
        }

        Ok(vdev)
    }
}'''

assert t.count(old_vdm_amyuni) == 1, f"{VDM}: expected 1 match for is_my_display end, got {t.count(old_vdm_amyuni)}"
t = t.replace(old_vdm_amyuni, new_vdm_amyuni)

old_vdm_win_end = '''        display_drivers
    }
}'''

new_vdm_win_end = '''        display_drivers
    }

    pub(super) fn get_device_string(name: &str) -> Option<String> {
        let mut dd: DISPLAY_DEVICEW = unsafe { std::mem::zeroed() };
        dd.cb = std::mem::size_of::<DISPLAY_DEVICEW>() as DWORD;
        let mut i_dev_num = 0;
        loop {
            let result = unsafe { EnumDisplayDevicesW(null_mut(), i_dev_num, &mut dd, 0) };
            if result == 0 {
                break;
            }
            i_dev_num += 1;
            if let (Ok(device_name), Ok(ds)) = (
                String::from_utf16(&dd.DeviceName),
                String::from_utf16(&dd.DeviceString),
            ) {
                let dn_clean = device_name.trim_end_matches('\\0');
                let target_clean = name.trim_end_matches('\\0');
                if dn_clean.eq_ignore_ascii_case(target_clean) {
                    return Some(ds.trim_end_matches('\\0').to_string());
                }
            }
        }
        None
    }

    pub(super) fn promote_display_and_maybe_detach(
        primary_name: &str,
        detach_name: Option<&str>,
        width: u32,
        height: u32,
    ) {
        use std::ffi::OsStr;
        use std::os::windows::ffi::OsStrExt;
        use winapi::um::winuser::ChangeDisplaySettingsExW;

        const CDS_UPDATEREGISTRY_FLAG: DWORD = 0x00000001;
        const CDS_SET_PRIMARY_FLAG: DWORD = 0x00000010;
        const CDS_RESET_FLAG: DWORD = 0x40000000;
        const CDS_NORESET_FLAG: DWORD = 0x10000000;
        const DM_POSITION_FLAG: DWORD = 0x00000020;
        const DM_PELSWIDTH_FLAG: DWORD = 0x00080000;
        const DM_PELSHEIGHT_FLAG: DWORD = 0x00100000;
        const DISP_CHANGE_OK: i32 = 0;

        let primary_w: Vec<u16> = OsStr::new(primary_name)
            .encode_wide()
            .chain(std::iter::once(0))
            .collect();

        unsafe {
            let mut dm_primary: DEVMODEW = std::mem::zeroed();
            dm_primary.dmSize = std::mem::size_of::<DEVMODEW>() as _;
            dm_primary.dmFields = DM_POSITION_FLAG | DM_PELSWIDTH_FLAG | DM_PELSHEIGHT_FLAG;
            dm_primary.dmPelsWidth = width;
            dm_primary.dmPelsHeight = height;

            if let Some(detach) = detach_name {
                let detach_w: Vec<u16> = OsStr::new(detach)
                    .encode_wide()
                    .chain(std::iter::once(0))
                    .collect();
                let mut dm_detach: DEVMODEW = std::mem::zeroed();
                dm_detach.dmSize = std::mem::size_of::<DEVMODEW>() as _;
                dm_detach.dmFields = DM_POSITION_FLAG | DM_PELSWIDTH_FLAG | DM_PELSHEIGHT_FLAG;
                // dmPelsWidth = 0, dmPelsHeight = 0 => detach from desktop

                let r1 = ChangeDisplaySettingsExW(
                    primary_w.as_ptr(),
                    &mut dm_primary,
                    null_mut(),
                    CDS_SET_PRIMARY_FLAG | CDS_UPDATEREGISTRY_FLAG | CDS_NORESET_FLAG,
                    null_mut(),
                );
                let r2 = ChangeDisplaySettingsExW(
                    detach_w.as_ptr(),
                    &mut dm_detach,
                    null_mut(),
                    CDS_UPDATEREGISTRY_FLAG | CDS_NORESET_FLAG,
                    null_mut(),
                );
                let r3 = ChangeDisplaySettingsExW(
                    std::ptr::null(),
                    null_mut(),
                    null_mut(),
                    0,
                    null_mut(),
                );
                if r1 == DISP_CHANGE_OK && r2 == DISP_CHANGE_OK && r3 == DISP_CHANGE_OK {
                    return;
                }
            }

            // 兜底：至少将虚拟显示器设为主屏并应用目标宽高
            let _ = ChangeDisplaySettingsExW(
                primary_w.as_ptr(),
                &mut dm_primary,
                null_mut(),
                CDS_SET_PRIMARY_FLAG | CDS_UPDATEREGISTRY_FLAG | CDS_RESET_FLAG,
                null_mut(),
            );
        }
    }
}'''

assert t.count(old_vdm_win_end) == 1, f"{VDM}: expected 1 match for windows mod end, got {t.count(old_vdm_win_end)}"
t = t.replace(old_vdm_win_end, new_vdm_win_end)
VDM.write_text(t, encoding="utf-8", newline="")

# ---------------------------------------------------------------------------
# 5. src/server/connection.rs — 分辨率切换失败时自动触发 Amyuni 虚拟显示器回退
#    + 被控端按控制端 ID (self.lr.my_id) 持久化记录生效分辨率并在下次同控制端连入时自动恢复
# ---------------------------------------------------------------------------
CONN = Path("src/server/connection.rs")
t = CONN.read_text(encoding="utf-8")

old_conn_sub = '''        } else if sub_service {
            if !wait_session_id_confirm {
                self.try_sub_monitor_services();
            }
        }'''

new_conn_sub = '''        } else if sub_service {
            if !wait_session_id_confirm {
                self.try_sub_monitor_services();
                #[cfg(not(any(target_os = "android", target_os = "ios")))]
                self.apply_saved_controller_resolution();
            }
        }'''

assert t.count(old_conn_sub) == 1, f"{CONN}: expected 1 match for try_sub_monitor_services block, got {t.count(old_conn_sub)}"
t = t.replace(old_conn_sub, new_conn_sub)

old_conn_cr = '''    #[cfg(not(any(target_os = "android", target_os = "ios")))]
    fn change_resolution(&mut self, d: Option<usize>, r: &Resolution) {
        if self.keyboard {
            if let Ok(displays) = display_service::try_get_displays() {
                let display_idx = d.unwrap_or(self.display_idx);
                if let Some(display) = displays.get(display_idx) {
                    let name = display.name();
                    #[cfg(windows)]
                    if let Some(_ok) =
                        virtual_display_manager::rustdesk_idd::change_resolution_if_is_virtual_display(
                            &name,
                            r.width as _,
                            r.height as _,
                        )
                    {
                        return;
                    }
                    #[allow(unused_mut)]
                    let mut record_changed = true;
                    #[cfg(windows)]
                    if virtual_display_manager::amyuni_idd::is_my_display(&name) {
                        record_changed = false;
                    }
                    #[cfg(not(target_os = "macos"))]
                    let scale = 1.0;
                    #[cfg(target_os = "macos")]
                    let scale = display.scale();
                    let original = (
                        ((display.width() as f64) / scale).round() as _,
                        (display.height() as f64 / scale).round() as _,
                    );
                    if record_changed {
                        display_service::set_last_changed_resolution(
                            &name,
                            original,
                            (r.width, r.height),
                        );
                    }
                    if let Err(e) =
                        crate::platform::change_resolution(&name, r.width as _, r.height as _)
                    {
                        log::error!(
                            "Failed to change resolution '{}' to ({},{}): {:?}",
                            &name,
                            r.width,
                            r.height,
                            e
                        );
                    }
                }
            }
        }
    }'''

new_conn_cr = '''    #[cfg(not(any(target_os = "android", target_os = "ios")))]
    fn hntom_peer_resolutions_path() -> Option<std::path::PathBuf> {
        hbb_common::config::Config::file()
            .parent()
            .map(|p| p.join("hntom_peer_resolutions.json"))
    }

    #[cfg(not(any(target_os = "android", target_os = "ios")))]
    fn load_controller_resolution(peer_id: &str) -> Option<(i32, i32)> {
        if peer_id.is_empty() {
            return None;
        }
        let path = Self::hntom_peer_resolutions_path()?;
        let data = std::fs::read_to_string(path).ok()?;
        let map: std::collections::HashMap<String, [i32; 2]> =
            serde_json::from_str(&data).ok()?;
        map.get(peer_id)
            .copied()
            .filter(|&[w, h]| w > 0 && h > 0)
            .map(|[w, h]| (w, h))
    }

    #[cfg(not(any(target_os = "android", target_os = "ios")))]
    fn save_controller_resolution(peer_id: &str, width: i32, height: i32) {
        lazy_static::lazy_static! {
            static ref RES_STORE_LOCK: Mutex<()> = Mutex::new(());
        }
        if peer_id.is_empty() || width <= 0 || height <= 0 {
            return;
        }
        let Some(path) = Self::hntom_peer_resolutions_path() else {
            return;
        };
        let _guard = RES_STORE_LOCK.lock().unwrap();
        let mut map: std::collections::HashMap<String, [i32; 2]> = std::fs::read_to_string(&path)
            .ok()
            .and_then(|s| serde_json::from_str(&s).ok())
            .unwrap_or_default();
        if map.get(peer_id) == Some(&[width, height]) {
            return;
        }
        map.insert(peer_id.to_string(), [width, height]);
        if let Some(parent) = path.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        if let Ok(json) = serde_json::to_string_pretty(&map) {
            let tmp = path.with_extension("json.tmp");
            if std::fs::write(&tmp, &json).is_ok() {
                if std::fs::rename(&tmp, &path).is_err() {
                    let _ = std::fs::write(&path, &json);
                    let _ = std::fs::remove_file(&tmp);
                }
            } else {
                let _ = std::fs::write(&path, &json);
            }
            log::info!(
                "Saved controller '{}' resolution ({},{}) to {:?}",
                peer_id,
                width,
                height,
                path
            );
        }
    }

    #[cfg(not(any(target_os = "android", target_os = "ios")))]
    fn apply_saved_controller_resolution(&mut self) {
        if !self.is_remote() || !self.keyboard || self.lr.my_id.is_empty() {
            return;
        }
        let Some((w, h)) = Self::load_controller_resolution(&self.lr.my_id) else {
            return;
        };
        log::info!(
            "Auto-applying saved resolution ({},{}) for returning controller '{}'",
            w,
            h,
            &self.lr.my_id
        );
        self.change_resolution(
            None,
            &Resolution {
                width: w,
                height: h,
                ..Default::default()
            },
        );
    }

    #[cfg(not(any(target_os = "android", target_os = "ios")))]
    fn change_resolution(&mut self, d: Option<usize>, r: &Resolution) {
        if self.keyboard {
            if let Ok(displays) = display_service::try_get_displays() {
                let display_idx = d.unwrap_or(self.display_idx);
                if let Some(display) = displays.get(display_idx) {
                    let name = display.name();
                    if r.width > 0
                        && r.height > 0
                        && display.width() as i32 == r.width
                        && display.height() as i32 == r.height
                    {
                        Self::save_controller_resolution(&self.lr.my_id, r.width, r.height);
                        return;
                    }
                    #[cfg(windows)]
                    if let Some(ok) =
                        virtual_display_manager::rustdesk_idd::change_resolution_if_is_virtual_display(
                            &name,
                            r.width as _,
                            r.height as _,
                        )
                    {
                        if ok {
                            Self::save_controller_resolution(&self.lr.my_id, r.width, r.height);
                        }
                        return;
                    }
                    #[allow(unused_mut)]
                    let mut record_changed = true;
                    #[cfg(windows)]
                    if virtual_display_manager::amyuni_idd::is_my_display(&name) {
                        record_changed = false;
                    }
                    #[cfg(not(target_os = "macos"))]
                    let scale = 1.0;
                    #[cfg(target_os = "macos")]
                    let scale = display.scale();
                    let original = (
                        ((display.width() as f64) / scale).round() as _,
                        (display.height() as f64 / scale).round() as _,
                    );
                    if record_changed {
                        display_service::set_last_changed_resolution(
                            &name,
                            original,
                            (r.width, r.height),
                        );
                    }
                    match crate::platform::change_resolution(&name, r.width as _, r.height as _) {
                        Ok(()) => {
                            Self::save_controller_resolution(&self.lr.my_id, r.width, r.height);
                        }
                        Err(e) => {
                            log::error!(
                                "Failed to change resolution '{}' to ({},{}): {:?}",
                                &name,
                                r.width,
                                r.height,
                                e
                            );
                            #[cfg(windows)]
                            if virtual_display_manager::is_virtual_display_supported() {
                                log::info!(
                                    "Fallback to Amyuni virtual display for resolution ({},{}) from '{}'",
                                    r.width,
                                    r.height,
                                    &name
                                );
                                match virtual_display_manager::amyuni_idd::ensure_resolution_via_virtual_display(
                                    &name,
                                    r.width as _,
                                    r.height as _,
                                ) {
                                    Ok(vdev) => {
                                        log::info!(
                                            "Virtual display '{}' activated at ({},{})",
                                            &vdev,
                                            r.width,
                                            r.height
                                        );
                                        Self::save_controller_resolution(
                                            &self.lr.my_id,
                                            r.width,
                                            r.height,
                                        );
                                        let _ = display_service::check_displays_changed();
                                        if let Ok(new_displays) = display_service::try_get_displays()
                                        {
                                            if let Some(new_idx) = new_displays.iter().position(|disp| {
                                                disp.name()
                                                    .trim_end_matches('\\0')
                                                    .eq_ignore_ascii_case(
                                                        vdev.trim_end_matches('\\0'),
                                                    )
                                            }) {
                                                if let Some(server) = self.server.upgrade() {
                                                    let _ = self.switch_display_to(new_idx, server);
                                                }
                                            }
                                        }
                                        self.refresh_video_display(None);
                                    }
                                    Err(ve) => {
                                        log::error!(
                                            "Fallback to Amyuni virtual display failed for ({},{}): {:?}",
                                            r.width,
                                            r.height,
                                            ve
                                        );
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }'''

assert t.count(old_conn_cr) == 1, f"{CONN}: expected 1 match for change_resolution fn, got {t.count(old_conn_cr)}"
t = t.replace(old_conn_cr, new_conn_cr)
CONN.write_text(t, encoding="utf-8", newline="")

# ---------------------------------------------------------------------------
# 6. src/ui_session_interface.rs — 控制端记录生效分辨率并重连自动恢复
#    - 延长生效确认窗口至 30 秒（覆盖首次虚拟显示器挂载）
#    - 不再因 original_resolution 相同或显示索引变化而误清 custom_resolutions
#    - 支持通过 PeerInfo.displays 更新确认生效并落盘到 PeerConfig.custom_resolutions
#    - 重连时优先匹配当前 display，回退 display 0；若当前分辨率已一致则跳过
# ---------------------------------------------------------------------------
UISI = Path("src/ui_session_interface.rs")
t = UISI.read_text(encoding="utf-8")

old_timeout = 'const CHANGE_RESOLUTION_VALID_TIMEOUT_SECS: u64 = 15;'
new_timeout = 'const CHANGE_RESOLUTION_VALID_TIMEOUT_SECS: u64 = 30;'
assert t.count(old_timeout) == 1, f"{UISI}: expected 1 match for CHANGE_RESOLUTION_VALID_TIMEOUT_SECS"
t = t.replace(old_timeout, new_timeout)

old_uisi_res = '''    fn set_custom_resolution(&self, display: &SwitchDisplay) {
        if display.width == display.original_resolution.width
            && display.height == display.original_resolution.height
        {
            self.lc
                .write()
                .unwrap()
                .set_custom_resolution(display.display, None);
        } else {
            let last_change_display = self.last_change_display.lock().unwrap();
            if last_change_display.display == display.display {
                let wh = if last_change_display.is_the_same_record(
                    display.display,
                    display.width,
                    display.height,
                ) {
                    Some((display.width, display.height))
                } else {
                    // display origin is changed, or some other events.
                    None
                };
                self.lc
                    .write()
                    .unwrap()
                    .set_custom_resolution(display.display, wh);
            }
        }
    }

    #[inline]
    pub fn handle_peer_switch_display(&self, display: &SwitchDisplay) {
        self.ui_handler.switch_display(display);
        self.set_custom_resolution(display);
    }

    #[inline]
    pub fn change_resolution(&self, display: i32, width: i32, height: i32) {
        *self.last_change_display.lock().unwrap() =
            ChangeDisplayRecord::new(display, width, height);
        self.do_change_resolution(display, width, height);
    }

    #[inline]
    fn try_change_init_resolution(&self, display: i32) {
        let Some((w, h)) = self.lc.read().unwrap().get_custom_resolution(display) else {
            return;
        };
        self.change_resolution(display, w, h);
    }'''

new_uisi_res = '''    fn persist_confirmed_resolution(&self, display: i32, width: i32, height: i32) {
        if width <= 0 || height <= 0 {
            return;
        }
        let mut lc = self.lc.write().unwrap();
        lc.set_custom_resolution(display, Some((width, height)));
        if display != 0 {
            lc.set_custom_resolution(0, Some((width, height)));
        }
        log::info!(
            "Persisted confirmed custom resolution ({},{}) for display {}",
            width,
            height,
            display
        );
    }

    fn set_custom_resolution(&self, display: &SwitchDisplay) {
        let matched = {
            let last = self.last_change_display.lock().unwrap();
            last.time.elapsed().as_secs() < CHANGE_RESOLUTION_VALID_TIMEOUT_SECS
                && last.width == display.width
                && last.height == display.height
                && display.width > 0
                && display.height > 0
        };
        if matched {
            self.persist_confirmed_resolution(display.display, display.width, display.height);
        }
    }

    pub fn confirm_resolution_from_displays(&self, displays: &[DisplayInfo]) {
        let (target_w, target_h, valid) = {
            let last = self.last_change_display.lock().unwrap();
            (
                last.width,
                last.height,
                last.time.elapsed().as_secs() < CHANGE_RESOLUTION_VALID_TIMEOUT_SECS
                    && last.width > 0
                    && last.height > 0,
            )
        };
        if !valid {
            return;
        }
        if let Some((idx, _)) = displays
            .iter()
            .enumerate()
            .find(|(_, d)| d.width == target_w && d.height == target_h)
        {
            self.persist_confirmed_resolution(idx as i32, target_w, target_h);
        }
    }

    #[inline]
    pub fn handle_peer_switch_display(&self, display: &SwitchDisplay) {
        self.ui_handler.switch_display(display);
        self.set_custom_resolution(display);
    }

    #[inline]
    pub fn change_resolution(&self, display: i32, width: i32, height: i32) {
        *self.last_change_display.lock().unwrap() =
            ChangeDisplayRecord::new(display, width, height);
        self.do_change_resolution(display, width, height);
    }

    #[inline]
    fn try_change_init_resolution(&self, display: i32) {
        let (saved, current_wh) = {
            let lc = self.lc.read().unwrap();
            let saved = lc
                .get_custom_resolution(display)
                .or_else(|| lc.get_custom_resolution(0));
            let current_wh = lc
                .peer_info
                .as_ref()
                .and_then(|pi| pi.displays.get(display as usize))
                .map(|d| (d.width, d.height));
            (saved, current_wh)
        };
        let Some((w, h)) = saved else {
            return;
        };
        if current_wh == Some((w, h)) {
            log::info!(
                "Initial display {} already at saved resolution ({},{}), skip change",
                display,
                w,
                h
            );
            return;
        }
        log::info!(
            "Auto-restoring saved custom resolution ({},{}) on display {}",
            w,
            h,
            display
        );
        self.change_resolution(display, w, h);
    }'''

assert t.count(old_uisi_res) == 1, f"{UISI}: expected 1 match for set_custom_resolution block, got {t.count(old_uisi_res)}"
t = t.replace(old_uisi_res, new_uisi_res)
UISI.write_text(t, encoding="utf-8", newline="")

# ---------------------------------------------------------------------------
# 7. src/client/io_loop.rs — 收到 PeerInfo 显示列表更新时确认并落盘生效分辨率
# ---------------------------------------------------------------------------
IOLOOP = Path("src/client/io_loop.rs")
t = IOLOOP.read_text(encoding="utf-8")

old_ioloop_pi = '''                Some(message::Union::PeerInfo(pi)) => {
                    self.handler.set_displays(&pi.displays);
                    self.handler.set_platform_additions(&pi.platform_additions);
                }'''

new_ioloop_pi = '''                Some(message::Union::PeerInfo(pi)) => {
                    self.handler.set_displays(&pi.displays);
                    self.handler.set_platform_additions(&pi.platform_additions);
                    self.handler.confirm_resolution_from_displays(&pi.displays);
                }'''

assert t.count(old_ioloop_pi) == 1, f"{IOLOOP}: expected 1 match for PeerInfo displays handler, got {t.count(old_ioloop_pi)}"
t = t.replace(old_ioloop_pi, new_ioloop_pi)
IOLOOP.write_text(t, encoding="utf-8", newline="")

print("resolution patch v4 applied")
