/*
 * simplefs.c — FUSE entry point for simplefs.
 *
 * Initializes the root inode, wires up the fuse_operations struct,
 * and starts the FUSE event loop with fuse_main().
 */

#define FUSE_USE_VERSION 31

#include "fuse_ops.h"
#include "inode_table.h"

#include <fuse.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

/* The global mutex declared in fuse_ops.h */
pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER;

/* The fuse_operations struct is defined in fuse_ops.c */
extern const struct fuse_operations simplefs_oper;

int main(int argc, char *argv[])
{
	/* Pre-create root inode (ino = 1) before FUSE starts */
	struct inode *root = inode_alloc(S_IFDIR | 0755, getuid(), getgid());
	if (!root) {
		fprintf(stderr, "simplefs: failed to create root inode\n");
		return 1;
	}
	/* root starts at ino=2 with the auto-increment, but we want it at ino=1.
	   The first call to inode_alloc gets ino=2 because g_next_ino starts at 2.
	   We need to fix the numbering. Let's handle this in inode_table.c by
	   initializing g_next_ino = 1 so root gets ino=1. */
	inode_put(root);

	return fuse_main(argc, argv, &simplefs_oper, NULL);
}
