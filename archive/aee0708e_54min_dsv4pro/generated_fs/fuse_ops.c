/*
 * fuse_ops.c — all FUSE high-level operation callbacks.
 *
 * Implements: getattr, readdir, open, read, write, create, unlink,
 * mkdir, rmdir, rename, symlink, readlink, truncate, chmod, setxattr,
 * getxattr, listxattr, removexattr, fsync, release.
 *
 * Each callback acquires the global mutex, normalizes/resolves paths,
 * and delegates to the appropriate internal module.
 */

#include "fuse_ops.h"
#include "inode_table.h"
#include "dir_ops.h"
#include "storage_backend.h"
#include "path_utils.h"
#include <string.h>
#include <stdlib.h>
#include <errno.h>
#include <unistd.h>
#include <stdio.h>

/* ---- helpers ------------------------------------------------------------ */

static void fill_stat(struct inode *ino, struct stat *stbuf)
{
	memset(stbuf, 0, sizeof(*stbuf));
	stbuf->st_ino   = ino->ino;
	stbuf->st_mode  = ino->mode;
	stbuf->st_nlink = ino->nlink;
	stbuf->st_size  = ino->size;
	stbuf->st_uid   = ino->uid;
	stbuf->st_gid   = ino->gid;
	stbuf->st_atime = ino->atime.tv_sec;
	stbuf->st_mtime = ino->mtime.tv_sec;
	stbuf->st_ctime = ino->ctime.tv_sec;
#ifdef st_atim
	stbuf->st_atim = ino->atime;
	stbuf->st_mtim = ino->mtime;
	stbuf->st_ctim = ino->ctime;
#endif
}

/* ---- xattr helpers ------------------------------------------------------ */

static struct xattr_node **xattr_find(struct inode *ino, const char *name)
{
	struct xattr_node **pp = &ino->xattrs;
	while (*pp) {
		if (strcmp((*pp)->name, name) == 0)
			return pp;
		pp = &(*pp)->next;
	}
	return pp; /* points to the next pointer where insertion would go */
}

/* ---- FUSE operations ---------------------------------------------------- */

static void *simplefs_init(struct fuse_conn_info *conn, struct fuse_config *cfg)
{
	(void)conn;
	cfg->kernel_cache = 0;
	return NULL;
}

static int simplefs_getattr(const char *path, struct stat *stbuf,
                            struct fuse_file_info *fi)
{
	(void)fi;
	pthread_mutex_lock(&g_lock);

	/* Only normalize the path — do NOT resolve symlinks.
	 * The FUSE kernel/VFS already resolves symlinks for stat() vs lstat():
	 * - stat() resolves symlinks before calling getattr
	 * - lstat() does NOT resolve, calling getattr on the symlink itself */
	char norm[PATH_MAX_SZ];
	int rc = path_normalize(path, norm, sizeof(norm));
	if (rc) {
		pthread_mutex_unlock(&g_lock);
		return rc;
	}

	struct inode *ino = inode_lookup_by_path(norm);
	if (!ino) {
		pthread_mutex_unlock(&g_lock);
		return -ENOENT;
	}

	fill_stat(ino, stbuf);
	inode_put(ino);
	pthread_mutex_unlock(&g_lock);
	return 0;
}

static int simplefs_readdir(const char *path, void *buf, fuse_fill_dir_t filler,
                            off_t offset, struct fuse_file_info *fi,
                            enum fuse_readdir_flags flags)
{
	(void)fi;
	(void)flags;
	pthread_mutex_lock(&g_lock);

	char norm[PATH_MAX_SZ];
	int rc = path_normalize(path, norm, sizeof(norm));
	if (rc) {
		pthread_mutex_unlock(&g_lock);
		return rc;
	}

	struct inode *dir = inode_lookup_by_path(norm);
	if (!dir || !S_ISDIR(dir->mode)) {
		if (dir) inode_put(dir);
		pthread_mutex_unlock(&g_lock);
		return -ENOENT;
	}

	rc = dir_readdir(dir->ino, offset, buf, filler);
	inode_put(dir);
	pthread_mutex_unlock(&g_lock);
	return rc;
}

