/*
 * inode_table.c — inode lifecycle management.
 *
 * - Global hash map keyed by inode number (uint64_t).
 * - Per-operation path→inode lookup walks from root via dir_ops.
 * - Reference counting: acquire on open/lookup, release on release/forget.
 * - Deallocation when refcount==0 && nlink==0.
 */

#include "inode_table.h"
#include "dir_ops.h"
#include <stdlib.h>
#include <string.h>
#include <errno.h>

/* ---- hash map (simple static-bucket hash table) -------------------------- */

#define HASH_BITS    13
#define HASH_SIZE    (1U << HASH_BITS)
#define HASH_MASK    (HASH_SIZE - 1)

static struct inode *g_ino_table[HASH_SIZE];
static uint64_t       g_next_ino = 1;  /* root gets ino=1 */

static uint32_t hash_ino(uint64_t ino)
{
	return (uint32_t)(ino * 2654435761ULL) & HASH_MASK;
}

/* ---- internal helpers --------------------------------------------------- */

static struct inode **ino_slot(uint64_t ino)
{
	uint32_t h = hash_ino(ino);
	return &g_ino_table[h];
}

static void free_inode_resources(struct inode *ino)
{
	/* free data buffer */
	free(ino->data);
	ino->data = NULL;

	/* free symlink target */
	free(ino->target);
	ino->target = NULL;

	/* free directory entries */
	struct dirent *de = ino->children;
	while (de) {
		struct dirent *next = de->next;
		free(de->name);
		free(de);
		de = next;
	}
	ino->children = NULL;

	/* free xattrs */
	struct xattr_node *xn = ino->xattrs;
	while (xn) {
		struct xattr_node *next = xn->next;
		free(xn->name);
		free(xn->value);
		free(xn);
		xn = next;
	}
	ino->xattrs = NULL;
}

/* ---- public API --------------------------------------------------------- */

struct inode *inode_alloc(mode_t mode, uid_t uid, gid_t gid)
{
	uint64_t ino = g_next_ino++;
	struct inode *ino_obj = calloc(1, sizeof(*ino_obj));
	if (!ino_obj)
		return NULL;

	ino_obj->ino    = ino;
	ino_obj->mode   = mode;
	ino_obj->uid    = uid;
	ino_obj->gid    = gid;
	ino_obj->nlink  = S_ISDIR(mode) ? 2 : 1;
	ino_obj->size   = 0;
	ino_obj->cap    = 0;
	ino_obj->data   = NULL;
	ino_obj->target = NULL;
	ino_obj->children = NULL;
	ino_obj->xattrs = NULL;
	ino_obj->refcount = 1;  /* caller gets one reference */

	clock_gettime(CLOCK_REALTIME, &ino_obj->atime);
	ino_obj->mtime = ino_obj->ctime = ino_obj->atime;

	/* insert into hash table */
	ino_obj->ino = ino;
	/* handle collisions via linked list stored inline (we keep array of list heads) */
	/* We insert at head for simplicity; lookup walks the chain. */
	/* Actually, we need chaining. Let's add a next pointer to inode. */
	/* Since the architecture plan doesn't define a per-inode hash-chain pointer,
	   we embed one here for implementation expedience. */
	/* But to keep fuse_ops.h clean, we define it here as a static global
	   workaround: we re-use a simple intrusive pointer. */
	/* Let's instead use open addressing. Simpler. */
	/* Re-check: the plan says "Global hash map keyed by inode number" —
	   open addressing with linear probing is fine. */
	/* For now, chain through a static array of buckets. We'll iterate. */
	/* Wait — simpler: just store the pointer in the slot if empty, else
	   linear-probe forward. */
	uint32_t idx = hash_ino(ino);
	while (g_ino_table[idx] != NULL)
		idx = (idx + 1) & HASH_MASK;
	g_ino_table[idx] = ino_obj;

	return ino_obj;
}

struct inode *inode_lookup(uint64_t ino)
{
	uint32_t idx = hash_ino(ino);
	for (uint32_t i = 0; i < HASH_SIZE; i++) {
		struct inode *n = g_ino_table[idx];
		if (n == NULL)
			return NULL;
		if (n->ino == ino) {
			n->refcount++;
			return n;
		}
		idx = (idx + 1) & HASH_MASK;
	}
	return NULL;
}

struct inode *inode_lookup_by_path(const char *path)
{
	/* walk from root via dir_ops component-by-component */
	if (!path || path[0] != '/')
		return NULL;

	struct inode *cur = inode_lookup(1);  /* root ino=1 */
	if (!cur)
		return NULL;
	/* We already bumped refcount; if we bail early we must put it. */

	if (strcmp(path, "/") == 0)
		return cur;  /* already refcounted */

	char component[256];
	const char *p = path + 1;  /* skip leading '/' */
	while (*p) {
		const char *slash = strchr(p, '/');
		size_t len;
		if (slash) {
			len = (size_t)(slash - p);
		} else {
			len = strlen(p);
		}
		if (len >= sizeof(component)) {
			inode_put(cur);
			return NULL;
		}
		memcpy(component, p, len);
		component[len] = '\0';

		if (!S_ISDIR(cur->mode)) {
			inode_put(cur);
			return NULL;
		}

		uint64_t child_ino;
		if (dir_lookup(cur->ino, component, &child_ino) != 0) {
			inode_put(cur);
			return NULL;
		}

		struct inode *child = inode_lookup(child_ino);
		inode_put(cur);
		if (!child)
			return NULL;
		cur = child;

		p += len;
		if (*p == '/') p++;
	}
	return cur;
}

void inode_put(struct inode *ino)
{
	if (!ino) return;
	ino->refcount--;
	if (ino->refcount <= 0 && ino->nlink == 0) {
		/* remove from hash table */
		uint32_t idx = hash_ino(ino->ino);
		while (g_ino_table[idx] != ino)
			idx = (idx + 1) & HASH_MASK;
		g_ino_table[idx] = NULL;

		free_inode_resources(ino);
		free(ino);
	}
}

void inode_unlink(struct inode *ino)
{
	if (!ino) return;
	ino->nlink--;
	/* if it was a directory, or nlink hit 0, caller must handle
	   actual deallocation via inode_put when refcount also 0. */
}
