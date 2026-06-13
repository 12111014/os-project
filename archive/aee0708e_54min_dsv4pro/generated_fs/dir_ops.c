/*
 * dir_ops.c — directory entry management.
 *
 * Each directory inode owns a sorted singly-linked list of dirent structures.
 * Operations: add entry, remove entry, lookup child by name, enumerate entries.
 */

#include "dir_ops.h"
#include "inode_table.h"
#include <stdlib.h>
#include <string.h>
#include <errno.h>

/* ------------------------------------------------------------------------ */
/*  Internal helpers                                                        */
/* ------------------------------------------------------------------------ */

/*
 * Insert a dirent into the sorted linked list (alphabetically by name).
 * Returns 0 on success, -EEXIST if name already present.
 */
static int children_insert(struct inode *dir, const char *name, uint64_t child_ino)
{
	struct dirent **pp = &dir->children;
	while (*pp) {
		int cmp = strcmp((*pp)->name, name);
		if (cmp == 0)
			return -EEXIST;
		if (cmp > 0)
			break;
		pp = &(*pp)->next;
	}

	struct dirent *de = calloc(1, sizeof(*de));
	if (!de)
		return -ENOMEM;
	de->name = strdup(name);
	if (!de->name) {
		free(de);
		return -ENOMEM;
	}
	de->ino = child_ino;
	de->next = *pp;
	*pp = de;
	return 0;
}

/* ------------------------------------------------------------------------ */
/*  Public API                                                              */
/* ------------------------------------------------------------------------ */

int dir_add(uint64_t parent_ino, const char *name, uint64_t child_ino)
{
	struct inode *dir = inode_lookup(parent_ino);
	if (!dir)
		return -ENOENT;
	if (!S_ISDIR(dir->mode)) {
		inode_put(dir);
		return -ENOTDIR;
	}

	int rc = children_insert(dir, name, child_ino);
	inode_put(dir);
	return rc;
}

int dir_remove(uint64_t parent_ino, const char *name)
{
	struct inode *dir = inode_lookup(parent_ino);
	if (!dir)
		return -ENOENT;
	if (!S_ISDIR(dir->mode)) {
		inode_put(dir);
		return -ENOTDIR;
	}

	struct dirent **pp = &dir->children;
	while (*pp) {
		if (strcmp((*pp)->name, name) == 0) {
			struct dirent *victim = *pp;
			*pp = victim->next;
			free(victim->name);
			free(victim);
			inode_put(dir);
			return 0;
		}
		pp = &(*pp)->next;
	}
	inode_put(dir);
	return -ENOENT;
}

int dir_lookup(uint64_t parent_ino, const char *name, uint64_t *child_out)
{
	struct inode *dir = inode_lookup(parent_ino);
	if (!dir)
		return -ENOENT;
	if (!S_ISDIR(dir->mode)) {
		inode_put(dir);
		return -ENOTDIR;
	}

	for (const struct dirent *de = dir->children; de; de = de->next) {
		if (strcmp(de->name, name) == 0) {
			*child_out = de->ino;
			inode_put(dir);
			return 0;
		}
	}
	inode_put(dir);
	return -ENOENT;
}

int dir_readdir(uint64_t parent_ino, off_t offset,
                void *buf, fuse_fill_dir_t filler)
{
	struct inode *dir = inode_lookup(parent_ino);
	if (!dir)
		return -ENOENT;
	if (!S_ISDIR(dir->mode)) {
		inode_put(dir);
		return -ENOTDIR;
	}

	/* offset is used as an index into the sorted list.
	   Entry 0 = ".", entry 1 = "..", entry 2+ = children. */
	int idx = 0;

	if (offset <= idx) {
		if (filler(buf, ".", NULL, idx + 1, 0))
			goto out;
	}
	idx++;

	if (offset <= idx) {
		if (filler(buf, "..", NULL, idx + 1, 0))
			goto out;
	}
	idx++;

	struct dirent *de = dir->children;
	while (de) {
		if (offset <= idx) {
			if (filler(buf, de->name, NULL, idx + 1, 0))
				goto out;
		}
		idx++;
		de = de->next;
	}

out:
	inode_put(dir);
	return 0;
}
