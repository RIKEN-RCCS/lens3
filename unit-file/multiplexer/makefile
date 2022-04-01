INSTALL=install
SYSTEMD_SYSTEM=/usr/lib/systemd/system
ETC=/etc
MUX_USER=_lenticularis
MUX_GROUP=_lenticularis
OWNER=-o $(MUX_USER) -g $(MUX_GROUP)

all:

install:
	$(INSTALL) -D -m 440 mux-config.yaml.in $(OWNER) $(ETC)/mux-config.yaml
	$(INSTALL) -D -m 444 lenticularis-mux.service.in $(SYSTEMD_SYSTEM)/lenticularis-mux.service

	@echo "Lenticularis MUX setting file templates are installed following pacle:"
	@echo "$(ETC)/mux-config.yaml"
	@echo "$(SYSTEMD_SYSTEM)/lenticularis-mux.service"
	@echo "Edit setting files to have appropriate values (surrounded by '@'s )"
	@echo "then, start daemons"
	@echo "systemctl daemon-reload"
	@echo "systemctl enable lenticularis-mux"
	@echo "systemctl start lenticularis-mux"

clean:
