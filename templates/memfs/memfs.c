/*
 * memfs - a minimal in-memory filesystem using the FUSE high-level API.
 *
 * This is a known-good reference/template for the agent code generator.
 * It implements the common POSIX operations entirely in RAM:
 *   getattr, readdir, mkdir, rmdir, create, open, read, write,
 *   unlink, rename, truncate, chmod, utimens, statfs.
 *
 * Storage model: a flat table of nodes keyed by absolute path. Directory
 * listing is computed by scanning for entries whose parent path matches.
 * This is O(n) per lookup which is perfectly fine for tests and small FSes.
 *
 * Build:
 *     gcc -Wall memfs.c `pkg-config fuse3 --cflags --libs` -o agentfs
 *
 * Mount (foreground):
 *     ./agentfs -f /mnt/point
 */

#define FUSE_USE_VERSION 31
#define _GNU_SOURCE

#include <fuse.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <time.h>
#include <limits.h>
#include <pthread.h>
#include <sys/stat.h>

#define MAX_NODES 8192

struct mnode {
	int    used;
	char   path[PATH_MAX];
	mode_t mode;          /* includes S_IFDIR / S_IFREG */
	size_t size;          /* file size in bytes */
	size_t cap;           /* allocated capacity of data buffer */
	char  *data;          /* file contents (NULL for directories) */
	nlink_t nlink;
	time_t atime, mtime, ctime;
};

static struct mnode g_nodes[MAX_NODES];
static pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER;

/* ---- helpers (must be called with g_lock held) ---- */

static struct mnode *node_find(const char *path)
{
	for (int i = 0; i < MAX_NODES; i++)
		if (g_nodes[i].used && strcmp(g_nodes[i].path, path) == 0)
			return &g_nodes[i];
	return NULL;
}

static struct mnode *node_alloc(const char *path, mode_t mode)
{
	for (int i = 0; i < MAX_NODES; i++) {
		struct mnode *n = &g_nodes[i];
		if (!n->used) {
			memset(n, 0, sizeof(*n));
			n->used = 1;
			snprintf(n->path, sizeof(n->path), "%s", path);
			n->mode = mode;
			n->size = 0;
			n->cap = 0;
			n->data = NULL;
			n->nlink = S_ISDIR(mode) ? 2 : 1;
			n->atime = n->mtime = n->ctime = time(NULL);
			return n;
		}
	}
	return NULL;
}

static void node_free(struct mnode *n)
{
	free(n->data);
	memset(n, 0, sizeof(*n));
}

/* Split "/a/b/c" -> parent "/a/b" (into pbuf), base "c". Root has no parent. */
static void path_split(const char *path, char *pbuf, size_t pbufsz,
		       const char **base)
{
	const char *slash = strrchr(path, '/');
	if (!slash) {                 /* shouldn't happen for absolute paths */
		snprintf(pbuf, pbufsz, "/");
		*base = path;
		return;
	}
	*base = slash + 1;
	if (slash == path)            /* parent is root */
		snprintf(pbuf, pbufsz, "/");
	else {
		size_t len = (size_t)(slash - path);
		if (len >= pbufsz)
			len = pbufsz - 1;
		memcpy(pbuf, path, len);
		pbuf[len] = '\0';
	}
}

/* Is `child` a direct child of directory `dir`? If so, return base name. */
static int is_direct_child(const char *child, const char *dir,
			   const char **base_out)
{
	char pbuf[PATH_MAX];
	const char *base;
	if (strcmp(child, dir) == 0)   /* a directory is not its own child */
		return 0;
	path_split(child, pbuf, sizeof(pbuf), &base);
	if (*base == '\0')             /* guard against empty entry names */
		return 0;
	if (strcmp(pbuf, dir) == 0) {
		*base_out = base;
		return 1;
	}
	return 0;
}

static int ensure_capacity(struct mnode *n, size_t need)
{
	if (need <= n->cap)
		return 0;
	size_t newcap = n->cap ? n->cap : 4096;
	while (newcap < need)
		newcap *= 2;
	char *p = realloc(n->data, newcap);
	if (!p)
		return -ENOMEM;
	/* zero-fill the freshly grown region */
	memset(p + n->cap, 0, newcap - n->cap);
	n->data = p;
	n->cap = newcap;
	return 0;
}

/* ---- FUSE operations ---- */

static void *memfs_init(struct fuse_conn_info *conn, struct fuse_config *cfg)
{
	(void)conn;
	cfg->kernel_cache = 0;
	/* create root directory */
	if (!node_find("/"))
		node_alloc("/", S_IFDIR | 0755);
	return NULL;
}