static int simplefs_open(const char *path, struct fuse_file_info *fi)
{
	(void)fi;
	pthread_mutex_lock(&g_lock);

	char norm[PATH_MAX_SZ];
	int rc = path_normalize(path, norm, sizeof(norm));
	if (rc) {
		pthread_mutex_unlock(&g_lock);
		return rc;
	}

	struct inode *ino = inode_lookup_by_path(norm);
	if (!ino) {
		pthread_mutex_unlock(&g_lock);
		return -ENOENT;
	}

	/* lookup already bumped refcount; keep it */
	pthread_mutex_unlock(&g_lock);
	return 0;
}

static int simplefs_read(const char *path, char *buf, size_t size, off_t offset,
                         struct fuse_file_info *fi)
{
	(void)fi;
	pthread_mutex_lock(&g_lock);

	char norm[PATH_MAX_SZ];
	int rc = path_normalize(path, norm, sizeof(norm));
	if (rc) {
		pthread_mutex_unlock(&g_lock);
		return rc;
	}

	struct inode *ino = inode_lookup_by_path(norm);
	if (!ino) {
		pthread_mutex_unlock(&g_lock);
		return -ENOENT;
	}

	if (!S_ISREG(ino->mode)) {
		inode_put(ino);
		pthread_mutex_unlock(&g_lock);
		return -EISDIR;
	}

	/* direct buffer access */
	if ((off_t)offset >= ino->size) {
		inode_put(ino);
		pthread_mutex_unlock(&g_lock);
		return 0;
	}

	size_t avail = (size_t)(ino->size - offset);
	if (size > avail)
		size = avail;

	memcpy(buf, ino->data + offset, size);
	clock_gettime(CLOCK_REALTIME, &ino->atime);
	inode_put(ino);
	pthread_mutex_unlock(&g_lock);
	return (int)size;
}

static int simplefs_write(const char *path, const char *buf, size_t size,
                          off_t offset, struct fuse_file_info *fi)
{
	(void)fi;
	pthread_mutex_lock(&g_lock);

	char norm[PATH_MAX_SZ];
	int rc = path_normalize(path, norm, sizeof(norm));
	if (rc) {
		pthread_mutex_unlock(&g_lock);
		return rc;
	}

	struct inode *ino = inode_lookup_by_path(norm);
	if (!ino) {
		pthread_mutex_unlock(&g_lock);
		return -ENOENT;
	}

	if (!S_ISREG(ino->mode)) {
		inode_put(ino);
		pthread_mutex_unlock(&g_lock);
		return -EISDIR;
	}

	size_t end = (size_t)offset + size;
	if (end > ino->cap) {
		size_t newcap = ino->cap ? ino->cap : 4096;
		while (newcap < end)
			newcap *= 2;
		uint8_t *p = realloc(ino->data, newcap);
		if (!p) {
			inode_put(ino);
			pthread_mutex_unlock(&g_lock);
			return -ENOMEM;
		}
		memset(p + ino->cap, 0, newcap - ino->cap);
		ino->data = p;
		ino->cap  = newcap;
	}

	memcpy(ino->data + offset, buf, size);
	if (end > (size_t)ino->size)
		ino->size = (off_t)end;
	clock_gettime(CLOCK_REALTIME, &ino->mtime);
	inode_put(ino);
	pthread_mutex_unlock(&g_lock);
	return (int)size;
}

static int simplefs_create(const char *path, mode_t mode,
                           struct fuse_file_info *fi)
{
	(void)fi;
	pthread_mutex_lock(&g_lock);

	char norm[PATH_MAX_SZ];
	int rc = path_normalize(path, norm, sizeof(norm));
	if (rc) {
		pthread_mutex_unlock(&g_lock);
		return rc;
	}

	/* ensure parent exists */
	char parent[PATH_MAX_SZ];
	const char *base;
	rc = path_parent(norm, parent, sizeof(parent), &base);
	if (rc || *base == '\0') {
		pthread_mutex_unlock(&g_lock);
		return -EINVAL;
	}

	/* resolve parent with symlinks */
	char presolved[PATH_MAX_SZ];
	rc = path_resolve_symlink(parent, presolved, sizeof(presolved));
	if (rc) {
		pthread_mutex_unlock(&g_lock);
		return rc;
	}

	struct inode *pdir = inode_lookup_by_path(presolved);
	if (!pdir || !S_ISDIR(pdir->mode)) {
		if (pdir) inode_put(pdir);
		pthread_mutex_unlock(&g_lock);
		return -ENOENT;
	}

