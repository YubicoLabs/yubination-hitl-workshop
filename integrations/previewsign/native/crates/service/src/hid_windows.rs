//! Windows-specific FIDO HID device enumeration using native SetupDi + HID APIs.
//!
//! The `hidapi` crate's C library opens devices with zero access rights during
//! `hid_enumerate`, which causes `HidD_GetPreparsedData` to fail — leaving
//! `usage_page = 0` and filtering out FIDO devices. This module opens devices
//! with `GENERIC_READ` so capability queries succeed.

#![cfg(windows)]

use log::{debug, warn};
use std::mem;
use std::ptr;

use windows::Win32::Devices::DeviceAndDriverInstallation::{
    DIGCF_DEVICEINTERFACE, DIGCF_PRESENT, SP_DEVICE_INTERFACE_DATA,
    SP_DEVICE_INTERFACE_DETAIL_DATA_W, SetupDiDestroyDeviceInfoList, SetupDiEnumDeviceInterfaces,
    SetupDiGetClassDevsW, SetupDiGetDeviceInterfaceDetailW,
};
use windows::core::GUID;

use yubikit::core::Version;
use yubikit::platform::hidapi::FidoDeviceInfo;

const YUBICO_VID: u16 = 0x1050;
const FIDO_USAGE_PAGE: u16 = 0xF1D0;
const FIDO_USAGE: u16 = 0x0001;

// Raw Win32 HID API types and FFI — avoids windows crate version-dependent
// wrappers for HID functions. Matches the approach used by authenticator-rs.

type HANDLE = *mut std::ffi::c_void;
type BOOLEAN = u8;
type NTSTATUS = i32;
type DWORD = u32;

const INVALID_HANDLE_VALUE: HANDLE = -1isize as HANDLE;
const GENERIC_READ: DWORD = 0x80000000;
const FILE_SHARE_READ: DWORD = 0x00000001;
const FILE_SHARE_WRITE: DWORD = 0x00000002;
const OPEN_EXISTING: DWORD = 3;
const HIDP_STATUS_SUCCESS: NTSTATUS = 0x0011_0000;

type PHIDP_PREPARSED_DATA = *mut std::ffi::c_void;

#[repr(C)]
struct HIDD_ATTRIBUTES {
    size: DWORD,
    vendor_id: u16,
    product_id: u16,
    version_number: u16,
}

#[repr(C)]
#[derive(Default)]
struct HIDP_CAPS {
    usage: u16,
    usage_page: u16,
    input_report_byte_length: u16,
    output_report_byte_length: u16,
    feature_report_byte_length: u16,
    reserved: [u16; 17],
    number_link_collection_nodes: u16,
    number_input_button_caps: u16,
    number_input_value_caps: u16,
    number_input_data_indices: u16,
    number_output_button_caps: u16,
    number_output_value_caps: u16,
    number_output_data_indices: u16,
    number_feature_button_caps: u16,
    number_feature_value_caps: u16,
    number_feature_data_indices: u16,
}

#[link(name = "hid")]
extern "system" {
    fn HidD_GetHidGuid(hid_guid: *mut GUID);
    fn HidD_GetAttributes(hid_device_object: HANDLE, attributes: *mut HIDD_ATTRIBUTES) -> BOOLEAN;
    fn HidD_GetPreparsedData(
        hid_device_object: HANDLE,
        preparsed_data: *mut PHIDP_PREPARSED_DATA,
    ) -> BOOLEAN;
    fn HidD_FreePreparsedData(preparsed_data: PHIDP_PREPARSED_DATA) -> BOOLEAN;
    fn HidP_GetCaps(
        preparsed_data: PHIDP_PREPARSED_DATA,
        capabilities: *mut HIDP_CAPS,
    ) -> NTSTATUS;
}

#[link(name = "kernel32")]
extern "system" {
    fn CreateFileW(
        file_name: *const u16,
        desired_access: DWORD,
        share_mode: DWORD,
        security_attributes: *const std::ffi::c_void,
        creation_disposition: DWORD,
        flags_and_attributes: DWORD,
        template_file: HANDLE,
    ) -> HANDLE;
    fn CloseHandle(handle: HANDLE) -> i32;
}

