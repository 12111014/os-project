mod directory;
mod filesystem;
mod inode;
mod path_mod;
mod permissions_mod;
mod symlink_mod;
mod xattr;

use std::ffi::OsStr;
use std::sync::RwLock;
use std::time;

use fuser::{
    BsdFileFlags, Config, Errno, FileAttr, FileHandle, FileType, Filesystem, FopenFlags,
    Generation, INodeNo, LockOwner, MountOption, OpenFlags, RenameFlags, ReplyAttr, ReplyCreate,
    ReplyData, ReplyDirectory, ReplyEmpty, ReplyEntry, ReplyOpen, ReplyStatfs, ReplyWrite,
    ReplyXattr, Request, TimeOrNow, WriteFlags,
};

use crate::filesystem::FsContainer;
use crate::inode::InodeData;
use crate::path_mod::{resolve, split_path, validate_name};

const TTL: time::Duration = time::Duration::from_secs(1);

fn inode_to_file_attr(inode: &inode::Inode) -> FileAttr {
    let kind = if inode.is_dir() {
        FileType::Directory
    } else if inode.is_symlink() {
        FileType::Symlink
    } else {
        FileType::RegularFile
    };
    FileAttr {
        ino: INodeNo(inode.ino),
        size: inode.size,
        blocks: (inode.size + 511) / 512,
        atime: time::UNIX_EPOCH + inode.atime,
        mtime: time::UNIX_EPOCH + inode.mtime,
        ctime: time::UNIX_EPOCH + inode.ctime,
        crtime: time::UNIX_EPOCH,
        kind,
        perm: (inode.mode & 0o777) as u16,
        nlink: inode.nlink,
        uid: inode.uid,
        gid: inode.gid,
        rdev: 0,
        blksize: 4096,
        flags: 0,
    }
}

fn errno(e: i32) -> Errno {
    Errno::from_i32(e)
}

struct AgentFS {
    fs: FsContainer,
}

impl AgentFS {
    fn new() -> Self {
        let uid = unsafe { libc::getuid() };
        let gid = unsafe { libc::getgid() };
        AgentFS {
            fs: FsContainer::new(uid, gid),
        }
    }
}

impl Filesystem for AgentFS {
    fn getattr(
        &self,
        _req: &Request,
        ino: INodeNo,
        _fh: Option<FileHandle>,
        reply: ReplyAttr,
    ) {
        let fs = self.fs.inner.read().unwrap();
        match fs.get_inode(ino.into()) {
            Some(inode) => {
                let attr = inode_to_file_attr(inode);
                reply.attr(&TTL, &attr);
            }
            None => reply.error(errno(libc::ENOENT)),
        }
    }

    fn readdir(
        &self,
        _req: &Request,
        ino: INodeNo,
        _fh: FileHandle,
        offset: u64,
        mut reply: ReplyDirectory,
    ) {
        let fs = self.fs.inner.read().unwrap();
        let ino_u: u64 = ino.into();
        let inode = match fs.get_inode(ino_u) {
            Some(i) => i,
            None => {
                reply.error(errno(libc::ENOENT));
                return;
            }
        };
        if !inode.is_dir() {
            reply.error(errno(libc::ENOTDIR));
            return;
        }
        let dir = match fs.dirs.get(&ino_u) {
            Some(d) => d,
            None => {
                reply.error(errno(libc::ENOENT));
                return;
            }
        };

        let mut entries: Vec<(u64, FileType, String)> = Vec::new();
        entries.push((ino_u, FileType::Directory, ".".to_string()));
        let parent_ino: u64 = if ino_u == 1 { 1 } else { 1 };
        entries.push((parent_ino, FileType::Directory, "..".to_string()));

        for (name, child_ino) in dir.list_entries() {
            let child = fs.get_inode(child_ino);
            let ftype = match child {
                Some(c) if c.is_dir() => FileType::Directory,
                Some(c) if c.is_symlink() => FileType::Symlink,
                _ => FileType::RegularFile,
            };
            entries.push((child_ino, ftype, name));
        }

        for (i, (entry_ino, ftype, name)) in entries.iter().enumerate() {
            if (i as u64) < offset {
                continue;
            }
            if !reply.add(INodeNo(*entry_ino), (i + 1) as u64, *ftype, name) {
                break;
            }
        }
        reply.ok();

        drop(fs);
        let mut fs = self.fs.inner.write().unwrap();
        if let Some(dir_inode) = fs.get_inode_mut(ino_u) {
            dir_inode.atime = time::SystemTime::now()
                .duration_since(time::UNIX_EPOCH)
                .unwrap_or_default();
        }
    }