	/* check duplicate */
	uint64_t existing;
	if (dir_lookup(pdir->ino, base, &existing) == 0) {
		inode_put(pdir);
		pthread_mutex_unlock(&g_lock);
		return -EEXIST;
	}

	struct inode *child = inode_alloc(S_IFREG | (mode & 07777), getuid(), getgid());
	if (!child) {
		inode_put(pdir);
		pthread_mutex_unlock(&g_lock);
		return -ENOMEM;
	}

	rc = dir_add(pdir->ino, base, child->ino);
	inode_put(pdir);
	if (rc) {
		inode_unlink(child);
		inode_put(child);
		pthread_mutex_unlock(&g_lock);
		return rc;
	}

	/* child refcount=1 from alloc, kept for the open */
	pthread_mutex_unlock(&g_lock);
	return 0;
}

static int simplefs_unlink(const char *path)
{
	pthread_mutex_lock(&g_lock);

	char norm[PATH_MAX_SZ];
	int rc = path_normalize(path, norm, sizeof(norm));
	if (rc) { pthread_mutex_unlock(&g_lock); return rc; }

	char parent[PATH_MAX_SZ];
	const char *base;
	rc = path_parent(norm, parent, sizeof(parent), &base);
	if (rc || *base == '\0') {
		pthread_mutex_unlock(&g_lock);
		return -EINVAL;
	}

	char presolved[PATH_MAX_SZ];
	rc = path_resolve_symlink(parent, presolved, sizeof(presolved));
	if (rc) { pthread_mutex_unlock(&g_lock); return rc; }

	struct inode *pdir = inode_lookup_by_path(presolved);
	if (!pdir || !S_ISDIR(pdir->mode)) {
		if (pdir) inode_put(pdir);
		pthread_mutex_unlock(&g_lock);
		return -ENOENT;
	}

	uint64_t child_ino;
	if (dir_lookup(pdir->ino, base, &child_ino) != 0) {
		inode_put(pdir);
		pthread_mutex_unlock(&g_lock);
		return -ENOENT;
	}

	struct inode *child = inode_lookup(child_ino);
	if (!child) {
		inode_put(pdir);
		pthread_mutex_unlock(&g_lock);
		return -ENOENT;
	}

	if (S_ISDIR(child->mode)) {
		inode_put(child);
		inode_put(pdir);
		pthread_mutex_unlock(&g_lock);
		return -EISDIR;
	}

	dir_remove(pdir->ino, base);
	inode_put(pdir);
	inode_unlink(child);
	/* one ref from inode_lookup; put it — may free if nlink==0 && refcount==0 */
	inode_put(child);
	pthread_mutex_unlock(&g_lock);
	return 0;
}

static int simplefs_mkdir(const char *path, mode_t mode)
{
	pthread_mutex_lock(&g_lock);

	char norm[PATH_MAX_SZ];
	int rc = path_normalize(path, norm, sizeof(norm));
	if (rc) { pthread_mutex_unlock(&g_lock); return rc; }

	char parent[PATH_MAX_SZ];
	const char *base;
	rc = path_parent(norm, parent, sizeof(parent), &base);
	if (rc || *base == '\0') {
		pthread_mutex_unlock(&g_lock);
		return -EINVAL;
	}

	char presolved[PATH_MAX_SZ];
	rc = path_resolve_symlink(parent, presolved, sizeof(presolved));
	if (rc) { pthread_mutex_unlock(&g_lock); return rc; }

	struct inode *pdir = inode_lookup_by_path(presolved);
	if (!pdir || !S_ISDIR(pdir->mode)) {
		if (pdir) inode_put(pdir);
		pthread_mutex_unlock(&g_lock);
		return -ENOENT;
	}

	uint64_t existing;
	if (dir_lookup(pdir->ino, base, &existing) == 0) {
		inode_put(pdir);
		pthread_mutex_unlock(&g_lock);
		return -EEXIST;
	}

	struct inode *child = inode_alloc(S_IFDIR | (mode & 07777), getuid(), getgid());
	if (!child) {
		inode_put(pdir);
		pthread_mutex_unlock(&g_lock);
		return -ENOMEM;
	}

	rc = dir_add(pdir->ino, base, child->ino);
	inode_put(pdir);
	if (rc) {
		inode_unlink(child);
		inode_put(child);
		pthread_mutex_unlock(&g_lock);
		return rc;
	}

	inode_put(child);
	pthread_mutex_unlock(&g_lock);
	return 0;
}

