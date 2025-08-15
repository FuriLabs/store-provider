PREFIX ?= /usr
LIBDIR ?= $(PREFIX)/lib
LIBEXECDIR ?= $(PREFIX)/libexec
DBUS_SERVICES_DIR = $(PREFIX)/share/dbus-1/services
STORE_PROVIDER_DIR = store-provider

MAIN = main.py
DBUS_SERVICES = data/io.FuriOS.StoreManager.service data/io.FuriOS.AndroidStore.service data/io.FuriOS.OpenStore.service

.PHONY: all install uninstall

all:
	@echo "Run 'make install' to install the files."

install:
	install -d $(DESTDIR)$(LIBDIR)/$(STORE_PROVIDER_DIR)
	install -d $(DESTDIR)$(LIBEXECDIR)
	install -m 755 $(MAIN) $(DESTDIR)$(LIBDIR)/$(STORE_PROVIDER_DIR)/

	cp -r common $(DESTDIR)$(LIBDIR)/$(STORE_PROVIDER_DIR)/
	cp -r open_store $(DESTDIR)$(LIBDIR)/$(STORE_PROVIDER_DIR)/
	cp -r android_store $(DESTDIR)$(LIBDIR)/$(STORE_PROVIDER_DIR)/
	cp -r store_manager $(DESTDIR)$(LIBDIR)/$(STORE_PROVIDER_DIR)/
	ln -sf ../lib/store-provider/main.py $(DESTDIR)$(LIBEXECDIR)/store-provider

	install -d $(DESTDIR)$(DBUS_SERVICES_DIR)
	install -m 644 data/io.FuriOS.StoreManager.service $(DESTDIR)$(DBUS_SERVICES_DIR)/
	install -m 644 data/io.FuriOS.AndroidStore.service $(DESTDIR)$(DBUS_SERVICES_DIR)/
	install -m 644 data/io.FuriOS.OpenStore.service $(DESTDIR)$(DBUS_SERVICES_DIR)/

uninstall:
	rm -rf $(DESTDIR)$(LIBDIR)/$(STORE_PROVIDER_DIR)/
	rm -f $(DESTDIR)$(DBUS_SERVICES_DIR)/io.FuriOS.StoreManager.service
	rm -f $(DESTDIR)$(DBUS_SERVICES_DIR)/io.FuriOS.AndroidStore.service
	rm -f $(DESTDIR)$(DBUS_SERVICES_DIR)/io.FuriOS.OpenStore.service
