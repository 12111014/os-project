/*
 * path_utils.c — path normalization, parent extraction, and symlink resolution.
 *
 * Symlink resolution is bounded by SYMLOOP_MAX to prevent infinite chains.
 */

#include "path_utils.h"
#include "inode_table.h"
#include "dir_ops.h"
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include <errno.h>

/* ------------------------------------------------------------------------ */
/*  path_normalize                                                          */
/*                                                                          */
/*  Collapse "//", "/./", and "/../" components.                            */
/*  Never returns a trailing '/' except for root "/".                       */
/*  Returns 0 on success, -ENAMETOOLONG if output buffer too small.         */
/* ------------------------------------------------------------------------ */
int path_normalize(const char *in, char *out, size_t outsz)
{
	if (!in || !out || outsz < 2)
		return -EINVAL;

	size_t w = 0;           /* write position */
	const char *r = in;     /* read position  */

	/* always start with a slash */
	out[w++] = '/';

	/* skip leading slashes */
	while (*r == '/')
		r++;

	while (*r) {
		/* copy component up to next '/' or end */
		const char *slash = strchr(r, '/');
		size_t clen = slash ? (size_t)(slash - r) : strlen(r);

		if (clen == 0 || (clen == 1 && r[0] == '.')) {
			/* empty component or ".": skip */
		} else if (clen == 2 && r[0] == '.' && r[1] == '.') {
			/* "..": pop last component (but not past root) */
			while (w > 1 && out[w - 1] != '/')
				w--;
			if (w > 1) w--;   /* remove the '/' too */
		} else {
			/* normal component */
			if (w + 1 + clen >= outsz)
				return -ENAMETOOLONG;
			if (w > 1)  /* not at root */
				out[w++] = '/';
			memcpy(out + w, r, clen);
			w += clen;
		}

		if (slash)
			r = slash + 1;
		else
			break;

		/* skip multiple slashes */
		while (*r == '/')
			r++;
	}

	if (w == 0)
		out[w++] = '/';
	out[w] = '\0';
	return 0;
}

/* ------------------------------------------------------------------------ */
/*  path_parent                                                             */
/*                                                                          */
/*  Given "/a/b/c", write "/a/b" -> parent[], set *basename = "c".         */
/*  Root "/" has no parent: parent is set to "/" and basename is "".       */
/*  Returns 0 on success, -errno on failure.                                */
/* ------------------------------------------------------------------------ */
int path_parent(const char *path, char *parent, size_t parent_sz,
                const char **basename)
{
	if (!path || !parent || !basename)
		return -EINVAL;

	const char *slash = strrchr(path, '/');
	if (!slash) {
		/* invalid: no leading slash */
		*basename = path;
		snprintf(parent, parent_sz, "/");
		return 0;
	}

	*basename = slash + 1;
	if (slash == path) {
		/* parent is root */
		snprintf(parent, parent_sz, "/");
	} else {
		size_t len = (size_t)(slash - path);
		if (len >= parent_sz)
			return -ENAMETOOLONG;
		memcpy(parent, path, len);
		parent[len] = '\0';
	}
	return 0;
}

/* ------------------------------------------------------------------------ */
/*  path_resolve_symlink                                                    */
/*                                                                          */
/*  Resolve all symlinks in `path` component by component, bounded by       */
/*  SYMLOOP_MAX iterations. The resolved absolute path is written to        */
/*  `resolved`. Returns 0 on success, -errno on failure.                    */
/* ------------------------------------------------------------------------ */
int path_resolve_symlink(const char *path, char *resolved, size_t res_sz)
{
	char norm[PATH_MAX_SZ];
	int rc = path_normalize(path, norm, sizeof(norm));
	if (rc) return rc;

	char cur[PATH_MAX_SZ];
	char next[PATH_MAX_SZ];
	snprintf(cur, sizeof(cur), "%s", norm);

	for (int loop = 0; loop < SYMLOOP_MAX; loop++) {
		/* walk components of `cur` up to the first symlink */
		char walk[PATH_MAX_SZ] = "/";
		const char *p = cur[0] == '/' ? cur + 1 : cur;
		int found_symlink = 0;

		/* check root itself */
		struct inode *root_ino = inode_lookup(1);
		if (!root_ino) return -ENOENT;
		inode_put(root_ino);

		while (*p) {
			const char *slash = strchr(p, '/');
			size_t clen = slash ? (size_t)(slash - p) : strlen(p);
			char comp[256];
			if (clen >= sizeof(comp))
				return -ENAMETOOLONG;
			memcpy(comp, p, clen);
			comp[clen] = '\0';

			/* append to walk */
			if (strcmp(walk, "/") != 0)
				strncat(walk, "/", sizeof(walk) - strlen(walk) - 1);
			strncat(walk, comp, sizeof(walk) - strlen(walk) - 1);

			/* lookup this path to see if it's a symlink */
			struct inode *ino = inode_lookup_by_path(walk);
			if (ino && S_ISLNK(ino->mode)) {
				/* build resolved path: parent + target */
				char parent[PATH_MAX_SZ];
				const char *base;
				path_parent(walk, parent, sizeof(parent), &base);
				/* resolve target relative to parent */
				if (ino->target[0] == '/') {
					snprintf(next, sizeof(next), "%s", ino->target);
				} else {
					if (strcmp(parent, "/") == 0)
						snprintf(next, sizeof(next), "/%s", ino->target);
					else
							snprintf(next, sizeof(next), "%s/%s", parent, ino->target);
				}
				/* append remaining components after this symlink */
				if (slash) {
					const char *rem = slash + 1;
					if (*rem) {
						size_t nl = strlen(next);
						snprintf(next + nl, sizeof(next) - nl, "/%s", rem);
					}
				}
				path_normalize(next, next, sizeof(next));
				found_symlink = 1;
				inode_put(ino);
				break;
			}
			if (ino) inode_put(ino);
			else return -ENOENT;

			p += clen;
			if (*p == '/') p++;
		}

		if (!found_symlink) {
			/* fully resolved */
			snprintf(resolved, res_sz, "%s", cur);
			return 0;
		}

		snprintf(cur, sizeof(cur), "%s", next);
	}

	return -ELOOP;
}