static int memfs_getattr(const char *path, struct stat *stbuf,
			 struct fuse_file_info *fi)
{
	(void)fi;
	int res = 0;
	pthread_mutex_lock(&g_lock);
	struct mnode *n = node_find(path);
	if (!n) {
		res = -ENOENT;
		goto out;
	}
	memset(stbuf, 0, sizeof(*stbuf));
	stbuf->st_mode = n->mode;
	stbuf->st_nlink = n->nlink;
	stbuf->st_size = (off_t)n->size;
	stbuf->st_uid = getuid();
	stbuf->st_gid = getgid();
	stbuf->st_atime = n->atime;
	stbuf->st_mtime = n->mtime;
	stbuf->st_ctime = n->ctime;
out:
	pthread_mutex_unlock(&g_lock);
	return res;
}

static int memfs_readdir(const char *path, void *buf, fuse_fill_dir_t filler,
			 off_t offset, struct fuse_file_info *fi,
			 enum fuse_readdir_flags flags)
{
	(void)offset;
	(void)fi;
	(void)flags;
	pthread_mutex_lock(&g_lock);
	struct mnode *dir = node_find(path);
	if (!dir || !S_ISDIR(dir->mode)) {
		pthread_mutex_unlock(&g_lock);
		return -ENOENT;
	}
	filler(buf, ".", NULL, 0, 0);
	filler(buf, "..", NULL, 0, 0);
	for (int i = 0; i < MAX_NODES; i++) {
		struct mnode *n = &g_nodes[i];
		const char *base;
		if (n->used && is_direct_child(n->path, path, &base))
			filler(buf, base, NULL, 0, 0);
	}
	pthread_mutex_unlock(&g_lock);
	return 0;
}

static int memfs_mkdir(const char *path, mode_t mode)
{
	int res = 0;
	pthread_mutex_lock(&g_lock);
	if (node_find(path)) {
		res = -EEXIST;
		goto out;
	}
	if (!node_alloc(path, S_IFDIR | (mode & 07777)))
		res = -ENOSPC;
out:
	pthread_mutex_unlock(&g_lock);
	return res;
}

static int memfs_rmdir(const char *path)
{
	int res = 0;
	pthread_mutex_lock(&g_lock);
	struct mnode *n = node_find(path);
	if (!n) {
		res = -ENOENT;
		goto out;
	}
	if (!S_ISDIR(n->mode)) {
		res = -ENOTDIR;
		goto out;
	}
	/* must be empty */
	for (int i = 0; i < MAX_NODES; i++) {
		const char *base;
		if (g_nodes[i].used && is_direct_child(g_nodes[i].path, path, &base)) {
			res = -ENOTEMPTY;
			goto out;
		}
	}
	node_free(n);
out:
	pthread_mutex_unlock(&g_lock);
	return res;
}

static int memfs_create(const char *path, mode_t mode,
			struct fuse_file_info *fi)
{
	(void)fi;
	int res = 0;
	pthread_mutex_lock(&g_lock);
	if (node_find(path)) {
		res = -EEXIST;
		goto out;
	}
	if (!node_alloc(path, S_IFREG | (mode & 07777)))
		res = -ENOSPC;
out:
	pthread_mutex_unlock(&g_lock);
	return res;
}

static int memfs_open(const char *path, struct fuse_file_info *fi)
{
	(void)fi;
	pthread_mutex_lock(&g_lock);
	struct mnode *n = node_find(path);
	int res = n ? 0 : -ENOENT;
	pthread_mutex_unlock(&g_lock);
	return res;
}

static int memfs_read(const char *path, char *buf, size_t size, off_t offset,
		      struct fuse_file_info *fi)
{
	(void)fi;
	pthread_mutex_lock(&g_lock);
	struct mnode *n = node_find(path);
	if (!n || S_ISDIR(n->mode)) {
		pthread_mutex_unlock(&g_lock);
		return -ENOENT;
	}
	if ((size_t)offset >= n->size) {
		pthread_mutex_unlock(&g_lock);
		return 0;
	}
	size_t avail = n->size - (size_t)offset;
	if (size > avail)
		size = avail;
	memcpy(buf, n->data + offset, size);
	n->atime = time(NULL);
	pthread_mutex_unlock(&g_lock);
	return (int)size;
}

