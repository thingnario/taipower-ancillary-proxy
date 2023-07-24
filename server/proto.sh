proto_dir="./protos"
out_dir="./"

python3 -m grpc_tools.protoc -I ${proto_dir} --python_out=${out_dir} --grpc_python_out=${out_dir} ${proto_dir}/*proto