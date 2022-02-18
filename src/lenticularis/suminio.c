// Copyright (c) 2022 RIKEN R-CCS.
// SPDX-License-Identifier: BSD-2-Clause

// DO NOT USE this code in real service.
// This Code is test code for develop/debug the system and
// not finished yet.

#if 1
#define	DEBUG
#endif

#include <sys/types.h>

#include <errno.h>
#include <libgen.h>
#include <pwd.h>
#include <grp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <syslog.h>
#include <unistd.h>

static void usage(void);
static void check_allowed_base_user(uid_t);
static void cechk_allowed_command(char const *);
static void check_allowed_users(uid_t);
static void check_allowed_groups(gid_t);

#define	nelems(e)	(sizeof (e) / sizeof *(e))

static char *progname;
#define	setprogname(s)	(progname = basename(s))
#define	getprogname()	(progname)

extern char **environ;

static void
usage()
{
	fprintf(stderr, "usage: %s -u user [-g group] "
		MINIO " [args...]\n", getprogname());
	exit(125);
}

int
main(argc, argv)
int argc;
char *argv[];
{
	int ch;
	char *user = NULL;
	char *group = NULL;
	struct passwd *pwd;
	struct group *grp = NULL;
	char *cmd[16];
	int i;
	uid_t uid;

	setprogname(argv[0]);

	openlog(getprogname(), LOG_PID, LOG_LOCAL7);

	uid = getuid();  /* This function is always successful. */

	check_allowed_base_user(uid);

#ifdef DEBUG
	syslog(LOG_DEBUG, "uid: %d", getuid());
	syslog(LOG_DEBUG, "euid: %d", geteuid());
	syslog(LOG_DEBUG, "gid: %d", getgid());
	syslog(LOG_DEBUG, "egid: %d", getegid());
#endif

	while ((ch = getopt(argc, argv, "+u:g:")) != -1) {
		switch (ch) {
		case 'u':
			user = optarg;
			break;
		case 'g':
			group = optarg;
			break;
		default:
			usage();
			break;
		}
	}
	argc -= optind, argv += optind;

	if (!user) {
		usage();
	}

	if (argc == 0) {
		fprintf(stderr, "command missing: should be \"" MINIO "\"\n");
		usage();
	}

	cechk_allowed_command(argv[0]);

	argc--, argv++;

#ifdef DEBUG
	syslog(LOG_DEBUG, "user: %s\n", user);
	syslog(LOG_DEBUG, "group: %s\n", group ? group : "null");
#endif

	if (!(pwd = getpwnam(user))) {
		fprintf(stderr, "%s: %s\n", user, "no such user");
		exit(2);
	}

	check_allowed_users(pwd->pw_uid);
	check_allowed_groups(pwd->pw_gid);

	if (group && !(grp = getgrnam(group))) {
		fprintf(stderr, "%s: %s\n", group, "no such group");
		exit(3);
	}

#ifdef DEBUG
	syslog(LOG_DEBUG, "user = %d\n", pwd->pw_uid);
	if (grp) {
		syslog(LOG_DEBUG, "group = %d\n", grp->gr_gid);
	}
#endif

	i = 0;
	cmd[i++] = MINIO;
//// use fixed pattern?
	while (i + 1 < nelems(cmd) && argc > 0) {
		cmd[i++] = argv[0];
		argc--, argv++;
	}
	cmd[i++] = NULL;

#ifdef DEBUG
	for (i = 0; cmd[i]; i++) {
		syslog(LOG_DEBUG, "%d: %s", i, cmd[i]);
	}
#endif

	if (argc > 0) {
		fprintf(stderr, "argument list too long\n");
		exit(4);
	}

	if (grp && setgid(grp->gr_gid) == -1) {
		fprintf(stderr, "setgid: %s\n", strerror(errno));
		exit(5);
	}

	if (setuid(pwd->pw_uid) == -1) {
		fprintf(stderr, "setuid: %s\n", strerror(errno));
		exit(6);
	}

#ifdef DEBUG
	syslog(LOG_DEBUG, "uid: %d", getuid());
	syslog(LOG_DEBUG, "euid: %d", geteuid());
	syslog(LOG_DEBUG, "gid: %d", getgid());
	syslog(LOG_DEBUG, "egid: %d", getegid());
#endif

	execve(MINIO, cmd, environ);
	fprintf(stderr, "execve: %s: %s\n", MINIO, strerror(errno));

	return 126;
}

static void
check_allowed_base_user(uid)
uid_t uid;
{
	if (uid != LENTICULARIS) {
		fprintf(stderr, "You have no rights to execute this command: %d\n", uid);
		exit(249);
	}
}

static void
cechk_allowed_command(cmd)
char const *cmd;
{
	if (strcmp(cmd, MINIO)) {
		fprintf(stderr, "command mismatch: should be \"" MINIO "\"\n");
		exit(250);
	}
}

static void
check_allowed_users(uid)
uid_t uid;
{
	static uid_t deniend_users[] = { DENIED_USERS };
	size_t i;
	for (i = 0; i < nelems(deniend_users); i++) {
		if (uid == deniend_users[i]) {
			exit(251);
		}
	}
}

static void
check_allowed_groups(gid)
gid_t gid;
{
	static uid_t allowed_groups[] = { ALLOWED_GROPUS };
	size_t i;
	for (i = 0; i < nelems(allowed_groups); i++) {
		if (gid != allowed_groups[i]) {
			exit(252);
		}
	}
}
