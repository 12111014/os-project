use crate::inode::Inode;

/// Check if the given uid/gid has read permission on the inode.
pub fn can_read(inode: &Inode, uid: u32, gid: u32) -> bool {
    if uid == 0 {
        return true; // root bypasses
    }
    let mode = inode.mode & 0o777;
    if uid == inode.uid {
        mode & 0o400 != 0
    } else if gid == inode.gid {
        mode & 0o040 != 0
    } else {
        mode & 0o004 != 0
    }
}

/// Check if the given uid/gid has write permission on the inode.
pub fn can_write(inode: &Inode, uid: u32, gid: u32) -> bool {
    if uid == 0 {
        return true;
    }
    let mode = inode.mode & 0o777;
    if uid == inode.uid {
        mode & 0o200 != 0
    } else if gid == inode.gid {
        mode & 0o020 != 0
    } else {
        mode & 0o002 != 0
    }
}

/// Check if the given uid/gid has execute permission on the inode.
pub fn can_execute(inode: &Inode, uid: u32, gid: u32) -> bool {
    if uid == 0 {
        return true;
    }
    let mode = inode.mode & 0o777;
    if uid == inode.uid {
        mode & 0o100 != 0
    } else if gid == inode.gid {
        mode & 0o010 != 0
    } else {
        mode & 0o001 != 0
    }
}

/// Check search (execute) on a directory.
pub fn can_search_dir(inode: &Inode, uid: u32, gid: u32) -> bool {
    can_execute(inode, uid, gid)
}