    fn lookup(&self, _req: &Request, parent: INodeNo, name: &OsStr, reply: ReplyEntry) {
        let fs = self.fs.inner.read().unwrap();
        let name_str = match name.to_str() {
            Some(s) => s,
            None => {
                reply.error(errno(libc::EINVAL));
                return;
            }
        };
        if let Err(e) = validate_name(name_str) {
            reply.error(errno(e));
            return;
        }
        let parent_u: u64 = parent.into();
        let dir = match fs.dirs.get(&parent_u) {
            Some(d) => d,
            None => {
                reply.error(errno(libc::ENOENT));
                return;
            }
        };
        match dir.lookup(name_str) {
            Some(ino) => match fs.get_inode(ino) {
                Some(inode) => {
                    let attr = inode_to_file_attr(inode);
                    reply.entry(&TTL, &attr, Generation(0));
                }
                None => reply.error(errno(libc::ENOENT)),
            },
            None => reply.error(errno(libc::ENOENT)),
        }
    }

    fn mkdir(
        &self,
        _req: &Request,
        parent: INodeNo,
        name: &OsStr,
        mode: u32,
        _umask: u32,
        reply: ReplyEntry,
    ) {
        let name_str = match name.to_str() {
            Some(s) => s,
            None => {
                reply.error(errno(libc::EINVAL));
                return;
            }
        };
        if let Err(e) = validate_name(name_str) {
            reply.error(errno(e));
            return;
        }
        let parent_u: u64 = parent.into();
        let mut fs = self.fs.inner.write().unwrap();
        match fs.get_inode(parent_u) {
            Some(i) if i.is_dir() => {}
            Some(_) => {
                reply.error(errno(libc::ENOTDIR));
                return;
            }
            None => {
                reply.error(errno(libc::ENOENT));
                return;
            }
        };
        if let Some(dir) = fs.dirs.get(&parent_u) {
            if dir.lookup(name_str).is_some() {
                reply.error(errno(libc::EEXIST));
                return;
            }
        }
        let uid = _req.uid();
        let gid = _req.gid();
        let child_ino = fs.inode_alloc(libc::S_IFDIR | (mode & 0o777), uid, gid);
        if let Some(dir) = fs.dirs.get_mut(&parent_u) {
            dir.add_entry(name_str, child_ino);
        }
        if let Some(pinode) = fs.get_inode_mut(parent_u) {
            pinode.nlink += 1;
            pinode.touch_mtime();
        }
        if let Some(child) = fs.get_inode(child_ino) {
            let attr = inode_to_file_attr(child);
            reply.entry(&TTL, &attr, Generation(0));
        } else {
            reply.error(errno(libc::EIO));
        }
    }

    fn rmdir(&self, _req: &Request, parent: INodeNo, name: &OsStr, reply: ReplyEmpty) {
        let name_str = match name.to_str() {
            Some(s) => s,
            None => {
                reply.error(errno(libc::EINVAL));
                return;
            }
        };
        let parent_u: u64 = parent.into();
        let mut fs = self.fs.inner.write().unwrap();
        let dir = match fs.dirs.get(&parent_u) {
            Some(d) => d,
            None => {
                reply.error(errno(libc::ENOENT));
                return;
            }
        };
        let child_ino = match dir.lookup(name_str) {
            Some(ino) => ino,
            None => {
                reply.error(errno(libc::ENOENT));
                return;
            }
        };
        let child = match fs.get_inode(child_ino) {
            Some(c) => c.clone(),
            None => {
                reply.error(errno(libc::ENOENT));
                return;
            }
        };
        if !child.is_dir() {
            reply.error(errno(libc::ENOTDIR));
            return;
        }
        if let Some(child_dir) = fs.dirs.get(&child_ino) {
            if !child_dir.is_empty() {
                reply.error(errno(libc::ENOTEMPTY));
                return;
            }
        }
        if let Some(dir) = fs.dirs.get_mut(&parent_u) {
            dir.remove_entry(name_str);
        }
        fs.remove_inode(child_ino);
        if let Some(pinode) = fs.get_inode_mut(parent_u) {
            pinode.nlink -= 1;
            pinode.touch_mtime();
        }
        reply.ok();
    }

