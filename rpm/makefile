## makefile

BUILDBIN = ~/rpmbuild/BUILD/usr/local/bin
BUILDLIC = ~/rpmbuild/BUILD/usr/share/licenses/lenticularis-s3

all::
	@echo "Run 'make cp' then 'make rpm'"

rpm::
	cp -p lenticularis-s3.spec ~/rpmbuild/SPECS/
	rpmbuild -v -bb ~/rpmbuild/SPECS/lenticularis-s3.spec

cp::
	mkdir -p $(BUILDBIN)
	cp -p ../v2/cmd/lenticularis-mux/lenticularis-mux $(BUILDBIN)
	cp -p ../v2/cmd/lens3-admin/lens3-admin $(BUILDBIN)
	mkdir -p $(BUILDLIC)
	cp -p ../LICENSE $(BUILDLIC)

lint::
	rpmlint lenticularis-s3.spec

##	rpmlint ~/rpmbuild/SPECS/lenticularis-s3.spec
