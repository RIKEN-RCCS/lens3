INSTALL=install
SYSTEMD_SYSTEM=/usr/lib/systemd/system
ETC=/etc
API_USER=_lenticularis
API_GROUP=_lenticularis
OWNER=-o $(API_USER) -g $(API_GROUP)

all:

install:
	$(INSTALL) -D -m 440 adm-config.yaml.in $(OWNER) $(ETC)/adm-config.yaml
	$(INSTALL) -D -m 444 lenticularis-api.service.in $(SYSTEMD_SYSTEM)/lenticularis-api.service

	@echo "Lenticularis API setting file templates are installed following pacle:"
	@echo "$(ETC)/adm-config.yaml"
	@echo "$(SYSTEMD_SYSTEM)/lenticularis-api.service"
	@echo "Edit setting files to have appropriate values (surrounded by '@'s )"
	@echo "then, start daemons"
	@echo "systemctl daemon-reload"
	@echo "systemctl enable lenticularis-api"
	@echo "systemctl start lenticularis-api"

clean:
