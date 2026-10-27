fn main() {
    // Embed an application manifest on Windows.
    // This enables ComCtl32 v6 visual styles so buttons, edit controls, etc.
    // render with the modern Windows theme instead of the classic Win95 look.
    // Also declares DPI awareness and Windows 10/11 compatibility.
    if std::env::var("CARGO_CFG_TARGET_OS").unwrap_or_default() == "windows" {
        // Resolve static imports from System32, never the writable extraction
        // directory, before main has a chance to restrict dynamic DLL loading.
        println!("cargo:rustc-link-arg=/DEPENDENTLOADFLAG:0x800");
        embed_manifest::embed_manifest_file("service.manifest")
            .expect("failed to embed manifest");
    }
}
