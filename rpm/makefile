## makefile

BUILDDIR = ~/rpmbuild/BUILD
BUILDBIN = ~/rpmbuild/BUILD/usr/local/bin

all::
	@echo "Run 'make cp' then 'make rpm'"

rpm::
	cp -p lenticularis-s3.spec ~/rpmbuild/SPECS/
	rpmbuild -v -bb ~/rpmbuild/SPECS/lenticularis-s3.spec

cp::
	mkdir -p $(BUILDBIN)
	cp -p ../v2/cmd/lenticularis-mux/lenticularis-mux $(BUILDBIN)
	cp -p ../v2/cmd/lens3-admin/lens3-admin $(BUILDBIN)
	mkdir -p $(BUILDDIR)/usr/share/licenses/lenticularis
	cp -p ../LICENSE $(BUILDDIR)/usr/share/licenses/lenticularis
	mkdir -p $(BUILDDIR)/usr/lib/sysusers.d
	cp -p lenticularis.conf $(BUILDDIR)/usr/lib/sysusers.d

dump::
	rpm --eval '_arch=%{_arch}'
	rpm --eval '?dist=%{?dist}'
	rpm --eval 'buildroot=%{buildroot}; '
	rpm --eval '_sysusersdir=%{_sysusersdir}'
	# rpm --showrc

lint::
	rpmlint lenticularis-s3.spec

##	rpmlint ~/rpmbuild/SPECS/lenticularis-s3.spec