static int simplefs_rmdir(const char *path)
{
	pthread_mutex_lock(&g_lock);

	char norm[PATH_MAX_SZ];
	int rc = path_normalize(path, norm, sizeof(norm));
	if (rc) { pthread_mutex_unlock(&g_lock); return rc; }

	char parent[PATH_MAX_SZ];
	const char *base;
	rc = path_parent(norm, parent, sizeof(parent), &base);
	if (rc || *base == '\0') {
		pthread_mutex_unlock(&g_lock);
		return -EINVAL;
	}

	char presolved[PATH_MAX_SZ];
	rc = path_resolve_symlink(parent, presolved, sizeof(presolved));
	if (rc) { pthread_mutex_unlock(&g_lock); return rc; }

	struct inode *pdir = inode_lookup_by_path(presolved);
	if (!pdir || !S_ISDIR(pdir->mode)) {
		if (pdir) inode_put(pdir);
		pthread_mutex_unlock(&g_lock);
		return -ENOENT;
	}

	uint64_t child_ino;
	if (dir_lookup(pdir->ino, base, &child_ino) != 0) {
		inode_put(pdir);
		pthread_mutex_unlock(&g_lock);
		return -ENOENT;
	}

	struct inode *child = inode_lookup(child_ino);
	if (!child) {
		inode_put(pdir);
		pthread_mutex_unlock(&g_lock);
		return -ENOENT;
	}

	if (!S_ISDIR(child->mode)) {
		inode_put(child);
		inode_put(pdir);
		pthread_mutex_unlock(&g_lock);
		return -ENOTDIR;
	}

	/* must be empty */
	if (child->children) {
		inode_put(child);
		inode_put(pdir);
		pthread_mutex_unlock(&g_lock);
		return -ENOTEMPTY;
	}

	dir_remove(pdir->ino, base);
	inode_put(pdir);
	inode_unlink(child);
	child->nlink = 0;  /* force deallocation */
	inode_put(child);
	pthread_mutex_unlock(&g_lock);
	return 0;
}

static int simplefs_rename(const char *from, const char *to, unsigned int flags)
{
	pthread_mutex_lock(&g_lock);

	(void)flags; /* RENAME_NOREPLACE handled via flag checking in dest-exists path */
	/* We accept flags=0 or RENAME_NOREPLACE; reject all others.
	   RENAME_NOREPLACE = (1 << 0) in Linux. */
	if (flags & ~1U) {
		pthread_mutex_unlock(&g_lock);
		return -EINVAL;
	}

	/* Resolve source parent */
	char from_norm[PATH_MAX_SZ];
	int rc = path_normalize(from, from_norm, sizeof(from_norm));
	if (rc) { pthread_mutex_unlock(&g_lock); return rc; }

	char from_parent[PATH_MAX_SZ];
	const char *from_base;
	rc = path_parent(from_norm, from_parent, sizeof(from_parent), &from_base);
	if (rc || *from_base == '\0' || strcmp(from_norm, "/") == 0) {
		pthread_mutex_unlock(&g_lock);
		return -EINVAL;
	}

	char from_presolved[PATH_MAX_SZ];
	rc = path_resolve_symlink(from_parent, from_presolved, sizeof(from_presolved));
	if (rc) { pthread_mutex_unlock(&g_lock); return rc; }

	struct inode *src_dir = inode_lookup_by_path(from_presolved);
	if (!src_dir || !S_ISDIR(src_dir->mode)) {
		if (src_dir) inode_put(src_dir);
		pthread_mutex_unlock(&g_lock);
		return -ENOENT;
	}

	uint64_t src_ino;
	if (dir_lookup(src_dir->ino, from_base, &src_ino) != 0) {
		inode_put(src_dir);
		pthread_mutex_unlock(&g_lock);
		return -ENOENT;
	}

	/* Resolve destination parent */
	char to_norm[PATH_MAX_SZ];
	rc = path_normalize(to, to_norm, sizeof(to_norm));
	if (rc) { inode_put(src_dir); pthread_mutex_unlock(&g_lock); return rc; }

	char to_parent[PATH_MAX_SZ];
	const char *to_base;
	rc = path_parent(to_norm, to_parent, sizeof(to_parent), &to_base);
	if (rc || *to_base == '\0') {
		inode_put(src_dir);
		pthread_mutex_unlock(&g_lock);
		return -EINVAL;
	}

	char to_presolved[PATH_MAX_SZ];
	rc = path_resolve_symlink(to_parent, to_presolved, sizeof(to_presolved));
	if (rc) {
		inode_put(src_dir);
		pthread_mutex_unlock(&g_lock);
		return rc;
	}

	struct inode *dst_dir = inode_lookup_by_path(to_presolved);
	if (!dst_dir || !S_ISDIR(dst_dir->mode)) {
		if (dst_dir) inode_put(dst_dir);
		inode_put(src_dir);
		pthread_mutex_unlock(&g_lock);
		return -ENOENT;
	}

	/* Check if dest already exists */
	uint64_t dst_ino;
	if (dir_lookup(dst_dir->ino, to_base, &dst_ino) == 0) {
		if (flags & 1U) { /* RENAME_NOREPLACE */
			inode_put(dst_dir);
			inode_put(src_dir);
			pthread_mutex_unlock(&g_lock);
			return -EEXIST;
		}
		/* Replace: remove the existing destination entry */
		struct inode *old_dst = inode_lookup(dst_ino);
		dir_remove(dst_dir->ino, to_base);
		if (old_dst) {
			inode_unlink(old_dst);
			inode_put(old_dst);
		}
	}

	/* Perform the rename: add to destination, remove from source */
	rc = dir_add(dst_dir->ino, to_base, src_ino);
	if (rc) {
		inode_put(dst_dir);
		inode_put(src_dir);
		pthread_mutex_unlock(&g_lock);
		return rc;
	}
	dir_remove(src_dir->ino, from_base);
	inode_put(dst_dir);
	inode_put(src_dir);
	pthread_mutex_unlock(&g_lock);
	return 0;
}

