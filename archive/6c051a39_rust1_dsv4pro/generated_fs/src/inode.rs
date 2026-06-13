use std::time::{Duration, SystemTime};

/// Core inode metadata and data container.
#[derive(Debug, Clone)]
pub struct Inode {
    pub ino: u64,
    pub mode: u32,
    pub uid: u32,
    pub gid: u32,
    pub size: u64, // logical file size
    pub nlink: u32,
    pub atime: Duration,
    pub mtime: Duration,
    pub ctime: Duration,
    pub data: InodeData,
}

#[derive(Debug, Clone)]
pub enum InodeData {
    File(Vec<u8>),
    Directory,
    Symlink(String),
}

fn now_duration() -> Duration {
    SystemTime::now()
        .duration_since(SystemTime::UNIX_EPOCH)
        .unwrap_or_default()
}

impl Inode {
    pub fn new(ino: u64, mode: u32, uid: u32, gid: u32) -> Self {
        let now = now_duration();
        let data = if (mode & libc::S_IFMT) == libc::S_IFDIR {
            InodeData::Directory
        } else if (mode & libc::S_IFMT) == libc::S_IFLNK {
            InodeData::Symlink(String::new())
        } else {
            InodeData::File(Vec::new())
        };
        let nlink = if (mode & libc::S_IFMT) == libc::S_IFDIR { 2 } else { 1 };
        Inode {
            ino,
            mode,
            uid,
            gid,
            size: 0,
            nlink,
            atime: now,
            mtime: now,
            ctime: now,
            data,
        }
    }

    pub fn is_dir(&self) -> bool {
        (self.mode & libc::S_IFMT) == libc::S_IFDIR
    }

    pub fn is_reg(&self) -> bool {
        (self.mode & libc::S_IFMT) == libc::S_IFREG
    }

    pub fn is_symlink(&self) -> bool {
        (self.mode & libc::S_IFMT) == libc::S_IFLNK
    }

    pub fn touch_atime(&mut self) {
        self.atime = now_duration();
    }

    pub fn touch_mtime(&mut self) {
        let now = now_duration();
        self.mtime = now;
        self.ctime = now;
    }

    pub fn touch_ctime(&mut self) {
        self.ctime = now_duration();
    }
}