    fn create(
        &self,
        _req: &Request,
        parent: INodeNo,
        name: &OsStr,
        mode: u32,
        _umask: u32,
        flags: i32,
        reply: ReplyCreate,
    ) {
        let name_str = match name.to_str() {
            Some(s) => s,
            None => {
                reply.error(errno(libc::EINVAL));
                return;
            }
        };
        if let Err(e) = validate_name(name_str) {
            reply.error(errno(e));
            return;
        }
        let parent_u: u64 = parent.into();
        let mut fs = self.fs.inner.write().unwrap();
        if !matches!(fs.get_inode(parent_u), Some(i) if i.is_dir()) {
            reply.error(errno(
                fs.get_inode(parent_u)
                    .map(|_| libc::ENOTDIR)
                    .unwrap_or(libc::ENOENT),
            ));
            return;
        }
        if let Some(dir) = fs.dirs.get(&parent_u) {
            if dir.lookup(name_str).is_some() {
                reply.error(errno(libc::EEXIST));
                return;
            }
        }
        let uid = _req.uid();
        let gid = _req.gid();
        let child_ino = fs.inode_alloc(libc::S_IFREG | (mode & 0o777), uid, gid);
        if let Some(dir) = fs.dirs.get_mut(&parent_u) {
            dir.add_entry(name_str, child_ino);
        }
        if let Some(pinode) = fs.get_inode_mut(parent_u) {
            pinode.touch_mtime();
        }
        let fh = fs.handle_alloc(child_ino, flags);
        if let Some(child) = fs.get_inode(child_ino) {
            let attr = inode_to_file_attr(child);
            reply.created(&TTL, &attr, Generation(0), FileHandle(fh), FopenFlags::empty());
        } else {
            reply.error(errno(libc::EIO));
        }
    }

    fn open(&self, _req: &Request, ino: INodeNo, _flags: OpenFlags, reply: ReplyOpen) {
        let ino_u: u64 = ino.into();
        let mut fs = self.fs.inner.write().unwrap();
        match fs.get_inode(ino_u) {
            Some(_) => {
                let fh = fs.handle_alloc(ino_u, 0);
                reply.opened(FileHandle(fh), FopenFlags::empty());
            }
            None => reply.error(errno(libc::ENOENT)),
        }
    }

    fn read(
        &self,
        _req: &Request,
        ino: INodeNo,
        _fh: FileHandle,
        offset: u64,
        size: u32,
        _flags: OpenFlags,
        _lock_owner: Option<LockOwner>,
        reply: ReplyData,
    ) {
        let ino_u: u64 = ino.into();
        let fs = self.fs.inner.write().unwrap();
        let inode = match fs.get_inode(ino_u) {
            Some(i) => i,
            None => {
                reply.error(errno(libc::ENOENT));
                return;
            }
        };
        if !inode.is_reg() {
            reply.error(errno(libc::EISDIR));
            return;
        }
        let data = match &inode.data {
            InodeData::File(ref v) => v,
            _ => {
                reply.error(errno(libc::EISDIR));
                return;
            }
        };
        let off = offset as usize;
        if off >= data.len() {
            reply.data(&[]);
            return;
        }
        let end = std::cmp::min(off + size as usize, data.len());
        reply.data(&data[off..end]);
    }

    fn write(
        &self,
        _req: &Request,
        ino: INodeNo,
        _fh: FileHandle,
        offset: u64,
        data: &[u8],
        _write_flags: WriteFlags,
        _flags: OpenFlags,
        _lock_owner: Option<LockOwner>,
        reply: ReplyWrite,
    ) {
        let ino_u: u64 = ino.into();
        let mut fs = self.fs.inner.write().unwrap();
        match fs.write_data(ino_u, offset, data) {
            Ok(n) => reply.written(n),
            Err(e) => reply.error(errno(e)),
        }
    }