static int simplefs_symlink(const char *target, const char *linkpath)
{
	pthread_mutex_lock(&g_lock);

	char norm[PATH_MAX_SZ];
	int rc = path_normalize(linkpath, norm, sizeof(norm));
	if (rc) { pthread_mutex_unlock(&g_lock); return rc; }

	char parent[PATH_MAX_SZ];
	const char *base;
	rc = path_parent(norm, parent, sizeof(parent), &base);
	if (rc || *base == '\0') {
		pthread_mutex_unlock(&g_lock);
		return -EINVAL;
	}

	/* Resolve parent path through symlinks because parent components
	 * can be symlinks.  But do NOT resolve the linkpath itself — we
	 * resolve only the parent directory (everything before the final
	 * component). */
	char presolved[PATH_MAX_SZ];
	rc = path_resolve_symlink(parent, presolved, sizeof(presolved));
	if (rc) { pthread_mutex_unlock(&g_lock); return rc; }

	struct inode *pdir = inode_lookup_by_path(presolved);
	if (!pdir || !S_ISDIR(pdir->mode)) {
		if (pdir) inode_put(pdir);
		pthread_mutex_unlock(&g_lock);
		return -ENOENT;
	}

	uint64_t existing;
	if (dir_lookup(pdir->ino, base, &existing) == 0) {
		inode_put(pdir);
		pthread_mutex_unlock(&g_lock);
		return -EEXIST;
	}

	/* Create the symlink inode with S_IFLNK mode */
	struct inode *child = inode_alloc(S_IFLNK | 0777, getuid(), getgid());
	if (!child) {
		inode_put(pdir);
		pthread_mutex_unlock(&g_lock);
		return -ENOMEM;
	}

	/* Store the target string on the symlink inode */
	child->target = strdup(target);
	if (!child->target) {
		inode_unlink(child);
		inode_put(child);
		inode_put(pdir);
		pthread_mutex_unlock(&g_lock);
		return -ENOMEM;
	}
	child->size = (off_t)strlen(target);

	/* Add the dirent entry pointing to the symlink inode.
	 * This must happen AFTER the inode is fully set up, so that if
	 * path_resolve_symlink encounters it during component walk, the
	 * S_ISLNK check returns true and the target is available. */
	rc = dir_add(pdir->ino, base, child->ino);
	inode_put(pdir);
	if (rc) {
		inode_unlink(child);
		inode_put(child);
		pthread_mutex_unlock(&g_lock);
		return rc;
	}

	inode_put(child);
	pthread_mutex_unlock(&g_lock);
	return 0;
}

