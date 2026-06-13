use std::collections::BTreeMap;

/// Directory entries: maps child name → child inode number.
#[derive(Debug, Clone, Default)]
pub struct Directory {
    pub entries: BTreeMap<String, u64>,
}

impl Directory {
    pub fn new() -> Self {
        Directory {
            entries: BTreeMap::new(),
        }
    }

    pub fn add_entry(&mut self, name: &str, child_ino: u64) -> bool {
        if self.entries.contains_key(name) {
            return false;
        }
        self.entries.insert(name.to_string(), child_ino);
        true
    }

    pub fn remove_entry(&mut self, name: &str) -> bool {
        self.entries.remove(name).is_some()
    }

    pub fn lookup(&self, name: &str) -> Option<u64> {
        self.entries.get(name).copied()
    }

    pub fn list_entries(&self) -> Vec<(String, u64)> {
        self.entries
            .iter()
            .map(|(k, v)| (k.clone(), *v))
            .collect()
    }

    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }
}
