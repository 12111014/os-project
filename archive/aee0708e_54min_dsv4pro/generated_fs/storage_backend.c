/*
 * storage_backend.c — per-file in-memory byte buffers.
 *
 * Each regular-file inode owns a dynamically allocated byte buffer (uint8_t*)
 * that grows via realloc. Size is tracked in the inode's size field.
 * Reads beyond EOF return 0 bytes. Writes beyond current size expand.
 */

#include "storage_backend.h"
#include "inode_table.h"
#include <stdlib.h>
#include <string.h>
#include <errno.h>

/* ---- internal ----------------------------------------------------------- */

static int ensure_capacity(struct inode *ino, size_t need)
{
	if (need <= ino->cap)
		return 0;

	size_t newcap = ino->cap ? ino->cap : 4096;
	while (newcap < need)
		newcap *= 2;

	uint8_t *p = realloc(ino->data, newcap);
	if (!p)
		return -ENOMEM;

	/* zero-fill the freshly grown region */
	memset(p + ino->cap, 0, newcap - ino->cap);
	ino->data = p;
	ino->cap  = newcap;
	return 0;
}

/* ---- public API --------------------------------------------------------- */

int storage_read(uint64_t ino, off_t offset, char *buf, size_t size)
{
	struct inode *n = inode_lookup(ino);
	if (!n)
		return -ENOENT;
	if (!S_ISREG(n->mode)) {
		inode_put(n);
		return -EISDIR;
	}

	if ((off_t)offset >= n->size) {
		inode_put(n);
		return 0;
	}

	size_t avail = (size_t)(n->size - offset);
	if (size > avail)
		size = avail;

	memcpy(buf, n->data + offset, size);
	inode_put(n);
	return (int)size;
}

int storage_write(uint64_t ino, off_t offset, const char *buf, size_t size)
{
	struct inode *n = inode_lookup(ino);
	if (!n)
		return -ENOENT;
	if (!S_ISREG(n->mode)) {
		inode_put(n);
		return -EISDIR;
	}

	size_t end = (size_t)offset + size;
	int rc = ensure_capacity(n, end);
	if (rc) {
		inode_put(n);
		return rc;
	}

	memcpy(n->data + offset, buf, size);
	if (end > (size_t)n->size)
		n->size = (off_t)end;
	inode_put(n);
	return (int)size;
}

int storage_truncate(uint64_t ino, off_t new_size)
{
	struct inode *n = inode_lookup(ino);
	if (!n)
		return -ENOENT;
	if (!S_ISREG(n->mode)) {
		inode_put(n);
		return -EISDIR;
	}

	int rc = ensure_capacity(n, (size_t)new_size);
	if (rc) {
		inode_put(n);
		return rc;
	}

	if ((size_t)new_size > (size_t)n->size)
		memset(n->data + n->size, 0, (size_t)new_size - n->size);

	n->size = new_size;
	inode_put(n);
	return 0;
}