static int simplefs_readlink(const char *path, char *buf, size_t size)
{
	pthread_mutex_lock(&g_lock);

	/* Use path_normalize for readlink — we do NOT want to follow the
	 * symlink, we want to read its target directly.  So we walk the
	 * path components ourselves, resolving symlinks only for parent
	 * directories. */
	char norm[PATH_MAX_SZ];
	int rc = path_normalize(path, norm, sizeof(norm));
	if (rc) { pthread_mutex_unlock(&g_lock); return rc; }

	/* Don't resolve the final component — readlink returns the raw target */
	char parent[PATH_MAX_SZ];
	const char *base;
	rc = path_parent(norm, parent, sizeof(parent), &base);
	if (rc || *base == '\0') {
		pthread_mutex_unlock(&g_lock);
		return -EINVAL;
	}

	/* Resolve parent through symlinks */
	char presolved[PATH_MAX_SZ];
	rc = path_resolve_symlink(parent, presolved, sizeof(presolved));
	if (rc) { pthread_mutex_unlock(&g_lock); return rc; }

	struct inode *pdir = inode_lookup_by_path(presolved);
	if (!pdir || !S_ISDIR(pdir->mode)) {
		if (pdir) inode_put(pdir);
		pthread_mutex_unlock(&g_lock);
		return -ENOENT;
	}

	uint64_t child_ino;
	if (dir_lookup(pdir->ino, base, &child_ino) != 0) {
		inode_put(pdir);
		pthread_mutex_unlock(&g_lock);
		return -ENOENT;
	}

	struct inode *child = inode_lookup(child_ino);
	inode_put(pdir);
	if (!child) {
		pthread_mutex_unlock(&g_lock);
		return -ENOENT;
	}

	if (!S_ISLNK(child->mode)) {
		inode_put(child);
		pthread_mutex_unlock(&g_lock);
		return -EINVAL;
	}

	size_t len = strlen(child->target);
	if (len >= size)
		len = size - 1;
	memcpy(buf, child->target, len);
	buf[len] = '\0';
	inode_put(child);
	pthread_mutex_unlock(&g_lock);
	return 0;
}

static int simplefs_truncate(const char *path, off_t size,
                             struct fuse_file_info *fi)
{
	(void)fi;
	pthread_mutex_lock(&g_lock);

	char norm[PATH_MAX_SZ];
	int rc = path_normalize(path, norm, sizeof(norm));
	if (rc) { pthread_mutex_unlock(&g_lock); return rc; }

	struct inode *ino = inode_lookup_by_path(norm);
	if (!ino) { pthread_mutex_unlock(&g_lock); return -ENOENT; }
	if (!S_ISREG(ino->mode)) {
		inode_put(ino);
		pthread_mutex_unlock(&g_lock);
		return -EISDIR;
	}

	if (size < 0) {
		inode_put(ino);
		pthread_mutex_unlock(&g_lock);
		return -EINVAL;
	}

	ino->size = size;
	clock_gettime(CLOCK_REALTIME, &ino->mtime);
	clock_gettime(CLOCK_REALTIME, &ino->ctime);
	inode_put(ino);
	pthread_mutex_unlock(&g_lock);
	return 0;
}

static int simplefs_chmod(const char *path, mode_t mode,
                          struct fuse_file_info *fi)
{
	(void)fi;
	pthread_mutex_lock(&g_lock);

	char norm[PATH_MAX_SZ];
	int rc = path_normalize(path, norm, sizeof(norm));
	if (rc) { pthread_mutex_unlock(&g_lock); return rc; }

	struct inode *ino = inode_lookup_by_path(norm);
	if (!ino) { pthread_mutex_unlock(&g_lock); return -ENOENT; }

	ino->mode = (ino->mode & S_IFMT) | (mode & 07777);
	clock_gettime(CLOCK_REALTIME, &ino->ctime);
	inode_put(ino);
	pthread_mutex_unlock(&g_lock);
	return 0;
}

