fn main() {
    // Embed Info.plist in the Mach-O binary so AppKit can find bundle metadata.
    // Without this, NSAlert and NSWindow crash because they need CFBundleGetValueForInfoKey.
    #[cfg(target_os = "macos")]
    {
        let manifest_dir = std::env::var("CARGO_MANIFEST_DIR").unwrap();
        let plist = std::path::Path::new(&manifest_dir).join("Info.plist");
        if plist.exists() {
            println!("cargo:rustc-link-arg=-sectcreate");
            println!("cargo:rustc-link-arg=__TEXT");
            println!("cargo:rustc-link-arg=__info_plist");
            println!("cargo:rustc-link-arg={}", plist.display());
        }
    }
}
