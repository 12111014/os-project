use crate::filesystem::Filesystem;

/// Maximum path component length (255 bytes).
pub const MAX_NAME_LEN: usize = 255;

/// Validate a single path component name.
pub fn validate_name(name: &str) -> Result<(), i32> {
    if name.is_empty() {
        return Err(libc::ENOENT);
    }
    if name.len() > MAX_NAME_LEN {
        return Err(libc::ENAMETOOLONG);
    }
    if name.contains('/') {
        return Err(libc::EINVAL);
    }
    if name == "." || name == ".." {
        return Err(libc::EINVAL);
    }
    Ok(())
}

/// Split "/a/b/c" into parent "/a/b" and base name "c". Root returns parent "/", base "".
pub fn split_path(path: &str) -> (&str, &str) {
    if path == "/" {
        return ("/", "");
    }
    let trimmed = path.trim_end_matches('/');
    if trimmed.is_empty() {
        return ("/", "");
    }
    match trimmed.rfind('/') {
        Some(pos) => {
            let parent = if pos == 0 { "/" } else { &trimmed[..pos] };
            let base = &trimmed[pos + 1..];
            (parent, base)
        }
        None => ("/", trimmed),
    }
}

/// Resolve a path to an inode number. Follows symlinks (up to 40 hops).
pub fn resolve(fs: &Filesystem, path: &str) -> Result<u64, i32> {
    if path == "/" {
        return Ok(1);
    }
    let parts = path
        .split('/')
        .filter(|s| !s.is_empty())
        .collect::<Vec<&str>>();

    let mut ino: u64 = 1; // root
    let mut symlink_hops = 0;
    let mut i = 0;

    while i < parts.len() {
        let component = parts[i];
        let dir = fs.dirs.get(&ino).ok_or(libc::ENOENT)?;
        let child_ino = dir.lookup(component).ok_or(libc::ENOENT)?;
        let child = fs.inodes.get(&child_ino).ok_or(libc::ENOENT)?;

        if child.is_symlink() {
            symlink_hops += 1;
            if symlink_hops > 40 {
                return Err(libc::ELOOP);
            }
            let target = match &child.data {
                crate::inode::InodeData::Symlink(t) => t.clone(),
                _ => unreachable!(),
            };
            // Resolve target relative to current directory
            let target_parts: Vec<&str> = target
                .split('/')
                .filter(|s| !s.is_empty())
                .collect();
            if target.starts_with('/') {
                ino = 1;
                i = 0;
                // Replace remaining parts with target_parts
                // We need to build a new full path. Instead, restart resolution
                // by resolving the target from root.
                let resolved = resolve(fs, &target)?;
                // Now resolve remaining original components from resolved
                if i + 1 >= parts.len() {
                    return Ok(resolved);
                }
                // resolve from resolved + remaining parts
                // We'll reconstruct: use a fresh resolve for the joined path
                let remaining = parts[i + 1..].join("/");
                let new_path = if remaining.is_empty() {
                    target
                } else if target.ends_with('/') {
                    format!("{}{}", target, remaining)
                } else {
                    format!("{}/{}", target, remaining)
                };
                return resolve(fs, &new_path);
            } else {
                // Relative symlink; replace current component with target
                i += 1;
                // We need to insert target_parts before remaining original parts
                let mut new_parts: Vec<&str> = parts[..i].to_vec(); // includes current component? No, already advanced i
                // Actually, we've consumed the symlink component. The target parts
                // should be inserted, then remaining original parts.
                // Simplify: build full remaining path
                let remaining = parts[i..].join("/");
                let new_path = if target.ends_with('/') {
                    format!("{}{}", target, remaining)
                } else {
                    format!("{}/{}", target, remaining)
                };
                // Resolve from current directory (not root)
                // We need the directory that contains the symlink
                // Reconstruct parent path
                let parent_path = parts[..i - 1].join("/");
                let parent_path = if parent_path.is_empty() {
                    "/".to_string()
                } else {
                    format!("/{}", parent_path)
                };
                let full_new = if target.starts_with('/') {
                    // Actually we already said relative, so skip this branch
                    new_path
                } else {
                    if parent_path == "/" {
                        format!("/{}", new_path)
                    } else {
                        format!("{}/{}", parent_path, new_path)
                    }
                };
                return resolve(fs, &full_new);
            }
        }

        ino = child_ino;
        i += 1;
    }

    Ok(ino)
}

/// Resolve parent directory and return (parent_ino, basename).
pub fn resolve_parent(fs: &Filesystem, path: &str) -> Result<(u64, String), i32> {
    let (parent_path, base) = split_path(path);
    if base.is_empty() {
        return Err(libc::ENOENT);
    }
    validate_name(base)?;
    let parent_ino = resolve(fs, parent_path)?;
    // Make sure parent is a directory
    let parent = fs.inodes.get(&parent_ino).ok_or(libc::ENOENT)?;
    if !parent.is_dir() {
        return Err(libc::ENOTDIR);
    }
    Ok((parent_ino, base.to_string()))
}
