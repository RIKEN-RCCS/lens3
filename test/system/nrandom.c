#include <sys/types.h>

#include <assert.h>
#include <libgen.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

static char *progname;
#define setprogname	progname = basename
#define	getprogname()	progname

static void
usage()
{
	fprintf(stderr, "usage: %s [-s size]\n", getprogname());
	fprintf(stderr, "       size is rounded up to multiple of 4096\n");
	fprintf(stderr, "       or zero for infinite\n");

	exit(1);
}

#define	BSIZE	4096

int
main(argc, argv)
char *argv[];
{
	char buf[BSIZE];
	size_t size = 0, i, count;
	int ch;

	setprogname(argv[0]);

	while ((ch = getopt(argc, argv, "s:")) != -1) {
		switch (ch) {
			char *end;
		case 's':
			size = strtoul(optarg, &end, 10);
			if (!(*optarg && !*end)) {
				fprintf(stderr, "invalid number: %s\n", optarg);
				usage();
			}
			break;
		case '?':
		default:
			usage();
			break;
		}
	}
	argc -= optind, argv += optind;
	if (argc != 0) {
		fprintf(stderr, "argument number\n");
		usage();
	}

	for (i = 0; i < sizeof buf; i++) {
		buf[i] = random() & 0xff;
	}

	if (size == 0) {
		count = 0;
	}
	else {
		count = (size + BSIZE - 1) / BSIZE;
		assert(count != 0);
	}
	for (i = 0; count == 0 || i < count; i++) {
		fwrite(buf, sizeof buf, 1, stdout);
	}

	return 0;
}
