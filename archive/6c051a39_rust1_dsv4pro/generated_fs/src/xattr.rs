use std::collections::{BTreeMap, HashMap};

/// Extended attributes per inode: key → value.
#[derive(Debug, Clone, Default)]
pub struct XattrStore {
    /// inode number → (name → value)
    pub attrs: BTreeMap<u64, HashMap<String, Vec<u8>>>,
}

/// Maximum total size of all xattr names+values for a single inode (64 KiB).
const MAX_XATTR_TOTAL: usize = 65536;

/// Maximum length of a single xattr value (16 KiB).
const MAX_XATTR_VALUE: usize = 16384;

/// Validate the namespace prefix of an xattr name.
/// Returns true for user.*, trusted.*, security.* names.
fn valid_xattr_namespace(name: &str) -> bool {
    name.starts_with("user.")
        || name.starts_with("trusted.")
        || name.starts_with("security.")
}

impl XattrStore {
    pub fn new() -> Self {
        XattrStore {
            attrs: BTreeMap::new(),
        }
    }

    fn ensure_map(&mut self, ino: u64) -> &mut HashMap<String, Vec<u8>> {
        self.attrs.entry(ino).or_insert_with(HashMap::new)
    }

    pub fn get_xattr(&self, ino: u64, name: &str) -> Option<&Vec<u8>> {
        self.attrs.get(&ino).and_then(|m| m.get(name))
    }

    /// Set an xattr. Returns 0 on success, negative errno on failure.
    pub fn set_xattr(&mut self, ino: u64, name: &str, value: &[u8], flags: i32) -> i32 {
        if !valid_xattr_namespace(name) || name.is_empty() {
            return -libc::EOPNOTSUPP;
        }
        if value.len() > MAX_XATTR_VALUE {
            return -libc::E2BIG;
        }
        let map = self.ensure_map(ino);

        // Check total size after update
        let existing_size: usize = map.iter().map(|(k, v)| k.len() + v.len()).sum();
        let new_entry_size = name.len() + value.len();
        let old_entry_size = map.get(name).map(|v| name.len() + v.len()).unwrap_or(0);
        let projected = existing_size + new_entry_size - old_entry_size;
        if projected > MAX_XATTR_TOTAL {
            return -libc::ENOSPC;
        }

        if flags & libc::XATTR_CREATE != 0 && map.contains_key(name) {
            return -libc::EEXIST;
        }
        if flags & libc::XATTR_REPLACE != 0 && !map.contains_key(name) {
            return -libc::ENODATA;
        }
        map.insert(name.to_string(), value.to_vec());
        0
    }

    pub fn list_xattr(&self, ino: u64) -> Vec<String> {
        self.attrs
            .get(&ino)
            .map(|m| m.keys().cloned().collect())
            .unwrap_or_default()
    }

    pub fn remove_xattr(&mut self, ino: u64, name: &str) -> i32 {
        let map = self.ensure_map(ino);
        if map.remove(name).is_some() {
            0
        } else {
            -libc::ENODATA
        }
    }
}
