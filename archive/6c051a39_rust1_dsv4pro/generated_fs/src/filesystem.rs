use std::collections::BTreeMap;
use std::sync::RwLock;

use crate::directory::Directory;
use crate::inode::{Inode, InodeData};
use crate::xattr::XattrStore;

/// Open file handle tracking inode, flags, and seek offset.
#[derive(Debug, Clone)]
pub struct OpenFileHandle {
    pub fh: u64,
    pub ino: u64,
    pub flags: i32,
    pub offset: u64,
}

/// Top-level in-memory filesystem state.
pub struct Filesystem {
    pub inodes: BTreeMap<u64, Inode>,
    pub next_ino: u64,
    pub dirs: BTreeMap<u64, Directory>,
    pub xattrs: XattrStore,
    pub handles: BTreeMap<u64, OpenFileHandle>,
    pub next_fh: u64,
    pub uid: u32,
    pub gid: u32,
}

impl Filesystem {
    pub fn new(uid: u32, gid: u32) -> Self {
        let mut fs = Filesystem {
            inodes: BTreeMap::new(),
            next_ino: 1,
            dirs: BTreeMap::new(),
            xattrs: XattrStore::new(),
            handles: BTreeMap::new(),
            next_fh: 1,
            uid,
            gid,
        };
        // Create root inode (ino=1)
        let root = Inode::new(1, libc::S_IFDIR | 0o755, uid, gid);
        fs.inodes.insert(1, root);
        fs.dirs.insert(1, Directory::new());
        fs.next_ino = 2;
        fs
    }

    /// Allocate a new inode and return its number.
    pub fn inode_alloc(&mut self, mode: u32, uid: u32, gid: u32) -> u64 {
        let ino = self.next_ino;
        self.next_ino += 1;
        let inode = Inode::new(ino, mode, uid, gid);
        self.inodes.insert(ino, inode);
        if (mode & libc::S_IFMT) == libc::S_IFDIR {
            self.dirs.insert(ino, Directory::new());
        }
        ino
    }

    pub fn get_inode(&self, ino: u64) -> Option<&Inode> {
        self.inodes.get(&ino)
    }

    pub fn get_inode_mut(&mut self, ino: u64) -> Option<&mut Inode> {
        self.inodes.get_mut(&ino)
    }

    pub fn remove_inode(&mut self, ino: u64) {
        self.inodes.remove(&ino);
        self.dirs.remove(&ino);
    }

    /// Allocate a new file handle.
    pub fn handle_alloc(&mut self, ino: u64, flags: i32) -> u64 {
        let fh = self.next_fh;
        self.next_fh += 1;
        self.handles.insert(
            fh,
            OpenFileHandle {
                fh,
                ino,
                flags,
                offset: 0,
            },
        );
        fh
    }

    pub fn handle_get(&self, fh: u64) -> Option<&OpenFileHandle> {
        self.handles.get(&fh)
    }

    pub fn handle_get_mut(&mut self, fh: u64) -> Option<&mut OpenFileHandle> {
        self.handles.get_mut(&fh)
    }

    pub fn handle_remove(&mut self, fh: u64) {
        self.handles.remove(&fh);
    }

    /// Write data to a regular file inode at a given offset.
    pub fn write_data(&mut self, ino: u64, offset: u64, buf: &[u8]) -> Result<u32, i32> {
        let inode = self.inodes.get_mut(&ino).ok_or(libc::ENOENT)?;
        if !inode.is_reg() {
            return Err(libc::EISDIR);
        }
        let data = match &mut inode.data {
            InodeData::File(ref mut v) => v,
            _ => return Err(libc::EISDIR),
        };
        let end = offset as usize + buf.len();
        if end > data.len() {
            data.resize(end, 0);
        }
        data[offset as usize..end].copy_from_slice(buf);
        if end as u64 > inode.size {
            inode.size = end as u64;
        }
        inode.touch_mtime();
        Ok(buf.len() as u32)
    }

    /// Read data from a regular file inode.
    pub fn read_data(&self, ino: u64, offset: u64, size: u32) -> Result<Vec<u8>, i32> {
        let inode = self.inodes.get(&ino).ok_or(libc::ENOENT)?;
        if !inode.is_reg() {
            return Err(libc::EISDIR);
        }
        let data = match &inode.data {
            InodeData::File(ref v) => v,
            _ => return Err(libc::EISDIR),
        };
        if offset as usize >= data.len() {
            return Ok(Vec::new());
        }
        let end = std::cmp::min(offset as usize + size as usize, data.len());
        Ok(data[offset as usize..end].to_vec())
    }

    /// Truncate a regular file inode to the given size.
    pub fn truncate_data(&mut self, ino: u64, size: u64) -> Result<(), i32> {
        let inode = self.inodes.get_mut(&ino).ok_or(libc::ENOENT)?;
        if !inode.is_reg() {
            return Err(libc::EISDIR);
        }
        let data = match &mut inode.data {
            InodeData::File(ref mut v) => v,
            _ => return Err(libc::EISDIR),
        };
        data.resize(size as usize, 0);
        inode.size = size;
        inode.touch_mtime();
        Ok(())
    }
}

/// Global filesystem instance, wrapped in RwLock.
pub struct FsContainer {
    pub inner: RwLock<Filesystem>,
}

impl FsContainer {
    pub fn new(uid: u32, gid: u32) -> Self {
        FsContainer {
            inner: RwLock::new(Filesystem::new(uid, gid)),
        }
    }
}