    fn unlink(&self, _req: &Request, parent: INodeNo, name: &OsStr, reply: ReplyEmpty) {
        let name_str = match name.to_str() {
            Some(s) => s,
            None => {
                reply.error(errno(libc::EINVAL));
                return;
            }
        };
        let parent_u: u64 = parent.into();
        let mut fs = self.fs.inner.write().unwrap();
        let dir = match fs.dirs.get(&parent_u) {
            Some(d) => d,
            None => {
                reply.error(errno(libc::ENOENT));
                return;
            }
        };
        let child_ino = match dir.lookup(name_str) {
            Some(ino) => ino,
            None => {
                reply.error(errno(libc::ENOENT));
                return;
            }
        };
        let child = match fs.get_inode(child_ino) {
            Some(c) => c.clone(),
            None => {
                reply.error(errno(libc::ENOENT));
                return;
            }
        };
        if child.is_dir() {
            reply.error(errno(libc::EISDIR));
            return;
        }
        if let Some(dir) = fs.dirs.get_mut(&parent_u) {
            dir.remove_entry(name_str);
        }
        fs.remove_inode(child_ino);
        if let Some(pinode) = fs.get_inode_mut(parent_u) {
            pinode.touch_mtime();
        }
        reply.ok();
    }

    fn rename(
        &self,
        _req: &Request,
        parent: INodeNo,
        name: &OsStr,
        newparent: INodeNo,
        newname: &OsStr,
        flags: RenameFlags,
        reply: ReplyEmpty,
    ) {
        let name_str = match name.to_str() {
            Some(s) => s,
            None => {
                reply.error(errno(libc::EINVAL));
                return;
            }
        };
        let newname_str = match newname.to_str() {
            Some(s) => s,
            None => {
                reply.error(errno(libc::EINVAL));
                return;
            }
        };
        if let Err(e) = validate_name(newname_str) {
            reply.error(errno(e));
            return;
        }
        let parent_u: u64 = parent.into();
        let newparent_u: u64 = newparent.into();
        let mut fs = self.fs.inner.write().unwrap();
        let src_dir = match fs.dirs.get(&parent_u) {
            Some(d) => d,
            None => {
                reply.error(errno(libc::ENOENT));
                return;
            }
        };
        let src_ino = match src_dir.lookup(name_str) {
            Some(ino) => ino,
            None => {
                reply.error(errno(libc::ENOENT));
                return;
            }
        };
        let dst_dir = match fs.dirs.get(&newparent_u) {
            Some(d) => d,
            None => {
                reply.error(errno(libc::ENOENT));
                return;
            }
        };
        if flags.contains(RenameFlags::RENAME_NOREPLACE) {
            if dst_dir.lookup(newname_str).is_some() {
                reply.error(errno(libc::EEXIST));
                return;
            }
        }
        if let Some(dst_ino) = dst_dir.lookup(newname_str) {
            let dst = fs.get_inode(dst_ino).cloned();
            if let Some(ref dst_inode) = dst {
                if dst_inode.is_dir() {
                    if let Some(dst_dir) = fs.dirs.get(&dst_ino) {
                        if !dst_dir.is_empty() {
                            reply.error(errno(libc::ENOTEMPTY));
                            return;
                        }
                    }
                }
                if let Some(ddir) = fs.dirs.get_mut(&newparent_u) {
                    ddir.remove_entry(newname_str);
                }
                fs.remove_inode(dst_ino);
            }
        }
        if let Some(sdir) = fs.dirs.get_mut(&parent_u) {
            sdir.remove_entry(name_str);
        }
        if let Some(ddir) = fs.dirs.get_mut(&newparent_u) {
            ddir.add_entry(newname_str, src_ino);
        }
        if let Some(pinode) = fs.get_inode_mut(parent_u) {
            pinode.touch_mtime();
        }
        if parent_u != newparent_u {
            if let Some(pinode) = fs.get_inode_mut(newparent_u) {
                pinode.touch_mtime();
            }
        }
        if let Some(sinode) = fs.get_inode_mut(src_ino) {
            sinode.touch_ctime();
        }
        reply.ok();
    }