static int memfs_write(const char *path, const char *buf, size_t size,
		       off_t offset, struct fuse_file_info *fi)
{
	(void)fi;
	pthread_mutex_lock(&g_lock);
	struct mnode *n = node_find(path);
	if (!n || S_ISDIR(n->mode)) {
		pthread_mutex_unlock(&g_lock);
		return -ENOENT;
	}
	size_t end = (size_t)offset + size;
	int rc = ensure_capacity(n, end);
	if (rc) {
		pthread_mutex_unlock(&g_lock);
		return rc;
	}
	memcpy(n->data + offset, buf, size);
	if (end > n->size)
		n->size = end;
	n->mtime = time(NULL);
	pthread_mutex_unlock(&g_lock);
	return (int)size;
}

static int memfs_unlink(const char *path)
{
	int res = 0;
	pthread_mutex_lock(&g_lock);
	struct mnode *n = node_find(path);
	if (!n)
		res = -ENOENT;
	else if (S_ISDIR(n->mode))
		res = -EISDIR;
	else
		node_free(n);
	pthread_mutex_unlock(&g_lock);
	return res;
}

static int memfs_rename(const char *from, const char *to, unsigned int flags)
{
	int res = 0;
	pthread_mutex_lock(&g_lock);
	struct mnode *src = node_find(from);
	if (!src) {
		res = -ENOENT;
		goto out;
	}
	struct mnode *dst = node_find(to);
	if (flags & RENAME_NOREPLACE) {
		if (dst) {
			res = -EEXIST;
			goto out;
		}
	}
	if (dst)
		node_free(dst);
	snprintf(src->path, sizeof(src->path), "%s", to);
	src->ctime = time(NULL);
out:
	pthread_mutex_unlock(&g_lock);
	return res;
}

static int memfs_truncate(const char *path, off_t size,
			  struct fuse_file_info *fi)
{
	(void)fi;
	pthread_mutex_lock(&g_lock);
	struct mnode *n = node_find(path);
	if (!n || S_ISDIR(n->mode)) {
		pthread_mutex_unlock(&g_lock);
		return -ENOENT;
	}
	int rc = ensure_capacity(n, (size_t)size);
	if (rc) {
		pthread_mutex_unlock(&g_lock);
		return rc;
	}
	if ((size_t)size > n->size)
		memset(n->data + n->size, 0, (size_t)size - n->size);
	n->size = (size_t)size;
	n->mtime = time(NULL);
	pthread_mutex_unlock(&g_lock);
	return 0;
}

static int memfs_chmod(const char *path, mode_t mode,
		       struct fuse_file_info *fi)
{
	(void)fi;
	pthread_mutex_lock(&g_lock);
	struct mnode *n = node_find(path);
	if (!n) {
		pthread_mutex_unlock(&g_lock);
		return -ENOENT;
	}
	n->mode = (n->mode & S_IFMT) | (mode & 07777);
	n->ctime = time(NULL);
	pthread_mutex_unlock(&g_lock);
	return 0;
}

static int memfs_utimens(const char *path, const struct timespec ts[2],
			 struct fuse_file_info *fi)
{
	(void)fi;
	pthread_mutex_lock(&g_lock);
	struct mnode *n = node_find(path);
	if (!n) {
		pthread_mutex_unlock(&g_lock);
		return -ENOENT;
	}
	n->atime = ts[0].tv_sec;
	n->mtime = ts[1].tv_sec;
	pthread_mutex_unlock(&g_lock);
	return 0;
}

static int memfs_statfs(const char *path, struct statvfs *stbuf)
{
	(void)path;
	memset(stbuf, 0, sizeof(*stbuf));
	stbuf->f_bsize = 4096;
	stbuf->f_blocks = 1024 * 1024;
	stbuf->f_bfree = 1024 * 1024;
	stbuf->f_bavail = 1024 * 1024;
	stbuf->f_namemax = 255;
	return 0;
}

static const struct fuse_operations memfs_oper = {
	.init     = memfs_init,
	.getattr  = memfs_getattr,
	.readdir  = memfs_readdir,
	.mkdir    = memfs_mkdir,
	.rmdir    = memfs_rmdir,
	.create   = memfs_create,
	.open     = memfs_open,
	.read     = memfs_read,
	.write    = memfs_write,
	.unlink   = memfs_unlink,
	.rename   = memfs_rename,
	.truncate = memfs_truncate,
	.chmod    = memfs_chmod,
	.utimens  = memfs_utimens,
	.statfs   = memfs_statfs,
};

int main(int argc, char *argv[])
{
	return fuse_main(argc, argv, &memfs_oper, NULL);
}