static int simplefs_setxattr(const char *path, const char *name,
                             const char *value, size_t size, int flags)
{
	pthread_mutex_lock(&g_lock);

	char norm[PATH_MAX_SZ];
	int rc = path_normalize(path, norm, sizeof(norm));
	if (rc) { pthread_mutex_unlock(&g_lock); return rc; }

	struct inode *ino = inode_lookup_by_path(norm);
	if (!ino) { pthread_mutex_unlock(&g_lock); return -ENOENT; }

	struct xattr_node **pp = xattr_find(ino, name);
	if (*pp) {
		if (flags == 1) {  /* XATTR_CREATE */
			inode_put(ino);
			pthread_mutex_unlock(&g_lock);
			return -EEXIST;
		}
		free((*pp)->value);
		(*pp)->value = malloc(size);
		if (!(*pp)->value) {
			inode_put(ino);
			pthread_mutex_unlock(&g_lock);
			return -ENOMEM;
		}
		memcpy((*pp)->value, value, size);
		(*pp)->value_len = size;
	} else {
		if (flags == 2) {  /* XATTR_REPLACE */
			inode_put(ino);
			pthread_mutex_unlock(&g_lock);
			return -ENODATA;
		}
		struct xattr_node *xn = calloc(1, sizeof(*xn));
		if (!xn) {
			inode_put(ino);
			pthread_mutex_unlock(&g_lock);
			return -ENOMEM;
		}
		xn->name = strdup(name);
		xn->value = malloc(size);
		if (!xn->name || !xn->value) {
			free(xn->name);
			free(xn->value);
			free(xn);
			inode_put(ino);
			pthread_mutex_unlock(&g_lock);
			return -ENOMEM;
		}
		memcpy(xn->value, value, size);
		xn->value_len = size;
		xn->next = ino->xattrs;
		ino->xattrs = xn;
	}

	clock_gettime(CLOCK_REALTIME, &ino->ctime);
	inode_put(ino);
	pthread_mutex_unlock(&g_lock);
	return 0;
}

static int simplefs_getxattr(const char *path, const char *name,
                             char *value, size_t size)
{
	pthread_mutex_lock(&g_lock);

	char norm[PATH_MAX_SZ];
	int rc = path_normalize(path, norm, sizeof(norm));
	if (rc) { pthread_mutex_unlock(&g_lock); return rc; }

	struct inode *ino = inode_lookup_by_path(norm);
	if (!ino) { pthread_mutex_unlock(&g_lock); return -ENOENT; }

	struct xattr_node **pp = xattr_find(ino, name);
	if (*pp == NULL) {
		inode_put(ino);
		pthread_mutex_unlock(&g_lock);
		return -ENODATA;
	}

	if (size == 0) {
		rc = (int)(*pp)->value_len;
	} else if (size >= (*pp)->value_len) {
		memcpy(value, (*pp)->value, (*pp)->value_len);
		rc = (int)(*pp)->value_len;
	} else {
		rc = -ERANGE;
	}
	inode_put(ino);
	pthread_mutex_unlock(&g_lock);
	return rc;
}

static int simplefs_listxattr(const char *path, char *list, size_t size)
{
	pthread_mutex_lock(&g_lock);

	char norm[PATH_MAX_SZ];
	int rc = path_normalize(path, norm, sizeof(norm));
	if (rc) { pthread_mutex_unlock(&g_lock); return rc; }

	struct inode *ino = inode_lookup_by_path(norm);
	if (!ino) { pthread_mutex_unlock(&g_lock); return -ENOENT; }

	size_t total = 0;
	for (struct xattr_node *xn = ino->xattrs; xn; xn = xn->next)
		total += strlen(xn->name) + 1;  /* name + null terminator */

	if (size == 0) {
		inode_put(ino);
		pthread_mutex_unlock(&g_lock);
		return (int)total;
	}

	if (size < total) {
		inode_put(ino);
		pthread_mutex_unlock(&g_lock);
		return -ERANGE;
	}

	char *p = list;
	for (struct xattr_node *xn = ino->xattrs; xn; xn = xn->next) {
		size_t nlen = strlen(xn->name) + 1;
		memcpy(p, xn->name, nlen);
		p += nlen;
	}
	inode_put(ino);
	pthread_mutex_unlock(&g_lock);
	return (int)total;
}

