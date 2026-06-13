#define FUSE_USE_VERSION 31
#define _GNU_SOURCE

#include <fuse.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <pthread.h>

#include "fuse_ops.h"
#include "inode_table.h"

/* Global mutex — declared extern in all other modules */
pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER;

/* Signal flag for graceful shutdown */
static volatile sig_atomic_t g_terminate = 0;

static void signal_handler(int sig)
{
    (void)sig;
    g_terminate = 1;
}

int main(int argc, char *argv[])
{
    int ret;

    /* Install signal handlers for graceful shutdown */
    struct sigaction sa;
    memset(&sa, 0, sizeof(sa));
    sa.sa_handler = signal_handler;
    sigaction(SIGTERM, &sa, NULL);
    sigaction(SIGINT, &sa, NULL);

    /* Initialize the inode table (creates root directory) */
    pthread_mutex_lock(&g_lock);
    inode_table_init();
    pthread_mutex_unlock(&g_lock);

    /* Mount and serve */
    struct fuse_operations *ops = agentfs_get_operations();
    ret = fuse_main(argc, argv, ops, NULL);

    /* Cleanup (only reached after unmount) */
    pthread_mutex_lock(&g_lock);
    inode_table_destroy();
    pthread_mutex_unlock(&g_lock);

    return ret;
}