    fn setattr(
        &self,
        _req: &Request,
        ino: INodeNo,
        mode: Option<u32>,
        _uid: Option<u32>,
        _gid: Option<u32>,
        size: Option<u64>,
        atime: Option<TimeOrNow>,
        mtime: Option<TimeOrNow>,
        _ctime: Option<time::SystemTime>,
        _fh: Option<FileHandle>,
        _crtime: Option<time::SystemTime>,
        _chgtime: Option<time::SystemTime>,
        _bkuptime: Option<time::SystemTime>,
        _flags: Option<BsdFileFlags>,
        reply: ReplyAttr,
    ) {
        let ino_u: u64 = ino.into();
        let mut fs = self.fs.inner.write().unwrap();
        let inode = match fs.get_inode_mut(ino_u) {
            Some(i) => i,
            None => {
                reply.error(errno(libc::ENOENT));
                return;
            }
        };

        if let Some(m) = mode {
            inode.mode = (inode.mode & !0o777) | (m & 0o777);
            inode.touch_ctime();
        }

        let now = time::SystemTime::now()
            .duration_since(time::UNIX_EPOCH)
            .unwrap_or_default();

        if let Some(at) = atime {
            match at {
                TimeOrNow::SpecificTime(t) => {
                    inode.atime = t.duration_since(time::UNIX_EPOCH).unwrap_or_default();
                }
                TimeOrNow::Now => {
                    inode.atime = now;
                }
            }
        }

        if let Some(mt) = mtime {
            match mt {
                TimeOrNow::SpecificTime(t) => {
                    inode.mtime = t.duration_since(time::UNIX_EPOCH).unwrap_or_default();
                }
                TimeOrNow::Now => {
                    inode.mtime = now;
                    inode.ctime = now;
                }
            }
        }

        if let Some(sz) = size {
            if inode.is_reg() {
                if let InodeData::File(ref mut v) = inode.data {
                    v.resize(sz as usize, 0);
                }
                inode.size = sz;
                inode.touch_mtime();
            } else if inode.is_dir() {
                reply.error(errno(libc::EISDIR));
                return;
            }
        }

        let attr = inode_to_file_attr(inode);
        reply.attr(&TTL, &attr);
    }

    fn symlink(
        &self,
        _req: &Request,
        parent: INodeNo,
        name: &OsStr,
        link: &std::path::Path,
        reply: ReplyEntry,
    ) {
        let name_str = match name.to_str() {
            Some(s) => s,
            None => {
                reply.error(errno(libc::EINVAL));
                return;
            }
        };
        let target_str = match link.to_str() {
            Some(s) => s,
            None => {
                reply.error(errno(libc::EINVAL));
                return;
            }
        };
        if let Err(e) = validate_name(name_str) {
            reply.error(errno(e));
            return;
        }
        if let Err(e) = symlink_mod::validate_target(target_str) {
            reply.error(errno(e));
            return;
        }
        let parent_u: u64 = parent.into();
        let mut fs = self.fs.inner.write().unwrap();
        if !matches!(fs.get_inode(parent_u), Some(i) if i.is_dir()) {
            reply.error(errno(libc::ENOTDIR));
            return;
        }
        if let Some(dir) = fs.dirs.get(&parent_u) {
            if dir.lookup(name_str).is_some() {
                reply.error(errno(libc::EEXIST));
                return;
            }
        }
        let uid = _req.uid();
        let gid = _req.gid();
        let child_ino = fs.inode_alloc(libc::S_IFLNK | 0o777, uid, gid);
        if let Some(child) = fs.get_inode_mut(child_ino) {
            child.data = InodeData::Symlink(target_str.to_string());
            child.size = target_str.len() as u64;
        }
        if let Some(dir) = fs.dirs.get_mut(&parent_u) {
            dir.add_entry(name_str, child_ino);
        }
        if let Some(pinode) = fs.get_inode_mut(parent_u) {
            pinode.touch_mtime();
        }
        if let Some(child) = fs.get_inode(child_ino) {
            let attr = inode_to_file_attr(child);
            reply.entry(&TTL, &attr, Generation(0));
        } else {
            reply.error(errno(libc::EIO));
        }
    }

    fn readlink(&self, _req: &Request, ino: INodeNo, reply: ReplyData) {
        let ino_u: u64 = ino.into();
        let fs = self.fs.inner.read().unwrap();
        match fs.get_inode(ino_u) {
            Some(inode) if inode.is_symlink() => {
                let target = match &inode.data {
                    InodeData::Symlink(t) => t.as_bytes(),
                    _ => &[],
                };
                reply.data(target);
            }
            Some(_) => reply.error(errno(libc::EINVAL)),
            None => reply.error(errno(libc::ENOENT)),
        }
    }