static int simplefs_removexattr(const char *path, const char *name)
{
	pthread_mutex_lock(&g_lock);

	char norm[PATH_MAX_SZ];
	int rc = path_normalize(path, norm, sizeof(norm));
	if (rc) { pthread_mutex_unlock(&g_lock); return rc; }

	struct inode *ino = inode_lookup_by_path(norm);
	if (!ino) { pthread_mutex_unlock(&g_lock); return -ENOENT; }

	struct xattr_node **pp = xattr_find(ino, name);
	if (*pp == NULL) {
		inode_put(ino);
		pthread_mutex_unlock(&g_lock);
		return -ENODATA;
	}

	struct xattr_node *victim = *pp;
	*pp = victim->next;
	free(victim->name);
	free(victim->value);
	free(victim);

	clock_gettime(CLOCK_REALTIME, &ino->ctime);
	inode_put(ino);
	pthread_mutex_unlock(&g_lock);
	return 0;
}

static int simplefs_fsync(const char *path, int isdatasync,
                          struct fuse_file_info *fi)
{
	(void)path;
	(void)isdatasync;
	(void)fi;
	/* writes are immediate; fsync is a no-op */
	return 0;
}

static int simplefs_utimens(const char *path, const struct timespec tv[2],
                            struct fuse_file_info *fi)
{
	(void)fi;
	pthread_mutex_lock(&g_lock);

	char norm[PATH_MAX_SZ];
	int rc = path_normalize(path, norm, sizeof(norm));
	if (rc) { pthread_mutex_unlock(&g_lock); return rc; }

	struct inode *ino = inode_lookup_by_path(norm);
	if (!ino) { pthread_mutex_unlock(&g_lock); return -ENOENT; }

	if (tv) {
		if (tv[0].tv_nsec != UTIME_OMIT)
			ino->atime = tv[0];
		if (tv[1].tv_nsec != UTIME_OMIT)
			ino->mtime = tv[1];
	} else {
		/* tv == NULL means set to current time */
		clock_gettime(CLOCK_REALTIME, &ino->atime);
		clock_gettime(CLOCK_REALTIME, &ino->mtime);
	}
	clock_gettime(CLOCK_REALTIME, &ino->ctime);
	inode_put(ino);
	pthread_mutex_unlock(&g_lock);
	return 0;
}

static int simplefs_release(const char *path, struct fuse_file_info *fi)
{
	(void)fi;
	pthread_mutex_lock(&g_lock);

	char norm[PATH_MAX_SZ];
	int rc = path_normalize(path, norm, sizeof(norm));
	if (rc) { pthread_mutex_unlock(&g_lock); return rc; }

	struct inode *ino = inode_lookup_by_path(norm);
	if (ino) {
		/* inode_lookup_by_path bumped refcount; release bumps it down twice:
		   once for the open ref and once for this lookup. */
		inode_put(ino);  /* release our lookup ref */
		inode_put(ino);  /* release the open ref */
	}

	pthread_mutex_unlock(&g_lock);
	return 0;
}

static int simplefs_statfs(const char *path, struct statvfs *stbuf)
{
	(void)path;
	memset(stbuf, 0, sizeof(*stbuf));
	stbuf->f_bsize   = 4096;
	stbuf->f_blocks  = 1024 * 1024;
	stbuf->f_bfree   = 1024 * 1024;
	stbuf->f_bavail  = 1024 * 1024;
	stbuf->f_namemax = 255;
	return 0;
}

/* ---- fuse_operations struct --------------------------------------------- */

const struct fuse_operations simplefs_oper = {
	.init        = simplefs_init,
	.getattr     = simplefs_getattr,
	.readdir     = simplefs_readdir,
	.open        = simplefs_open,
	.read        = simplefs_read,
	.write       = simplefs_write,
	.create      = simplefs_create,
	.unlink      = simplefs_unlink,
	.mkdir       = simplefs_mkdir,
	.rmdir       = simplefs_rmdir,
	.rename      = simplefs_rename,
	.symlink     = simplefs_symlink,
	.readlink    = simplefs_readlink,
	.truncate    = simplefs_truncate,
	.chmod       = simplefs_chmod,
	.setxattr    = simplefs_setxattr,
	.getxattr    = simplefs_getxattr,
	.listxattr   = simplefs_listxattr,
	.removexattr = simplefs_removexattr,
	.fsync       = simplefs_fsync,
	.utimens     = simplefs_utimens,
	.release     = simplefs_release,
	.statfs      = simplefs_statfs,
};