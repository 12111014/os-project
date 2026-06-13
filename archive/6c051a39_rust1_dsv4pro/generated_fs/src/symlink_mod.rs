/// Thin helpers for creating and reading symlink target strings.
/// Actual inode management happens in Filesystem; this module is a
/// lightweight wrapper that keeps symlink logic in one place.

/// Maximum symlink target length (4096 bytes).
pub const MAX_SYMLINK_TARGET: usize = 4096;

/// Validate and normalize a symlink target.
/// Returns Ok(target) or Err(errno).
pub fn validate_target(target: &str) -> Result<&str, i32> {
    if target.is_empty() {
        return Err(-libc::ENOENT);
    }
    if target.len() > MAX_SYMLINK_TARGET {
        return Err(-libc::ENAMETOOLONG);
    }
    Ok(target)
}

/// Build the target string stored in a symlink inode.
pub fn build_target(target: &str) -> String {
    target.to_string()
}
