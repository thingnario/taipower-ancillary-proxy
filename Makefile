.PHONY: patch

patch:
	@cd libiec61850 && git checkout . && git clean -fd
	@find patch -name "*.patch" -type f -exec patch -p1 -i {} \;
