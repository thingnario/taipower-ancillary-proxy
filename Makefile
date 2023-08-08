.PHONY: clean/libiec61850 patch/libiec61850 build/grpc build/libiec61850 install/libiec61850 install/config run/server

PATCH_FILES := $(shell find patch -name "*.patch" -type f)

GRPC_GENERATED_FILES := server/taipower_ancillary_pb2.py server/taipower_ancillary_pb2_grpc.py
IEC61850_GENERATED_FILES := libiec61850/pyiec61850/iec61850.py libiec61850/pyiec61850/_iec61850.so

clean/libiec61850:
	@cd libiec61850 && git checkout . && git clean -fd

patch/libiec61850:
	@for patch_file in $(PATCH_FILES); do \
		if patch --dry-run --reverse --force -i "$$patch_file" >/dev/null 2>&1; then \
			echo "Patch already applied: $$patch_file"; \
		else \
			echo "Applying patch: $$patch_file"; \
			patch -i "$$patch_file"; \
		fi; \
	done

build/grpc: $(GRPC_GENERATED_FILES)
$(GRPC_GENERATED_FILES):
	@python -m grpc_tools.protoc -I protos --python_out=server --grpc_python_out=server protos/*proto


# Force compile with C++11 standard or higher to fix the error on macOS:
# libiec61850/pyiec61850/CMakeFiles/_iec61850.dir/iec61850PYTHON_wrap.cxx:4423:59:
# error: non-aggregate type 'std::map<std::string, EventSubscriber *>' (aka 'map<basic_string<char, char_traits<char>, allocator<char> >, EventSubscriber *>')
# cannot be initialized with an initializer list
# std::map< std::string, EventSubscriber*> EventSubscriber::m_subscriber_map = {};

# Manually set Python-related variables to correct the paths provided by CMake, which are incorrect when used within a virtual environment.
PYTHON_INCLUDE := $(shell python -c "import sysconfig;print(sysconfig.get_path('include'))")
PYTHON_LIBDIR := $(shell python -c "import sysconfig;print(sysconfig.get_config_var('LIBDIR'))")
PYTHON_INSTSONAME := $(shell python -c "import sysconfig;print(sysconfig.get_config_var('INSTSONAME'))")

build/libiec61850: $(IEC61850_GENERATED_FILES)
$(IEC61850_GENERATED_FILES):
	@cd libiec61850 && cmake . \
		-DBUILD_PYTHON_BINDINGS=ON \
		-DCMAKE_CXX_STANDARD=11 \
		-DPYTHON_INCLUDE_DIR=$(PYTHON_INCLUDE) \
		-DPYTHON_LIBRARY=$(PYTHON_LIBDIR)/$(PYTHON_INSTSONAME)
	@cd libiec61850 && make

install/libiec61850:
	@cp libiec61850/pyiec61850/iec61850.py server/
	@cp libiec61850/pyiec61850/_iec61850.so server/
	@cp libiec61850/pyiec61850/iec61850.py client/
	@cp libiec61850/pyiec61850/_iec61850.so client/
	@cp libiec61850/pyiec61850/iec61850.py bin/
	@cp libiec61850/pyiec61850/_iec61850.so bin/

install/config:
	@mkdir -p server/config
	@cp config/points.json server/config/

run/server: install/libiec61850 build/grpc
	@cd server && python proxy_server.py