/// Enumerate Yubico FIDO HID devices using Windows SetupDi + HID APIs.
///
/// Opens each HID device with `GENERIC_READ` to reliably query usage page/usage
/// via `HidD_GetPreparsedData` + `HidP_GetCaps`.
pub fn list_fido_devices_native() -> Vec<FidoDeviceInfo> {
    let mut devices = Vec::new();

    let mut hid_guid = GUID::default();
    unsafe { HidD_GetHidGuid(&mut hid_guid) };

    let dev_info = unsafe {
        SetupDiGetClassDevsW(
            Some(&hid_guid),
            None,
            None,
            DIGCF_DEVICEINTERFACE | DIGCF_PRESENT,
        )
    };

    let dev_info = match dev_info {
        Ok(h) => h,
        Err(e) => {
            warn!("SetupDiGetClassDevsW failed: {e}");
            return devices;
        }
    };

    let mut index: u32 = 0;
    loop {
        let mut iface_data = SP_DEVICE_INTERFACE_DATA {
            cbSize: mem::size_of::<SP_DEVICE_INTERFACE_DATA>() as u32,
            ..Default::default()
        };

        let ok = unsafe {
            SetupDiEnumDeviceInterfaces(dev_info, None, &hid_guid, index, &mut iface_data)
        };
        if ok.is_err() {
            break;
        }
        index += 1;

        let mut required_size: u32 = 0;
        let _ = unsafe {
            SetupDiGetDeviceInterfaceDetailW(
                dev_info,
                &iface_data,
                None,
                0,
                Some(&mut required_size),
                None,
            )
        };

        if required_size == 0 {
            continue;
        }

        let mut buf = vec![0u8; required_size as usize];
        let detail = buf.as_mut_ptr() as *mut SP_DEVICE_INTERFACE_DETAIL_DATA_W;
        unsafe {
            (*detail).cbSize = mem::size_of::<SP_DEVICE_INTERFACE_DETAIL_DATA_W>() as u32;
        }

        let ok = unsafe {
            SetupDiGetDeviceInterfaceDetailW(
                dev_info,
                &iface_data,
                Some(detail),
                required_size,
                None,
                None,
            )
        };

        if ok.is_err() {
            continue;
        }

        let path = unsafe {
            let path_ptr = (*detail).DevicePath.as_ptr();
            let path_bytes = required_size as usize
                - mem::offset_of!(SP_DEVICE_INTERFACE_DETAIL_DATA_W, DevicePath);
            let path_len = path_bytes / mem::size_of::<u16>();
            let slice = std::slice::from_raw_parts(path_ptr, path_len);
            let len = slice.iter().position(|&c| c == 0).unwrap_or(path_len);
            String::from_utf16_lossy(&slice[..len])
        };

        if let Some(info) = probe_fido_device(&path) {
            debug!(
                "Found FIDO device via native enumeration: path={}, pid={:#06x}",
                info.path, info.pid
            );
            devices.push(info);
        }
    }

    unsafe {
        let _ = SetupDiDestroyDeviceInfoList(dev_info);
    }

    devices
}

/// Open a HID device path with GENERIC_READ and check if it is a Yubico FIDO device.
fn probe_fido_device(path: &str) -> Option<FidoDeviceInfo> {
    let wide_path: Vec<u16> = path.encode_utf16().chain(std::iter::once(0)).collect();

    let handle = unsafe {
        CreateFileW(
            wide_path.as_ptr(),
            GENERIC_READ,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            ptr::null(),
            OPEN_EXISTING,
            0,
            ptr::null_mut(),
        )
    };

    if handle == INVALID_HANDLE_VALUE {
        return None;
    }

    let result = check_fido_device(handle, path);

    unsafe {
        CloseHandle(handle);
    }

    result
}

fn check_fido_device(handle: HANDLE, path: &str) -> Option<FidoDeviceInfo> {
    let mut attrib = HIDD_ATTRIBUTES {
        size: mem::size_of::<HIDD_ATTRIBUTES>() as DWORD,
        vendor_id: 0,
        product_id: 0,
        version_number: 0,
    };

    if unsafe { HidD_GetAttributes(handle, &mut attrib) } == 0 {
        return None;
    }

    if attrib.vendor_id != YUBICO_VID {
        return None;
    }

    let mut pp_data: PHIDP_PREPARSED_DATA = ptr::null_mut();
    if unsafe { HidD_GetPreparsedData(handle, &mut pp_data) } == 0 || pp_data.is_null() {
        return None;
    }

    let mut caps = HIDP_CAPS::default();
    let status = unsafe { HidP_GetCaps(pp_data, &mut caps) };
    unsafe {
        HidD_FreePreparsedData(pp_data);
    }

    if status != HIDP_STATUS_SUCCESS {
        return None;
    }

    if caps.usage_page != FIDO_USAGE_PAGE || caps.usage != FIDO_USAGE {
        return None;
    }

    Some(FidoDeviceInfo {
        path: path.to_string(),
        pid: attrib.product_id,
        version: Version(0, 0, 0),
        report_size_in: 64,
        report_size_out: 64,
    })
}