    fn fsync(
        &self,
        _req: &Request,
        _ino: INodeNo,
        _fh: FileHandle,
        _datasync: bool,
        reply: ReplyEmpty,
    ) {
        reply.ok();
    }

    fn flush(
        &self,
        _req: &Request,
        _ino: INodeNo,
        _fh: FileHandle,
        _lock_owner: LockOwner,
        reply: ReplyEmpty,
    ) {
        reply.ok();
    }

    fn release(
        &self,
        _req: &Request,
        _ino: INodeNo,
        fh: FileHandle,
        _flags: OpenFlags,
        _lock_owner: Option<LockOwner>,
        _flush: bool,
        reply: ReplyEmpty,
    ) {
        let mut fs = self.fs.inner.write().unwrap();
        fs.handle_remove(fh.0);
        reply.ok();
    }

    fn statfs(&self, _req: &Request, _ino: INodeNo, reply: ReplyStatfs) {
        reply.statfs(
            1024 * 1024,
            1024 * 1024,
            1024 * 1024,
            0,
            0,
            4096,
            255,
            0,
        );
    }

    fn getxattr(
        &self,
        _req: &Request,
        ino: INodeNo,
        name: &OsStr,
        size: u32,
        reply: ReplyXattr,
    ) {
        let name_str = match name.to_str() {
            Some(s) => s,
            None => {
                reply.error(errno(libc::EINVAL));
                return;
            }
        };
        let ino_u: u64 = ino.into();
        let fs = self.fs.inner.read().unwrap();
        match fs.xattrs.get_xattr(ino_u, name_str) {
            Some(val) => {
                if size == 0 {
                    reply.size(val.len() as u32);
                } else if size < val.len() as u32 {
                    reply.error(errno(libc::ERANGE));
                } else {
                    reply.data(val);
                }
            }
            None => reply.error(errno(libc::ENODATA)),
        }
    }

    fn setxattr(
        &self,
        _req: &Request,
        ino: INodeNo,
        name: &OsStr,
        value: &[u8],
        flags: i32,
        _position: u32,
        reply: ReplyEmpty,
    ) {
        let name_str = match name.to_str() {
            Some(s) => s,
            None => {
                reply.error(errno(libc::EINVAL));
                return;
            }
        };
        let ino_u: u64 = ino.into();
        let mut fs = self.fs.inner.write().unwrap();
        match fs.xattrs.set_xattr(ino_u, name_str, value, flags) {
            0 => {
                if let Some(inode) = fs.get_inode_mut(ino_u) {
                    inode.touch_ctime();
                }
                reply.ok();
            }
            e => reply.error(errno(-e)),
        }
    }

    fn listxattr(&self, _req: &Request, ino: INodeNo, size: u32, reply: ReplyXattr) {
        let ino_u: u64 = ino.into();
        let fs = self.fs.inner.read().unwrap();
        let names = fs.xattrs.list_xattr(ino_u);
        let mut data: Vec<u8> = Vec::new();
        for name in &names {
            data.extend_from_slice(name.as_bytes());
            data.push(0);
        }
        if size == 0 {
            reply.size(data.len() as u32);
        } else if size < data.len() as u32 {
            reply.error(errno(libc::ERANGE));
        } else {
            reply.data(&data);
        }
    }

    fn removexattr(&self, _req: &Request, ino: INodeNo, name: &OsStr, reply: ReplyEmpty) {
        let name_str = match name.to_str() {
            Some(s) => s,
            None => {
                reply.error(errno(libc::EINVAL));
                return;
            }
        };
        let ino_u: u64 = ino.into();
        let mut fs = self.fs.inner.write().unwrap();
        match fs.xattrs.remove_xattr(ino_u, name_str) {
            0 => {
                if let Some(inode) = fs.get_inode_mut(ino_u) {
                    inode.touch_ctime();
                }
                reply.ok();
            }
            e => reply.error(errno(-e)),
        }
    }
}

fn main() {
    let mountpoint = std::env::args_os()
        .nth(1)
        .expect("Usage: agentfs <mountpoint>");
    let mut config = Config::default();
    config.mount_options = vec![MountOption::FSName("agentfs".to_string())];
    let fs = AgentFS::new();
    fuser::mount2(fs, mountpoint, &config).unwrap();
}
